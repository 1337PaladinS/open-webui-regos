# regos-installer

Standalone installer for **RegOS** (Regulatory Compliance Copilot) — deploys onto stock Open WebUI with a single command. No fork required.

RegOS transforms Open WebUI into a regulatory compliance assistant powered by Graph-RAG retrieval, automated threshold evaluation, tamper-evident audit logging, and confidence-scored responses with escalation workflows.

RegOS supports multiple regulatory modules that can be installed independently or together:

- **Chapter 24** — Miami-Dade Environmental Regulations (96 regulatory thresholds, wastewater/stormwater/industrial compliance)
- **Opa-Locka** — City of Opa-Locka Code of Ordinances and Land Development Regulations (municipal code, zoning, ethics, business licensing)

## Quick Start

```bash
git clone <repo-url> regos-installer
cd regos-installer

# One command — clones stock Open WebUI, patches it, builds, and deploys:
./setup.sh --clone --token <your-admin-token>
```

If you don't have a token yet (first-time install):

```bash
# Build first, get token after:
./setup.sh --clone

# Open http://localhost:3000, create admin account, get API token
# Then finish the install:
./setup.sh --source ../open-webui --skip-patch --skip-build --token <your-token>
```

## How It Works

`setup.sh` orchestrates the full deployment pipeline:

1. **Get source** — Clones stock Open WebUI (or uses an existing checkout)
2. **Patch source** — Runs `source-patches/apply-patches.py` to surgically inject RegOS features (admin panel, guest access, disclaimer modal, confidence display) into the source tree
3. **Apply branding** — Copies logo/favicon/splash assets if a `branding/` directory exists
4. **Docker build** — Runs `docker compose up -d --build` to build and deploy
5. **Install neo4j** — Installs the neo4j Python driver inside the container
6. **Run installer** — Executes `install.sh` to register functions, create models, copy data, and configure settings via the Open WebUI REST API

The source patcher is idempotent — safe to re-run on already-patched source.

## What Gets Installed

| Component | Description |
|---|---|
| **graphrag_filter_chapter24** | Graph-RAG filter for Chapter 24 — Miami-Dade environmental regulatory retrieval, threshold evaluation, guardrails |
| **graphrag_filter_opalocka** | Graph-RAG filter for Opa-Locka — municipal code retrieval, role entity traversal, cross-reference expansion |
| **audit_logger** | Tamper-evident audit trail with SHA-256 hashing |
| **threshold_eval** | Standalone threshold evaluation against 96 Chapter 24 limits |
| **regulatory_thresholds.json** | 96 regulatory thresholds from Miami-Dade Chapter 24 |
| **concepts.json** | Knowledge graph ontology definitions |
| **apas_metric_mappings.json** | APAS telemetry sensor-to-regulation mappings |
| **Demo scripts** | Hash verification, record display, tamper simulation |
| **Custom model(s)** | Module-specific models with tailored system prompts (Chapter 24 Copilot, Opa-Locka Copilot, or both) |
| **Guest access mode** | Anonymous guest experience (configurable chat + generation limits, session TTL, locked-down permissions) |
| **Onboarding disclaimer** | One-time service agreement modal for all users on first visit |
| **Admin panel tab** | Top-level RegOS tab in Open WebUI admin panel — configure disclaimer, guest access, and confidence display |

## Requirements

- Docker Desktop (or Docker Engine + Docker Compose)
- `bash`, `curl`, `jq`, `python3`
- `git` (if using `--clone`)
- Admin API token from Open WebUI (for steps 05-10)

### Getting Your Token

Open WebUI → click your profile icon → **Settings** → **Account** → **API Keys** → create a new key.

## setup.sh Usage

```bash
# First-time: clone, patch, build, install everything
./setup.sh --clone --token eyJhbG...

# Use an existing Open WebUI checkout
./setup.sh --source /path/to/open-webui --token eyJhbG...

# Re-run after code changes (skip patch if already applied)
./setup.sh --source ../open-webui --skip-patch --token eyJhbG...

# Patch only (no build, no install)
./setup.sh --source ../open-webui --skip-build --skip-install

# Different container or URL
./setup.sh --source ../open-webui --container my-webui --api-url http://10.0.0.5:3000 --token <jwt>
```

### setup.sh Options

| Option | Description |
|---|---|
| `--source PATH` | Path to existing Open WebUI source tree |
| `--clone` | Clone stock Open WebUI from GitHub |
| `--tag TAG` | Git tag to checkout (default: `v0.8.1`) |
| `--token TOKEN` | Admin API token for installer steps 05-10 |
| `--api-url URL` | Open WebUI API URL (default: `http://localhost:3000`) |
| `--container NAME` | Docker container name (default: `open-webui`) |
| `--project NAME` | Docker Compose project name (controls volume naming) |
| `--skip-patch` | Skip source patching (already patched) |
| `--skip-build` | Skip Docker build (already running) |
| `--skip-install` | Skip installer (functions/model already registered) |

## install.sh Usage (Advanced)

For granular control over individual installer steps:

```bash
# Full install — both modules (requires running container)
./install.sh --token <jwt>

# Install only the Opa-Locka module
./install.sh --modules opalocka --token <jwt>

# Install only Chapter 24
./install.sh --modules chapter24 --token <jwt>

# Install both modules explicitly
./install.sh --modules both --token <jwt>

# Interactive mode — prompts for module selection
./install.sh --interactive --token <jwt>

# Single step only
./install.sh --step 05 --token <jwt>    # Re-register functions only

# Preview mode
./install.sh --dry-run --verbose

# Push default RegOS admin settings
./install.sh --step 10 --configure --token <jwt>
```

### Installation Steps

