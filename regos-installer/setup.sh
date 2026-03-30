#!/usr/bin/env bash
set -euo pipefail
#
# setup.sh — One-command RegOS deployment on stock Open WebUI
#
# This script patches a stock Open WebUI source tree with RegOS features,
# builds and deploys via Docker Compose, and runs the RegOS installer to
# register functions, create the model, and configure settings.
#
# Usage:
#   ./setup.sh                                    # Interactive — prompts for everything
#   ./setup.sh --source /path/to/open-webui       # Use existing source tree
#   ./setup.sh --clone                            # Clone stock Open WebUI from GitHub
#   ./setup.sh --token <jwt>                      # Pass API token for installer
#
# Requirements:
#   - Docker Desktop (or Docker Engine + Docker Compose)
#   - python3, bash, curl, jq
#   - git (if using --clone)
#

# ─── Constants ──────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UPSTREAM_REPO="https://github.com/open-webui/open-webui.git"
UPSTREAM_TAG="v0.8.1"
DEFAULT_SOURCE_DIR="$(dirname "$SCRIPT_DIR")/open-webui"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

# ─── Helpers ────────────────────────────────────────────────────────
banner()  { echo -e "\n${BLUE}${BOLD}═══════════════════════════════════════════════════════${NC}"; echo -e "  ${BOLD}$1${NC}"; echo -e "${BLUE}${BOLD}═══════════════════════════════════════════════════════${NC}\n"; }
info()    { echo -e "${BLUE}→${NC} $1"; }
success() { echo -e "${GREEN}✓${NC} $1"; }
warn()    { echo -e "${YELLOW}⚠${NC} $1"; }
fail()    { echo -e "${RED}✗${NC} $1"; }
fatal()   { fail "$1"; exit 1; }

# ─── Defaults ───────────────────────────────────────────────────────
SOURCE_DIR=""
DO_CLONE=false
OPENWEBUI_TOKEN="${OPENWEBUI_TOKEN:-}"
OPENWEBUI_URL="${OPENWEBUI_URL:-http://localhost:3000}"
CONTAINER_NAME="${CONTAINER_NAME:-open-webui}"
SKIP_BUILD=false
SKIP_INSTALL=false
SKIP_PATCH=false
COMPOSE_PROJECT=""
BRANDING_DIR="${SCRIPT_DIR}/branding"

# ─── Parse CLI arguments ────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --source)       SOURCE_DIR="$2"; shift 2 ;;
    --clone)        DO_CLONE=true; shift ;;
    --tag)          UPSTREAM_TAG="$2"; shift 2 ;;
    --token)        OPENWEBUI_TOKEN="$2"; shift 2 ;;
    --api-url)      OPENWEBUI_URL="$2"; shift 2 ;;
    --container)    CONTAINER_NAME="$2"; shift 2 ;;
    --skip-build)   SKIP_BUILD=true; shift ;;
    --skip-install) SKIP_INSTALL=true; shift ;;
    --skip-patch)   SKIP_PATCH=true; shift ;;
    --project)      COMPOSE_PROJECT="$2"; shift 2 ;;
    --help|-h)
      cat <<'USAGE'
Usage: ./setup.sh [OPTIONS]

RegOS one-command deployment on stock Open WebUI.

SOURCE OPTIONS (pick one):
  --source PATH     Path to an existing Open WebUI source tree
  --clone           Clone stock Open WebUI from GitHub into ../open-webui/
  --tag TAG         Git tag to checkout when cloning (default: v0.8.1)

DEPLOYMENT OPTIONS:
  --token TOKEN     Open WebUI admin API token (for installer steps 05-10)
  --api-url URL     Open WebUI API URL (default: http://localhost:3000)
  --container NAME  Docker container name (default: open-webui)
  --project NAME    Docker Compose project name (controls volume naming)

SKIP OPTIONS:
  --skip-patch      Skip source patching (already patched)
  --skip-build      Skip Docker build (already running)
  --skip-install    Skip installer (functions/model already registered)

EXAMPLES:
  # First-time deployment — clone, patch, build, install everything:
  ./setup.sh --clone --token eyJhbG...

  # Re-run on existing patched source (just rebuild + reinstall):
  ./setup.sh --source ../open-webui --skip-patch --token eyJhbG...

  # Patch only (no build or install):
  ./setup.sh --source ../open-webui --skip-build --skip-install
USAGE
      exit 0
      ;;
    *) fatal "Unknown option: $1" ;;
  esac
