#!/usr/bin/env bash
# ============================================================================
# RegOS Backend Setup — Step 1 of 2
# Copies data files and utility scripts into the Open WebUI Docker container.
#
# Usage:
#   chmod +x regos_backend_setup.sh
#   ./regos_backend_setup.sh
#
# Prerequisites:
#   - Docker container named "open-webui" is running
#   - This script is run from the setup/ directory (or adjust SCRIPT_DIR)
# ============================================================================

set -euo pipefail

CONTAINER="open-webui"
DATA_DIR="/app/backend/data"
TMP_DIR="/tmp"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "  RegOS Backend Setup — Step 1: Data Files & Utility Scripts"
echo "  =========================================================="
echo ""

# ── Verify Docker container is running ──
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
    echo "  ERROR: Container '${CONTAINER}' is not running."
    echo "  Start it first: docker compose up -d"
    exit 1
fi
echo "  [OK] Container '${CONTAINER}' is running."

# ── 1. Copy regulatory thresholds JSON ──
echo ""
echo "  1. Copying regulatory_thresholds.json → ${DATA_DIR}/"
docker cp "${SCRIPT_DIR}/../data/regulatory_thresholds.json" \
    "${CONTAINER}:${DATA_DIR}/regulatory_thresholds.json"
echo "     Done."

# ── 2. Copy verification script ──
echo ""
echo "  2. Copying verify_hashes.py → ${TMP_DIR}/"
docker cp "${SCRIPT_DIR}/../scripts/verify_hashes.py" \
    "${CONTAINER}:${TMP_DIR}/verify_hashes.py"
echo "     Done."

# ── 3. Copy demo scripts ──
echo ""
echo "  3. Copying demo scripts → ${TMP_DIR}/"
for script in demo_show_records.py demo_tamper.py demo_reset.py; do
    docker cp "${SCRIPT_DIR}/../scripts/${script}" \
        "${CONTAINER}:${TMP_DIR}/${script}"
    echo "     Copied ${script}"
done

# ── 4. Verify files are in place ──
echo ""
echo "  4. Verifying files inside container..."
echo ""

docker exec "${CONTAINER}" bash -c "
    echo '     Data files:'
    ls -la ${DATA_DIR}/regulatory_thresholds.json 2>/dev/null && echo '     [OK] regulatory_thresholds.json' || echo '     [MISSING] regulatory_thresholds.json'
    echo ''
    echo '     Utility scripts:'
    for f in verify_hashes.py demo_show_records.py demo_tamper.py demo_reset.py; do
        ls ${TMP_DIR}/\$f >/dev/null 2>&1 && echo \"     [OK] \$f\" || echo \"     [MISSING] \$f\"
    done
"

echo ""
echo "  =========================================================="
echo "  Step 1 complete."
echo ""
echo "  Next: Run regos_register_functions.sh to register the filter"
echo "  functions and system prompt via the Open WebUI API."
echo ""
