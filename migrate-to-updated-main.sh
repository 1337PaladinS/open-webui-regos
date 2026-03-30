#!/usr/bin/env bash
set -euo pipefail
#
# migrate-to-updated-main.sh
#
# Safely migrates the regos-anmol-dev branch to the CTO's updated origin/main
# without manually resolving hundreds of unrelated-histories conflicts.
#
# Strategy:
#   1. Abort any in-progress merge
#   2. Save RegOS-custom directories/files to a temp location
#   3. Create a new branch from origin/main (updated Open WebUI)
#   4. Copy RegOS-custom work back on top
#   5. Re-apply source patches via apply-patches.py
#   6. Commit everything
#
# Usage:
#   cd /path/to/open-webui-regos
#   chmod +x migrate-to-updated-main.sh
#   ./migrate-to-updated-main.sh
#

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

info()    { echo -e "${BLUE}→${NC} $1"; }
success() { echo -e "${GREEN}✓${NC} $1"; }
warn()    { echo -e "${YELLOW}⚠${NC} $1"; }
fail()    { echo -e "${RED}✗${NC} $1"; }

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="/tmp/regos-migration-backup-$(date +%s)"
NEW_BRANCH="regos-anmol-dev-v2"

echo ""
echo -e "${BOLD}═══════════════════════════════════════════════════════${NC}"
echo -e "  ${BOLD}RegOS Branch Migration — origin/main upgrade${NC}"
echo -e "${BOLD}═══════════════════════════════════════════════════════${NC}"
echo ""
echo "  Repo:        ${REPO_DIR}"
echo "  Backup to:   ${BACKUP_DIR}"
echo "  New branch:  ${NEW_BRANCH}"
echo ""

# ─── Safety checks ──────────────────────────────────────────────
cd "$REPO_DIR"

if [[ ! -d ".git" ]]; then
    fail "Not a git repository. Run this from the repo root."
    exit 1
fi

CURRENT_BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")
info "Current branch: ${CURRENT_BRANCH}"

# ─── Step 0: Abort any in-progress merge ────────────────────────
echo ""
echo -e "${BOLD}Step 0: Abort any in-progress merge${NC}"
if git merge --abort 2>/dev/null; then
    success "Merge aborted"
else
    info "No merge in progress — clean state"
fi

# ─── Step 1: Backup RegOS-custom directories ────────────────────
echo ""
echo -e "${BOLD}Step 1: Backup RegOS-custom work${NC}"
mkdir -p "$BACKUP_DIR"

# Directories (these don't exist in stock Open WebUI)
REGOS_DIRS=(
    "regos_setup"
    "regos-docs"
    "regos-installer"
    "inventory"
    "strategies"
    "APAS-Legal-PDF-Chunking-Dashboard"
    "chunks"
)

for dir in "${REGOS_DIRS[@]}"; do
    if [[ -d "$dir" ]]; then
        cp -R "$dir" "$BACKUP_DIR/"
        success "Backed up ${dir}/ ($(find "$dir" -type f | wc -l | tr -d ' ') files)"
    else
        warn "${dir}/ not found — skipping"
    fi
done

# Root-level RegOS files
REGOS_FILES=(
    "OPERATIONS.md"
    "concepts.json"
    "apas_metric_mappings.json"
    "RegOS_Integration_Package.zip"
    "Opa-locka, FL Code of Ordinances.pdf"
    "test results.docx"
    "docker-compose.yaml"
)

for f in "${REGOS_FILES[@]}"; do
    if [[ -f "$f" ]]; then
        cp "$f" "$BACKUP_DIR/"
        success "Backed up ${f}"
    fi
done

# Custom CSS files
mkdir -p "$BACKUP_DIR/_custom_css"
for css in "static/custom.css" "static/static/custom.css" "backend/open_webui/static/custom.css"; do
    if [[ -f "$css" ]]; then
        mkdir -p "$BACKUP_DIR/_custom_css/$(dirname "$css")"
        cp "$css" "$BACKUP_DIR/_custom_css/$css"
        success "Backed up ${css}"
    fi
done

echo ""
info "Backup complete: ${BACKUP_DIR}"
info "Total backup size: $(du -sh "$BACKUP_DIR" | cut -f1)"

# ─── Step 2: Fetch latest and create new branch ─────────────────
echo ""
echo -e "${BOLD}Step 2: Create new branch from origin/main${NC}"
git fetch origin
success "Fetched origin"

