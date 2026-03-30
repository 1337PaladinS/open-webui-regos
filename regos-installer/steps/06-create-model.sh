#!/usr/bin/env bash
# Step 06: Create the "RegOS Compliance Copilot" custom model

step_06_create_model() {
  log_step "06" "Creating custom model"

  if [[ "${CREATE_MODEL:-true}" != "true" ]]; then
    log_info "Model creation skipped (CREATE_MODEL=false)"
    return 0
  fi

  if [[ -z "${OPENWEBUI_TOKEN:-}" ]]; then
    log_warn "OPENWEBUI_TOKEN not set — skipping model creation"
    return 0
  fi

  local model_id="${MODEL_ID:-regos-compliance-copilot}"
  local model_name="${MODEL_NAME:-RegOS Compliance Copilot}"
  local base_model="${BASE_MODEL:-openrouter/google/gemini-2.0-flash-001}"

  # Read system prompt
  local prompt_file="${INSTALLER_DIR}/prompts/system_prompt.md"
  local system_prompt=""
  if [[ -f "$prompt_file" ]]; then
    system_prompt=$(cat "$prompt_file")
    log_debug "Loaded system prompt (${#system_prompt} chars)"
  else
    log_warn "System prompt file not found: ${prompt_file}"
  fi

  # Build payload
  local payload
  payload=$(python3 -c "
import json
print(json.dumps({
    'id': '$model_id',
    'name': '$model_name',
    'base_model_id': '$base_model',
    'meta': {
        'description': 'RegOS Regulatory Compliance Copilot — Chapter 24 Miami-Dade',
        'profile_image_url': '',
        'capabilities': {'vision': False}
    },
    'params': {
        'system': '''$(echo "$system_prompt" | sed "s/'/\\\\'/g")'''
    }
}))
" 2>/dev/null)

  if [[ -z "$payload" ]]; then
    log_error "Failed to build model payload"
    return 1
  fi

  # Check if model already exists
  local status
  status=$(api::call_status GET "/api/v1/models/${model_id}")

  if [[ "$status" == "200" ]]; then
    log_info "Model '${model_name}' exists — updating..."
    api::call POST "/api/v1/models/${model_id}/update" "$payload" >/dev/null && \
      log_success "Updated model: ${model_name}" || \
      log_error "Failed to update model"
  else
    log_info "Creating model: ${model_name}..."
    api::call POST "/api/v1/models/create" "$payload" >/dev/null && \
      log_success "Created model: ${model_name}" || \
      log_error "Failed to create model"
  fi

  return 0
}
