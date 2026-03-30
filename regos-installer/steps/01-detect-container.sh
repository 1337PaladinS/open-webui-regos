#!/usr/bin/env bash
# Step 01: Detect and verify the Open WebUI Docker container

step_01_detect_container() {
  log_step "01" "Detecting Open WebUI container"

  docker::check_installed || return 1

  local cid
  cid=$(docker::find_container "$CONTAINER_NAME") || return 1

  CONTAINER_ID="$cid"
  local info
  info=$(docker::get_info "$CONTAINER_NAME")
  log_success "Found container: ${CONTAINER_NAME} (${CONTAINER_ID:0:12})"
  log_debug "Container info: ${info}"

  # Verify it's actually Open WebUI
  if docker::exec_quiet "$CONTAINER_NAME" test -d /app/backend 2>/dev/null; then
    log_success "Confirmed: Open WebUI instance"
  else
    log_warn "Container found but /app/backend not detected — may not be Open WebUI"
  fi

  return 0
}
