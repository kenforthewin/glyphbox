"""FastAPI application factory."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .auth import auth_router
from .routes import router
from .ws import ws_router

logger = logging.getLogger(__name__)

FRONTEND_DIST = Path(__file__).parent.parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage async engine lifecycle."""
    from sqlalchemy.ext.asyncio import create_async_engine

    from src.config import load_config
    from src.persistence.postgres import PostgresRepository
    from src.web.run_manager import InProcessBackend, RunManager

    config = load_config()

    # Engine may be pre-created by CLI and stored on app.state
    if not getattr(app.state, "engine", None):
        app.state.engine = create_async_engine(
            config.database.url,
            pool_size=config.database.pool_max_size,
        )

    if not getattr(app.state, "repo", None):
        app.state.repo = PostgresRepository(app.state.engine)

    # Store auth config (may already be set by CLI)
    if not getattr(app.state, "auth_config", None):
        app.state.auth_config = config.auth

    # Create run manager with appropriate backend
    if not getattr(app.state, "run_manager", None):
        if config.worker.enabled:
            from src.web.procrastinate_backend import ProcrastinateBackend
            from src.worker.app import configure

            proc_app = configure(config.database.conninfo)
            await proc_app.connector.open_async()
            app.state.procrastinate_app = proc_app

            backend = ProcrastinateBackend(proc_app, app.state.repo)
            await backend.start_monitoring(interval=config.worker.monitor_interval)
            app.state.procrastinate_backend = backend
        else:
            backend = InProcessBackend(
                repo=app.state.repo,
                auth_config=config.auth,
            )

        run_manager = RunManager(
            backend=backend,
            max_runs_per_user=5,
            max_total_runs=10,
        )

        # Wire up the on_finished callback so RunManager cleans up _user_runs
        backend.set_on_finished_callback(run_manager.get_on_finished_callback())

        app.state.run_manager = run_manager

        # Recover in-memory state from DB (for restarts with running workers)
        if config.worker.enabled:
            await run_manager.recover_state(app.state.repo)

    yield

    # Shutdown: stop all active runs
    if hasattr(app.state, "run_manager"):
        await app.state.run_manager.stop_all()

    # Shutdown Procrastinate backend if active
    if hasattr(app.state, "procrastinate_backend"):
        await app.state.procrastinate_backend.stop_monitoring()
    if hasattr(app.state, "procrastinate_app"):
        await app.state.procrastinate_app.connector.close_async()

    if hasattr(app.state, "engine") and app.state.engine:
        await app.state.engine.dispose()


def create_app(engine=None) -> FastAPI:
    """Create FastAPI application.

    Args:
        engine: Optional AsyncEngine. If None, created in lifespan from config.
    """
    app = FastAPI(
        title="Glyphbox API",
        description="REST + WebSocket API for watching and replaying Glyphbox agent runs",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Pre-set engine if provided (lifespan will use it instead of creating one)
    if engine is not None:
        app.state.engine = engine

    app.include_router(router, prefix="/api")
    app.include_router(auth_router)
    app.include_router(ws_router)

    # Serve built frontend in production (when dist/ exists)
    if FRONTEND_DIST.exists():

        @app.middleware("http")
        async def spa_fallback(request: Request, call_next) -> Response:
            response = await call_next(request)
            path = request.url.path
            if response.status_code == 404 and not path.startswith(("/api", "/ws")):
                return FileResponse(FRONTEND_DIST / "index.html")
            return response

        app.mount(
            "/",
            StaticFiles(directory=str(FRONTEND_DIST), html=True),
            name="frontend",
        )

    return app