done

# ═══════════════════════════════════════════════════════════════════
# PREFLIGHT CHECKS
# ═══════════════════════════════════════════════════════════════════

banner "RegOS Setup — Preflight Checks"

# Check required tools
for cmd in python3 docker; do
  if command -v "$cmd" &>/dev/null; then
    success "$cmd found: $(command -v "$cmd")"
  else
    fatal "$cmd is required but not found. Please install it."
  fi
done

# Check docker compose (v2 plugin or standalone)
if docker compose version &>/dev/null 2>&1; then
  COMPOSE_CMD="docker compose"
  success "Docker Compose v2 found"
elif command -v docker-compose &>/dev/null; then
  COMPOSE_CMD="docker-compose"
  success "Docker Compose standalone found"
else
  fatal "Docker Compose is required but not found."
fi

# Verify patcher exists
PATCHER="${SCRIPT_DIR}/source-patches/apply-patches.py"
if [[ ! -f "$PATCHER" ]]; then
  fatal "Patcher not found at ${PATCHER}"
fi
success "Patcher found"

# ═══════════════════════════════════════════════════════════════════
# STEP 1: GET SOURCE
# ═══════════════════════════════════════════════════════════════════

banner "Step 1 — Open WebUI Source"

if [[ "$DO_CLONE" == "true" ]]; then
  SOURCE_DIR="${SOURCE_DIR:-$DEFAULT_SOURCE_DIR}"

  if [[ -d "$SOURCE_DIR" && -d "$SOURCE_DIR/backend/open_webui" ]]; then
    warn "Source directory already exists: $SOURCE_DIR"
    info "Pulling latest and checking out ${UPSTREAM_TAG}..."
    cd "$SOURCE_DIR"
    git fetch --tags
    git checkout "$UPSTREAM_TAG" 2>/dev/null || git checkout "tags/$UPSTREAM_TAG"
    cd "$SCRIPT_DIR"
  else
    info "Cloning Open WebUI from ${UPSTREAM_REPO}..."
    git clone --depth 1 --branch "$UPSTREAM_TAG" "$UPSTREAM_REPO" "$SOURCE_DIR"
  fi
  success "Source ready at ${SOURCE_DIR}"

elif [[ -n "$SOURCE_DIR" ]]; then
  if [[ ! -d "$SOURCE_DIR/backend/open_webui" ]]; then
    fatal "${SOURCE_DIR} does not look like an Open WebUI source tree (missing backend/open_webui/)"
  fi
  success "Using existing source at ${SOURCE_DIR}"

else
  # No --source or --clone: try to auto-detect
  if [[ -d "$DEFAULT_SOURCE_DIR/backend/open_webui" ]]; then
    SOURCE_DIR="$DEFAULT_SOURCE_DIR"
    success "Auto-detected source at ${SOURCE_DIR}"
  else
    echo ""
    echo "No source directory specified. Options:"
    echo "  1) ./setup.sh --clone                     # Clone from GitHub"
    echo "  2) ./setup.sh --source /path/to/open-webui  # Use existing"
    echo ""
    fatal "Please specify a source directory."
  fi
fi

SOURCE_DIR="$(cd "$SOURCE_DIR" && pwd)"

# ═══════════════════════════════════════════════════════════════════
# STEP 2: PATCH SOURCE
# ═══════════════════════════════════════════════════════════════════

banner "Step 2 — Patch Source with RegOS Features"

if [[ "$SKIP_PATCH" == "true" ]]; then
  warn "Skipping source patching (--skip-patch)"
else
  info "Running patcher on ${SOURCE_DIR}..."
  python3 "$PATCHER" "$SOURCE_DIR"
  success "Source patched successfully"
fi

