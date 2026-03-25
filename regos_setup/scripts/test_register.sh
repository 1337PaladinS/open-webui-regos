#!/usr/bin/env bash
# ============================================================================
# RegOS Test Registration Script
# Registers a dummy filter function to verify the API flow works.
# After testing, it can also clean up by deleting the dummy function.
#
# Usage:
#   export OPENWEBUI_URL=http://localhost:3000
#   export OPENWEBUI_TOKEN=sk-your-admin-api-key
#
#   ./test_register.sh            # Register the dummy filter
#   ./test_register.sh --cleanup  # Delete the dummy filter
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
FUNCTION_ID="regos_test_dummy"

# ── Check env vars ──
if [ -z "${OPENWEBUI_URL:-}" ]; then
    echo ""
    echo "  ERROR: OPENWEBUI_URL not set."
    echo "  export OPENWEBUI_URL=http://localhost:3000"
    exit 1
fi

if [ -z "${OPENWEBUI_TOKEN:-}" ]; then
    echo ""
    echo "  ERROR: OPENWEBUI_TOKEN not set."
    echo "  Get your API key: Admin > Settings > Account > API Keys"
    echo "  export OPENWEBUI_TOKEN=sk-..."
    exit 1
fi

BASE_URL="${OPENWEBUI_URL}/api/v1"
AUTH="Authorization: Bearer ${OPENWEBUI_TOKEN}"
CT="Content-Type: application/json"

# ── Helper ──
api_call() {
    local method="$1"
    local endpoint="$2"
    local data="${3:-}"
    local response

    if [ "$method" = "POST" ]; then
        response=$(curl -s -w "\n%{http_code}" -X POST \
            "${BASE_URL}${endpoint}" \
            -H "${AUTH}" -H "${CT}" \
            -d "${data}")
    elif [ "$method" = "GET" ]; then
        response=$(curl -s -w "\n%{http_code}" \
            "${BASE_URL}${endpoint}" \
            -H "${AUTH}")
    elif [ "$method" = "DELETE" ]; then
        response=$(curl -s -w "\n%{http_code}" -X DELETE \
            "${BASE_URL}${endpoint}" \
            -H "${AUTH}")
    fi

    local http_code=$(echo "$response" | tail -1)
    local body=$(echo "$response" | sed '$d')

    echo "HTTP_CODE:${http_code}"
    echo "BODY:${body}"

    if [ "$http_code" -ge 200 ] && [ "$http_code" -lt 300 ]; then
        return 0
    else
        return 1
    fi
}

echo ""
echo "  ╔═══════════════════════════════════════════════╗"
echo "  ║     RegOS Registration Test                   ║"
echo "  ╚═══════════════════════════════════════════════╝"
echo ""
echo "  Target: ${OPENWEBUI_URL}"
echo ""

# ── Cleanup mode ──
if [ "${1:-}" = "--cleanup" ]; then
    echo "  Cleaning up: Deleting dummy filter '${FUNCTION_ID}'..."
    echo ""
    result=$(api_call DELETE "/functions/id/${FUNCTION_ID}/delete" 2>&1) || true
    http=$(echo "$result" | grep "HTTP_CODE:" | cut -d: -f2)
    body=$(echo "$result" | grep "BODY:" | cut -d: -f2-)

    if [ "$http" = "200" ]; then
        echo "  [OK] Dummy filter deleted successfully."
    else
        echo "  [INFO] HTTP ${http} — filter may not exist or was already deleted."
        echo "  Response: ${body}"
    fi
    echo ""
    exit 0
fi

# ── Step 1: Test connectivity ──
echo "  1. Testing API connectivity..."
result=$(api_call GET "/auths/" 2>&1) || true
http=$(echo "$result" | grep "HTTP_CODE:" | cut -d: -f2)

if [ "$http" = "200" ]; then
    echo "     [OK] API reachable, token is valid."
else
    echo "     [FAIL] HTTP ${http}. Check your URL and token."
    exit 1
fi