| Step | What it does |
|---|---|
| 01 | Detect and verify the Open WebUI Docker container |
| 02 | Install `neo4j` Python driver inside the container |
| 03 | Copy data files (thresholds, concepts, mappings) into container |
| 04 | Copy demo/utility scripts into container |
| 05 | Register filter functions via Open WebUI REST API (module-aware) |
| 06 | Create custom model(s) with module-specific system prompts |
| 07 | (Optional) Create user groups |
| 08 | Verify everything installed correctly |
| 09 | Verify guest access mode & onboarding disclaimer deployment |
| 10 | Verify & configure RegOS admin panel settings |

Each step is idempotent — safe to re-run.

## Rebuilding After Source Changes (CRITICAL)

All application data (user accounts, models, API keys, chat history, uploaded files) is stored in a Docker **volume** mounted at `/app/backend/data`. If you detach from the wrong volume, all data is lost.

**ALWAYS use `docker compose` to rebuild.** Never use raw `docker run` for production instances.

### Safe rebuild process

```bash
cd /path/to/open-webui

# 1. Rebuild and restart (data volume is preserved automatically)
docker compose up -d --build

# 2. Verify your data is intact
#    Open http://localhost:3000 — your account, models, keys should all be there

# 3. Install neo4j driver (lost on rebuild since it's in the container, not the volume)
docker exec open-webui pip install neo4j
```

### Why `docker compose` is safe

`docker compose` automatically manages the volume name using the pattern `<project-name>_<volume-name>`. Running `docker compose up -d --build` always reattaches to this same volume, preserving all data.

### What NOT to do

```bash
# DANGEROUS — creates a NEW empty volume called "open-webui", losing all data:
docker run -d -p 3000:8080 --name open-webui -v open-webui:/app/backend/data ...

# DANGEROUS — deletes the data volume permanently:
docker compose down -v

# SAFE alternatives:
docker compose up -d --build     # rebuild + restart, data preserved
docker compose stop              # stop without removing anything
docker compose restart            # restart without rebuilding
```

### If you accidentally used `docker run` with the wrong volume

Your data is still in the original compose volume. To recover:

```bash
# 1. Check what volumes exist
docker volume ls | grep webui

# 2. You should see two volumes:
#    open-webui                        ← empty (created by docker run)
#    <project>_open-webui              ← your actual data

# 3. Stop and remove the bad container
docker stop open-webui && docker rm open-webui

# 4. Restart with docker compose (auto-mounts the correct volume)
cd /path/to/open-webui
docker compose up -d --build

# 5. (Optional) Remove the empty orphan volume
docker volume rm open-webui
```

### Post-rebuild checklist

After every rebuild, run:

```bash
# Re-install neo4j driver (not persisted in volume)
docker exec open-webui pip install neo4j

# Re-run the RegOS installer to verify everything
cd /path/to/regos-installer
./install.sh --token <your-token>
```

## Configuration

Edit `config/install.conf` for persistent settings, or use `.env` for local overrides.

Key settings:

| Variable | Default | Description |
|---|---|---|
| `CONTAINER_NAME` | `open-webui` | Docker container name |
| `OPENWEBUI_URL` | `http://localhost:3000` | API base URL |
| `OPENWEBUI_TOKEN` | — | Required for steps 05-10 |
| `MODULES` | `both` | Regulatory module(s): `chapter24`, `opalocka`, or `both` |
| `CREATE_MODEL` | `true` | Create the custom model(s) |
| `SETUP_GROUPS` | `false` | Create user groups |
| `BASE_MODEL` | `openrouter/google/gemini-2.0-flash-001` | LLM backend |
| `GUEST_MESSAGE_LIMIT` | `10` | Max chats per guest session |
| `REGOS_GUEST_GENERATION_LIMIT` | `50` | Max AI responses per guest session |
| `GUEST_MESSAGE_WINDOW` | `10800` | Guest session TTL in seconds (3 hours) |

## Post-Installation

1. **Set Neo4j credentials**: Admin → Functions → select the installed filter(s) → Valves → enter Neo4j URI + password
2. **Upload Knowledge Base**: Upload regulatory PDF documents to a Knowledge Base in Open WebUI
3. **Assign KB to model**: Edit the RegOS model(s) → connect the Knowledge Base
4. **Configure RegOS settings**: Admin → RegOS → adjust disclaimer, guest access, and confidence display
5. **Test Chapter 24**: Select "RegOS Chapter 24 Copilot" → ask: *"What are the BOD limits for wastewater discharge?"*
6. **Test Opa-Locka**: Select "RegOS Opa-Locka Copilot" → ask: *"What are the requirements for lobbyist registration under Section 2-18?"*

## Graph Data

The 226 MB Neo4j graph export (`chaptor_24_graph.json`) is too large for git. See [docs/GRAPH_SETUP.md](docs/GRAPH_SETUP.md) for instructions on adding it.

## Repo Structure

```
regos-installer/
├── setup.sh                # One-command deployment (clone → patch → build → install)
├── install.sh              # Granular installer (register functions, create models, etc.)
├── Makefile                # make install / make dry-run
├── source-patches/         # Source patcher for stock Open WebUI
│   ├── apply-patches.py    # Surgical Python patcher (7 patch functions)
│   └── new/                # New files copied into source tree
├── branding/               # (Optional) Custom logos, favicons, app name
├── config/                 # Configuration
├── lib/                    # Shared bash utilities
├── steps/                  # Modular install steps (01-10)
├── functions/              # Open WebUI filter functions
├── data/                   # Data files for container
├── scripts/                # Demo & utility scripts
├── prompts/                # System prompt for custom model
├── test-admin-panel.sh     # Quick test for admin panel endpoints
└── docs/                   # Documentation
```

## Version

v1.9.0 — March 2026

## License

Proprietary — APAS Group
