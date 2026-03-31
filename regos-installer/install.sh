#!/usr/bin/env bash
set -euo pipefail
#
# install.sh — RegOS Installer for Open WebUI
#
# Installs the RegOS Regulatory Compliance Copilot into a running
# Open WebUI Docker instance. Copies data files, registers filter
# functions, and optionally creates a custom model.
#
# Usage:
#   ./install.sh                          # Interactive install
#   ./install.sh --container open-webui   # Specify container
#   ./install.sh --step 05               # Run single step
#   ./install.sh --dry-run               # Preview without changes
#
# Environment variables:
#   CONTAINER_NAME    Docker container name (default: open-webui)
#   OPENWEBUI_URL     API base URL (default: http://localhost:3000)
#   OPENWEBUI_TOKEN   JWT or API key for REST API calls
#   VERBOSE           Enable debug output (default: false)
#   DRY_RUN           Preview mode (default: false)
#

# ─── Resolve installer directory ──────────────────────────────────────
INSTALLER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export INSTALLER_DIR

# ─── Load libraries ───────────────────────────────────────────────────
source "${INSTALLER_DIR}/lib/logger.sh"
source "${INSTALLER_DIR}/lib/docker.sh"
source "${INSTALLER_DIR}/lib/api.sh"

# ─── Load config ──────────────────────────────────────────────────────
if [[ -f "${INSTALLER_DIR}/config/install.conf" ]]; then
  source "${INSTALLER_DIR}/config/install.conf"
fi

# Load .env if present (user overrides)
if [[ -f "${INSTALLER_DIR}/.env" ]]; then
  set -a
  source "${INSTALLER_DIR}/.env"
  set +a
fi

# ─── Defaults ─────────────────────────────────────────────────────────
CONTAINER_NAME="${CONTAINER_NAME:-open-webui}"
OPENWEBUI_URL="${OPENWEBUI_URL:-http://localhost:3000}"
OPENWEBUI_TOKEN="${OPENWEBUI_TOKEN:-}"
VERBOSE="${VERBOSE:-false}"
DRY_RUN="${DRY_RUN:-false}"
CREATE_MODEL="${CREATE_MODEL:-true}"
SETUP_GROUPS="${SETUP_GROUPS:-false}"
REGOS_CONFIGURE="${REGOS_CONFIGURE:-false}"
MODULES="${MODULES:-}"  # chapter24, opalocka, or both

# ─── Parse CLI arguments ──────────────────────────────────────────────
SINGLE_STEP=""
INTERACTIVE=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --container)   CONTAINER_NAME="$2"; shift 2 ;;
    --api-url)     OPENWEBUI_URL="$2"; shift 2 ;;
    --token)       OPENWEBUI_TOKEN="$2"; shift 2 ;;
    --step)        SINGLE_STEP="$2"; shift 2 ;;
    --dry-run)     DRY_RUN=true; shift ;;
    --verbose)     VERBOSE=true; shift ;;
    --create-model) CREATE_MODEL=true; shift ;;
    --no-model)    CREATE_MODEL=false; shift ;;
    --setup-groups) SETUP_GROUPS=true; shift ;;
    --interactive) INTERACTIVE=true; shift ;;
    --configure)   REGOS_CONFIGURE=true; shift ;;
    --modules)     MODULES="$2"; shift 2 ;;
    --help|-h)
      echo "Usage: ./install.sh [OPTIONS]"
      echo ""
      echo "Options:"
      echo "  --container NAME    Docker container name (default: open-webui)"
      echo "  --api-url URL       Open WebUI API URL (default: http://localhost:3000)"
      echo "  --token TOKEN       JWT or API key for authentication"
      echo "  --modules MODULE    Regulatory module(s) to install:"
      echo "                        chapter24  — Chapter 24 (Miami-Dade Environmental)"
      echo "                        opalocka   — Opa-Locka (Municipal Code)"
      echo "                        both       — Install both modules"
      echo "  --step N            Run only step N (e.g., 05)"
      echo "  --dry-run           Preview without making changes"
      echo "  --verbose           Enable debug output"
      echo "  --create-model      Create RegOS custom model (default)"
      echo "  --no-model          Skip model creation"
      echo "  --setup-groups      Create user groups"
      echo "  --configure         Push RegOS admin panel defaults"
      echo "  --interactive       Prompt for settings"
      echo "  --help              Show this help"
      exit 0
      ;;
    *) log_error "Unknown option: $1"; exit 1 ;;
  esac
