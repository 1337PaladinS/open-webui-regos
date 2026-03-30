#!/usr/bin/env bash
# test-admin-panel.sh — Quick test for RegOS Admin Panel endpoints
#
# Usage:
#   ./test-admin-panel.sh <OPENWEBUI_URL> <ADMIN_TOKEN>
#
# Example:
#   ./test-admin-panel.sh http://localhost:3000 eyJhbGciOi...
#
# This script tests:
#   1. GET /configs/regos (admin)
#   2. POST /configs/regos (admin) — set test config
#   3. GET /configs/regos/public (authenticated)
#   4. GET /configs/regos/guest-status (unauthenticated)
#   5. Verify round-trip (set → get → compare)

set -euo pipefail

URL="${1:-http://localhost:3000}"
TOKEN="${2:-}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() { echo -e "${GREEN}✓ PASS${NC}: $1"; }
fail() { echo -e "${RED}✗ FAIL${NC}: $1"; FAILURES=$((FAILURES + 1)); }
info() { echo -e "${YELLOW}→${NC} $1"; }

FAILURES=0

echo "═══════════════════════════════════════════════════════"
echo "  RegOS Admin Panel — Endpoint Tests"
echo "  URL: ${URL}"
echo "═══════════════════════════════════════════════════════"
echo ""

if [[ -z "$TOKEN" ]]; then
  echo "Usage: $0 <OPENWEBUI_URL> <ADMIN_TOKEN>"
  echo ""
  echo "Get your token from:"
  echo "  Open WebUI → Profile → Settings → Account → API Keys"
  exit 1
fi

# ── 1. GET /configs/regos (admin) ──
info "Testing GET /configs/regos (admin)..."
RESPONSE=$(curl -s -w "\n%{http_code}" \
  "${URL}/api/v1/configs/regos" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" 2>/dev/null)

CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [[ "$CODE" == "200" ]]; then
  pass "GET /configs/regos → 200"

  # Verify structure
  SECTIONS=$(echo "$BODY" | python3 -c "
import sys, json
d = json.load(sys.stdin)
sections = []
for s in ['disclaimer', 'guest', 'confidence']:
    if s in d: sections.append(s)
print(','.join(sections))
" 2>/dev/null)

  if [[ "$SECTIONS" == "disclaimer,guest,confidence" ]]; then
    pass "Response has all 3 sections: ${SECTIONS}"
  else
    fail "Missing sections. Got: ${SECTIONS}"
  fi

  echo "  Current config:"
  echo "$BODY" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(json.dumps(d, indent=2))
" 2>/dev/null | head -30
  echo ""
else
  fail "GET /configs/regos → HTTP ${CODE}"
  echo "  Response: ${BODY}"
fi

# ── 2. POST /configs/regos (admin) ──
info "Testing POST /configs/regos (set test config)..."
TEST_CONFIG='{
  "disclaimer": {
    "enabled": true,
    "title": "RegOS Test Disclaimer",
    "body": "**This is a test.** Markdown _works_ here.\n\n- Item 1\n- Item 2",
    "accept_label": "I Accept"
  },
  "guest": {
    "enabled": true,
    "message_limit": 10,
    "generation_limit": 50,
    "session_ttl": 10800,
    "show_button": true
  },
  "confidence": {
    "enabled": true,
    "style": "emoji_blockquote",
    "high_threshold": 70,
    "medium_threshold": 45
  }
}'

POST_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "${URL}/api/v1/configs/regos" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "$TEST_CONFIG" 2>/dev/null)

if [[ "$POST_CODE" == "200" ]]; then
  pass "POST /configs/regos → 200"
else
  fail "POST /configs/regos → HTTP ${POST_CODE}"
fi

# ── 3. Verify round-trip ──
info "Verifying round-trip (read back what we just set)..."
READBACK=$(curl -s \
  "${URL}/api/v1/configs/regos" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" 2>/dev/null)

TITLE=$(echo "$READBACK" | python3 -c "import sys,json; print(json.load(sys.stdin)['disclaimer']['title'])" 2>/dev/null)
if [[ "$TITLE" == "RegOS Test Disclaimer" ]]; then
  pass "Round-trip verified: title matches"
else
  fail "Round-trip failed: expected 'RegOS Test Disclaimer', got '${TITLE}'"
fi

# ── 4. GET /configs/regos/public (authenticated) ──
info "Testing GET /configs/regos/public (authenticated user)..."
PUBLIC_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
  "${URL}/api/v1/configs/regos/public" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" 2>/dev/null)

if [[ "$PUBLIC_CODE" == "200" ]]; then
  pass "GET /configs/regos/public → 200"
else
  fail "GET /configs/regos/public → HTTP ${PUBLIC_CODE}"
fi

# ── 5. GET /configs/regos/guest-status (unauthenticated) ──
info "Testing GET /configs/regos/guest-status (no auth)..."
GUEST_RESPONSE=$(curl -s -w "\n%{http_code}" \
  "${URL}/api/v1/configs/regos/guest-status" \
  -H "Content-Type: application/json" 2>/dev/null)

GUEST_CODE=$(echo "$GUEST_RESPONSE" | tail -1)
GUEST_BODY=$(echo "$GUEST_RESPONSE" | sed '$d')

if [[ "$GUEST_CODE" == "200" ]]; then
  pass "GET /configs/regos/guest-status → 200 (unauthenticated)"

  GUEST_ENABLED=$(echo "$GUEST_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('enabled', 'MISSING'))" 2>/dev/null)
  GUEST_SHOW=$(echo "$GUEST_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('show_button', 'MISSING'))" 2>/dev/null)
  pass "Guest status: enabled=${GUEST_ENABLED}, show_button=${GUEST_SHOW}"
else
  fail "GET /configs/regos/guest-status → HTTP ${GUEST_CODE}"
fi

# ── Summary ──
echo ""
echo "═══════════════════════════════════════════════════════"
if [[ $FAILURES -eq 0 ]]; then
  echo -e "  ${GREEN}All tests passed!${NC}"
else
  echo -e "  ${RED}${FAILURES} test(s) failed${NC}"
fi
echo "═══════════════════════════════════════════════════════"
echo ""
echo "Next steps:"
echo "  1. Open ${URL}/admin/settings/regos in your browser"
echo "  2. Verify the RegOS tab appears with 3 sections"
echo "  3. Toggle settings and verify they persist on reload"
echo ""

exit $FAILURES