# Check if branch already exists
if git show-ref --verify --quiet "refs/heads/${NEW_BRANCH}" 2>/dev/null; then
    fail "Branch ${NEW_BRANCH} already exists. Delete it first or change NEW_BRANCH in this script."
    exit 1
fi

git checkout -b "$NEW_BRANCH" origin/main
success "Created and switched to ${NEW_BRANCH} (based on origin/main)"

# Show what version of Open WebUI we're now on
LATEST_COMMIT=$(git log --oneline -1)
info "Latest commit on main: ${LATEST_COMMIT}"

# ─── Step 3: Copy RegOS-custom work back ────────────────────────
echo ""
echo -e "${BOLD}Step 3: Restore RegOS-custom work${NC}"

for dir in "${REGOS_DIRS[@]}"; do
    if [[ -d "$BACKUP_DIR/$dir" ]]; then
        cp -R "$BACKUP_DIR/$dir" "$REPO_DIR/"
        success "Restored ${dir}/"
    fi
done

for f in "${REGOS_FILES[@]}"; do
    if [[ -f "$BACKUP_DIR/$f" ]]; then
        cp "$BACKUP_DIR/$f" "$REPO_DIR/"
        success "Restored ${f}"
    fi
done

# Restore custom CSS
if [[ -d "$BACKUP_DIR/_custom_css" ]]; then
    for css in "static/custom.css" "static/static/custom.css" "backend/open_webui/static/custom.css"; do
        if [[ -f "$BACKUP_DIR/_custom_css/$css" ]]; then
            cp "$BACKUP_DIR/_custom_css/$css" "$REPO_DIR/$css"
            success "Restored ${css}"
        fi
    done
fi

# ─── Step 4: Re-apply source patches ────────────────────────────
echo ""
echo -e "${BOLD}Step 4: Re-apply RegOS source patches${NC}"

PATCHER="$REPO_DIR/regos-installer/source-patches/apply-patches.py"
if [[ -f "$PATCHER" ]]; then
    info "Running apply-patches.py..."
    if python3 "$PATCHER" "$REPO_DIR"; then
        success "All source patches applied successfully"
    else
        warn "Some patches failed — this may be due to upstream code changes."
        warn "Check the output above. Failed patches may need manual updates."
        warn "The patcher is idempotent — you can fix and re-run it safely."
    fi
else
    fail "Patcher not found at ${PATCHER}"
    warn "You'll need to re-apply source patches manually."
fi

# ─── Step 5: Stage and show status ──────────────────────────────
echo ""
echo -e "${BOLD}Step 5: Review changes${NC}"

git add -A
echo ""
info "Files staged for commit:"
git diff --cached --stat | tail -5
echo ""
info "Summary:"
echo "  Added:    $(git diff --cached --numstat | wc -l | tr -d ' ') files"
echo "  Branch:   ${NEW_BRANCH}"
echo "  Based on: origin/main"
echo ""

# ─── Step 6: Commit ─────────────────────────────────────────────
echo -e "${BOLD}Step 6: Commit${NC}"

git commit -m "$(cat <<'EOF'
feat: migrate RegOS custom work to updated Open WebUI base

Rebased all RegOS-custom work onto the CTO's updated origin/main
which includes the latest Open WebUI upstream merge.

Custom work preserved:
- regos_setup/ (functions, APIs, data, configs, docs)
- regos-docs/ (all documentation)
- regos-installer/ (10-step installer, source patches, setup scripts)
- inventory/ (manifests, baselines, strategies)
- strategies/ (benchmarking, chunking, integration)
- APAS-Legal-PDF-Chunking-Dashboard/ (full-stack app)
- docker-compose.yaml (Auth0 SSO + n8n service)
- Source patches re-applied via apply-patches.py

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"

success "Committed!"

# ─── Done ────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}═══════════════════════════════════════════════════════${NC}"
echo -e "  ${GREEN}${BOLD}Migration complete!${NC}"
echo -e "${BOLD}═══════════════════════════════════════════════════════${NC}"
echo ""
echo "  New branch: ${NEW_BRANCH}"
echo "  Backup at:  ${BACKUP_DIR}"
echo ""
echo "  Next steps:"
echo "    1. Review: git log --oneline -5"
echo "    2. Test:   docker compose up -d --build"
echo "    3. If happy, rename branches:"
echo "       git branch -m regos-anmol-dev regos-anmol-dev-old"
echo "       git branch -m ${NEW_BRANCH} regos-anmol-dev"
echo "    4. Push:   git push origin regos-anmol-dev --force-with-lease"
echo "    5. Cleanup: rm -rf ${BACKUP_DIR}"
echo ""
