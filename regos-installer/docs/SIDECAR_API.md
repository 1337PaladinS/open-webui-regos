# RegOS Sidecar API — Complete Reference (v2.0.0)

## Overview

The RegOS Sidecar API is a FastAPI service that sits alongside Open WebUI and provides a single, clean interface for external consumers to query the full RegOS compliance pipeline. Callers POST a question and get back a fully-scored, cited, trace-enabled response — without needing to know about Open WebUI internals, model IDs, filter functions, or the two-step inlet/outlet dance.

**Base path:** `http://<host>:8300`
**Source:** `regos-installer/api/regos_api.py`

---

## Architecture

```
External Consumer
      │
      ▼
┌──────────────┐     ┌───────────────────────────────────────────┐
│  Sidecar API │────▶│              Open WebUI (:8080)           │
│   (:8300)    │     │                                           │
│              │     │  ┌─────────┐   ┌─────┐   ┌────────────┐  │
│  /query ─────┼────▶│  │  Inlet  │──▶│ LLM │──▶│   Outlet   │  │
│              │     │  │ Filters │   │     │   │  Filters   │  │
│  /models ────┼────▶│  │(GraphRAG│   │     │   │(Confidence,│  │
│              │     │  │ context)│   │     │   │ Audit Log) │  │
│  /tools ─────┼────▶│  └─────────┘   └──┬──┘   └────────────┘  │
│              │     │                    │                       │
│              │     │              ┌─────▼─────┐                │
│              │     │              │ MCP Tools  │                │
│              │     │              │ (PumpIQ,   │                │
│              │     │              │  etc.)     │                │
│              │     │              └────────────┘                │
└──────────────┘     └───────────────────────────────────────────┘
```

**Pipeline per request:**

1. Sidecar receives `POST /api/regos/query`
2. Builds the messages array (with optional context preamble)
3. Calls Open WebUI `POST /api/chat/completions` with model ID, messages, and optional `tool_ids`
4. Open WebUI runs **inlet filters** (GraphRAG retrieval, context injection)
5. LLM generates response (with optional MCP tool-calling loop if `tool_ids` provided)
6. Sidecar calls `POST /api/chat/completed` to trigger **outlet filters** (confidence scoring, threshold evaluation, audit logging)
7. Returns the final outlet-processed response to the caller

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENWEBUI_URL` | Yes | `http://localhost:3000` | Base URL of the Open WebUI instance |
| `OPENWEBUI_TOKEN` | Yes | (empty) | Admin API token from Open WebUI (Settings → Account → API Keys) |
| `REGOS_MODEL_ID` | No | `better-hardeepai` | Default model ID when caller doesn't specify one |
| `REGOS_API_PORT` | No | `8300` | Port the sidecar listens on |
| `REGOS_DEFAULT_STREAM` | No | `false` | Default streaming mode |

---

## Endpoints

### POST /api/regos/query

The primary endpoint. Sends a question through the full RegOS pipeline and returns a compliance-scored response.

#### Request Body

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `question` | string | **Yes** | — | The regulatory compliance question |
| `model` | string | No | `REGOS_MODEL_ID` env var | Model ID to use. Use `GET /api/regos/models` to discover available models. |
| `stream` | boolean | No | `false` | Enable Server-Sent Events (SSE) streaming |
| `show_reasoning` | boolean | No | `false` | Include reasoning/thinking tokens in the response |
| `context` | string | No | `null` | Optional prior context (e.g., facility info, permit number) |
| `show_trace` | boolean | No | `false` | Include retrieval trace in the response |
| `conversation_id` | string | No | `null` | Continue an existing conversation (maps to Open WebUI chat_id) |
| `messages` | array | No | `null` | Full message history for advanced multi-turn usage (overrides `question` + `context`) |
| `tool_ids` | array[string] | No | `null` | Tool IDs to make available to the model. See `GET /api/regos/tools`. |

#### Response (non-streaming)

```json
{
  "content": "Based on Section 24-42.3(b) of the Miami-Dade County Code...\n\n**Confidence: HIGH**",
  "reasoning": null,
  "model": "openrouter/nvidia/llama-3.1-nemotron-70b-instruct",
  "confidence": "HIGH",
  "usage": {
    "prompt_tokens": 4521,
    "completion_tokens": 387,
    "total_tokens": 4908
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `content` | string | Full response including citations (`[G1]`, `[G2]`) and confidence band |
| `reasoning` | string or null | Model's reasoning/thinking tokens (only if `show_reasoning: true` and the provider exposes them) |
| `model` | string | Actual model ID used (resolved base model) |
| `confidence` | string or null | Extracted confidence band: `HIGH`, `MEDIUM`, or `LOW` |
| `usage` | object or null | Token usage statistics from the LLM provider |

#### Response (streaming)

When `stream: true`, the endpoint returns an SSE stream. Each event is a JSON chunk following the OpenAI streaming format:

```
data: {"choices":[{"delta":{"content":"Based on"},"finish_reason":null}]}

