# Cloudflare Tunnel Runbook — *.apas.ai

> One-time setup guide for routing APAS AI subdomains through Cloudflare Tunnel on RunPod pods.

## Prerequisites

| Requirement | Detail |
|---|---|
| Cloudflare account | Free tier is sufficient |
| `apas.ai` domain | Nameservers pointed to Cloudflare |
| RunPod pod | Running the latest APAS image (with `cloudflared` baked in) |
| SSH access | To the pod (`runpodctl ssh` or web terminal) |

---

## Part A: One-Time Setup (run once, persists forever)

These steps create the tunnel and store credentials in `/workspace/cloudflared/`.
Since `/workspace` persists across pod restarts, you only do this once.

### A1. SSH into the pod

```bash
# Via runpodctl
runpodctl ssh <pod-id>

# Or use the RunPod web terminal
```

### A2. Authenticate cloudflared with your Cloudflare account

```bash
cloudflared tunnel login
```

This prints a URL. Open it in your browser, select the `apas.ai` zone, and authorize.
A `cert.pem` file is saved to `~/.cloudflared/`.

**Move it to persistent storage:**

```bash
mkdir -p /workspace/cloudflared
cp ~/.cloudflared/cert.pem /workspace/cloudflared/cert.pem
```

### A3. Create a named tunnel

```bash
cloudflared tunnel --origincert /workspace/cloudflared/cert.pem \
  create regos-runpod
```

Output:
```
Created tunnel regos-runpod with id xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

**Save the tunnel UUID** — you'll need it for DNS and env vars.

The credentials JSON is auto-saved to `~/.cloudflared/<uuid>.json`.
Move it to persistent storage:

```bash
cp ~/.cloudflared/<uuid>.json /workspace/cloudflared/<uuid>.json
```

### A4. Route DNS to the tunnel

For each subdomain you want to route through this tunnel:

```bash
# Primary RegOS interface
cloudflared tunnel --origincert /workspace/cloudflared/cert.pem \
  route dns regos-runpod regos.apas.ai

# Sidecar API (if using separate subdomain)
cloudflared tunnel --origincert /workspace/cloudflared/cert.pem \
  route dns regos-runpod regos-api.apas.ai
```

This creates CNAME records in Cloudflare DNS pointing each subdomain to `<uuid>.cfargotunnel.com`.

### A5. Set RunPod environment variables

In the RunPod pod template (or pod settings), add:

| Variable | Value | Example |
|---|---|---|
| `CLOUDFLARED_TUNNEL_ID` | Tunnel UUID from step A3 | `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` |
| `CLOUDFLARED_HOSTNAME` | Primary hostname | `regos.apas.ai` |

### A6. Restart the pod

Stop and start the pod. On boot, `start.sh` will:
1. Find `CLOUDFLARED_TUNNEL_ID` is set
2. Locate credentials at `/workspace/cloudflared/<uuid>.json`
3. Generate `config.yml` from the template
4. Launch `cloudflared tunnel run` in the background

---

## Part B: Verification

### B1. Check tunnel is running

```bash
# On the pod
cat /workspace/logs/cloudflared.log

# Should see:
# Connection ... registered connectorID=... location=...
# Connection ... registered connectorID=... location=...
# (4 connections = healthy)
```

### B2. Test from your machine

```bash
# Main interface
curl -sI https://regos.apas.ai | head -5

# Sidecar API health
curl -s https://regos-api.apas.ai/api/regos/health | jq .

# Sidecar API info
curl -s https://regos-api.apas.ai/api/regos/info | jq .
```

### B3. Verify SSL

```bash
echo | openssl s_client -connect regos.apas.ai:443 -servername regos.apas.ai 2>/dev/null | openssl x509 -noout -issuer -dates
```

Should show Cloudflare-issued certificate.

---

## Part C: Adding More Subdomains

Soham's directive: use `*.apas.ai` subdomains for all internal tools.

### To add a new subdomain (e.g., `chunking.apas.ai`):

1. **Route DNS:**
   ```bash
   cloudflared tunnel --origincert /workspace/cloudflared/cert.pem \
     route dns regos-runpod chunking.apas.ai
   ```

2. **Edit the config template** (`runpod/cloudflared-config.yml`) — add an ingress rule:
   ```yaml
   - hostname: chunking.apas.ai
     service: http://localhost:8400
     originRequest:
       disableChunkedEncoding: true
   ```

3. **Push, rebuild, restart** the pod.

### Subdomain strategy

| Subdomain | Service | Port | Auth |
|---|---|---|---|
| `regos.apas.ai` | Open WebUI (RegOS) | 8080 | Built-in login |
| `regos-api.apas.ai` | RegOS Sidecar API | 8300 | Token-based |
| `chunking.apas.ai` | Chunking Dashboard | 8400 | TBD |
| `ingestion.apas.ai` | Future — data ingestion | TBD | Cloudflare Access |
| `billing.apas.ai` | Future — billing portal | TBD | Cloudflare Access |

### Gating with login (Cloudflare Access)

For subdomains that need login protection (per Soham's directive), use Cloudflare Access (free for up to 50 users):

1. Go to Cloudflare Zero Trust dashboard → Access → Applications
2. Add an application for the subdomain
3. Set a policy (e.g., email domain `@regos.ai` or specific emails)
4. Users get a Cloudflare login page before reaching the service

---

## Part D: Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `cloudflared credentials not found` in start.sh log | Credentials JSON missing from `/workspace/cloudflared/` | Re-run Part A steps A2–A3 |
| `CLOUDFLARED_TUNNEL_ID not set` in start.sh log | Env var not configured in RunPod | Add to pod template (step A5) |
| Tunnel connects but site returns 502 | Target service not ready yet | cloudflared starts before Open WebUI; it retries automatically. Wait 30s. |
| SSE responses buffered/delayed | Cloudflare caching | Ensure `disableChunkedEncoding: true` in config + `Cache-Control: no-cache` header on streaming endpoints |
| `ERR Too many connections` | Quick Tunnel limit (200 concurrent) | We use named tunnels — this shouldn't happen. Check config. |

---

## File Locations

| File | Path | Persists? |
|---|---|---|
| cloudflared binary | `/usr/local/bin/cloudflared` | Baked into image |
| Config template | `/runpod/cloudflared-config.yml` | Baked into image |
| Runtime config | `/workspace/cloudflared/config.yml` | Yes (generated on boot) |
| Credentials JSON | `/workspace/cloudflared/<uuid>.json` | Yes |
| Auth cert | `/workspace/cloudflared/cert.pem` | Yes |
| Tunnel logs | `/workspace/logs/cloudflared.log` | Yes |

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `CLOUDFLARED_TUNNEL_ID` | Yes | (none) | Tunnel UUID from `cloudflared tunnel create` |
| `CLOUDFLARED_HOSTNAME` | No | `regos.apas.ai` | Primary hostname for the tunnel |
