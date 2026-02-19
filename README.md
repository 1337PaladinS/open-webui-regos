# Apas OS

Apas OS is APAS AI's self-hosted AI chat platform — a branded fork of [Open WebUI](https://github.com/open-webui/open-webui). It gives your team a ChatGPT-style interface that connects to any LLM backend (Ollama for local models, or OpenAI/Groq/Azure for cloud APIs), with features like RAG, image generation, voice/video, RBAC, and SSO built in.

This repo contains everything you need to build and deploy Apas OS. Pick the setup guide that matches your environment:

**Upstream version:** Open WebUI v0.8.1

---

### Setup guides

| Environment | What it's for | Jump to |
|---|---|---|
| **Local (Mac/Windows)** | Development and testing on your own machine using Docker Desktop | [Quick start](#quick-start) |
| **Local (Linux)** | Self-hosted on a Linux server or VM with Docker Engine | [Quick start](#quick-start) |
| **RunPod (GPU)** | Cloud GPU pod running Ollama for local model inference | [Deploying on RunPod](#deploying-on-runpod) |
| **RunPod (CPU)** | Cloud pod connecting to external APIs (no local models) | [Deploying on RunPod](#deploying-on-runpod) |

---

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

## Deploying on RunPod

RunPod requires a different setup than local Docker Desktop. Below covers both GPU pods (for running Ollama locally) and CPU pods (for connecting to external APIs).

### 1. Create a pod

In the RunPod dashboard, create a new pod. Choose a template with Docker pre-installed (e.g. **RunPod Pytorch** or **RunPod Ubuntu**). Make sure to:

- **Expose HTTP port 3000** — under "Expose HTTP Ports", add `3000`. This gives you a public URL like `https://{pod-id}-3000.proxy.runpod.net`.
- **Set a volume mount** — attach a persistent volume at `/workspace` so your data survives pod restarts.

### 2. Install Docker (if not pre-installed)

Some RunPod templates include Docker, some don't. Check with `docker --version`. If it's missing:

```bash
curl -fsSL https://get.docker.com | sh
```

For GPU pods, also install the NVIDIA Container Toolkit so Docker containers can access the GPU:

```bash
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
apt-get update && apt-get install -y nvidia-container-toolkit
nvidia-ctk runtime configure --runtime=docker
systemctl restart docker
```

Verify GPU access from Docker: `docker run --rm --gpus all nvidia/cuda:12.2.0-base-ubuntu22.04 nvidia-smi`

### 3. Clone and configure

```bash
cd /workspace
git clone https://github.com/APAS-ai/open-webui-regos.git
cd open-webui-regos
cp .env.example .env
```

### 4a. GPU pod with Ollama (local models)

Install Ollama directly on the host (not in Docker — simpler and avoids GPU passthrough issues):

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama serve &
ollama pull llama3.1
```

Then edit `docker-compose.yaml` and set the Ollama URL to the host network:

```yaml
environment:
  - 'OLLAMA_BASE_URL=http://172.17.0.1:11434'
```

Build and start:

```bash
docker compose up -d --build
```

### 4b. CPU pod with external APIs (OpenAI, Groq, etc.)

No Ollama needed. Just build and start:

```bash
docker compose up -d --build
```

After first login, go to **Admin Settings > Connections** and add your API endpoint and key (e.g. OpenAI, Azure OpenAI, Groq).

### 5. Persist data across restarts

By default the Docker volume stores data inside the container's storage, which is **ephemeral on RunPod**. To persist data, bind-mount to `/workspace` instead. Edit `docker-compose.yaml`:

```yaml
volumes:
  - /workspace/open-webui-data:/app/backend/data
```

Remove or comment out the `volumes:` block at the bottom of the file.

### 6. Access the app

Your app will be available at the RunPod proxy URL:

```
https://{pod-id}-3000.proxy.runpod.net
```

Find this URL in the RunPod dashboard under your pod's "Connect" section.

### RunPod troubleshooting

- **"Permission denied" on Docker** — RunPod pods typically run as root, so this shouldn't happen. If it does, run `chmod 666 /var/run/docker.sock`.
- **Build runs out of memory** — pods with < 16GB RAM may struggle with the frontend build. The `NODE_OPTIONS=--max-old-space-size=4096` is already set, but if you're on a low-memory pod, you can pull a pre-built image instead of building locally.
- **Ollama can't see the GPU** — make sure you installed Ollama on the host, not inside Docker. Run `ollama list` to verify it's working.
- **Port not accessible** — confirm port 3000 is listed in "Expose HTTP Ports" in your pod settings. RunPod won't proxy ports that aren't declared.

## Upstream documentation

For full feature documentation (RAG, image generation, voice/video, RBAC, LDAP/SSO, etc.), refer to the [Open WebUI docs](https://docs.openwebui.com/).
