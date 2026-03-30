# RegOS Setup — Fresh Open WebUI Instance

Three scripts to replicate the full RegOS setup on a clean Open WebUI installation.

## What Gets Installed

| Component | Method | Script |
|-----------|--------|--------|
| `regulatory_thresholds.json` | docker cp → `/app/backend/data/` | `regos_backend_setup.sh` |
| `verify_hashes.py` | docker cp → `/tmp/` | `regos_backend_setup.sh` |
| Demo scripts (3 files) | docker cp → `/tmp/` | `regos_backend_setup.sh` |
| `graphrag_filter` v0.17.3 (filter function) | Open WebUI REST API | `regos_register_functions.sh` |
| `audit_logger` (filter function) | Open WebUI REST API | `regos_register_functions.sh` |
| System prompt + model | Open WebUI REST API | `regos_register_functions.sh` |

## Prerequisites

- Docker with `open-webui` container running
- Admin auth token from Open WebUI (see "Getting Your Token" below)
- Neo4j Aura password (for the GraphRAG filter)
- Python 3 on the host machine (used to JSON-escape file contents)

## Getting Your Token

The setup scripts authenticate against the Open WebUI API. You need an admin-level token. There are two ways to get one:

**Option A — JWT token from browser cookie (recommended):**
1. Log into Open WebUI in your browser as an admin
2. Open Developer Tools (F12 or Cmd+Option+I)
3. Go to **Application → Cookies → your Open WebUI URL**
4. Find the cookie named `token` and copy its value
5. It will start with `eyJ...` (this is a JWT)

**Option B — API key from Settings:**
1. Open WebUI → **Admin → Settings → Account → API Keys**
2. Click "Generate New Key"
3. Copy the key (starts with `sk-...`)
4. Note: This option may not be available on all Open WebUI versions

## Quick Start

```bash
cd regos_setup/setup/

# Set required environment variables
export OPENWEBUI_URL=http://localhost:3000
export OPENWEBUI_TOKEN=eyJhbGciOiJIUzI1NiIs...   # JWT from browser cookie
export NEO4J_PASSWORD=your-neo4j-password           # optional, can set in UI
export MODEL_ID=gpt-4o                              # optional, default: gpt-4o

# Option A: Run everything in one go
chmod +x regos_setup.sh
./regos_setup.sh

# Option B: Run steps individually
chmod +x regos_backend_setup.sh regos_register_functions.sh
./regos_backend_setup.sh          # Step 1: data files into Docker
./regos_register_functions.sh      # Step 2: functions + model via API
```

## After Running

1. Go to **Admin → Functions** — verify both filters show as enabled (global)
2. Go to **Admin → Functions → graphrag_filter** — check the Neo4j password valve
3. Upload Chapter 24 documents to a **Knowledge Base collection**
4. Select **"RegOS Compliance Copilot"** as your model in the chat
5. Test with: *"What are the BOD limits for industrial wastewater?"*

## Files Not Covered by Scripts

These are created automatically at runtime:
- `audit.db` — created on first query by the audit logger
- `regos_breaches.db` — created on first threshold evaluation by GraphRAG filter

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "Container not running" | `docker compose up -d` |
| API returns 401 | Token is invalid or expired — get a fresh JWT from browser cookies or generate a new API key |
| Function already exists error | Script auto-falls back to update |
| Neo4j connection fails | Set password in Admin → Functions → graphrag_filter valves |
