"""Procrastinate application for agent worker processes.

The connector is created with deferred configuration -- call
``configure(conninfo)`` before running the worker or deferring jobs.
"""

import procrastinate


def create_procrastinate_app(conninfo: str | None = None) -> procrastinate.App:
    """Create a Procrastinate App with a psycopg connector.

    Args:
        conninfo: PostgreSQL connection string (libpq format).
            e.g. "postgresql://user:pass@host:5432/dbname"
            If None, must be configured later before use.
    """
    kwargs = {}
    if conninfo:
        kwargs["conninfo"] = conninfo
    connector = procrastinate.PsycopgConnector(**kwargs)
    return procrastinate.App(
        connector=connector,
        import_paths=["src.worker.tasks"],
    )


# Module-level app used by the worker CLI and for defer_async() calls.
# Connector is configured at startup via configure().
_app: procrastinate.App | None = None


def get_app() -> procrastinate.App:
    """Return the configured Procrastinate app singleton."""
    if _app is None:
        raise RuntimeError(
            "Procrastinate app not configured. Call configure() first."
        )
    return _app


def configure(conninfo: str) -> procrastinate.App:
    """Configure the module-level Procrastinate app.

    Args:
        conninfo: PostgreSQL connection string.

    Returns:
        The configured App instance.
    """
    global _app
    _app = create_procrastinate_app(conninfo)
    return _app
