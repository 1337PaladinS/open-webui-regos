#!/usr/bin/env bash
# Step 07: (Optional) Create user groups in Open WebUI

step_07_setup_groups() {
  log_step "07" "Setting up user groups"

  if [[ "${SETUP_GROUPS:-false}" != "true" ]]; then
    log_info "Group setup skipped (SETUP_GROUPS=false)"
    return 0
  fi

  if [[ -z "${OPENWEBUI_TOKEN:-}" ]]; then
    log_warn "OPENWEBUI_TOKEN not set — skipping group setup"
    return 0
  fi

  # Create a tester/compliance group
  local group_name="${GROUP_NAME:-RegOS Testers}"
  local group_desc="Users with access to RegOS Compliance Copilot"

  local payload
  payload=$(python3 -c "
import json
print(json.dumps({
    'name': '$group_name',
    'description': '$group_desc',
    'permissions': {'models': {'regos-compliance-copilot': True}}
}))
")

  log_info "Creating group: ${group_name}..."
  local result
  result=$(api::call POST "/api/v1/groups/create" "$payload" 2>/dev/null)

  if echo "$result" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('id',''))" 2>/dev/null | grep -q .; then
    log_success "Created group: ${group_name}"
  else
    log_warn "Group creation returned unexpected response — may already exist"
    log_debug "Response: ${result:0:200}"
  fi

  # Add tester emails if configured
  if [[ -n "${GROUP_MEMBERS:-}" ]]; then
    log_info "Note: Add members manually via Open WebUI Admin → Users → Groups"
    log_info "Members to add: ${GROUP_MEMBERS}"
  fi

  return 0
}