data: {"choices":[{"delta":{"content":" Section 24-42"},"finish_reason":null}]}

...

data: [DONE]
```

**Reasoning markers** (when `show_reasoning: true`):

```
data: {"choices":[{"delta":{"role":"reasoning_start"},"finish_reason":null}]}

data: {"choices":[{"delta":{"reasoning_content":"Let me analyze..."},"finish_reason":null}]}

data: {"choices":[{"delta":{"role":"reasoning_end"},"finish_reason":null}]}

data: {"choices":[{"delta":{"content":"Based on my analysis..."},"finish_reason":null}]}
```

Clients can use the `reasoning_start` / `reasoning_end` markers to toggle a "thinking" UI state.

---

### GET /api/regos/models

Lists all **custom models** defined in the Open WebUI instance. These are models created via the admin panel or the RegOS installer — not raw base models like `gpt-4o` or `llama3:latest`. Each custom model wraps a base model with a system prompt, filter functions, and parameter overrides.

#### Response

```json
[
  {
    "id": "regos-chapter24-copilot",
    "name": "RegOS Chapter 24 Copilot",
    "description": "Miami-Dade County Chapter 24 Environmental Protection compliance assistant",
    "base_model_id": "openrouter/nvidia/llama-3.1-nemotron-70b-instruct",
    "is_active": true,
    "tags": [{"name": "compliance"}, {"name": "chapter24"}]
  },
  {
    "id": "regos-opalocka-copilot",
    "name": "RegOS Opa-Locka Copilot",
    "description": "City of Opa-Locka Code of Ordinances assistant",
    "base_model_id": "openrouter/nvidia/llama-3.1-nemotron-70b-instruct",
    "is_active": true,
    "tags": [{"name": "compliance"}, {"name": "opalocka"}]
  },
  {
    "id": "regos-miami-copilot",
    "name": "RegOS Miami Copilot",
    "description": "City of Miami municipal code compliance assistant",
    "base_model_id": "openrouter/nvidia/llama-3.1-nemotron-70b-instruct",
    "is_active": true,
    "tags": [{"name": "compliance"}, {"name": "miami"}]
  }
]
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Model ID — use this as the `model` parameter in `/api/regos/query` |
| `name` | string | Human-readable display name |
| `description` | string or null | Model description |
| `base_model_id` | string | Underlying LLM provider model (e.g., OpenRouter, Ollama) |
| `is_active` | boolean | Whether the model is currently enabled |
| `tags` | array or null | Categorisation tags |

---

### GET /api/regos/tools

Lists all tools available in the Open WebUI instance, including MCP server tools, OpenAPI server tools, and user-defined Python tool functions.

#### Response

```json
[
  {
    "id": "server:mcp:pumpiq",
    "name": "PumpIQ",
    "type": "mcp",
    "description": "Water infrastructure monitoring — NOAA weather, SFWMD hydrology, pump station data"
  },
  {
    "id": "web_search",
    "name": "Web Search",
    "type": "function",
    "description": "Search the web for current information"
  }
]
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Tool ID — use this in the `tool_ids` array of `/api/regos/query` |
| `name` | string | Human-readable tool name |
| `type` | string | Tool type: `function` (Python tool), `mcp` (MCP server), `openapi` (OpenAPI server) |
| `description` | string or null | What the tool does |

**Tool ID conventions:**

- `server:mcp:<server_id>` — MCP protocol servers (e.g., PumpIQ)
- `server:<server_id>` — OpenAPI tool servers
- `<tool_id>` — User-defined Python tool functions

---

### GET /api/regos/health

Returns the sidecar's connectivity status with Open WebUI.

```json
{"status": "healthy", "openwebui": "connected", "default_model": "regos-chapter24-copilot"}
```

Possible `status` values: `healthy`, `degraded` (Open WebUI returned non-200), `unhealthy` (connection failed).

---

### GET /api/regos/info

Returns the sidecar's configuration and available endpoints.

```json
{
  "version": "2.0.0",
  "default_model": "regos-chapter24-copilot",
  "openwebui_url": "http://localhost:8080",
  "streaming_supported": true,
  "reasoning_supported": true,
  "tool_calling_supported": true,
  "endpoints": {
    "query": "POST /api/regos/query",
    "models": "GET /api/regos/models",
    "tools": "GET /api/regos/tools",
    "health": "GET /api/regos/health",
    "info": "GET /api/regos/info"
  }
}
```

---

## Usage Examples

### Basic query (default model)

```bash
curl -X POST http://localhost:8300/api/regos/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What are the BOD limits for wastewater discharge?"}'
```

### Query with specific model

```bash
curl -X POST http://localhost:8300/api/regos/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What are the setback requirements for new construction?",
    "model": "regos-miami-copilot"
  }'
