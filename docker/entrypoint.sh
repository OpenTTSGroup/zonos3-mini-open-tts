#!/usr/bin/env bash
set -euo pipefail

: "${ZONOS3_MODEL:=Zyphra/ZONOS3-Mini}"
: "${ZONOS3_DEVICE:=auto}"
: "${VOICES_DIR:=/voices}"
: "${HOST:=0.0.0.0}"
: "${PORT:=8000}"
: "${LOG_LEVEL:=info}"
export ZONOS3_MODEL ZONOS3_DEVICE VOICES_DIR HOST PORT LOG_LEVEL

if [ "$#" -eq 0 ]; then
  exec uvicorn app.server:app --host "$HOST" --port "$PORT" --log-level "$LOG_LEVEL" --workers 1
fi
exec "$@"
