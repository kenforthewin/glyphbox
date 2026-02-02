"""FastAPI dependency injection."""

from fastapi import HTTPException, Request

from src.config import AuthConfig
from src.persistence.models import UserRecord
from src.persistence.postgres import PostgresRepository
from src.web.auth import decode_jwt


def get_repo(request: Request) -> PostgresRepository:
    """Provide the PostgresRepository from app state."""
    return request.app.state.repo


def get_auth_config(request: Request) -> AuthConfig | None:
    """Return AuthConfig if auth is enabled, else None."""
    config = getattr(request.app.state, "auth_config", None)
    if config and config.enabled:
        return config
    return None


async def get_current_user(request: Request) -> UserRecord:
    """Require an authenticated user. Raises 401 if not logged in."""
    auth_config = get_auth_config(request)
    if not auth_config:
        raise HTTPException(401, "Authentication is not configured")

    token = request.cookies.get("session")
    if not token:
        raise HTTPException(401, "Not authenticated")

    payload = decode_jwt(token, auth_config.session_secret)
    if not payload:
        raise HTTPException(401, "Invalid or expired session")

    repo = get_repo(request)
    user = await repo.get_user(int(payload["sub"]))
    if not user:
        raise HTTPException(401, "User not found")

    return user


def get_auth_enabled(request: Request) -> bool:
    """Return True if auth is configured on this server."""
    return get_auth_config(request) is not None


async def get_optional_user(request: Request) -> UserRecord | None:
    """Return current user if authenticated, None otherwise.

    Never raises — anonymous access is allowed.
    """
    auth_config = get_auth_config(request)
    if not auth_config:
        return None

    token = request.cookies.get("session")
    if not token:
        return None

    payload = decode_jwt(token, auth_config.session_secret)
    if not payload:
        return None

    repo = get_repo(request)
    return await repo.get_user(int(payload["sub"]))
