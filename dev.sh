#!/usr/bin/env bash
set -euo pipefail

PIDS=()
SECRETS_FILE=".dev-secrets"

cleanup() {
  echo ""
  echo "Shutting down..."
  for pid in "${PIDS[@]}"; do
    kill "$pid" 2>/dev/null && wait "$pid" 2>/dev/null
  done
  echo "Done."
}

trap cleanup EXIT INT TERM

# -----------------------------------------------------------------------
# Auth secrets — generate once, persist in .dev-secrets (gitignored)
# -----------------------------------------------------------------------

if [ -f "$SECRETS_FILE" ]; then
  # shellcheck source=/dev/null
  source "$SECRETS_FILE"
  echo "Loaded auth secrets from $SECRETS_FILE"
else
  echo "Generating auth secrets (first run)..."
  AUTH_SESSION_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
  AUTH_ENCRYPTION_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
  cat > "$SECRETS_FILE" <<EOF
export AUTH_SESSION_SECRET="$AUTH_SESSION_SECRET"
export AUTH_ENCRYPTION_KEY="$AUTH_ENCRYPTION_KEY"
EOF
  chmod 600 "$SECRETS_FILE"
  echo "Saved auth secrets to $SECRETS_FILE"
fi

export AUTH_SESSION_SECRET
export AUTH_ENCRYPTION_KEY
export AUTH_COOKIE_SECURE=false

# -----------------------------------------------------------------------
# ngrok tunnel — required for OpenRouter OAuth (HTTPS callback)
# -----------------------------------------------------------------------

if ! command -v ngrok &>/dev/null; then
  echo "ERROR: ngrok is not installed."
  echo "Install with: brew install ngrok"
  echo "Then authenticate: ngrok config add-authtoken <your-token>"
  exit 1
fi

echo "Starting ngrok tunnel to :3000..."
ngrok http 3000 --log=stdout --log-level=warn > /dev/null &
PIDS+=($!)

# Wait for ngrok to start and grab the public URL
NGROK_URL=""
for i in $(seq 1 30); do
  NGROK_URL=$(curl -s http://127.0.0.1:4040/api/tunnels 2>/dev/null \
    | python3 -c "import sys,json; tunnels=json.load(sys.stdin).get('tunnels',[]); print(next((t['public_url'] for t in tunnels if t['public_url'].startswith('https')), ''))" 2>/dev/null) || true
  if [ -n "$NGROK_URL" ]; then
    break
  fi
  sleep 0.5
done

if [ -z "$NGROK_URL" ]; then
  echo "ERROR: Failed to get ngrok public URL."
  echo "Make sure ngrok is authenticated: ngrok config add-authtoken <token>"
  exit 1
fi

export AUTH_CALLBACK_URL="${NGROK_URL}/api/auth/callback"
echo "ngrok tunnel: $NGROK_URL"
echo "OAuth callback: $AUTH_CALLBACK_URL"

# -----------------------------------------------------------------------
# Database
# -----------------------------------------------------------------------

echo "Starting Postgres..."
docker compose up -d postgres
until docker compose exec postgres pg_isready -U nethack -d nethack_agent 2>/dev/null; do
  sleep 1
done
echo "Postgres ready."

echo "Running migrations..."
uv run alembic upgrade head

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

# -----------------------------------------------------------------------
# Backend + Worker + Frontend
# -----------------------------------------------------------------------

LOG_DIR="data/logs"
mkdir -p "$LOG_DIR"

echo "Starting backend on :8000..."
uv run python -m src.cli serve >> "$LOG_DIR/serve.log" 2>&1 &
PIDS+=($!)

echo "Starting worker..."
uv run python -m src.cli worker >> "$LOG_DIR/worker.log" 2>&1 &
PIDS+=($!)

echo "Starting frontend on :3000..."
(cd frontend && exec npx vite) > /dev/null 2>&1 &
PIDS+=($!)

echo ""
echo "==========================================="
echo "  Open: $NGROK_URL"
echo "  Local: http://localhost:3000"
echo "==========================================="
echo ""
wait
