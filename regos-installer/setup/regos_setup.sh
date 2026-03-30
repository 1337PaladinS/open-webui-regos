#!/usr/bin/env bash
# ============================================================================
# RegOS Complete Setup Script
# Runs both setup steps in sequence:
#   1. Copy backend data files into the Open WebUI Docker container
#   2. Register filter functions, model, and system prompt via API
#
# Usage:
#   export OPENWEBUI_URL=http://localhost:3000
#   export OPENWEBUI_TOKEN=eyJhbGciOiJIUzI1NiIs...   # JWT from browser cookie (see README)
#   export NEO4J_PASSWORD=your-neo4j-password          # optional
#   export MODEL_ID=gpt-4o                             # optional, default: gpt-4o
#
#   chmod +x regos_setup.sh
#   ./regos_setup.sh
#
# You can also run each step independently:
#   ./regos_backend_setup.sh     # Step 1 only
#   ./regos_register_functions.sh # Step 2 only
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "  ╔═══════════════════════════════════════════════════════╗"
echo "  ║           RegOS — Complete Setup                      ║"
echo "  ╚═══════════════════════════════════════════════════════╝"
echo ""

# ── Step 1: Backend files ──
echo "  Running Step 1: Backend data files..."
echo "  ─────────────────────────────────────"
bash "${SCRIPT_DIR}/regos_backend_setup.sh"

echo ""
echo ""

# ── Step 2: API registration ──
echo "  Running Step 2: API registration..."
echo "  ─────────────────────────────────────"
bash "${SCRIPT_DIR}/regos_register_functions.sh"

echo ""
echo "  ╔═══════════════════════════════════════════════════════╗"
echo "  ║           RegOS Setup Complete!                       ║"
echo "  ╚═══════════════════════════════════════════════════════╝"
echo ""
