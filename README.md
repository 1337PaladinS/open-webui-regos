# Apas OS

Apas OS is a branded fork of [Open WebUI](https://github.com/open-webui/open-webui) maintained by APAS AI. It provides a self-hosted AI chat interface with custom branding, connecting to LLM backends like Ollama and OpenAI-compatible APIs.

**Upstream version:** Open WebUI v0.8.1

## What's changed from upstream

This fork tracks upstream Open WebUI with the following customizations:

- **App name** changed from "Open WebUI" to "Apas OS" in `backend/open_webui/env.py`
- **All logo and favicon assets** replaced with Apas branding (in `backend/open_webui/static/` and `static/static/`)
- **Ollama service removed** from `docker-compose.yaml` — the app expects an external Ollama instance rather than bundling one
- **NODE_OPTIONS** set to `--max-old-space-size=4096` in the compose file to prevent frontend build OOM errors

Everything else — backend logic, API routes, database schema, frontend components, RAG pipeline — is stock Open WebUI pulled in via regular upstream merges.

## Syncing with upstream

The repo is configured with `open-webui/main` as a remote. Upstream changes are merged in via pull requests (see PRs #1–#10 in the repo history). After each merge, verify that the branding customizations in `env.py` and the static assets haven't been overwritten.

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (or Docker Engine + Docker Compose on Linux)
- An LLM backend — either:
  - [Ollama](https://ollama.com/) running on your host machine, or
  - An OpenAI-compatible API endpoint (OpenAI, Azure OpenAI, LM Studio, Groq, etc.)

## Quick start

1. **Clone the repo:**

```bash
git clone https://github.com/APAS-ai/open-webui-regos.git
cd open-webui-regos
```

2. **Configure the LLM backend.** Edit `docker-compose.yaml` and set `OLLAMA_BASE_URL` based on your setup:

| Setup | Value |
|---|---|
| Ollama running on host (Mac/Windows) | `http://host.docker.internal:11434` |
| Ollama running on host (Linux) | `http://172.17.0.1:11434` |
| OpenAI API only (no Ollama) | Leave blank — configure via the admin UI after first login |

3. **Build and start:**

```bash
docker compose up -d --build
```

The first build takes 10–15 minutes (frontend compilation + ~150 Python packages). Subsequent starts are fast.

4. **Open the app** at [http://localhost:3000](http://localhost:3000).

5. **Create an admin account.** The first user to sign up automatically becomes the administrator.

## Environment variables

Copy `.env.example` to `.env` for local overrides. Key variables:

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://ollama:11434` | URL of your Ollama instance |
| `OPENAI_API_BASE_URL` | (empty) | OpenAI-compatible API endpoint |
| `OPENAI_API_KEY` | (empty) | API key for OpenAI-compatible services |
| `OPEN_WEBUI_PORT` | `3000` | Port exposed on your host |
| `WEBUI_SECRET_KEY` | (empty) | Secret for session signing — auto-generated if blank |
| `WEBUI_NAME` | `Apas OS` | Display name shown in the UI |

## Common operations

**Stop the app:**
```bash
docker compose stop
```

**Restart after code changes:**
```bash
docker compose up -d --build
```

**View logs:**
```bash
docker compose logs -f open-webui
```

**Reset all data** (users, chats, uploads):
```bash
docker compose down -v
```

## Data persistence

All application data (SQLite database, uploaded files, model configs) is stored in the `open-webui` Docker volume, mounted at `/app/backend/data` inside the container. This persists across restarts. Use `docker compose down -v` only if you want to wipe everything.

## GPU support

For NVIDIA GPU acceleration (Linux only):

```bash
docker compose -f docker-compose.gpu.yaml up -d --build
```

For AMD GPUs:

```bash
docker compose -f docker-compose.amdgpu.yaml up -d --build
```

## Project structure

```
├── backend/
│   └── open_webui/
│       ├── main.py            # FastAPI app entry point
│       ├── env.py             # Config & env vars (branding is here)
│       ├── routers/           # 29 API endpoint modules
│       ├── models/            # 24 SQLAlchemy database models
│       ├── migrations/        # Alembic DB migrations
│       └── static/            # Favicon, logo, splash assets
├── src/                       # SvelteKit frontend
│   ├── lib/
│   │   ├── apis/              # Frontend API clients
│   │   ├── components/        # UI components
│   │   └── stores/            # Svelte state stores
│   └── routes/                # Page routes
├── docker-compose.yaml        # Main compose config
├── Dockerfile                 # Multi-stage build (Node + Python)
└── static/                    # Static assets served at root
```

## Upstream documentation

For full feature documentation (RAG, image generation, voice/video, RBAC, LDAP/SSO, etc.), refer to the [Open WebUI docs](https://docs.openwebui.com/).
