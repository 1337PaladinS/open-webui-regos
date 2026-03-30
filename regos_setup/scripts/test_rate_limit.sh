#!/bin/bash
# ─────────────────────────────────────────────────────────────
# Rate Limit Test Script for RegOS GraphRAG Filter v0.19.0
# ─────────────────────────────────────────────────────────────
# Sends N requests rapidly to the Open WebUI chat completions API.
# The rate limiter should block requests after the configured max
# (default: 30 per 60 seconds).
#
# Usage:
#   bash test_rate_limit.sh [OPENWEBUI_URL] [API_KEY] [NUM_REQUESTS]
#
# Example:
#   bash test_rate_limit.sh http://localhost:3000 sk-your-api-key 35
#
# The API key is your Open WebUI API key (Admin → Settings → Account → API Keys).
# ─────────────────────────────────────────────────────────────

OPENWEBUI_URL="${1:-http://localhost:3000}"
API_KEY="${2:-}"
NUM_REQUESTS="${3:-35}"

if [ -z "$API_KEY" ]; then
    echo "ERROR: API key required."
    echo ""
    echo "Usage: bash test_rate_limit.sh [URL] [API_KEY] [NUM_REQUESTS]"
    echo ""
    echo "Get your API key from Open WebUI:"
    echo "  → Click your profile icon (bottom-left)"
    echo "  → Settings → Account → API Keys → Create new key"
    echo ""
    echo "Example:"
    echo "  bash test_rate_limit.sh http://localhost:3000 sk-abc123 35"
    exit 1
fi

ENDPOINT="${OPENWEBUI_URL}/api/chat/completions"

# ── Model selection ──
# Use 4th argument if provided, otherwise default to better-hardeepai
MODEL="${4:-better-hardeepai}"
echo "Using model: $MODEL"

# Quick sanity check — send one request and print the raw response for debugging
echo "Running sanity check..."
SANITY=$(curl -s -w "\n---HTTP:%{http_code}" -X POST "$ENDPOINT" \
    -H "Authorization: Bearer $API_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"model\":\"$MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"sanity check\"}],\"stream\":false}" 2>/dev/null)
SANITY_CODE=$(echo "$SANITY" | grep "^---HTTP:" | sed 's/---HTTP://')
SANITY_BODY=$(echo "$SANITY" | grep -v "^---HTTP:")
echo "  HTTP: $SANITY_CODE"
echo "  Body (first 200 chars): ${SANITY_BODY:0:200}"

if [ "$SANITY_CODE" = "400" ]; then
    echo ""
    echo "ERROR: Got HTTP 400. The model name '$MODEL' may be wrong."
    echo "Try passing the model as the 4th argument:"
    echo "  bash test_rate_limit.sh URL API_KEY 35 your-model-id"
    echo ""
    echo "Available models:"
    curl -s "${OPENWEBUI_URL}/api/models" \
        -H "Authorization: Bearer $API_KEY" 2>/dev/null \
        | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    models = data.get('data', data) if isinstance(data, dict) else data
    for m in (models if isinstance(models, list) else []):
        print(f\"  - {m.get('id','?')}\")
except:
    print('  (could not parse)')
" 2>/dev/null
    exit 1
fi
echo ""

echo "═══════════════════════════════════════════════════════"
echo "  RegOS Rate Limit Test"
echo "═══════════════════════════════════════════════════════"
echo "  Target:    ${ENDPOINT}"
echo "  Model:     ${MODEL}"
echo "  Requests:  ${NUM_REQUESTS}"
echo "  Expected:  Blocked after request #30 (default limit)"
echo "═══════════════════════════════════════════════════════"
echo ""

BLOCKED=0
ALLOWED=0
FIRST_BLOCK=""

for i in $(seq 1 "$NUM_REQUESTS"); do
    RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$ENDPOINT" \
        -H "Authorization: Bearer $API_KEY" \
        -H "Content-Type: application/json" \
        -d "{\"model\":\"$MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"test query $i\"}],\"stream\":false}" 2>/dev/null)

    HTTP_CODE=$(echo "$RESPONSE" | tail -1)
    BODY=$(echo "$RESPONSE" | sed '$d')

    # Check if rate limited (look for "rate_limit" or "Too Many" in response)
    if echo "$BODY" | grep -qi "rate.limit\|too many requests\|Rate limit exceeded"; then
        STATUS="BLOCKED (rate limited)"
        BLOCKED=$((BLOCKED + 1))
        if [ -z "$FIRST_BLOCK" ]; then
            FIRST_BLOCK=$i
        fi
    elif echo "$BODY" | grep -qi "Security Notice\|injection_detected"; then
        STATUS="BLOCKED (security)"
        BLOCKED=$((BLOCKED + 1))
    elif [ "$HTTP_CODE" = "429" ]; then
        STATUS="BLOCKED (HTTP 429)"
        BLOCKED=$((BLOCKED + 1))
        if [ -z "$FIRST_BLOCK" ]; then
            FIRST_BLOCK=$i
        fi
    else
        STATUS="ALLOWED (HTTP $HTTP_CODE)"
        ALLOWED=$((ALLOWED + 1))
    fi

    # Print progress
    printf "  Request #%-3d → %s\n" "$i" "$STATUS"
done

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  Results"
echo "═══════════════════════════════════════════════════════"
echo "  Total requests:  ${NUM_REQUESTS}"
echo "  Allowed:         ${ALLOWED}"
echo "  Blocked:         ${BLOCKED}"
if [ -n "$FIRST_BLOCK" ]; then
    echo "  First block at:  Request #${FIRST_BLOCK}"
else
    echo "  First block at:  NONE (rate limit did not trigger)"
fi
echo "═══════════════════════════════════════════════════════"

if [ -n "$FIRST_BLOCK" ] && [ "$FIRST_BLOCK" -le 31 ]; then
    echo ""
    echo "  ✅ PASS — Rate limiter kicked in at request #${FIRST_BLOCK}"
elif [ "$BLOCKED" -gt 0 ]; then
    echo ""
    echo "  ⚠️  Rate limiter triggered but later than expected (request #${FIRST_BLOCK})"
else
    echo ""
    echo "  ❌ FAIL — Rate limiter did not trigger in ${NUM_REQUESTS} requests"
    echo "     Check that rate_limit_enabled=True in the GraphRAG filter valves."
fi
