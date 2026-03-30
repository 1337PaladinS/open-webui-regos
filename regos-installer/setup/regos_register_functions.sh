#!/usr/bin/env bash
# ============================================================================
# RegOS Function Registration — Step 2 of 2
# Registers filter functions and system prompt via Open WebUI REST API.
#
# Usage:
#   chmod +x regos_register_functions.sh
#   ./regos_register_functions.sh
#
# Required environment variables:
#   OPENWEBUI_URL     — Base URL of Open WebUI (e.g., http://localhost:3000)
#   OPENWEBUI_TOKEN   — Admin API token. Two ways to get this:
#
#     Option A — JWT token (recommended):
#       1. Log into Open WebUI in your browser
#       2. Open Developer Tools → Application → Cookies
#       3. Copy the value of the "token" cookie (starts with "eyJ...")
#
#     Option B — API key:
#       1. Open WebUI → Admin → Settings → Account → API Keys
#       2. Generate a new key (starts with "sk-...")
#       Note: API keys may not be available on all Open WebUI versions.
#
# Optional environment variables:
#   NEO4J_PASSWORD    — Neo4j Aura password (set on the GraphRAG filter valve)
#   MODEL_ID          — Base model ID for the RegOS model (default: gpt-4o)
#
# Example:
#   export OPENWEBUI_URL=http://localhost:3000
#   export OPENWEBUI_TOKEN=eyJhbGciOiJIUzI1NiIs...   # JWT from browser cookie
#   export NEO4J_PASSWORD=your_neo4j_password
#   ./regos_register_functions.sh
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ── Check required env vars ──
if [ -z "${OPENWEBUI_URL:-}" ]; then
    echo ""
    echo "  ERROR: OPENWEBUI_URL not set."
    echo "  export OPENWEBUI_URL=http://localhost:3000"
    exit 1
fi

if [ -z "${OPENWEBUI_TOKEN:-}" ]; then
    echo ""
    echo "  ERROR: OPENWEBUI_TOKEN not set."
    echo ""
    echo "  Option A (JWT — recommended):"
    echo "    Log into Open WebUI → Developer Tools → Application → Cookies"
    echo "    Copy the 'token' cookie value (starts with eyJ...)"
    echo ""
    echo "  Option B (API key):"
    echo "    Open WebUI → Admin → Settings → Account → API Keys"
    echo "    Generate a new key (starts with sk-...)"
    echo ""
    echo "  export OPENWEBUI_TOKEN=your-token-here"
    exit 1
fi

BASE_URL="${OPENWEBUI_URL}/api/v1"
AUTH="Authorization: Bearer ${OPENWEBUI_TOKEN}"
CT="Content-Type: application/json"
MODEL_ID="${MODEL_ID:-gpt-4o}"

echo ""
echo "  RegOS Function Registration — Step 2: API Setup"
echo "  ================================================"
echo ""
echo "  Target: ${OPENWEBUI_URL}"
echo "  Model:  ${MODEL_ID}"
echo ""

# ── Helper: API call with error handling ──
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
    fi

    local http_code=$(echo "$response" | tail -1)
    local body=$(echo "$response" | sed '$d')

    if [ "$http_code" -ge 200 ] && [ "$http_code" -lt 300 ]; then
        echo "$body"
        return 0
    else
        echo "  HTTP ${http_code}: ${body}" >&2
        return 1
    fi
}

# ── 1. Test API connectivity ──
echo "  1. Testing API connectivity..."
if api_call GET "/auths/" > /dev/null 2>&1; then
    echo "     [OK] API is reachable and token is valid."
else
    echo "     [FAIL] Cannot connect. Check URL and token."
    exit 1
fi

# ── 2. Register GraphRAG Filter ──
echo ""
echo "  2. Registering GraphRAG Filter (graphrag_filter)..."

