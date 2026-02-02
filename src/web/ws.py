"""WebSocket handler for live turn streaming."""

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.persistence.postgres import PostgresRepository

logger = logging.getLogger(__name__)

ws_router = APIRouter()


@ws_router.websocket("/ws/runs/{run_id}/live")
async def live_stream(websocket: WebSocket, run_id: str):
    """Stream turns for a live run via WebSocket.

    Protocol:
    - Server sends JSON messages: {"type": "turn", "data": {...}}
    - Server sends {"type": "run_ended", "data": {...}} when the run finishes
    - Server polls the repository for new turns (decoupled from agent runner)
    """
    repo: PostgresRepository = websocket.app.state.repo
    await websocket.accept()

    run = await repo.get_run(run_id)
    if not run:
        await websocket.send_json({"type": "error", "message": f"Run {run_id} not found"})
        await websocket.close()
        return

    last_seen_turn = 0
    poll_interval = 0.3

    try:
        while True:
            new_turns = await repo.get_turns(run_id, after_turn=last_seen_turn, limit=50)

            for turn in new_turns:
                await websocket.send_json(
                    {
                        "type": "turn",
                        "data": turn.to_dict(),
                    }
                )
                last_seen_turn = turn.turn_number

            # Check if run has ended
            run = await repo.get_run(run_id)
            if run and run.status in ("stopped", "error", "completed"):
                await websocket.send_json(
                    {
                        "type": "run_ended",
                        "data": run.to_dict(),
                    }
                )
                break

            await asyncio.sleep(poll_interval)

    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected from run {run_id}")
    except Exception as e:
        logger.error(f"WebSocket error for run {run_id}: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
