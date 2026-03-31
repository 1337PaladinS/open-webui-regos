#!/usr/bin/env bash
# Step 06: Create RegOS custom model(s)
#
# Respects the MODULES variable (chapter24 | opalocka | both) to create
# the appropriate model(s) with the correct system prompt and filter.

step_06_create_model() {
  log_step "06" "Creating custom model(s)"

  if [[ "${CREATE_MODEL:-true}" != "true" ]]; then
    log_info "Model creation skipped (CREATE_MODEL=false)"
    return 0
  fi

  if [[ -z "${OPENWEBUI_TOKEN:-}" ]]; then
    log_warn "OPENWEBUI_TOKEN not set — skipping model creation"
    return 0
  fi

  local base_model="${BASE_MODEL:-openrouter/google/gemini-2.0-flash-001}"
  local created=0 failed=0

  # ── Build list of models to create based on MODULES ──
  # Each entry: model_id|model_name|prompt_file|filter_id|description
  local models=()

  case "${MODULES:-both}" in
    chapter24)
      models+=("regos-chapter24-copilot|RegOS Chapter 24 Copilot|system_prompt_chapter24.md|graphrag_filter_chapter24|RegOS Regulatory Compliance Copilot — Chapter 24 Miami-Dade Environmental")
      ;;
    opalocka)
      models+=("regos-opalocka-copilot|RegOS Opa-Locka Copilot|system_prompt_opalocka.md|graphrag_filter_opalocka|RegOS Municipal Code Assistant — City of Opa-Locka Code of Ordinances")
      ;;
    both|*)
      models+=("regos-chapter24-copilot|RegOS Chapter 24 Copilot|system_prompt_chapter24.md|graphrag_filter_chapter24|RegOS Regulatory Compliance Copilot — Chapter 24 Miami-Dade Environmental")
      models+=("regos-opalocka-copilot|RegOS Opa-Locka Copilot|system_prompt_opalocka.md|graphrag_filter_opalocka|RegOS Municipal Code Assistant — City of Opa-Locka Code of Ordinances")
      ;;
  esac

  for entry in "${models[@]}"; do
    IFS='|' read -r model_id model_name prompt_filename filter_id description <<< "$entry"

    # Read system prompt
    local prompt_file="${INSTALLER_DIR}/prompts/${prompt_filename}"
    local system_prompt=""
    if [[ -f "$prompt_file" ]]; then
      system_prompt=$(cat "$prompt_file")
      log_debug "Loaded system prompt for ${model_name} (${#system_prompt} chars)"
    else
      log_warn "System prompt file not found: ${prompt_file}"
    fi

    # Build payload
    local payload
    payload=$(python3 -c "
import json, sys
prompt = sys.stdin.read()
print(json.dumps({
    'id': '${model_id}',
    'name': '${model_name}',
    'base_model_id': '${base_model}',
    'meta': {
        'description': '${description}',
        'profile_image_url': '',
        'capabilities': {'vision': False}
    },
    'params': {
        'system': prompt
    }
}))
" <<< "$system_prompt" 2>/dev/null)

    if [[ -z "$payload" ]]; then
      log_error "Failed to build model payload for ${model_name}"
      ((failed++))
      continue
    fi

    # Check if model already exists
    local status
    status=$(api::call_status GET "/api/v1/models/${model_id}")

    if [[ "$status" == "200" ]]; then
      log_info "Model '${model_name}' exists — updating..."
      if api::call POST "/api/v1/models/${model_id}/update" "$payload" >/dev/null; then
        log_success "Updated model: ${model_name}"
        ((created++))
      else
        log_error "Failed to update model: ${model_name}"
        ((failed++))
      fi
    else
      log_info "Creating model: ${model_name}..."
      if api::call POST "/api/v1/models/create" "$payload" >/dev/null; then
        log_success "Created model: ${model_name}"
        ((created++))
      else
        log_error "Failed to create model: ${model_name}"
        ((failed++))
      fi
    fi
  done

  log_info "${created} model(s) created/updated, ${failed} failed"
  [[ $failed -eq 0 ]] && return 0 || return 1
}