```

### Query with MCP tools

```bash
curl -X POST http://localhost:8300/api/regos/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What is the current flow rate at the main pump station and does it comply with permit limits?",
    "model": "regos-opalocka-copilot",
    "tool_ids": ["server:mcp:pumpiq"]
  }'
```

### Streaming response

```bash
curl -N -X POST http://localhost:8300/api/regos/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Summarise the environmental protection ordinances",
    "model": "regos-chapter24-copilot",
    "stream": true
  }'
```

### Streaming with reasoning tokens

```bash
curl -N -X POST http://localhost:8300/api/regos/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What are the BOD limits?",
    "stream": true,
    "show_reasoning": true
  }'
```

### With facility context

```bash
curl -X POST http://localhost:8300/api/regos/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Are we in compliance?",
    "context": "Facility: North District WWTP. Permit: FLA123456. Current BOD discharge: 18 mg/L. Flow: 4.2 MGD.",
    "model": "regos-chapter24-copilot"
  }'
```

### Multi-turn conversation

```bash
# First message
curl -X POST http://localhost:8300/api/regos/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What are the discharge limits for BOD?",
    "conversation_id": "session-001"
  }'

# Follow-up using full message history
curl -X POST http://localhost:8300/api/regos/query \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "What are the discharge limits for BOD?"},
      {"role": "assistant", "content": "According to Section 24-42.3(b)..."},
      {"role": "user", "content": "What about TSS?"}
    ],
    "conversation_id": "session-001"
  }'
```

### List available models

```bash
curl http://localhost:8300/api/regos/models
```

### List available tools

```bash
curl http://localhost:8300/api/regos/tools
```

### Health check

```bash
curl http://localhost:8300/api/regos/health
```

---

## MCP Tool Calling — How It Works

When you pass `tool_ids` in a query, the sidecar forwards them to Open WebUI's `/api/chat/completions` endpoint. Open WebUI's middleware then:

1. **Resolves tools**: For each tool ID, looks up the tool definition (Python function, MCP server connection, or OpenAPI spec).
2. **Connects to MCP servers**: For `server:mcp:*` IDs, establishes a connection to the MCP server, authenticates (bearer token, OAuth 2.1, etc.), and retrieves the tool spec (function names, parameter schemas).
3. **Injects tool definitions**: Adds the resolved tool specs to the LLM request as OpenAI-compatible function definitions.
4. **Executes tool calls**: When the LLM returns a `tool_calls` response, the middleware executes each tool call server-side (calls the MCP server's `call_tool` method or runs the Python function), then feeds the results back to the LLM for a final response.
5. **Returns completed response**: The final LLM response (incorporating tool results) is returned to the sidecar.

**Requirements for tool calling to work:**

- The model must support function calling. Set `function_calling: native` in the model's parameters (Admin → Models → Edit → Advanced Params) for best results.
- The MCP server must be registered in Open WebUI (Admin → Settings → Tools → Tool Servers).
- The API token used by the sidecar must have access to the tool.

**Supported tool types:**

| Type | ID Format | Example | Execution |
|------|-----------|---------|-----------|
| MCP Server | `server:mcp:<id>` | `server:mcp:pumpiq` | Server-side via MCP protocol |
| OpenAPI Server | `server:<id>` | `server:weather-api` | Server-side via HTTP |
| Python Function | `<tool_id>` | `web_search` | Server-side in Open WebUI |

---

## Deployment

### RunPod (Docker image)

The sidecar is baked into the APAS Open WebUI Docker image. It launches automatically on boot via `runpod/start.sh`.

**Relevant Dockerfile sections:**

```dockerfile
# Copy sidecar API files
COPY --chown=$UID:$GID ./regos-installer/api /opt/regos-api/api

# Install dependencies
RUN pip3 install --no-cache-dir aiohttp

# Expose port
EXPOSE 8080 8001 8300 22
```

**start.sh launch block:**

```bash
if [ -f /opt/regos-api/api/regos_api.py ]; then
  OPENWEBUI_URL="http://localhost:8080" \
  OPENWEBUI_TOKEN="${OPENWEBUI_TOKEN:-}" \
  REGOS_MODEL_ID="${REGOS_MODEL_ID:-regos-chapter24-copilot}" \
  REGOS_API_PORT="8300" \
  nohup python3 -m uvicorn api.regos_api:app \
    --host 0.0.0.0 --port 8300 --app-dir /opt/regos-api \
    >>"${LOGS_DIR}/regos-api.log" 2>&1 &
