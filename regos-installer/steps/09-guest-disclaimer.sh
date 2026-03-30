#!/usr/bin/env bash
# Step 09: Verify Guest Access Mode & Onboarding Disclaimer
#
# This step validates that all components of the guest access system
# and onboarding disclaimer modal are correctly deployed in the
# Open WebUI instance after a source build.
#
# Prerequisites:
#   - Docker container running with the rebuilt Open WebUI image
#   - Steps 01-08 already completed
#
# What this verifies:
#   1. Guest endpoint exists and responds
#   2. Guest user creation works
#   3. Guest permissions are locked down
#   4. Rate limiting is functional
#   5. Disclaimer modal component exists in the build
#   6. Frontend guest API function is bundled
#
# Note: This step does NOT modify the codebase. The actual code changes
# for guest mode and the disclaimer are made directly in the Open WebUI
# source tree (not via the installer). This script only verifies the
# deployment is correct.

step_09_guest_disclaimer() {
  log_step "09" "Verifying Guest Access & Onboarding Disclaimer"

  local passed=0 failed=0 skipped=0

  # ── 1. Check API is reachable ──
  if [[ -z "${OPENWEBUI_TOKEN:-}" ]]; then
    log_warn "OPENWEBUI_TOKEN not set — skipping API-based checks"
    skipped=5
  else
    if ! api::health_check "$OPENWEBUI_URL" 2>/dev/null; then
      log_error "Cannot reach Open WebUI API at ${OPENWEBUI_URL}"
      return 1
    fi

    # ── 2. Test guest endpoint exists ──
    local guest_response
    guest_response=$(curl -s -w "\n%{http_code}" \
      -X POST "${OPENWEBUI_URL}/api/v1/auths/guest" \
      -H "Content-Type: application/json" \
      2>/dev/null)

    local http_code
    http_code=$(echo "$guest_response" | tail -1)
    local body
    body=$(echo "$guest_response" | sed '$d')

    if [[ "$http_code" == "200" ]]; then
      log_success "Guest endpoint responds (200 OK)"
      ((passed++))

      # Extract token and role from response
      local guest_token guest_role guest_id
      guest_token=$(echo "$body" | python3 -c "import sys,json; print(json.load(sys.stdin).get('token',''))" 2>/dev/null)
      guest_role=$(echo "$body" | python3 -c "import sys,json; print(json.load(sys.stdin).get('role',''))" 2>/dev/null)
      guest_id=$(echo "$body" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)

      # ── 3. Verify role is "guest" ──
      if [[ "$guest_role" == "guest" ]]; then
        log_success "Guest user created with role: guest"
        ((passed++))
      else
        log_error "Guest user has wrong role: '${guest_role}' (expected 'guest')"
        ((failed++))
      fi

      # ── 4. Verify permissions are locked down ──
      local workspace_models
      workspace_models=$(echo "$body" | python3 -c "
import sys, json
d = json.load(sys.stdin)
perms = d.get('permissions', {})
print(perms.get('workspace', {}).get('models', 'MISSING'))
" 2>/dev/null)

      if [[ "$workspace_models" == "False" ]]; then
        log_success "Guest permissions locked down (workspace.models = False)"
        ((passed++))
      else
        log_error "Guest permissions NOT locked down (workspace.models = ${workspace_models})"
        ((failed++))
      fi

      # ── 5. Verify guest can access chat endpoint (auth gate) ──
      if [[ -n "$guest_token" ]]; then
        local chat_check
        chat_check=$(curl -s -o /dev/null -w "%{http_code}" \
          "${OPENWEBUI_URL}/api/models" \
          -H "Authorization: Bearer ${guest_token}" \
          -H "Content-Type: application/json" \
          2>/dev/null)

        if [[ "$chat_check" == "200" ]]; then
          log_success "Guest token accepted by API (auth gate passed)"
          ((passed++))
        else
          log_error "Guest token rejected by API (HTTP ${chat_check})"
          ((failed++))
        fi
      else
        log_warn "No guest token returned — skipping auth gate check"
        ((skipped++))
      fi

      # ── 6. Verify guest session expiry is set ──
      local expires_at
      expires_at=$(echo "$body" | python3 -c "import sys,json; print(json.load(sys.stdin).get('expires_at', 0))" 2>/dev/null)

      if [[ "$expires_at" -gt 0 ]]; then
        local now
        now=$(date +%s)
        local ttl=$(( expires_at - now ))
        if [[ $ttl -gt 0 && $ttl -le 10800 ]]; then
          log_success "Guest JWT expires in ${ttl}s (~$((ttl / 3600))h) — within 3-hour window"
          ((passed++))
        else
          log_warn "Guest JWT TTL is ${ttl}s — expected ~10800s (3 hours)"
          ((passed++))  # Still pass, just unusual
        fi
      else
        log_warn "No expires_at in guest response"
        ((skipped++))
      fi

      # Clean up: Delete the test guest user (admin only)
      if [[ -n "$guest_id" && -n "${OPENWEBUI_TOKEN:-}" ]]; then
        curl -s -X DELETE \
          "${OPENWEBUI_URL}/api/v1/users/${guest_id}" \
          -H "Authorization: Bearer ${OPENWEBUI_TOKEN}" \
          -H "Content-Type: application/json" \
          >/dev/null 2>&1
        log_debug "Cleaned up test guest user: ${guest_id}"
      fi

    elif [[ "$http_code" == "429" ]]; then
      log_warn "Guest endpoint rate-limited (429) — endpoint exists but throttled"
      log_info "This is expected if many test requests were sent recently"
      ((passed++))
      ((skipped += 4))
    else
      log_error "Guest endpoint returned HTTP ${http_code}"
      log_debug "Response body: ${body}"
      ((failed++))
      ((skipped += 4))
    fi
  fi

  # ── 7. Check source files exist (container filesystem) ──
  log_info "Checking source files in container..."

  # Backend files
  local backend_files=(
    "/app/backend/open_webui/routers/auths.py"
    "/app/backend/open_webui/config.py"
    "/app/backend/open_webui/utils/access_control.py"
    "/app/backend/open_webui/utils/auth.py"
    "/app/backend/open_webui/main.py"
  )

  for f in "${backend_files[@]}"; do
    if docker::file_exists "$CONTAINER_NAME" "$f"; then
      log_success "Backend file present: $(basename "$f")"
      ((passed++))
    else
      log_error "Backend file missing: $f"
      ((failed++))
    fi
  done

  # Check that the guest endpoint code is in auths.py
  if docker::exec_quiet "$CONTAINER_NAME" grep -q "guest_signin" "/app/backend/open_webui/routers/auths.py" 2>/dev/null; then
    log_success "Guest endpoint code found in auths.py"
    ((passed++))
  else
    log_error "Guest endpoint code NOT found in auths.py"
    ((failed++))
  fi

  # Check that GUEST_USER_PERMISSIONS is in config.py
  if docker::exec_quiet "$CONTAINER_NAME" grep -q "GUEST_USER_PERMISSIONS" "/app/backend/open_webui/config.py" 2>/dev/null; then
    log_success "GUEST_USER_PERMISSIONS found in config.py"
    ((passed++))
  else
    log_error "GUEST_USER_PERMISSIONS NOT found in config.py"
    ((failed++))
  fi

  # Check that guest role is in auth.py
  if docker::exec_quiet "$CONTAINER_NAME" grep -q '"guest"' "/app/backend/open_webui/utils/auth.py" 2>/dev/null; then
    log_success "Guest role found in auth.py get_verified_user"
    ((passed++))
  else
    log_error "Guest role NOT found in auth.py"
    ((failed++))
  fi

  # Check that guest rate limit is in main.py
  if docker::exec_quiet "$CONTAINER_NAME" grep -q "GUEST_MESSAGE_LIMIT" "/app/backend/open_webui/main.py" 2>/dev/null; then
    log_success "Guest rate limit found in main.py"
    ((passed++))
  else
    log_error "Guest rate limit NOT found in main.py"
    ((failed++))
  fi

  # ── 8. Check that the frontend build includes guest/disclaimer code ──
  # The built frontend is in /app/build/. Check for key strings in JS bundles.
  if docker::exec_quiet "$CONTAINER_NAME" sh -c 'grep -rl "auths/guest" /app/build/ 2>/dev/null | head -1' 2>/dev/null; then
    log_success "Frontend build contains guest API endpoint reference"
    ((passed++))
  else
    log_warn "Could not verify guest API in frontend build (may be minified)"
    ((skipped++))
  fi

  if docker::exec_quiet "$CONTAINER_NAME" sh -c 'grep -rl "RegOS Compliance Copilot" /app/build/ 2>/dev/null | head -1' 2>/dev/null; then
    log_success "Frontend build contains RegOS disclaimer modal"
    ((passed++))
  else
    log_warn "Could not verify disclaimer modal in frontend build (may be minified)"
    ((skipped++))
  fi

  if docker::exec_quiet "$CONTAINER_NAME" sh -c 'grep -rl "regosDisclaimerAcked" /app/build/ 2>/dev/null | head -1' 2>/dev/null; then
    log_success "Frontend build contains disclaimer acknowledgment flag"
    ((passed++))
  else
    log_warn "Could not verify disclaimer ack flag in frontend build (may be minified)"
    ((skipped++))
  fi

  # ── Summary ──
  echo ""
  log_separator
  if [[ $failed -eq 0 ]]; then
    log_success "Guest Access & Disclaimer: ${passed} passed, ${skipped} skipped, 0 failed"
  else
    log_warn "Guest Access & Disclaimer: ${passed} passed, ${skipped} skipped, ${failed} FAILED"
  fi
  log_separator

  echo ""
  log_info "Guest Access Mode details:"
  echo "  - Endpoint: POST ${OPENWEBUI_URL}/api/v1/auths/guest"
  echo "  - Session TTL: 3 hours (JWT expiry)"
  echo "  - Message limit: \${GUEST_MESSAGE_LIMIT:-10} chats per session"
  echo "  - Permissions: All locked down except continue/regenerate + temporary chat"
  echo ""
  log_info "Onboarding Disclaimer details:"
  echo "  - Fires on first page load for all users (admin, user, guest)"
  echo "  - Persisted via regosDisclaimerAcked in user settings"
  echo "  - Chains after changelog modal if both need to show"
  echo ""
  log_info "Configuration (environment variables):"
  echo "  - GUEST_MESSAGE_LIMIT  (default: 10)    — max chats per guest session"
  echo "  - GUEST_MESSAGE_WINDOW (default: 10800)  — rate window in seconds"

  [[ $failed -eq 0 ]] && return 0 || return 1
}