# ═══════════════════════════════════════════════════════════════════
# STEP 3: APPLY BRANDING (if branding/ directory exists)
# ═══════════════════════════════════════════════════════════════════

banner "Step 3 — Apply Branding"

if [[ -d "$BRANDING_DIR" ]]; then
  info "Copying branding assets from ${BRANDING_DIR}..."

  # Backend static assets (favicon, logo, splash)
  BACKEND_STATIC="${SOURCE_DIR}/backend/open_webui/static"
  if [[ -d "${BRANDING_DIR}/static" ]]; then
    cp -rv "${BRANDING_DIR}/static/"* "$BACKEND_STATIC/" 2>/dev/null || true
    success "Backend static assets copied"
  fi

  # Frontend static assets
  FRONTEND_STATIC="${SOURCE_DIR}/static/static"
  if [[ -d "${BRANDING_DIR}/frontend-static" ]]; then
    mkdir -p "$FRONTEND_STATIC"
    cp -rv "${BRANDING_DIR}/frontend-static/"* "$FRONTEND_STATIC/" 2>/dev/null || true
    success "Frontend static assets copied"
  fi

  # env.py branding (app name)
  ENV_PY="${SOURCE_DIR}/backend/open_webui/env.py"
  if [[ -f "${BRANDING_DIR}/app_name.txt" ]]; then
    APP_NAME=$(cat "${BRANDING_DIR}/app_name.txt")
    info "Setting app name to: ${APP_NAME}"
    python3 -c "
import re, sys
with open('$ENV_PY', 'r') as f:
    content = f.read()
# Replace DEFAULT_NAME in env.py
content = re.sub(
    r'(WEBUI_NAME\s*=\s*.*?\")(Open WebUI)(\")',
    r'\g<1>${APP_NAME}\g<3>',
    content
)
with open('$ENV_PY', 'w') as f:
    f.write(content)
print('  App name updated in env.py')
"
    success "Branding applied: ${APP_NAME}"
  fi
else
  info "No branding/ directory found — using stock Open WebUI branding"
  info "To add branding, create ${BRANDING_DIR}/ with your assets"
fi

# ═══════════════════════════════════════════════════════════════════
# STEP 4: DOCKER BUILD + DEPLOY
# ═══════════════════════════════════════════════════════════════════

banner "Step 4 — Docker Build & Deploy"

if [[ "$SKIP_BUILD" == "true" ]]; then
  warn "Skipping Docker build (--skip-build)"
else
  cd "$SOURCE_DIR"

  # Verify docker-compose.yaml exists
  if [[ ! -f "docker-compose.yaml" && ! -f "docker-compose.yml" ]]; then
    fatal "No docker-compose.yaml found in ${SOURCE_DIR}"
  fi

  # Set NODE_OPTIONS to prevent OOM during frontend build
  info "Ensuring NODE_OPTIONS is set for frontend build..."
  COMPOSE_FILE="docker-compose.yaml"
  [[ ! -f "$COMPOSE_FILE" ]] && COMPOSE_FILE="docker-compose.yml"

  if ! grep -q "NODE_OPTIONS" "$COMPOSE_FILE" 2>/dev/null; then
    warn "NODE_OPTIONS not set in ${COMPOSE_FILE} — frontend build may OOM"
    warn "Consider adding: NODE_OPTIONS=--max-old-space-size=4096"
  fi

  # Build project name args
  COMPOSE_ARGS=""
  if [[ -n "$COMPOSE_PROJECT" ]]; then
    COMPOSE_ARGS="-p $COMPOSE_PROJECT"
  fi

  info "Building and deploying with Docker Compose..."
  info "This may take 10-15 minutes on first build (frontend compilation + Python packages)."
  echo ""

  $COMPOSE_CMD $COMPOSE_ARGS up -d --build

  echo ""
  success "Docker build complete"

  # Wait for container to be healthy
  info "Waiting for container to start..."
  WAIT_SECONDS=0
  MAX_WAIT=120
  while [[ $WAIT_SECONDS -lt $MAX_WAIT ]]; do
    if docker exec "$CONTAINER_NAME" python3 -c "print('ok')" &>/dev/null 2>&1; then
      break
    fi
    sleep 2
    WAIT_SECONDS=$((WAIT_SECONDS + 2))
    printf "."
  done
  echo ""

  if [[ $WAIT_SECONDS -ge $MAX_WAIT ]]; then
    warn "Container did not become ready within ${MAX_WAIT}s — continuing anyway"
  else
    success "Container '${CONTAINER_NAME}' is running"
  fi

  cd "$SCRIPT_DIR"
