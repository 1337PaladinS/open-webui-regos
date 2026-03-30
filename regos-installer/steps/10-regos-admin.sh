#!/usr/bin/env bash
# Step 10: Verify & Configure RegOS Admin Settings
#
# This step validates that the RegOS admin panel endpoints are deployed
# and optionally pushes initial configuration (disclaimer text, guest
# settings, confidence thresholds) via the API.
#
# Prerequisites:
#   - Docker container running with the rebuilt Open WebUI image
#   - Steps 01-09 already completed
#   - OPENWEBUI_TOKEN set (admin)
#
# What this does:
#   1. Verify /configs/regos endpoint responds (admin)
#   2. Verify /configs/regos/public endpoint responds (authenticated)
#   3. Verify /configs/regos/guest-status endpoint responds (unauthenticated)
#   4. Push initial RegOS config if --configure flag is set
#   5. Verify frontend build contains RegOS admin tab
#   6. Sync confidence thresholds to graphrag_filter valves

step_10_regos_admin() {
  log_step "10" "Verifying RegOS Admin Panel"

  local passed=0 failed=0 skipped=0

  # ── 1. Check API is reachable ──
  if [[ -z "${OPENWEBUI_TOKEN:-}" ]]; then
    log_warn "OPENWEBUI_TOKEN not set — skipping API-based checks"
    skipped=6
  else
    if ! api::health_check "$OPENWEBUI_URL" 2>/dev/null; then
      log_error "Cannot reach Open WebUI API at ${OPENWEBUI_URL}"
      return 1
    fi

    # ── 2. Test admin endpoint: GET /configs/regos ──
    local admin_response admin_code
    admin_response=$(curl -s -w "\n%{http_code}" \
      "${OPENWEBUI_URL}/api/v1/configs/regos" \
      -H "Authorization: Bearer ${OPENWEBUI_TOKEN}" \
      -H "Content-Type: application/json" \
      2>/dev/null)

    admin_code=$(echo "$admin_response" | tail -1)
    local admin_body
    admin_body=$(echo "$admin_response" | sed '$d')

    if [[ "$admin_code" == "200" ]]; then
      log_success "Admin endpoint GET /configs/regos responds (200 OK)"
      ((passed++))

      # Verify response structure
      local has_disclaimer has_guest has_confidence
      has_disclaimer=$(echo "$admin_body" | python3 -c "import sys,json; d=json.load(sys.stdin); print('yes' if 'disclaimer' in d else 'no')" 2>/dev/null)
      has_guest=$(echo "$admin_body" | python3 -c "import sys,json; d=json.load(sys.stdin); print('yes' if 'guest' in d else 'no')" 2>/dev/null)
      has_confidence=$(echo "$admin_body" | python3 -c "import sys,json; d=json.load(sys.stdin); print('yes' if 'confidence' in d else 'no')" 2>/dev/null)

      if [[ "$has_disclaimer" == "yes" && "$has_guest" == "yes" && "$has_confidence" == "yes" ]]; then
        log_success "Response contains all 3 sections: disclaimer, guest, confidence"
        ((passed++))
      else
        log_error "Response missing sections (disclaimer=${has_disclaimer}, guest=${has_guest}, confidence=${has_confidence})"
        ((failed++))
      fi
    else
      log_error "Admin endpoint returned HTTP ${admin_code}"
      ((failed++))
      ((skipped++))
    fi

    # ── 3. Test public endpoint: GET /configs/regos/public ──
    local public_code
    public_code=$(curl -s -o /dev/null -w "%{http_code}" \
      "${OPENWEBUI_URL}/api/v1/configs/regos/public" \
      -H "Authorization: Bearer ${OPENWEBUI_TOKEN}" \
      -H "Content-Type: application/json" \
      2>/dev/null)

    if [[ "$public_code" == "200" ]]; then
      log_success "Public endpoint GET /configs/regos/public responds (200 OK)"
      ((passed++))
    else
      log_error "Public endpoint returned HTTP ${public_code}"
      ((failed++))
    fi

    # ── 4. Test unauthenticated endpoint: GET /configs/regos/guest-status ──
    local guest_status_code guest_status_body
    guest_status_body=$(curl -s -w "\n%{http_code}" \
      "${OPENWEBUI_URL}/api/v1/configs/regos/guest-status" \
      -H "Content-Type: application/json" \
      2>/dev/null)

    guest_status_code=$(echo "$guest_status_body" | tail -1)

    if [[ "$guest_status_code" == "200" ]]; then
      log_success "Guest status endpoint responds (200 OK, unauthenticated)"
      ((passed++))
    else
      log_error "Guest status endpoint returned HTTP ${guest_status_code}"
      ((failed++))
    fi

    # ── 5. Push initial configuration if --configure is set ──
    if [[ "${REGOS_CONFIGURE:-false}" == "true" ]]; then
      log_info "Pushing initial RegOS configuration..."

      local config_payload
      config_payload=$(python3 -c "
import json, os

config = {
    'disclaimer': {
        'enabled': os.environ.get('REGOS_DISCLAIMER_ENABLED', 'true').lower() == 'true',
        'title': os.environ.get('REGOS_DISCLAIMER_TITLE', 'RegOS Compliance Copilot'),
        'body': os.environ.get('REGOS_DISCLAIMER_BODY', ''),
        'accept_label': os.environ.get('REGOS_DISCLAIMER_ACCEPT_LABEL', \"I Understand, Let's Go\"),
    },
    'guest': {
        'enabled': os.environ.get('REGOS_GUEST_ENABLED', 'true').lower() == 'true',
        'message_limit': int(os.environ.get('GUEST_MESSAGE_LIMIT', '10')),
        'generation_limit': int(os.environ.get('REGOS_GUEST_GENERATION_LIMIT', '50')),
        'session_ttl': int(os.environ.get('GUEST_MESSAGE_WINDOW', '10800')),
        'show_button': os.environ.get('REGOS_GUEST_SHOW_BUTTON', 'true').lower() == 'true',
    },
    'confidence': {
        'enabled': os.environ.get('REGOS_CONFIDENCE_ENABLED', 'true').lower() == 'true',
        'style': os.environ.get('REGOS_CONFIDENCE_STYLE', 'emoji_blockquote'),
        'high_threshold': int(os.environ.get('REGOS_CONFIDENCE_HIGH_THRESHOLD', '70')),
        'medium_threshold': int(os.environ.get('REGOS_CONFIDENCE_MEDIUM_THRESHOLD', '45')),
    },
}
print(json.dumps(config))
" 2>/dev/null)

      if [[ -n "$config_payload" ]]; then
        local set_code
        set_code=$(curl -s -o /dev/null -w "%{http_code}" \
          -X POST "${OPENWEBUI_URL}/api/v1/configs/regos" \
          -H "Authorization: Bearer ${OPENWEBUI_TOKEN}" \
          -H "Content-Type: application/json" \
          -d "$config_payload" \
          2>/dev/null)

        if [[ "$set_code" == "200" ]]; then
          log_success "Initial RegOS configuration pushed successfully"
          ((passed++))
        else
          log_error "Failed to push RegOS config (HTTP ${set_code})"
          ((failed++))
        fi
      else
        log_error "Failed to build config payload"
        ((failed++))
      fi
    else
      log_info "Skipping config push (use --configure or REGOS_CONFIGURE=true to push defaults)"
      ((skipped++))
    fi

    # ── 6. Sync confidence thresholds to graphrag_filter valves ──
    if [[ "${REGOS_CONFIGURE:-false}" == "true" ]]; then
      # Admin panel stores percentages (70, 45); filter valves use 0.0-1.0 scale
      local high_pct="${REGOS_CONFIDENCE_HIGH_THRESHOLD:-70}"
      local med_pct="${REGOS_CONFIDENCE_MEDIUM_THRESHOLD:-45}"
      local high_t=$(python3 -c "print(${high_pct} / 100.0)")
      local med_t=$(python3 -c "print(${med_pct} / 100.0)")

      log_info "Syncing confidence thresholds to graphrag_filter valves (HIGH=${high_t}, MEDIUM=${med_t})..."

      # Get current valves
      local valves_response valves_code
      valves_response=$(curl -s -w "\n%{http_code}" \
        "${OPENWEBUI_URL}/api/v1/functions/id/graphrag_filter/valves" \
        -H "Authorization: Bearer ${OPENWEBUI_TOKEN}" \
        -H "Content-Type: application/json" \
        2>/dev/null)

      valves_code=$(echo "$valves_response" | tail -1)

      if [[ "$valves_code" == "200" ]]; then
        local valves_body
        valves_body=$(echo "$valves_response" | sed '$d')

        # Update the threshold valves
        local updated_valves
        updated_valves=$(echo "$valves_body" | python3 -c "
import sys, json
valves = json.load(sys.stdin)
valves['confidence_high_threshold'] = float(sys.argv[1])
valves['confidence_medium_threshold'] = float(sys.argv[2])
print(json.dumps(valves))
" "$high_t" "$med_t" 2>/dev/null)

        if [[ -n "$updated_valves" ]]; then
          local update_code
          update_code=$(curl -s -o /dev/null -w "%{http_code}" \
            -X POST "${OPENWEBUI_URL}/api/v1/functions/id/graphrag_filter/valves/update" \
            -H "Authorization: Bearer ${OPENWEBUI_TOKEN}" \
            -H "Content-Type: application/json" \
            -d "$updated_valves" \
            2>/dev/null)

          if [[ "$update_code" =~ ^2 ]]; then
            log_success "Confidence thresholds synced to graphrag_filter valves"
            ((passed++))
          else
            log_warn "Could not update graphrag_filter valves (HTTP ${update_code})"
            ((skipped++))
          fi
        fi
      else
        log_warn "Could not read graphrag_filter valves (HTTP ${valves_code}) — function may not be registered yet"
        ((skipped++))
      fi
    else
      ((skipped++))
    fi
  fi

  # ── 7. Check frontend build contains RegOS admin tab ──
  log_info "Checking frontend build for RegOS admin tab..."

  if docker::exec_quiet "$CONTAINER_NAME" sh -c 'grep -rl "regos" /app/build/ 2>/dev/null | head -1' 2>/dev/null; then
    log_success "Frontend build contains RegOS admin tab reference"
    ((passed++))
  else
    log_warn "Could not verify RegOS admin tab in frontend build (may need rebuild)"
    ((skipped++))
  fi

  if docker::exec_quiet "$CONTAINER_NAME" sh -c 'grep -rl "configs/regos" /app/build/ 2>/dev/null | head -1' 2>/dev/null; then
    log_success "Frontend build contains RegOS API endpoint reference"
    ((passed++))
  else
    log_warn "Could not verify RegOS API in frontend build (may need rebuild)"
    ((skipped++))
  fi

  # ── Summary ──
  echo ""
  log_separator
  if [[ $failed -eq 0 ]]; then
    log_success "RegOS Admin Panel: ${passed} passed, ${skipped} skipped, 0 failed"
  else
    log_warn "RegOS Admin Panel: ${passed} passed, ${skipped} skipped, ${failed} FAILED"
  fi
  log_separator

  echo ""
  log_info "RegOS Admin Panel details:"
  echo "  - Admin settings: Open WebUI → Admin → Settings → RegOS"
  echo "  - Sections: Onboarding Disclaimer, Guest Access, Confidence Display"
  echo "  - API endpoints:"
  echo "    GET  /api/v1/configs/regos         (admin only)"
  echo "    POST /api/v1/configs/regos         (admin only)"
  echo "    GET  /api/v1/configs/regos/public  (any authenticated user)"
  echo "    GET  /api/v1/configs/regos/guest-status (unauthenticated)"
  echo ""
  log_info "To push default config: ./install.sh --step 10 --configure"

  [[ $failed -eq 0 ]] && return 0 || return 1
}