GRAPHRAG_CODE=$(python3 -c "
import json, sys
with open('${SCRIPT_DIR}/../functions/graphrag_filter.py') as f:
    print(json.dumps(f.read()))
")

GRAPHRAG_PAYLOAD=$(cat <<JSONEOF
{
    "id": "graphrag_filter",
    "name": "RegOS GraphRAG Filter",
    "type": "filter",
    "content": ${GRAPHRAG_CODE},
    "meta": {
        "description": "Graph-enhanced RAG v0.17.3 for Chapter 24 regulatory queries. FEA schema: document search, entity traversal, concept expansion, and direct search via Neo4j. Confidence scoring, threshold evaluation, escalation, and guardrails. Works with ANY model."
    }
}
JSONEOF
)

# Try create first; if it already exists, update it
if api_call POST "/functions/create" "$GRAPHRAG_PAYLOAD" > /dev/null 2>&1; then
    echo "     [OK] Created graphrag_filter."
else
    echo "     Already exists — updating..."
    if api_call POST "/functions/id/graphrag_filter/update" "$GRAPHRAG_PAYLOAD" > /dev/null 2>&1; then
        echo "     [OK] Updated graphrag_filter."
    else
        echo "     [WARN] Could not create or update. You may need to register it manually."
    fi
fi

# Enable it globally
api_call POST "/functions/id/graphrag_filter/toggle" '{}' > /dev/null 2>&1 || true

# Set Neo4j password valve if provided
if [ -n "${NEO4J_PASSWORD:-}" ]; then
    echo "     Setting Neo4j password valve..."
    VALVE_PAYLOAD=$(cat <<VJSON
{
    "neo4j_password": "${NEO4J_PASSWORD}"
}
VJSON
)
    api_call POST "/functions/id/graphrag_filter/valves/update" "$VALVE_PAYLOAD" > /dev/null 2>&1 && \
        echo "     [OK] Neo4j password configured." || \
        echo "     [WARN] Could not set valve. Set it manually in Admin > Functions > GraphRAG Filter."
fi

# ── 3. Register Audit Logger ──
echo ""
echo "  3. Registering Audit Logger (audit_logger)..."

AUDIT_CODE=$(python3 -c "
import json, sys
with open('${SCRIPT_DIR}/../functions/audit_logger.py') as f:
    print(json.dumps(f.read()))
")

AUDIT_PAYLOAD=$(cat <<JSONEOF
{
    "id": "audit_logger",
    "name": "RegOS Audit Logger",
    "content": ${AUDIT_CODE},
    "meta": {
        "description": "Captures structured audit records for every query — stores query metadata, retrieval context, citations, model info, and timestamps in a dedicated SQLite database."
    }
}
JSONEOF
)

if api_call POST "/functions/create" "$AUDIT_PAYLOAD" > /dev/null 2>&1; then
    echo "     [OK] Created audit_logger."
else
    echo "     Already exists — updating..."
    if api_call POST "/functions/id/audit_logger/update" "$AUDIT_PAYLOAD" > /dev/null 2>&1; then
        echo "     [OK] Updated audit_logger."
    else
        echo "     [WARN] Could not create or update. Register manually."
    fi
fi

# Enable it globally
api_call POST "/functions/id/audit_logger/toggle" '{}' > /dev/null 2>&1 || true

# ── 3b. Register Escalation Action ──
echo ""
echo "  3b. Registering Escalation Action (escalation_action)..."

ESCALATION_CODE=$(python3 -c "
import json, sys
with open('${SCRIPT_DIR}/../functions/escalation_action.py') as f:
    print(json.dumps(f.read()))
")

ESCALATION_PAYLOAD=$(cat <<JSONEOF
{
    "id": "escalation_action",
    "name": "RegOS Manual Escalation",
    "type": "action",
    "content": ${ESCALATION_CODE},
    "meta": {
        "description": "Flag any RegOS response for expert compliance review. Sends case packet to n8n escalation workflow and writes audit trail."
    }
}
JSONEOF
)

if api_call POST "/functions/create" "$ESCALATION_PAYLOAD" > /dev/null 2>&1; then
    echo "     [OK] Created escalation_action."
else
    echo "     Already exists — updating..."
    if api_call POST "/functions/id/escalation_action/update" "$ESCALATION_PAYLOAD" > /dev/null 2>&1; then
        echo "     [OK] Updated escalation_action."
    else
        echo "     [WARN] Could not create or update. Register manually."
    fi
fi

# Enable it globally
api_call POST "/functions/id/escalation_action/toggle" '{}' > /dev/null 2>&1 || true

# Set webhook URL valve if provided
if [ -n "${ESCALATION_WEBHOOK_URL:-}" ]; then
    echo "     Setting escalation webhook URL valve..."
    ESC_VALVE_PAYLOAD=$(cat <<VJSON
{
    "escalation_webhook_url": "${ESCALATION_WEBHOOK_URL}"
}
VJSON
)
    api_call POST "/functions/id/escalation_action/valves/update" "$ESC_VALVE_PAYLOAD" > /dev/null 2>&1 && \
        echo "     [OK] Webhook URL configured." || \
        echo "     [WARN] Could not set valve. Set it manually in Admin > Functions > RegOS Manual Escalation."
fi

# ── 4. Register GraphRAG Pipe ──
echo ""
echo "  4. Registering GraphRAG Pipe (graphrag_pipe)..."

PIPE_CODE=$(python3 -c "
import json, sys
with open('${SCRIPT_DIR}/../functions/graphrag_pipe.py') as f:
    print(json.dumps(f.read()))
")

PIPE_PAYLOAD=$(cat <<JSONEOF
{
    "id": "graphrag_pipe",
    "name": "RegOS GraphRAG Pipe",
    "type": "pipe",
    "content": ${PIPE_CODE},
    "meta": {
        "description": "GraphRAG pipeline model for Chapter 24 regulatory queries. Provides an alternative pipe-based interface to the GraphRAG retrieval engine."
    }
}
JSONEOF
)

if api_call POST "/functions/create" "$PIPE_PAYLOAD" > /dev/null 2>&1; then
    echo "     [OK] Created graphrag_pipe."
else
    echo "     Already exists — updating..."
    if api_call POST "/functions/id/graphrag_pipe/update" "$PIPE_PAYLOAD" > /dev/null 2>&1; then
        echo "     [OK] Updated graphrag_pipe."
    else
        echo "     [WARN] Could not create or update. Register manually."
    fi
fi

# Enable it globally
api_call POST "/functions/id/graphrag_pipe/toggle" '{}' > /dev/null 2>&1 || true

# ── 5. Create/Update RegOS Model with System Prompt ──
echo ""
echo "  4. Creating RegOS model with system prompt..."

SYSTEM_PROMPT=$(python3 -c "
import json
with open('${SCRIPT_DIR}/../prompts/system_prompt.md') as f:
    print(json.dumps(f.read()))
")

MODEL_PAYLOAD=$(cat <<JSONEOF
{
    "id": "regos-compliance-copilot",
    "name": "RegOS Compliance Copilot",
    "base_model_id": "${MODEL_ID}",
    "params": {
        "system": ${SYSTEM_PROMPT},
        "temperature": 0.3
    },
    "meta": {
        "description": "Regulatory compliance copilot for Miami-Dade Chapter 24. Uses GraphRAG + Knowledge Base + threshold evaluation for grounded, cited regulatory analysis.",
        "profile_image_url": "",
        "capabilities": {
            "vision": false,
            "usage": true
        }
    }
}
JSONEOF
)

if api_call POST "/models/create" "$MODEL_PAYLOAD" > /dev/null 2>&1; then
    echo "     [OK] Created model 'regos-compliance-copilot'."
else
    echo "     Already exists — updating..."
    if api_call POST "/models/id/regos-compliance-copilot/update" "$MODEL_PAYLOAD" > /dev/null 2>&1; then
        echo "     [OK] Updated model."
    else
        echo "     [WARN] Could not create or update. Configure manually."
    fi
fi

# ── 6. Summary ──
echo ""
echo "  ================================================"
echo "  Registration complete!"
echo ""
echo "  What was configured:"
echo "    - graphrag_filter (filter function, enabled globally)"
echo "    - audit_logger (filter function, enabled globally)"
echo "    - escalation_action (action function, enabled globally)"
echo "    - graphrag_pipe (pipe function, enabled globally)"
echo "    - regos-compliance-copilot (model with system prompt)"
echo ""
echo "  Remaining manual steps:"
echo "    1. Go to Admin > Functions > graphrag_filter"
echo "       → Verify the Neo4j password valve is set"
echo "       → Toggle 'Global' ON if not already"
echo "    2. Go to Admin > Functions > audit_logger"
echo "       → Toggle 'Global' ON if not already"
echo "    3. Go to Admin > Functions > escalation_action"
echo "       → Set the escalation webhook URL valve (n8n webhook)"
echo "    4. Upload your Knowledge Base documents"
echo "       → Admin > Knowledge > Create Collection"
echo "       → Upload Chapter 24 PDF/DOCX files"
echo "    5. Select 'RegOS Compliance Copilot' as your model in the chat"
echo ""
echo "  Test it:"
echo "    Ask: 'What are the BOD limits for industrial wastewater?'"
echo "    Then: 'My BOD is 45 mg/L, am I compliant?'"
echo ""
