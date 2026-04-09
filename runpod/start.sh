#!/usr/bin/env bash
# APAS Open WebUI — first-boot / every-boot script for RunPod.
#
# Responsibilities:
#   1. Ensure /workspace layout exists
#   2. Symlink /app/backend/data -> /workspace/openwebui/data
#      (so SQLite, uploads, vector DB, configs persist across image upgrades)
#   3. Install PUBLIC_KEY into /root/.ssh/authorized_keys and start sshd
#      (gives RunPod web terminal + runpodctl ssh access on custom images)
#   4. Optional escape hatch: APAS_RESET_DB=1 wipes webui.db on boot
#   5. Hand off to the upstream Open WebUI start script (which itself
#      starts the bundled Ollama — we no longer start it here to avoid
#      the double-bind on port 11434)
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

# --- 2b. Escape hatch: wipe webui.db on boot --------------------------------
# Set APAS_RESET_DB=1 in the pod env to force a fresh admin signup after boot.
# Remember to unset / set back to 0 after the next boot or every restart nukes users.
if [ "${APAS_RESET_DB:-0}" = "1" ]; then
  if [ -f "${OWUI_DATA_DEST}/webui.db" ]; then
    log "APAS_RESET_DB=1 — removing ${OWUI_DATA_DEST}/webui.db"
    rm -f "${OWUI_DATA_DEST}/webui.db" \
          "${OWUI_DATA_DEST}/webui.db-wal" \
          "${OWUI_DATA_DEST}/webui.db-shm"
  else
    log "APAS_RESET_DB=1 — no webui.db to remove"
  fi
fi

# --- 3. SSH daemon ----------------------------------------------------------
# RunPod injects the account's SSH public key(s) into $PUBLIC_KEY on pod start.
# Stock RunPod images install them automatically; our custom image has to do it.
if command -v sshd >/dev/null 2>&1; then
  mkdir -p /root/.ssh
  chmod 700 /root/.ssh
  : > /root/.ssh/authorized_keys
  if [ -n "${PUBLIC_KEY:-}" ]; then
    # PUBLIC_KEY may contain multiple keys separated by literal \n
    printf '%b\n' "${PUBLIC_KEY}" >> /root/.ssh/authorized_keys
    log "installed PUBLIC_KEY into /root/.ssh/authorized_keys"
  else
    log "no PUBLIC_KEY env var — sshd will start but no keys are authorized"
  fi
  chmod 600 /root/.ssh/authorized_keys

  # Generate host keys if the image build somehow missed it
  if [ ! -f /etc/ssh/ssh_host_ed25519_key ]; then
    ssh-keygen -A
  fi
  mkdir -p /var/run/sshd

  log "starting sshd on :22"
  /usr/sbin/sshd >>"${LOGS_DIR}/sshd.log" 2>&1 || log "sshd failed to start (see ${LOGS_DIR}/sshd.log)"
else
  log "sshd not installed — skipping"
fi

# --- 4. Hand off to upstream Open WebUI entrypoint --------------------------
log "handing off to upstream start.sh"
cd /app/backend
exec bash start.sh
