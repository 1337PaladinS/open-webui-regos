#!/usr/bin/env bash
# APAS Open WebUI — first-boot / every-boot script for RunPod.
#
# Responsibilities:
#   1. Ensure /workspace layout exists
#   2. Symlink /app/backend/data -> /workspace/openwebui/data
#      (so SQLite, uploads, vector DB, configs persist across image upgrades)
#   3. Install PUBLIC_KEY into /root/.ssh/authorized_keys and start sshd
#      (gives RunPod web terminal + runpodctl ssh access on custom images)
#   4. Start Cloudflare Tunnel (*.apas.ai custom domains) if configured
#   5. Start PumpIQ MCP server on :8001
#   6. Start RegOS Sidecar API on :8300
#   7. Hand off to the upstream Open WebUI start script (which itself
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

# --- 4. Cloudflare Tunnel (*.apas.ai custom domains) -----------------------
# Requires one-time setup: see docs/CLOUDFLARE_TUNNEL_RUNBOOK.md
#   CLOUDFLARED_TUNNEL_ID  – tunnel UUID
#   CLOUDFLARED_HOSTNAME   – primary hostname (e.g. regos.apas.ai)
# Credentials JSON must be at /workspace/cloudflared/<tunnel-id>.json
CF_DIR="${WORKSPACE}/cloudflared"
CF_TUNNEL_ID="${CLOUDFLARED_TUNNEL_ID:-}"
CF_HOSTNAME="${CLOUDFLARED_HOSTNAME:-regos.apas.ai}"

if command -v cloudflared >/dev/null 2>&1 && [ -n "${CF_TUNNEL_ID}" ]; then
  CF_CREDS="${CF_DIR}/${CF_TUNNEL_ID}.json"
  CF_CONFIG="${CF_DIR}/config.yml"

  if [ -f "${CF_CREDS}" ]; then
    # Generate config.yml from template, replacing placeholders
    mkdir -p "${CF_DIR}"
    sed \
      -e "s|TUNNEL_ID_PLACEHOLDER|${CF_TUNNEL_ID}|g" \
      -e "s|CREDS_FILE_PLACEHOLDER|${CF_CREDS}|g" \
      -e "s|HOSTNAME_PLACEHOLDER|${CF_HOSTNAME}|g" \
      /runpod/cloudflared-config.yml > "${CF_CONFIG}"

    log "starting cloudflared tunnel (${CF_HOSTNAME} -> localhost)"
    nohup cloudflared tunnel --config "${CF_CONFIG}" run \
      >>"${LOGS_DIR}/cloudflared.log" 2>&1 &
    log "cloudflared started (pid $!)"
  else
    log "cloudflared credentials not found at ${CF_CREDS} — skipping tunnel"
    log "  run the one-time setup: see docs/CLOUDFLARE_TUNNEL_RUNBOOK.md"
  fi
else
  if [ -z "${CF_TUNNEL_ID}" ]; then
    log "CLOUDFLARED_TUNNEL_ID not set — skipping Cloudflare Tunnel"
  else
    log "cloudflared binary not found — skipping tunnel"
  fi
fi

# --- 5. PumpIQ MCP server ----------------------------------------------------
# Runs mcpo bridge wrapping the PumpIQ stdio MCP server on port 8001.
# Env vars: NOAA_CDO_TOKEN, SFWMD_API_KEY (optional, set in RunPod template).
if [ -f /opt/pumpiq-mcp/dist/index.js ]; then
  log "starting PumpIQ MCP server on :8001"
  NOAA_CDO_TOKEN="${NOAA_CDO_TOKEN:-}" \
  SFWMD_API_KEY="${SFWMD_API_KEY:-}" \
  nohup mcpo --port 8001 --host 0.0.0.0 -- node /opt/pumpiq-mcp/dist/index.js \
    >>"${LOGS_DIR}/pumpiq-mcp.log" 2>&1 &
  log "PumpIQ MCP server started (pid $!)"
else
  log "PumpIQ MCP server not found — skipping"
fi

# --- 6. RegOS Sidecar API ---------------------------------------------------
# Runs the RegOS API (regos_api + apas_bridge + scada_stream) on port 8300.
# Env vars: OPENWEBUI_TOKEN, REGOS_MODEL_ID (set in RunPod template).
# File logging is handled by Python's RotatingFileHandler (10MB, 5 backups)
# via the REGOS_LOG_DIR env var — no shell redirect needed.
if [ -f /opt/regos-api/api/regos_api.py ]; then
  log "starting RegOS sidecar API on :8300"
  OPENWEBUI_URL="http://localhost:8080" \
  OPENWEBUI_TOKEN="${OPENWEBUI_TOKEN:-}" \
  REGOS_MODEL_ID="${REGOS_MODEL_ID:-regos-chapter24-copilot}" \
  REGOS_API_PORT="8300" \
  REGOS_LOG_DIR="${LOGS_DIR}" \
  nohup python3 -m uvicorn api.regos_api:app \
    --host 0.0.0.0 --port 8300 --app-dir /opt/regos-api \
    >/dev/null 2>&1 &
  log "RegOS sidecar API started (pid $!)"
else
  log "RegOS sidecar API not found — skipping"
fi

# --- 7. Ollama model warmup (background) ------------------------------------
# On pod restart, Ollama starts with no model in VRAM. The first user request
# triggers a cold load (30-60s). This background script waits for Ollama to be
# ready, then sends a tiny prompt to preload the model into GPU memory.
# OLLAMA_KEEP_ALIVE=-1 ensures it stays loaded permanently.
OLLAMA_WARMUP_MODEL="${OLLAMA_WARMUP_MODEL:-}"
if [ -n "${OLLAMA_WARMUP_MODEL}" ]; then
  (
    log "warmup: waiting for Ollama to become ready..."
    for i in $(seq 1 60); do
      if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
        log "warmup: Ollama is ready, preloading model '${OLLAMA_WARMUP_MODEL}'"
        # Pull the model if not already present (no-op if cached in /workspace/ollama)
        curl -sf http://localhost:11434/api/pull -d "{\"name\":\"${OLLAMA_WARMUP_MODEL}\"}" >/dev/null 2>&1 || true
        # Send a tiny generate request to load model into VRAM
        curl -sf http://localhost:11434/api/generate -d "{\"model\":\"${OLLAMA_WARMUP_MODEL}\",\"prompt\":\"hi\",\"options\":{\"num_predict\":1}}" >/dev/null 2>&1
        log "warmup: model '${OLLAMA_WARMUP_MODEL}' loaded into VRAM"
        break
      fi
      sleep 2
    done
  ) &
  log "warmup script launched in background (pid $!)"
fi

# --- 8. Hand off to upstream Open WebUI entrypoint --------------------------
# File logging is handled by Loguru's file sink (50MB rotation, zip, 5 retained)
# via the OWUI_LOG_FILE_PATH env var — stdout stays clean for RunPod console.
log "handing off to upstream start.sh"
cd /app/backend
export OWUI_LOG_FILE_PATH="${LOGS_DIR}/openwebui.log"
exec bash start.sh
