#!/usr/bin/env bash
# Step 05: Register filter functions via Open WebUI REST API

step_05_register_functions() {
  log_step "05" "Registering filter functions"

  if [[ -z "${OPENWEBUI_TOKEN:-}" ]]; then
    log_error "OPENWEBUI_TOKEN is required for function registration"
    log_info "Get your token from: Open WebUI → Profile → Account → API Keys"
    log_info "Or set it via: export OPENWEBUI_TOKEN=<your-token>"
    return 1
  fi

  # Verify API is reachable
  if ! api::health_check "$OPENWEBUI_URL"; then
    log_error "Cannot reach Open WebUI API at ${OPENWEBUI_URL}"
    return 1
  fi

  local func_dir="${INSTALLER_DIR}/functions"
  local registered=0 failed=0

  # Register each function
  local functions=("graphrag_filter:filter" "audit_logger:filter" "escalation_action:action" "graphrag_pipe:pipe")

  for entry in "${functions[@]}"; do
    local func_id="${entry%%:*}"
    local func_type="${entry##*:}"
    local func_file="${func_dir}/${func_id}.py"

    if [[ ! -f "$func_file" ]]; then
      log_warn "Function file not found: ${func_file} — skipping"
      ((failed++))
      continue
    fi

    if api::register_function "$func_id" "$func_file" "$func_type" >/dev/null; then
      log_success "Registered: ${func_id} (${func_type})"
      ((registered++))
    else
      log_error "Failed to register: ${func_id}"
      ((failed++))
    fi
  done

  log_info "${registered} function(s) registered, ${failed} failed"
  [[ $failed -eq 0 ]] && return 0 || return 1
}
