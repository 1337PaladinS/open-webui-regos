#!/usr/bin/env bash
# APAS Open WebUI — first-boot / every-boot script for RunPod.
#
# Responsibilities:
#   1. Ensure /workspace layout exists on the network volume
#   2. Symlink /app/backend/data -> /workspace/openwebui/data
#      (so all SQLite, uploads, vector DB, configs persist across image upgrades)
#   3. Start bundled Ollama in the background, logging to /workspace/logs/ollama.log
#   4. Hand off to the upstream Open WebUI start script (bash start.sh)
#
# This script is idempotent: safe to run on every container boot.

set -euo pipefail

log() { echo "[apas-start] $*"; }

WORKSPACE="${WORKSPACE:-/workspace}"
OWUI_DATA_SRC="/app/backend/data"
OWUI_DATA_DEST="${WORKSPACE}/openwebui/data"
OLLAMA_DIR="${WORKSPACE}/ollama"
LOGS_DIR="${WORKSPACE}/logs"

log "boot starting — workspace=${WORKSPACE}"

# --- 1. Volume layout -------------------------------------------------------
mkdir -p "${WORKSPACE}/openwebui" "${OLLAMA_DIR}" "${LOGS_DIR}"

# --- 2. Persistent data symlink --------------------------------------------
# If /app/backend/data is a real directory with content (first boot on fresh
# image), migrate it into the volume, then replace it with a symlink.
if [ -e "${OWUI_DATA_SRC}" ] && [ ! -L "${OWUI_DATA_SRC}" ]; then
  if [ ! -d "${OWUI_DATA_DEST}" ]; then
    log "migrating ${OWUI_DATA_SRC} -> ${OWUI_DATA_DEST}"
    mkdir -p "$(dirname "${OWUI_DATA_DEST}")"
    mv "${OWUI_DATA_SRC}" "${OWUI_DATA_DEST}"
  else
    log "destination exists, removing stale ${OWUI_DATA_SRC}"
    rm -rf "${OWUI_DATA_SRC}"
  fi
fi

if [ ! -L "${OWUI_DATA_SRC}" ]; then
  mkdir -p "${OWUI_DATA_DEST}"
  ln -s "${OWUI_DATA_DEST}" "${OWUI_DATA_SRC}"
  log "symlinked ${OWUI_DATA_SRC} -> ${OWUI_DATA_DEST}"
else
  log "symlink already in place: ${OWUI_DATA_SRC}"
fi

# --- 3. Ollama bring-up -----------------------------------------------------
if [ "${ENABLE_OLLAMA_API:-true}" = "true" ] && command -v ollama >/dev/null 2>&1; then
  export OLLAMA_MODELS="${OLLAMA_MODELS:-${OLLAMA_DIR}}"
  export OLLAMA_HOST="${OLLAMA_HOST:-0.0.0.0}"
  export OLLAMA_KEEP_ALIVE="${OLLAMA_KEEP_ALIVE:--1}"
  mkdir -p "${OLLAMA_MODELS}"
  log "starting ollama (models=${OLLAMA_MODELS} host=${OLLAMA_HOST})"
  nohup ollama serve >>"${LOGS_DIR}/ollama.log" 2>&1 &
  OLLAMA_PID=$!
  log "ollama pid=${OLLAMA_PID}"

  # Wait up to 30s for ollama to respond
  for i in $(seq 1 30); do
    if curl -fsS "http://localhost:11434/api/version" >/dev/null 2>&1; then
      log "ollama healthy after ${i}s"
      break
    fi
    sleep 1
  done
else
  log "skipping ollama bring-up (disabled or binary missing)"
fi

# --- 4. Hand off to upstream Open WebUI entrypoint --------------------------
log "handing off to upstream start.sh"
cd /app/backend
exec bash start.sh
