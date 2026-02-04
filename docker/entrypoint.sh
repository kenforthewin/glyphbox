#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-serve}"

# Wait for postgres to accept connections
echo "Waiting for postgres..."
until python -c "
import socket, os, sys
host = os.environ.get('NETHACK_AGENT_DB_HOST', 'localhost')
port = int(os.environ.get('NETHACK_AGENT_DB_PORT', '5432'))
s = socket.socket()
try:
    s.connect((host, port))
    s.close()
    sys.exit(0)
except Exception:
    sys.exit(1)
" 2>/dev/null; do
    sleep 1
done
echo "Postgres is ready."

# Build DB URL for Alembic (which checks NETHACK_AGENT_DB_URL)
DB_HOST="${NETHACK_AGENT_DB_HOST:-localhost}"
DB_PORT="${NETHACK_AGENT_DB_PORT:-5432}"
DB_NAME="${NETHACK_AGENT_DB_NAME:-nethack_agent}"
DB_USER="${NETHACK_AGENT_DB_USER:-nethack}"
DB_PASS="${NETHACK_AGENT_DB_PASSWORD:-nethack}"
export NETHACK_AGENT_DB_URL="postgresql+asyncpg://${DB_USER}:${DB_PASS}@${DB_HOST}:${DB_PORT}/${DB_NAME}"

if [ "$MODE" = "serve" ]; then
    # Run Alembic migrations
    echo "Running migrations..."
    uv run alembic upgrade head

    # Apply Procrastinate schema
    echo "Applying Procrastinate schema..."
    uv run python -c "
from procrastinate import SyncPsycopgConnector
from procrastinate.schema import SchemaManager
from procrastinate.exceptions import ConnectorException
from src.config import load_config
conninfo = load_config().database.conninfo
connector = SyncPsycopgConnector(conninfo=conninfo)
connector.open()
try:
    SchemaManager(connector).apply_schema()
    print('Procrastinate schema applied.')
except ConnectorException:
    print('Procrastinate schema already exists.')
finally:
    connector.close()
"

    echo "Starting API server..."
    exec uv run python -m src.cli serve
elif [ "$MODE" = "worker" ]; then
    echo "Starting worker..."
    exec uv run python -m src.cli worker
else
    echo "Unknown mode: $MODE"
    exit 1
fi
