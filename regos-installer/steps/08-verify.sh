#!/usr/bin/env bash
# Step 08: Post-installation verification

step_08_verify() {
  log_step "08" "Verifying installation"

  local passed=0 failed=0

  # 1. Container running
  if docker::container_running "$CONTAINER_NAME"; then
    log_success "Container '${CONTAINER_NAME}' is running"
    ((passed++))
  else
    log_error "Container '${CONTAINER_NAME}' is not running"
    ((failed++))
  fi

  # 2. Data files present
  local data_files=("regulatory_thresholds.json" "concepts.json" "apas_metric_mappings.json")
  local dest="${CONTAINER_DATA_DIR:-/app/backend/data}"
  for f in "${data_files[@]}"; do
    if docker::file_exists "$CONTAINER_NAME" "${dest}/${f}"; then
      log_success "Data file present: ${f}"
      ((passed++))
    else
      log_error "Data file missing: ${dest}/${f}"
      ((failed++))
    fi
  done

  # 3. neo4j driver installed
  if docker::exec_quiet "$CONTAINER_NAME" python3 -c "import neo4j" 2>/dev/null; then
    log_success "neo4j Python driver installed"
    ((passed++))
  else
    log_error "neo4j Python driver not found"
    ((failed++))
  fi

  # 4. Demo scripts present
  local scripts=("verify_hashes.py" "demo_show_records.py" "demo_tamper.py" "demo_reset.py")
  local script_dest="${CONTAINER_SCRIPTS_DIR:-/tmp}"
  for s in "${scripts[@]}"; do
    if docker::file_exists "$CONTAINER_NAME" "${script_dest}/${s}"; then
      log_success "Script present: ${s}"
      ((passed++))
    else
      log_warn "Script missing: ${script_dest}/${s}"
      ((failed++))
    fi
  done

  # 5. API-registered functions (only if token available)
  if [[ -n "${OPENWEBUI_TOKEN:-}" ]]; then
    for func_id in graphrag_filter audit_logger escalation_action graphrag_pipe; do
      if api::function_exists "$func_id"; then
        log_success "Function registered: ${func_id}"
        ((passed++))
      else
        log_error "Function NOT registered: ${func_id}"
        ((failed++))
      fi
    done
  else
    log_info "Skipping function verification (no token)"
  fi

  # Summary
  echo ""
  log_separator
  if [[ $failed -eq 0 ]]; then
    log_success "All ${passed} checks passed!"
  else
    log_warn "${passed} passed, ${failed} failed"
  fi
  log_separator

  echo ""
  log_info "Next steps:"
  echo "  1. Open WebUI → Admin → Functions → Verify all filters/actions are enabled"
  echo "  2. Set Neo4j password in graphrag_filter Valves"
  echo "  3. Set escalation webhook URL in escalation_action Valves (if using n8n)"
  echo "  4. Upload Chapter 24 KB documents (if not already done)"
  echo "  5. Select model: 'RegOS Compliance Copilot' in chat"
  echo "  6. Test: 'What are the BOD limits for wastewater discharge?'"

  [[ $failed -eq 0 ]] && return 0 || return 1
}
