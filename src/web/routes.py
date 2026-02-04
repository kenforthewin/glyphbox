"""REST API endpoints for runs, turns, and run management."""

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from src.persistence.models import UserRecord
from src.persistence.postgres import PostgresRepository
from src.web.auth import decrypt_key
from src.web.run_config import RunConfig

from .deps import get_auth_config, get_current_user, get_repo

logger = logging.getLogger(__name__)

router = APIRouter()


# === Run management endpoints ===


class StartRunRequest(BaseModel):
    model: str
    character: str = "random"
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    reasoning: str = Field(default="none")
    max_turns: int = Field(default=10000, ge=1, le=100000)


@router.post("/runs")
async def start_run(
    body: StartRunRequest,
    request: Request,
    user: UserRecord = Depends(get_current_user),
    repo: PostgresRepository = Depends(get_repo),
):
    """Start a new agent run. Requires authentication."""
    from src.web.run_manager import RunManager

    auth_config = get_auth_config(request)
    if not auth_config:
        raise HTTPException(500, "Auth not configured")

    # Validate that user has an API key (don't decrypt here -- backend does it)
    if not user.encrypted_openrouter_key:
        raise HTTPException(
            400,
            "No OpenRouter API key stored. Please log out and log in again.",
        )

    # Build RunConfig (no API key -- backend decrypts using user_id)
    config = RunConfig(
        model=body.model,
        character=body.character,
        temperature=body.temperature,
        reasoning=body.reasoning,
        max_turns=body.max_turns,
    )

    # Start with concurrency checks (raises 429 if at limit)
    run_manager: RunManager = request.app.state.run_manager
    run_id = await run_manager.create_and_start_run(user.id, config)

    return {"run_id": run_id, "status": "starting"}


@router.post("/runs/{run_id}/stop")
async def stop_run(
    run_id: str,
    request: Request,
    user: UserRecord = Depends(get_current_user),
):
    """Stop a running agent run. Requires ownership."""
    from src.web.run_manager import RunManager

    run_manager: RunManager = request.app.state.run_manager
    await run_manager.stop_run(run_id, user.id)
    return {"ok": True}


@router.get("/models")
async def list_models(
    request: Request,
    user: UserRecord = Depends(get_current_user),
):
    """List available OpenRouter models that support tool calling."""
    auth_config = get_auth_config(request)
    if not auth_config:
        raise HTTPException(500, "Auth not configured")

    if not user.encrypted_openrouter_key:
        raise HTTPException(400, "No OpenRouter API key stored")

    api_key = decrypt_key(user.encrypted_openrouter_key, auth_config.encryption_key)

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://openrouter.ai/api/v1/models",
                params={"supported_parameters": "tools"},
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=15.0,
            )
        if resp.status_code != 200:
            raise HTTPException(502, "Failed to fetch models from OpenRouter")

        data = resp.json().get("data", [])
        # Return simplified model info
        models = []
        for m in data:
            pricing = m.get("pricing", {})
            models.append(
                {
                    "id": m.get("id", ""),
                    "name": m.get("name", m.get("id", "")),
                    "context_length": m.get("context_length", 0),
                    "pricing": {
                        "prompt": pricing.get("prompt", "0"),
                        "completion": pricing.get("completion", "0"),
                    },
                }
            )
        return models

    except httpx.HTTPError as e:
        logger.error(f"OpenRouter models request failed: {e}")
        raise HTTPException(502, "Failed to fetch models from OpenRouter")


# === Run query endpoints (all public, no visibility filtering) ===


@router.get("/runs")
async def list_runs(
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    sort_by: str = Query(default="recent", pattern="^(recent|score|depth)$"),
    model: str | None = Query(default=None),
    user_id: int | None = Query(default=None),
    repo: PostgresRepository = Depends(get_repo),
):
    """List all runs with optional filtering and sorting."""
    runs = await repo.list_runs(
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        model_filter=model,
        user_id=user_id,
    )
    return [r.to_dict() for r in runs]


@router.get("/runs/models")
async def get_run_models(
    repo: PostgresRepository = Depends(get_repo),
):
    """Get distinct model names from all runs."""
    return await repo.list_distinct_models()


@router.get("/runs/{run_id}")
async def get_run(
    run_id: str,
    repo: PostgresRepository = Depends(get_repo),
):
    """Get a single run by ID."""
    run = await repo.get_run(run_id)
    if not run:
        raise HTTPException(404, f"Run {run_id} not found")
    return run.to_dict()


# === Leaderboard ===


@router.get("/leaderboard")
async def get_leaderboard(
    sort_by: str = Query(default="best_score", pattern="^(best_score|avg_score|best_depth)$"),
    limit: int = Query(default=50, le=200),
    repo: PostgresRepository = Depends(get_repo),
):
    """Get model leaderboard with aggregated stats."""
    return await repo.get_model_leaderboard(sort_by=sort_by, limit=limit)


# === Turn endpoints ===


async def _check_run_exists(run_id: str, repo: PostgresRepository):
    """Verify a run exists before returning its turns."""
    run = await repo.get_run(run_id)
    if not run:
        raise HTTPException(404, f"Run {run_id} not found")
    return run


@router.get("/runs/{run_id}/turns")
async def get_turns(
    run_id: str,
    after: int = Query(default=0, ge=0, description="Return turns after this turn_number"),
    limit: int = Query(default=100, le=500),
    repo: PostgresRepository = Depends(get_repo),
):
    """Get turns for a run. Use 'after' for pagination or live polling."""
    await _check_run_exists(run_id, repo)

    turns = await repo.get_turns(run_id, after_turn=after, limit=limit)
    return {
        "run_id": run_id,
        "turns": [t.to_dict() for t in turns],
        "total": await repo.count_turns(run_id),
    }


@router.get("/runs/{run_id}/turns/latest")
async def get_latest_turn(
    run_id: str,
    repo: PostgresRepository = Depends(get_repo),
):
    """Get the most recent turn for a run."""
    await _check_run_exists(run_id, repo)

    turn = await repo.get_latest_turn(run_id)
    if not turn:
        raise HTTPException(404, f"No turns found for run {run_id}")
    return turn.to_dict()


@router.get("/runs/{run_id}/turns/{turn_number}")
async def get_turn(
    run_id: str,
    turn_number: int,
    repo: PostgresRepository = Depends(get_repo),
):
    """Get a specific turn."""
    await _check_run_exists(run_id, repo)

    turn = await repo.get_turn(run_id, turn_number)
    if not turn:
        raise HTTPException(404, f"Turn {turn_number} not found in run {run_id}")
    return turn.to_dict()
