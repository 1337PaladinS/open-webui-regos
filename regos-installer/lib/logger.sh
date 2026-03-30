#!/usr/bin/env bash
# logger.sh — Colored logging utilities for regos-installer

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
GRAY='\033[0;90m'
BOLD='\033[1m'
NC='\033[0m'

_log() { local color="$1" label="$2"; shift 2; echo -e "${color}[${label}]${NC} $*"; }

log_info()    { _log "$BLUE"   "INFO"    "$@"; }
log_success() { _log "$GREEN"  "  OK  "  "$@"; }
log_warn()    { _log "$YELLOW" " WARN "  "$@"; }
log_error()   { _log "$RED"    "ERROR"   "$@"; }
log_debug()   { [[ "${VERBOSE:-false}" == "true" ]] && _log "$GRAY" "DEBUG" "$@"; }
log_step()    { echo -e "\n${BOLD}${BLUE}── Step $1: $2 ──${NC}"; }

log_separator() {
  echo -e "${GRAY}────────────────────────────────────────────────${NC}"
}

log_banner() {
  echo -e "${BOLD}${BLUE}"
  echo "  ┌─────────────────────────────────────────┐"
  echo "  │       RegOS Installer v$(cat "${INSTALLER_DIR}/VERSION" 2>/dev/null || echo '1.0.0')            │"
  echo "  │  Regulatory Compliance Copilot Setup     │"
  echo "  └─────────────────────────────────────────┘"
  echo -e "${NC}"
}

log_summary() {
  local passed="$1" failed="$2" skipped="${3:-0}" duration="${4:-?}"
  echo ""
  log_separator
  echo -e "${BOLD}Installation Summary${NC}"
  log_separator
  echo -e "  ${GREEN}Passed:${NC}  $passed"
  echo -e "  ${RED}Failed:${NC}  $failed"
  echo -e "  ${YELLOW}Skipped:${NC} $skipped"
  echo -e "  ${GRAY}Duration:${NC} ${duration}s"
  log_separator
}
