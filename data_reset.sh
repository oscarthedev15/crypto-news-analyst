#!/usr/bin/env bash
set -euo pipefail

# Config (no hardcoded absolute paths)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$SCRIPT_DIR}"

# Derived paths (override-able via env if desired)
BACKEND_DIR="${BACKEND_DIR:-$PROJECT_ROOT/backend}"
SQLITE_DB="${SQLITE_DB:-$BACKEND_DIR/news_articles.db}"
QDRANT_STORAGE="${QDRANT_STORAGE:-$PROJECT_ROOT/qdrant-storage}"
QDRANT_URL="${QDRANT_URL:-http://localhost:6333}"

# Logging
LOG_DIR="$BACKEND_DIR/logs"
mkdir -p "$LOG_DIR"
TS="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="$LOG_DIR/data_reset_${TS}.log"
echo "Logging to: $LOG_FILE"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "=== Data reset starting at $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
echo "PROJECT_ROOT=$PROJECT_ROOT"
echo "SQLITE_DB=$SQLITE_DB"
echo "QDRANT_STORAGE=$QDRANT_STORAGE"

cd "$PROJECT_ROOT"

echo "[1/5] Stopping services (docker compose + uvicorn if running)..."
# Stop and remove compose stack for this repo (remove orphans and volumes to be thorough)
docker compose down --remove-orphans --volumes || true
# Additionally, force-remove any lingering container with the fixed name used in compose
# This handles conflicts when another clone/repo instance created the same named container
docker rm -f crypto-news-qdrant 2>/dev/null || true
# Best-effort network cleanup (if a stale default network exists)
docker network rm "$(basename "$PROJECT_ROOT")_default" 2>/dev/null || true
pkill -f "uvicorn.*app.main" 2>/dev/null || true

echo "[2/5] Removing SQLite DB and Qdrant local storage..."
rm -f "$SQLITE_DB" || true
rm -rf "$QDRANT_STORAGE" || true

echo "[3/5] Starting Qdrant fresh (docker compose up -d)..."
# Start only the qdrant service
docker compose up -d qdrant

echo "[4/5] Waiting for Qdrant to become reachable at $QDRANT_URL ..."
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

echo "[5/5] Done. Data removed and Qdrant restarted."
echo "✓ Data reset completed at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "Log file: $LOG_FILE"


