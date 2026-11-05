#!/bin/sh
set -eu
# Railway provides PORT dynamically. One worker is intentional: camera buffers,
# pairing tokens and WebSocket clients currently live in process memory.
if [ "${APP_ENV:-production}" = "production" ] && [ -n "${RAILWAY_ENVIRONMENT:-}" ]; then
  case "${DB_URL:-}" in
    sqlite:////data/*) ;;
    *) echo "ERROR: Railway requires DB_URL=sqlite:////data/smartshelf.db on a persistent volume." >&2; exit 1 ;;
  esac
  case "${UPLOAD_DIR:-}" in
    /data/*) ;;
    *) echo "ERROR: Railway requires UPLOAD_DIR=/data/uploads on the same persistent volume." >&2; exit 1 ;;
  esac
  if [ ! -w /data ]; then
    echo "ERROR: /data must be a writable persistent volume. Mount Railway Volume at /data." >&2
    exit 1
  fi
fi
exec python -m uvicorn backend.app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1
