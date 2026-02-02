"""OpenRouter OAuth2 PKCE authentication.

Flow:
1. GET /api/auth/login  -- generates PKCE pair, sets code_verifier cookie,
   redirects to OpenRouter
2. OpenRouter redirects back to GET /api/auth/callback?code=...
3. Backend exchanges code + code_verifier for an API key via OpenRouter
4. Backend upserts user, encrypts API key, sets JWT session cookie
5. Subsequent requests carry the JWT cookie; deps.py extracts the user
"""

import base64
import hashlib
import logging
import os
import re
from datetime import datetime, timedelta, timezone

import httpx
import jwt
from cryptography.fernet import Fernet
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

from src.config import AuthConfig
from src.persistence.postgres import PostgresRepository

logger = logging.getLogger(__name__)

auth_router = APIRouter(prefix="/api/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# PKCE helpers
# ---------------------------------------------------------------------------


def generate_pkce_pair() -> tuple[str, str]:
    """Generate a PKCE code_verifier and code_challenge (S256)."""
    verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode("ascii")
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .rstrip(b"=")
        .decode("ascii")
    )
    return verifier, challenge


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------


def create_jwt(user_id: int, secret: str, expiry_days: int = 7) -> str:
    """Create an HS256 JWT with the user's database ID."""
    payload = {
        "sub": str(user_id),
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(days=expiry_days),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_jwt(token: str, secret: str) -> dict | None:
    """Decode and validate a JWT. Returns payload or None on failure."""
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


# ---------------------------------------------------------------------------
# Fernet encryption helpers
# ---------------------------------------------------------------------------


def encrypt_key(api_key: str, encryption_key: str) -> str:
    """Encrypt an API key using Fernet symmetric encryption."""
    f = Fernet(encryption_key.encode("utf-8"))
    return f.encrypt(api_key.encode("utf-8")).decode("utf-8")


def decrypt_key(encrypted: str, encryption_key: str) -> str:
    """Decrypt an API key."""
    f = Fernet(encryption_key.encode("utf-8"))
    return f.decrypt(encrypted.encode("utf-8")).decode("utf-8")


# ---------------------------------------------------------------------------
# Helper to read config/repo from app state
# ---------------------------------------------------------------------------


def _get_auth_config(request: Request) -> AuthConfig | None:
    config = getattr(request.app.state, "auth_config", None)
    if config and config.enabled:
        return config
    return None


def _get_repo(request: Request) -> PostgresRepository:
    return request.app.state.repo


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@auth_router.get("/login")
async def login(request: Request):
    """Start the OAuth flow. Redirect user to OpenRouter."""
    auth_config = _get_auth_config(request)
    if not auth_config:
        return JSONResponse({"error": "Authentication is not configured"}, status_code=501)

    verifier, challenge = generate_pkce_pair()

    # Store verifier in a short-lived httponly cookie
    openrouter_url = (
        f"{auth_config.openrouter_auth_url}"
        f"?callback_url={auth_config.callback_url}"
        f"&code_challenge={challenge}"
        f"&code_challenge_method=S256"
    )

    response = RedirectResponse(url=openrouter_url, status_code=302)
    response.set_cookie(
        key="pkce_verifier",
        value=verifier,
        httponly=True,
        secure=auth_config.cookie_secure,
        samesite="lax",
        max_age=600,  # 10 minutes
        domain=auth_config.cookie_domain or None,
    )
    return response


@auth_router.get("/callback")
async def callback(request: Request):
    """Handle the OpenRouter OAuth callback."""
    auth_config = _get_auth_config(request)
    if not auth_config:
        return JSONResponse({"error": "Authentication is not configured"}, status_code=501)

    code = request.query_params.get("code")
    if not code:
        return JSONResponse({"error": "Missing 'code' parameter"}, status_code=400)

    verifier = request.cookies.get("pkce_verifier")
    if not verifier:
        return JSONResponse(
            {"error": "Missing PKCE verifier cookie. Please try logging in again."},
            status_code=400,
        )

    # Exchange code for API key
    async with httpx.AsyncClient() as client:
        exchange_resp = await client.post(
            auth_config.openrouter_keys_url,
            json={
                "code": code,
                "code_verifier": verifier,
                "code_challenge_method": "S256",
            },
        )

    if exchange_resp.status_code != 200:
        logger.error(f"OpenRouter key exchange failed: {exchange_resp.text}")
        return JSONResponse(
            {"error": "Failed to exchange code with OpenRouter"},
            status_code=502,
        )

    data = exchange_resp.json()
    api_key = data.get("key")
    openrouter_user_id = data.get("user_id", "")

    if not api_key:
        return JSONResponse({"error": "No API key returned from OpenRouter"}, status_code=502)

    # Encrypt the API key for storage
    encrypted = encrypt_key(api_key, auth_config.encryption_key)

    # Upsert user
    repo = _get_repo(request)
    display_name = f"user-{openrouter_user_id[:8]}" if openrouter_user_id else "anonymous"
    user = await repo.upsert_user(
        openrouter_id=openrouter_user_id,
        display_name=display_name,
        encrypted_openrouter_key=encrypted,
    )

    # Create JWT session
    token = create_jwt(user.id, auth_config.session_secret, auth_config.jwt_expiry_days)

    # Redirect to frontend root with session cookie
    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(
        key="session",
        value=token,
        httponly=True,
        secure=auth_config.cookie_secure,
        samesite="lax",
        max_age=auth_config.jwt_expiry_days * 86400,
        domain=auth_config.cookie_domain or None,
    )
    # Clear the PKCE verifier cookie
    response.delete_cookie("pkce_verifier", domain=auth_config.cookie_domain or None)
    return response


@auth_router.get("/me")
async def get_me(request: Request):
    """Return the current authenticated user, or 401."""
    auth_config = _get_auth_config(request)
    if not auth_config:
        return JSONResponse({"error": "Authentication is not configured"}, status_code=501)

    token = request.cookies.get("session")
    if not token:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    payload = decode_jwt(token, auth_config.session_secret)
    if not payload:
        return JSONResponse({"error": "Invalid or expired session"}, status_code=401)

    repo = _get_repo(request)
    user = await repo.get_user(int(payload["sub"]))
    if not user:
        return JSONResponse({"error": "User not found"}, status_code=401)

    return user.to_public_dict()


@auth_router.post("/logout")
async def logout(request: Request):
    """Clear the session cookie."""
    auth_config = _get_auth_config(request)
    response = JSONResponse({"ok": True})
    response.delete_cookie(
        "session",
        domain=(auth_config.cookie_domain if auth_config else None) or None,
    )
    return response


USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{3,30}$")


@auth_router.patch("/me")
async def update_me(request: Request):
    """Update the current user's profile (display_name)."""
    auth_config = _get_auth_config(request)
    if not auth_config:
        return JSONResponse({"error": "Authentication is not configured"}, status_code=501)

    token = request.cookies.get("session")
    if not token:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)

    payload = decode_jwt(token, auth_config.session_secret)
    if not payload:
        return JSONResponse({"error": "Invalid or expired session"}, status_code=401)

    body = await request.json()
    display_name = body.get("display_name", "").strip()

    if not USERNAME_PATTERN.match(display_name):
        return JSONResponse(
            {"error": "Username must be 3-30 characters, alphanumeric, hyphens, or underscores"},
            status_code=400,
        )

    repo = _get_repo(request)
    user_id = int(payload["sub"])

    try:
        user = await repo.update_user_display_name(user_id, display_name)
    except Exception as e:
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            return JSONResponse({"error": "Username already taken"}, status_code=409)
        raise

    return user.to_public_dict()
