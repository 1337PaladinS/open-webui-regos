# APAS Open WebUI — RunPod Template

Copy-paste config for creating the RunPod template via **Templates → New Template** in the console.

---

## Basic

| Field | Value |
|---|---|
| **Template Name** | `apas-open-webui-prod` |
| **Template Type** | Pod |
| **Container Image** | `ghcr.io/apas-ai/open-webui-regos:apas-prod-dev` |
| **Container Registry Credentials** | `ghcr-apas-readonly` |
| **Container Disk** | `100` GB |
| **Volume Disk** | `200` GB |
| **Volume Mount Path** | `/workspace` |

## Ports

| Field | Value |
|---|---|
| **Expose HTTP Ports** | `8080` |
| **Expose TCP Ports** | `11434` (optional — only if you want to reach bundled Ollama directly) |

## Container start command

```
bash /runpod/start.sh
```

> If RunPod doesn't let you reference a path inside the image, use the Docker `CMD` override instead: `["bash","/runpod/start.sh"]`. The script is at `/runpod/start.sh` inside the image once we bake it in (or mount it — see "Delivering start.sh" below).

## GPU

| Field | Value |
|---|---|
| **GPU Type** | A6000 40 GB, or 2× RTX 4090 |
| **GPU Count** | 1 (A6000) or 2 (4090) |

---

## Environment Variables

Paste the following block into the template's **Environment Variables** editor. Replace `REPLACE_ME` values before saving, or — better — store them in **RunPod Secrets** and reference with `{{ RUNPOD_SECRET_<name> }}`.

### Security & auth
```
WEBUI_SECRET_KEY=REPLACE_ME
WEBUI_AUTH=true
ENABLE_SIGNUP=false
DEFAULT_USER_ROLE=pending
ENABLE_LOGIN_FORM=true
ENABLE_API_KEYS=true
WEBUI_SESSION_COOKIE_SECURE=true
WEBUI_SESSION_COOKIE_SAME_SITE=lax
JWT_EXPIRES_IN=7d
CORS_ALLOW_ORIGIN=REPLACE_ME_WITH_COMMA_SEPARATED_VPN_AND_SERVER_IPS
```

### Telemetry / update popups (kill all phone-home)
```
ENABLE_VERSION_UPDATE_CHECK=false
SCARF_NO_ANALYTICS=true
DO_NOT_TRACK=true
ANONYMIZED_TELEMETRY=false
```

### Feature hygiene
```
ENABLE_COMMUNITY_SHARING=false
ENABLE_MESSAGE_RATING=true
ENABLE_ADMIN_EXPORT=true
ENABLE_ADMIN_CHAT_ACCESS=false
RESET_CONFIG_ON_START=false
```

### LLM backends (all 3 modes supported)
```
ENABLE_OPENAI_API=true
OPENAI_API_BASE_URL=REPLACE_ME
OPENAI_API_KEY=REPLACE_ME

ENABLE_OLLAMA_API=true
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_HOST=0.0.0.0
OLLAMA_MODELS=/workspace/ollama
OLLAMA_KEEP_ALIVE=-1
```

### Persistence & URLs
```
DATA_DIR=/workspace/openwebui/data
WEBUI_URL=REPLACE_ME_WITH_RUNPOD_PROXY_URL
WEBUI_NAME=APAS
```

### Logging & timeouts
```
GLOBAL_LOG_LEVEL=INFO
AIOHTTP_CLIENT_TIMEOUT=300
WEBUI_HOST=0.0.0.0
WEBUI_PORT=8080
```

### OAuth (deferred — leave commented until provider is chosen)
```
# OAUTH_CLIENT_ID=
# OAUTH_CLIENT_SECRET=
# OAUTH_PROVIDER_NAME=
# OPENID_PROVIDER_URL=
# OAUTH_ROLES_CLAIM=https://open-webui/roles
# OAUTH_ALLOWED_ROLES=guest
# OAUTH_ADMIN_ROLES=admin
```

---

## Delivering start.sh

`runpod/start.sh` lives in the repo but is **not yet baked into the image** — the build workflow uses the upstream Dockerfile unmodified. Two options:

### Option A (recommended) — bake it into the image
Add a small APAS-only Dockerfile layer on top of the built image, or extend the workflow to `COPY runpod/start.sh /runpod/start.sh && chmod +x /runpod/start.sh` into the final stage. One-line Dockerfile change, triggers a rebuild.

### Option B — fetch at boot
Leave the image alone; add this to the RunPod template's start command instead:
```
bash -c "curl -fsSL https://raw.githubusercontent.com/APAS-ai/open-webui-regos/regos-anmol-dev/runpod/start.sh -o /tmp/start.sh && bash /tmp/start.sh"
```
Works immediately with the current image but requires a public raw URL. Since the repo is private, you'd need a `?token=` or switch to a deploy key — ugly.

**Pick Option A.** I can add the `COPY` line to the Dockerfile and the workflow will rebuild automatically.

---

## After template is saved

1. **Deploy pod** from the template. Pick the GPU, attach the network volume.
2. **First boot checks:**
   - Pod logs show `[apas-start]` lines
   - `curl http://<proxy>/health` returns 200
   - Login page loads at the proxy URL
3. **Create the admin user** — the first account created becomes admin (since `DEFAULT_USER_ROLE=pending` applies only to subsequent signups, and `ENABLE_SIGNUP=false` blocks public ones, do the first signup via the admin bootstrap flow — see Open WebUI docs).
4. **Test each LLM backend mode** — external OpenAI, bundled Ollama, remote Ollama.
5. **Install graphrag_filter Function** manually via regos-installer (deferred per review).
6. **Swap `WEBUI_URL` and `CORS_ALLOW_ORIGIN`** once Cloudflare custom domain is wired.

---

## CORS allowlist format

`CORS_ALLOW_ORIGIN` takes a comma-separated list of origins. Example (replace with real values):

```
CORS_ALLOW_ORIGIN=https://eqcb.apas.ai,https://apas.ai,http://10.0.0.5:3000,http://10.0.0.6:3000
```

No wildcards, no `*`. Only VPN-internal and our own server origins per review.

---

## Rollback

Edit the pod's image tag in RunPod to the previous `apas-prod-git-<oldsha>`, restart. Volume persists.