fi
```

**RunPod environment variables to set:**

- `OPENWEBUI_TOKEN` — Your Open WebUI admin API token
- `REGOS_MODEL_ID` — Default model (e.g., `regos-chapter24-copilot`)

**Logs:** `tail -f /workspace/logs/regos-api.log`

### Bare Metal / VPS (systemd)

```ini
[Unit]
Description=RegOS Sidecar API
After=network.target docker.service

[Service]
Type=simple
WorkingDirectory=/root/regos-installer
Environment=OPENWEBUI_URL=http://localhost:3000
Environment=OPENWEBUI_TOKEN=<your-jwt-token>
Environment=REGOS_MODEL_ID=regos-chapter24-copilot
ExecStart=/usr/local/bin/uvicorn api.regos_api:app --host 0.0.0.0 --port 8300
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable regos-api
systemctl start regos-api
journalctl -u regos-api -f
```

---

## Audit Tagging

All API calls are tagged with a `regos-api:` prefix in the session ID, allowing audit logs to distinguish between browser UI queries and sidecar API queries:

- **Browser UI**: `session_id = "<uuid>"`
- **Sidecar API**: `session_id = "regos-api:<uuid>"`

This flows through to the outlet filters (confidence scoring, audit logger) so you can filter audit records by source.

---

## Security Considerations

The sidecar API currently has **no built-in authentication or rate limiting**. All security is delegated to the `OPENWEBUI_TOKEN` it holds internally.

**Before production/external use, you must:**

1. **Add API key authentication** — either at the sidecar level (middleware) or via a reverse proxy (nginx, Caddy, Cloudflare Tunnel).
2. **Enable HTTPS** — the sidecar serves plain HTTP. Terminate TLS at a reverse proxy or load balancer.
3. **Restrict network access** — on RunPod, only expose port 8300 to trusted IPs. On bare metal, use firewall rules.
4. **Rotate the Open WebUI token** — if the token is compromised, an attacker has full admin access to Open WebUI through the sidecar.

---

## Companion APIs

The RegOS sidecar runs alongside these other services:

| Service | Port | Source | Purpose |
|---------|------|--------|---------|
| Open WebUI | 8080 | upstream | Chat UI + API |
| PumpIQ MCP | 8001 | `pumpiq-mcp-server/` | Water infrastructure data (NOAA, SFWMD, SCADA) |
| RegOS Sidecar | 8300 | `regos-installer/api/regos_api.py` | External query proxy |
| APAS Bridge | (internal) | `regos-installer/api/apas_bridge.py` | SCADA telemetry polling |
| Breach API | (internal) | `regos-installer/api/breach_api.py` | Compliance breach database |
| SCADA Stream | (internal) | `regos-installer/api/scada_stream.py` | Real-time SCADA WebSocket/SSE |

---

## Changelog

### v2.0.0 (April 2026)

- **Per-request model selection** — New `model` field in query requests. Callers can target any custom model without changing the server default.
- **Custom models endpoint** — `GET /api/regos/models` lists all custom models (those with a base_model_id) defined in the Open WebUI instance.
- **MCP tool calling** — New `tool_ids` field in query requests. Passes tool IDs through to Open WebUI's middleware, which resolves MCP servers, connects, and executes the full tool-calling loop server-side.
- **Tools endpoint** — `GET /api/regos/tools` lists all available tools (MCP servers, OpenAPI servers, Python tool functions).
- **Version bumped** to 2.0.0.

### v1.1.0 (March 2026)

- **Streaming support** — SSE streaming via `stream: true`.
- **Reasoning token forwarding** — Supports OpenRouter/DeepSeek (`reasoning_content`), Anthropic (`thinking`), and generic (`reasoning`) formats. Emits `reasoning_start`/`reasoning_end` markers for client UI state.
- **Outlet filter integration** — After LLM response, calls `/api/chat/completed` to trigger confidence scoring, threshold evaluation, and audit logging. Appends outlet additions to the streamed response.
- **Audit tagging** — `regos-api:` prefix on session IDs.

### v1.0.0 (February 2026)

- Initial release. Blocking query endpoint, health check, info endpoint.
- Full pipeline: inlet → LLM → outlet in a single POST.
- Confidence band extraction (HIGH/MEDIUM/LOW).

---

*Last updated: April 2026*