fi

# Note: neo4j is now in requirements.txt — baked into the Docker image at build time.
# No need for a separate "docker exec pip install neo4j" step.

# ═══════════════════════════════════════════════════════════════════
# STEP 5: RUN REGOS INSTALLER
# ═══════════════════════════════════════════════════════════════════

banner "Step 6 — Run RegOS Installer"

if [[ "$SKIP_INSTALL" == "true" ]]; then
  warn "Skipping RegOS installer (--skip-install)"
else
  if [[ -z "$OPENWEBUI_TOKEN" ]]; then
    echo ""
    warn "No API token provided."
    echo ""
    echo "  The RegOS installer needs an admin API token to register functions,"
    echo "  create models, and configure settings (steps 05-10)."
    echo ""
    echo "  To get your token:"
    echo "    1. Open ${OPENWEBUI_URL} in your browser"
    echo "    2. Create an admin account (first user becomes admin)"
    echo "    3. Click profile icon → Settings → Account → API Keys → Create"
    echo ""
    echo "  Then re-run:"
    echo "    ./setup.sh --source ${SOURCE_DIR} --skip-patch --skip-build --token <your-token>"
    echo ""
    warn "Skipping installer steps that require authentication."
    echo ""

    # Still run steps 01-04 (no token needed)
    info "Running installer steps 01-04 (no token required)..."
    "${SCRIPT_DIR}/install.sh" \
      --container "$CONTAINER_NAME" \
      --api-url "$OPENWEBUI_URL" \
      --step 01 || true
    "${SCRIPT_DIR}/install.sh" \
      --container "$CONTAINER_NAME" \
      --api-url "$OPENWEBUI_URL" \
      --step 03 || true
    "${SCRIPT_DIR}/install.sh" \
      --container "$CONTAINER_NAME" \
      --api-url "$OPENWEBUI_URL" \
      --step 04 || true
  else
    info "Running full RegOS installer..."
    "${SCRIPT_DIR}/install.sh" \
      --container "$CONTAINER_NAME" \
      --api-url "$OPENWEBUI_URL" \
      --token "$OPENWEBUI_TOKEN" \
      --configure
    success "RegOS installer complete"
  fi
fi

# ═══════════════════════════════════════════════════════════════════
# DONE
# ═══════════════════════════════════════════════════════════════════

banner "Setup Complete"

echo -e "  ${GREEN}${BOLD}RegOS has been deployed successfully!${NC}"
echo ""
echo "  Open ${OPENWEBUI_URL} in your browser."
echo ""

if [[ -z "$OPENWEBUI_TOKEN" ]]; then
  echo "  Next steps:"
  echo "    1. Create an admin account (first user)"
  echo "    2. Get your API token (Profile → Settings → Account → API Keys)"
  echo "    3. Run the installer to finish setup:"
  echo ""
  echo "       ./setup.sh --source ${SOURCE_DIR} --skip-patch --skip-build --token <your-token>"
  echo ""
fi

echo "  Post-installation:"
echo "    1. Set Neo4j credentials: Admin → Functions → graphrag_filter → Valves"
echo "    2. Upload Knowledge Base: Chapter 24 PDF documents"
echo "    3. Assign KB to model: Edit RegOS Compliance Copilot → connect KB"
echo "    4. Configure RegOS: Admin → RegOS → adjust settings"
echo "    5. Test: Select 'RegOS Compliance Copilot' → ask a regulatory question"
echo ""
echo "  IMPORTANT — Safe rebuild process:"
echo "    Always use 'docker compose up -d --build' to rebuild."
echo "    NEVER use raw 'docker run' — it creates a different volume and you lose data."
echo ""
