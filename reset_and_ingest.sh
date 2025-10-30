#!/usr/bin/env bash
set -euo pipefail

# Config (no hardcoded absolute paths)
# Resolve directory of this script and default PROJECT_ROOT to it
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$SCRIPT_DIR}"

# Derived paths (override-able via env if desired)
BACKEND_DIR="${BACKEND_DIR:-$PROJECT_ROOT/backend}"
VENV_ACTIVATE="${VENV_ACTIVATE:-$BACKEND_DIR/venv/bin/activate}"
SQLITE_DB="${SQLITE_DB:-$BACKEND_DIR/news_articles.db}"

# Qdrant storage should match docker-compose volume mapping (./qdrant-storage)
QDRANT_STORAGE="${QDRANT_STORAGE:-$PROJECT_ROOT/qdrant-storage}"

# Other settings
QDRANT_URL="${QDRANT_URL:-http://localhost:6333}"
COLLECTION_NAME="${COLLECTION_NAME:-crypto_news_articles}"
MAX_PER_SOURCE="${MAX_PER_SOURCE:-25}"

# Logging
LOG_DIR="$BACKEND_DIR/logs"
mkdir -p "$LOG_DIR"
TS="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="$LOG_DIR/reset_ingest_${TS}.log"
echo "Logging to: $LOG_FILE"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "=== Reset + Ingest starting at $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
echo "PROJECT_ROOT=$PROJECT_ROOT"
echo "SQLITE_DB=$SQLITE_DB"
echo "QDRANT_STORAGE=$QDRANT_STORAGE"
echo "QDRANT_URL=$QDRANT_URL"
echo "COLLECTION_NAME=$COLLECTION_NAME"
echo "MAX_PER_SOURCE=$MAX_PER_SOURCE"

cd "$PROJECT_ROOT"

echo "[1/8] Stopping Qdrant (docker compose down)..."
docker compose down || true

echo "[2/8] Stopping backend dev server if running (uvicorn)..."
pkill -f "uvicorn.*app.main" 2>/dev/null || true

echo "[3/8] Removing SQLite DB and Qdrant local storage..."
rm -f "$SQLITE_DB" || true
rm -rf "$QDRANT_STORAGE" || true

echo "[4/8] Starting Qdrant fresh (docker compose up -d)..."
docker compose up -d

echo "[5/8] Waiting for Qdrant to become healthy..."
ATTEMPTS=0
until curl -fsS "$QDRANT_URL/" >/dev/null; do
  ATTEMPTS=$((ATTEMPTS+1))
  if [[ $ATTEMPTS -ge 60 ]]; then
    echo "Qdrant did not become ready in time" >&2
    exit 1
  fi
  sleep 1
done
echo "Qdrant is reachable."

echo "[6/8] Deleting collection '$COLLECTION_NAME' if it exists..."
curl -fsS -X DELETE "$QDRANT_URL/collections/$COLLECTION_NAME" >/dev/null || true
echo "Collection delete requested (ignored if not present)."

echo "[7/8] Running ingest script (max per source: $MAX_PER_SOURCE)..."
cd "$BACKEND_DIR"
if [[ -f "$VENV_ACTIVATE" ]]; then
  # shellcheck disable=SC1090
  source "$VENV_ACTIVATE"
else
  echo "Warning: venv not found at $VENV_ACTIVATE; attempting with system python" >&2
fi

python scripts/ingest_news.py --max-articles-per-source "$MAX_PER_SOURCE"
INGEST_EXIT=$?

echo "[8/8] Verifying fresh state and results..."
if [[ -f "$SQLITE_DB" ]]; then
  echo "SQLite DB recreated at: $SQLITE_DB"
else
  echo "Warning: SQLite DB not found after ingest: $SQLITE_DB" >&2
fi

echo "Ingest exit code: $INGEST_EXIT"
if [[ $INGEST_EXIT -ne 0 ]]; then
  echo "✗ Ingestion failed. See log: $LOG_FILE" >&2
  exit $INGEST_EXIT
fi

echo "✓ Reset + Ingest completed at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "Log file: $LOG_FILE"