done

# ─── Interactive mode ─────────────────────────────────────────────────
if [[ "$INTERACTIVE" == "true" ]]; then
  echo ""
  read -rp "Container name [${CONTAINER_NAME}]: " input
  CONTAINER_NAME="${input:-$CONTAINER_NAME}"

  read -rp "Open WebUI URL [${OPENWEBUI_URL}]: " input
  OPENWEBUI_URL="${input:-$OPENWEBUI_URL}"

  if [[ -z "$OPENWEBUI_TOKEN" ]]; then
    echo ""
    echo "To get your token:"
    echo "  Open WebUI → Click profile icon → Settings → Account → API Keys"
    echo "  Or: Browser DevTools → Application → Cookies → 'token'"
    echo ""
    read -rp "API Token: " OPENWEBUI_TOKEN
  fi

  if [[ -z "$MODULES" ]]; then
    echo ""
    echo "Which regulatory module(s) do you want to install?"
    echo "  1) Chapter 24      — Miami-Dade Environmental Regulations"
    echo "  2) Opa-Locka       — Municipal Code of Ordinances"
    echo "  3) Both"
    echo ""
    read -rp "Select [1/2/3]: " module_choice
    case "$module_choice" in
      1) MODULES="chapter24" ;;
      2) MODULES="opalocka" ;;
      3) MODULES="both" ;;
      *) log_warn "Invalid choice — defaulting to 'both'"; MODULES="both" ;;
    esac
  fi

  read -rp "Create custom model? [Y/n]: " input
  [[ "${input,,}" == "n" ]] && CREATE_MODEL=false

  read -rp "Setup user groups? [y/N]: " input
  [[ "${input,,}" == "y" ]] && SETUP_GROUPS=true
fi

# ─── Default modules to 'both' if not set ─────────────────────────────
if [[ -z "$MODULES" ]]; then
  MODULES="both"
fi

# ─── Load step scripts ────────────────────────────────────────────────
for step_file in "${INSTALLER_DIR}"/steps/*.sh; do
  source "$step_file"
done

# ─── Export for step scripts ──────────────────────────────────────────
export CONTAINER_NAME OPENWEBUI_URL OPENWEBUI_TOKEN VERBOSE DRY_RUN
export CREATE_MODEL SETUP_GROUPS INSTALLER_DIR REGOS_CONFIGURE MODULES

# ─── Run ──────────────────────────────────────────────────────────────
START_TIME=$(date +%s)

log_banner

if [[ "$DRY_RUN" == "true" ]]; then
  log_warn "DRY RUN MODE — no changes will be made"
  echo ""
fi

PASSED=0
FAILED=0
SKIPPED=0

run_step() {
  local num="$1" func="$2"
  if [[ -n "$SINGLE_STEP" && "$SINGLE_STEP" != "$num" ]]; then
    ((SKIPPED++))
    return 0
  fi
  if "$func"; then
    ((PASSED++))
  else
    ((FAILED++))
    log_error "Step ${num} failed"
    # Steps 01 and 02 are critical — abort on failure
    if [[ "$num" == "01" || "$num" == "02" ]]; then
      log_error "Critical step failed — aborting"
      return 1
    fi
  fi
  return 0
}

run_step "01" step_01_detect_container || exit 2
run_step "02" step_02_install_deps     || exit 2
run_step "03" step_03_copy_data
run_step "04" step_04_copy_scripts
run_step "05" step_05_register_functions
run_step "06" step_06_create_model
run_step "07" step_07_setup_groups
run_step "08" step_08_verify
run_step "09" step_09_guest_disclaimer
run_step "10" step_10_regos_admin

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

log_summary "$PASSED" "$FAILED" "$SKIPPED" "$DURATION"

if [[ $FAILED -eq 0 ]]; then
  log_success "RegOS installation complete!"
  exit 0
else
  log_warn "Installation completed with ${FAILED} error(s)"
  exit 1
fi
