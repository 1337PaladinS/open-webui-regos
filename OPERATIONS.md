# RegOS Operations Reference

## Server Details

- **Droplet IP**: 157.245.15.224
- **Open WebUI**: http://localhost:3000 (internal) / https://eqcb.apas.ai (public)
- **Sidecar API**: http://157.245.15.224:8300 (⚠️ no auth/HTTPS — do not share externally)

---

## Sidecar API

### Endpoint

```
POST http://157.245.15.224:8300/api/regos/query
```

> **⚠️ SECURITY WARNING**: This endpoint is currently exposed without authentication or encryption. Do not share this URL outside the team. Treat it as you would a database connection string — it provides direct access to the compliance engine and audit system. HTTPS and API key authentication must be configured before any production or external use.

### Example Request

```bash
curl -X POST http://157.245.15.224:8300/api/regos/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What are the BOD limits for wastewater discharge?"}'
```

### Request Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| question | string | Yes | The regulatory compliance question |
| stream | boolean | No | Enable SSE streaming (default: false) |
| show_reasoning | boolean | No | Include model thinking tokens (default: false) |
| context | string | No | Optional prior context (facility info, etc.) |
| show_trace | boolean | No | Include retrieval trace (default: false) |

### Other Endpoints

- `GET /api/regos/health` — Health check
- `GET /api/regos/info` — Sidecar configuration info

---

## Service Management (systemd)

The sidecar runs as a systemd service: `regos-api`

```bash
# Check status
systemctl status regos-api

# View live logs
journalctl -u regos-api -f

# Restart
systemctl restart regos-api

# Stop
systemctl stop regos-api

# Start
systemctl start regos-api
```

### Service Configuration

File: `/etc/systemd/system/regos-api.service`

```ini
[Unit]
Description=RegOS Sidecar API
After=network.target docker.service

[Service]
Type=simple
WorkingDirectory=/root/regos-installer
Environment=OPENWEBUI_URL=http://localhost:3000
Environment=OPENWEBUI_TOKEN=<your-jwt-token>
ExecStart=/usr/local/bin/uvicorn api.regos_api:app --host 0.0.0.0 --port 8300
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

After editing this file, run: `systemctl daemon-reload && systemctl restart regos-api`

---

## Open WebUI Valve Configuration

After installation, these Valves must be set in Admin → Functions → graphrag_filter:

| Valve | Where to Set | Description |
|-------|-------------|-------------|
| Neo4j password | Admin → Functions → graphrag_filter → Valves | Neo4j database password |
| doc_api_key | Admin → Functions → graphrag_filter → Valves | OpenRouter API key (for document analysis) |

---

## Installer

### Fresh Install (on a new server with Open WebUI already running)

```bash
git clone https://<PAT_TOKEN>@github.com/APAS-ai/regos-installer.git
cd regos-installer
bash install.sh --container open-webui --api-url http://localhost:3000 --token <OPENWEBUI_JWT>
```

### Re-register Functions Only

```bash
cd ~/regos-installer && bash install.sh --step 05 --api-url http://localhost:3000 --token <OPENWEBUI_JWT>
```

### Update Code from GitHub

```bash
cd ~/regos-installer && git pull origin main
bash install.sh --step 05 --api-url http://localhost:3000 --token <OPENWEBUI_JWT>
systemctl restart regos-api
```

---

## Dependencies Installed on Server

| Package | Purpose | Installed Via |
|---------|---------|---------------|
| poppler-utils | pdftoppm — PDF to image conversion | apt (inside Docker container) |
| libreoffice | soffice — Office doc to PDF conversion | apt (inside Docker container + host) |
| python3-pip | pip3 — Python package manager | apt (host) |
| fastapi, uvicorn, aiohttp | Sidecar API runtime | pip3 (host) |
| neo4j (Python driver) | Graph database connectivity | pip (inside Docker container) |

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| API returns connection refused | `systemctl start regos-api` |
| API returns 401 | JWT token expired — regenerate from Open WebUI Settings → Account → API Keys, update service file |
| Functions not registering (Step 05 fails) | Check JWT token validity, check Open WebUI is running on localhost:3000 |
| Document analysis not working | Check doc_api_key Valve is set, check poppler-utils and libreoffice are installed inside the Docker container |
| Neo4j queries failing | Check Neo4j password Valve is set correctly in graphrag_filter |

---

*Last updated: March 2026*