# ── Step 2: Register dummy filter ──
echo ""
echo "  2. Registering dummy filter '${FUNCTION_ID}'..."

FILTER_CODE=$(python3 -c "
import json
with open('${SCRIPT_DIR}/test_dummy_filter.py') as f:
    print(json.dumps(f.read()))
")

PAYLOAD=$(cat <<JSONEOF
{
    "id": "${FUNCTION_ID}",
    "name": "RegOS Test Dummy Filter",
    "type": "filter",
    "content": ${FILTER_CODE},
    "meta": {
        "description": "Test filter — prepends [RegOS Test] to responses. Safe to delete."
    }
}
JSONEOF
)

result=$(api_call POST "/functions/create" "$PAYLOAD" 2>&1) || true
http=$(echo "$result" | grep "HTTP_CODE:" | cut -d: -f2)
body=$(echo "$result" | grep "BODY:" | cut -d: -f2-)

if [ "$http" = "200" ] || [ "$http" = "201" ]; then
    echo "     [OK] Created '${FUNCTION_ID}'."
else
    echo "     Create returned HTTP ${http} — trying update..."
    result=$(api_call POST "/functions/id/${FUNCTION_ID}/update" "$PAYLOAD" 2>&1) || true
    http2=$(echo "$result" | grep "HTTP_CODE:" | cut -d: -f2)
    if [ "$http2" = "200" ]; then
        echo "     [OK] Updated '${FUNCTION_ID}'."
    else
        echo "     [FAIL] Could not create or update. HTTP ${http2}"
        echo "     Response: $(echo "$result" | grep "BODY:" | cut -d: -f2-)"
        exit 1
    fi
fi

# ── Step 3: Verify it exists ──
echo ""
echo "  3. Verifying filter was registered..."

result=$(api_call GET "/functions/id/${FUNCTION_ID}" 2>&1) || true
http=$(echo "$result" | grep "HTTP_CODE:" | cut -d: -f2)
body=$(echo "$result" | grep "BODY:" | cut -d: -f2-)

if [ "$http" = "200" ]; then
    echo "     [OK] Filter '${FUNCTION_ID}' found in Open WebUI."
    # Extract the name from the response
    name=$(echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('name','?'))" 2>/dev/null || echo "?")
    echo "     Name: ${name}"
else
    echo "     [WARN] HTTP ${http} — could not verify. Check Admin > Functions."
fi

# ── Step 4: Test valve update ──
echo ""
echo "  4. Testing valve update (changing tag_text)..."

VALVE_PAYLOAD='{"tag_text": "[TEST OK]"}'
result=$(api_call POST "/functions/id/${FUNCTION_ID}/valves/update" "$VALVE_PAYLOAD" 2>&1) || true
http=$(echo "$result" | grep "HTTP_CODE:" | cut -d: -f2)

if [ "$http" = "200" ]; then
    echo "     [OK] Valve 'tag_text' updated to '[TEST OK]'."
else
    echo "     [INFO] HTTP ${http} — valve update may require manual config."
    echo "     This is non-critical; some Open WebUI versions handle valves differently."
fi

# ── Summary ──
echo ""
echo "  ╔═══════════════════════════════════════════════╗"
echo "  ║     Test Complete!                            ║"
echo "  ╚═══════════════════════════════════════════════╝"
echo ""
echo "  What was tested:"
echo "    ✓ API connectivity and authentication"
echo "    ✓ Function creation via POST /functions/create"
echo "    ✓ Function retrieval via GET /functions/id/{id}"
echo "    ✓ Valve update via POST /functions/id/{id}/valves/update"
echo ""
echo "  Next steps:"
echo "    1. Open ${OPENWEBUI_URL} → Admin → Functions"
echo "    2. Look for 'RegOS Test Dummy Filter'"
echo "    3. Enable it globally and send a test message"
echo "    4. The response should be prefixed with [TEST OK]"
echo ""
echo "  Cleanup when done:"
echo "    ./test_register.sh --cleanup"
echo ""
