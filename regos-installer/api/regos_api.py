"""
RegOS Sidecar API — Single-endpoint proxy for the full RegOS pipeline.

Sits alongside Open WebUI and chains inlet -> LLM -> outlet in one call.
Consumers don't need to know about Open WebUI internals, model IDs, or
the two-step filter dance. They just POST a question and get back a
fully-scored, cited, trace-enabled response.

Environment:
  OPENWEBUI_URL     Base URL of your Open WebUI instance (e.g. https://eqcb.apas.ai)
  OPENWEBUI_TOKEN   Admin API token from Open WebUI
  REGOS_MODEL_ID    Default model ID to query (default: better-hardeepai)
  REGOS_API_PORT    Port for the sidecar API (default: 8300)

Usage:
  export OPENWEBUI_URL="https://<your-openwebui-host>"
  export OPENWEBUI_TOKEN="<your-token>"
  uvicorn api.regos_api:app --host 0.0.0.0 --port 8300

  # Regular (blocking) response:
  curl -X POST https://<your-sidecar-host>:8300/api/regos/query \
    -H "Content-Type: application/json" \
    -d '{"question": "What are the BOD limits for wastewater?"}'

  # With a specific model:
  curl -X POST https://<your-sidecar-host>:8300/api/regos/query \
    -H "Content-Type: application/json" \
    -d '{"question": "What are the BOD limits?", "model": "regos-miami-copilot"}'

  # With MCP tools enabled:
  curl -X POST https://<your-sidecar-host>:8300/api/regos/query \
    -H "Content-Type: application/json" \
    -d '{"question": "What is the current pump station flow?", "tool_ids": ["server:mcp:pumpiq"]}'

  # Streaming with reasoning/thinking tokens visible:
  curl -N -X POST https://<your-sidecar-host>:8300/api/regos/query \
    -H "Content-Type: application/json" \
    -d '{"question": "What are the BOD limits?", "stream": true, "show_reasoning": true}'

  # List available custom models:
  curl https://<your-sidecar-host>:8300/api/regos/models

  # List available tools (MCP servers + tool functions):
  curl https://<your-sidecar-host>:8300/api/regos/tools
"""

import os
import json
import asyncio
import logging
import uuid
from typing import Optional

import aiohttp
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# --- Logging ---------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("regos-api")

# --- Configuration (env vars or defaults) -----------------------------------

OPENWEBUI_URL = os.getenv("OPENWEBUI_URL", "http://localhost:3000")  # Set to your host, e.g. https://eqcb.apas.ai
OPENWEBUI_TOKEN = os.getenv("OPENWEBUI_TOKEN", "")
REGOS_MODEL_ID = os.getenv("REGOS_MODEL_ID", "better-hardeepai")
DEFAULT_STREAM = os.getenv("REGOS_DEFAULT_STREAM", "false").lower() == "true"
PORT = int(os.getenv("REGOS_API_PORT", "8300"))

# --- App Setup --------------------------------------------------------------

app = FastAPI(
    title="RegOS API",
    description="Regulatory Compliance Copilot — single-endpoint sidecar proxy",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Exception handler ------------------------------------------------------
# Starlette's default 500 handler returns plain-text "Internal Server Error"
# with no diagnostic info. Replace it with a JSON handler that logs the
# traceback server-side and returns a useful payload to the caller.
@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled exception in {request.method} {request.url.path}")
    return JSONResponse(
        status_code=500,
        content={
            "detail": f"{type(exc).__name__}: {exc}",
            "path": request.url.path,
        },
    )


# --- Request / Response Models -----------------------------------------------

class RegOSRequest(BaseModel):
    question: str = Field(..., description="The regulatory compliance question")
    model: Optional[str] = Field(default=None, description="Model ID to use (omit to use server default). Use GET /api/regos/models to list available models.")
    stream: bool = Field(default=False, description="Enable SSE streaming")
    show_reasoning: bool = Field(default=False, description="Include reasoning/thinking tokens in streaming response")
    context: Optional[str] = Field(default=None, description="Optional prior context or facility info")
    show_trace: bool = Field(default=False, description="Include retrieval trace in response")
    conversation_id: Optional[str] = Field(default=None, description="Continue an existing conversation")
    messages: Optional[list] = Field(default=None, description="Full message history (advanced usage)")
    tool_ids: Optional[list[str]] = Field(default=None, description="List of tool IDs to make available to the model. Use GET /api/regos/tools to list available tools. Example: ['server:mcp:pumpiq']")


class RegOSResponse(BaseModel):
    content: str = Field(..., description="Full RegOS response with citations and confidence")
    reasoning: Optional[str] = Field(default=None, description="Model reasoning/thinking tokens (if available)")
    model: str = Field(default="", description="Model used")
    confidence: Optional[str] = Field(default=None, description="Extracted confidence band (HIGH/MEDIUM/LOW)")
    usage: Optional[dict] = Field(default=None, description="Token usage stats")


class ModelInfo(BaseModel):
    id: str = Field(..., description="Model ID to use in query requests")
    name: str = Field(default="", description="Display name")
    description: Optional[str] = Field(default=None, description="Model description")
    base_model_id: Optional[str] = Field(default=None, description="Underlying base model (e.g. openrouter/nvidia/llama-3.1-nemotron-70b-instruct)")
    is_active: bool = Field(default=True, description="Whether the model is active")
    tags: Optional[list[dict]] = Field(default=None, description="Model tags for categorisation")


class ToolInfo(BaseModel):
    id: str = Field(..., description="Tool ID to pass in tool_ids")
    name: str = Field(default="", description="Display name")
    type: str = Field(default="", description="Tool type: 'function', 'mcp', or 'openapi'")
    description: Optional[str] = Field(default=None, description="What the tool does")


# --- Helpers ------------------------------------------------------------------

def _auth_headers():
    if not OPENWEBUI_TOKEN:
        raise HTTPException(
            status_code=500,
            detail="OPENWEBUI_TOKEN not configured. Set it as an environment variable.",
        )
    return {
        "Authorization": f"Bearer {OPENWEBUI_TOKEN}",
        "Content-Type": "application/json",
    }


def _resolve_model(req: RegOSRequest) -> str:
    """Return the model ID for this request: per-request override or server default."""
    return req.model or REGOS_MODEL_ID


def _build_messages(req: RegOSRequest) -> list:
    """Build the messages array from the request."""
    if req.messages:
        return req.messages

    messages = []

    # Add context as a user preamble if provided
    if req.context:
        messages.append({"role": "user", "content": req.context})
        messages.append({"role": "assistant", "content": "Understood. I'll keep that context in mind."})

    messages.append({"role": "user", "content": req.question})
    return messages


def _extract_confidence(content: str) -> Optional[str]:
    """Pull out the confidence band from the response content."""
    for band in ["HIGH", "MEDIUM", "LOW"]:
        if f"**Confidence:" in content and band in content:
            return band
        if f"Confidence:" in content and band in content:
            return band
    return None


def _extract_reasoning_from_usage(usage: Optional[dict]) -> Optional[str]:
    """
    Some providers only report reasoning token counts in usage stats
    but don't return the actual text. Return a metadata note in that case.
    """
    if not usage:
        return None
    details = usage.get("completion_tokens_details", {})
    reasoning_tokens = details.get("reasoning_tokens", 0)
    if reasoning_tokens > 0:
        return f"[Model used {reasoning_tokens} reasoning tokens — content not exposed by provider]"
    return None


# --- Core: Non-Streaming -----------------------------------------------------

async def _query_blocking(req: RegOSRequest) -> RegOSResponse:
    """
    Full pipeline: /api/chat/completions -> collect response -> /api/chat/completed
    Returns the outlet-processed response with confidence scores and trace.
    """
    headers = _auth_headers()
    messages = _build_messages(req)
    model_id = _resolve_model(req)

    # Step 1: Call chat/completions (inlet filters fire, LLM generates response)
    chat_payload = {
        "model": model_id,
        "messages": messages,
        "stream": False,
    }

    # Inject tool_ids so Open WebUI's middleware resolves and executes tools
    if req.tool_ids:
        chat_payload["tool_ids"] = req.tool_ids

    async with aiohttp.ClientSession() as session:
        # -- Step 1: Inlet + LLM (+ tool-calling loop if tool_ids provided) --
        async with session.post(
            f"{OPENWEBUI_URL}/api/chat/completions",
            headers=headers,
            json=chat_payload,
        ) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                raise HTTPException(status_code=resp.status, detail=f"Open WebUI error: {error_text}")
            completion = await resp.json()

        # Extract the assistant's response
        assistant_msg = completion.get("choices", [{}])[0].get("message", {})
        usage = completion.get("usage")
        model_used = completion.get("model", model_id)

        # Extract reasoning content if available and requested
        reasoning_content = None
        if req.show_reasoning:
            # Check multiple locations where providers place reasoning tokens
            choice = completion.get("choices", [{}])[0]
            reasoning_content = (
                assistant_msg.get("reasoning_content")       # OpenRouter / DeepSeek style
                or assistant_msg.get("thinking")             # Anthropic style
                or choice.get("reasoning_content")           # Some providers put it at choice level
                or _extract_reasoning_from_usage(usage)      # Fall back to usage metadata
            )

        # -- Step 2: Outlet (confidence scoring, threshold eval, audit logging) --
        # Build the completed payload: full conversation including assistant response
        # /api/chat/completed requires: id, model, chat_id, session_id
        # Tag with "regos-api:" prefix so audit logs can distinguish API vs UI calls
        completed_messages = messages + [assistant_msg]
        msg_id = str(uuid.uuid4())
        session_id = f"regos-api:{uuid.uuid4()}"
        completed_payload = {
            "id": msg_id,
            "model": model_id,
            "messages": completed_messages,
            "chat_id": req.conversation_id or f"api-{uuid.uuid4()}",
            "session_id": session_id,
        }

        logger.info(f"[OUTLET] Calling /api/chat/completed for model={model_id}")
        async with session.post(
            f"{OPENWEBUI_URL}/api/chat/completed",
            headers=headers,
            json=completed_payload,
        ) as resp:
            logger.info(f"[OUTLET] Response status: {resp.status}")
            if resp.status == 200:
                outlet_result = await resp.json()
                logger.info(f"[OUTLET] Outlet returned {len(outlet_result.get('messages', []))} messages")
                # The outlet may modify the messages (append confidence, trace, etc.)
                outlet_messages = outlet_result.get("messages", completed_messages)
                # Get the last assistant message (outlet-processed)
                final_content = ""
                for msg in reversed(outlet_messages):
                    if msg.get("role") == "assistant":
                        final_content = msg.get("content", "")
                        break
                if not final_content:
                    final_content = assistant_msg.get("content", "")
            else:
                # Outlet failed — fall back to raw LLM response
                error_body = await resp.text()
                logger.warning(f"[OUTLET] Failed with status {resp.status}: {error_body[:500]}")
                final_content = assistant_msg.get("content", "")

    return RegOSResponse(
        content=final_content,
        reasoning=reasoning_content,
        model=model_used,
        confidence=_extract_confidence(final_content),
        usage=usage,
    )


# --- Core: Streaming ---------------------------------------------------------

async def _query_streaming(req: RegOSRequest):
    """
    Streams the LLM response in real-time via SSE, then after the stream
    completes, calls /api/chat/completed to trigger outlet filters and
    sends the outlet additions (confidence block, trace) as final chunks.

    When show_reasoning=True, reasoning/thinking tokens are forwarded as
    separate SSE events with a "reasoning_content" field in the delta,
    allowing clients to display the model's chain-of-thought.
    """
    headers = _auth_headers()
    messages = _build_messages(req)
    model_id = _resolve_model(req)

    chat_payload = {
        "model": model_id,
        "messages": messages,
        "stream": True,
    }

    # Inject tool_ids so Open WebUI's middleware resolves and executes tools
    if req.tool_ids:
        chat_payload["tool_ids"] = req.tool_ids

    show_reasoning = req.show_reasoning

    async def event_generator():
        full_content = ""
        full_reasoning = ""

        async with aiohttp.ClientSession() as session:
            # -- Phase 1: Stream the LLM response --
            async with session.post(
                f"{OPENWEBUI_URL}/api/chat/completions",
                headers=headers,
                json=chat_payload,
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    yield f"data: {json.dumps({'error': error_text})}\n\n"
                    yield "data: [DONE]\n\n"
                    return

                # If reasoning is enabled, send an initial marker so the client
                # knows to expect reasoning chunks before the main content
                if show_reasoning:
                    marker = {"choices": [{"delta": {"role": "reasoning_start"}, "finish_reason": None}]}
                    yield f"data: {json.dumps(marker)}\n\n"

                reasoning_phase_ended = False

                async for line in resp.content:
                    decoded = line.decode("utf-8", errors="ignore").strip()
                    if not decoded or not decoded.startswith("data: "):
                        continue

                    data_str = decoded[6:]  # Strip "data: " prefix
                    if data_str == "[DONE]":
                        break

                    # Parse the chunk to check for reasoning tokens
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})

                        # -- Reasoning token detection --
                        # Providers use different field names for reasoning/thinking:
                        reasoning_piece = (
                            delta.get("reasoning_content")    # OpenRouter / DeepSeek
                            or delta.get("thinking")          # Anthropic
                            or delta.get("reasoning")         # Some other providers
                        )

                        if reasoning_piece and show_reasoning:
                            full_reasoning += reasoning_piece
                            # Send reasoning as a distinct event type
                            reasoning_chunk = {
                                "choices": [{
                                    "delta": {"reasoning_content": reasoning_piece},
                                    "finish_reason": None,
                                }]
                            }
                            yield f"data: {json.dumps(reasoning_chunk)}\n\n"
                            continue  # Don't forward as regular content

                        # -- Regular content --
                        content_piece = delta.get("content", "")

                        # If we were in reasoning phase and now got content, send a marker
                        if show_reasoning and not reasoning_phase_ended and content_piece and full_reasoning:
                            reasoning_phase_ended = True
                            marker = {"choices": [{"delta": {"role": "reasoning_end"}, "finish_reason": None}]}
                            yield f"data: {json.dumps(marker)}\n\n"

                        if content_piece:
                            full_content += content_piece

                        # Forward the chunk to the client
                        yield f"data: {data_str}\n\n"

                    except (json.JSONDecodeError, IndexError, KeyError):
                        # Forward unparseable chunks as-is
                        yield f"data: {data_str}\n\n"

            # If reasoning happened but no content followed (edge case), close reasoning
            if show_reasoning and full_reasoning and not reasoning_phase_ended:
                marker = {"choices": [{"delta": {"role": "reasoning_end"}, "finish_reason": None}]}
                yield f"data: {json.dumps(marker)}\n\n"

            # -- Phase 2: Trigger outlet filters --
            if full_content:
                assistant_msg = {"role": "assistant", "content": full_content}
                completed_messages = messages + [assistant_msg]
                msg_id = str(uuid.uuid4())
                session_id = f"regos-api:{uuid.uuid4()}"
                completed_payload = {
                    "id": msg_id,
                    "model": model_id,
                    "messages": completed_messages,
                    "chat_id": req.conversation_id or f"api-{uuid.uuid4()}",
                    "session_id": session_id,
                }

                logger.info(f"[OUTLET-STREAM] Calling /api/chat/completed for model={model_id}")
                async with session.post(
                    f"{OPENWEBUI_URL}/api/chat/completed",
                    headers=headers,
                    json=completed_payload,
                ) as resp:
                    logger.info(f"[OUTLET-STREAM] Response status: {resp.status}")
                    if resp.status == 200:
                        outlet_result = await resp.json()
                        outlet_messages = outlet_result.get("messages", [])

                        # Find the outlet-processed assistant message
                        outlet_content = ""
                        for msg in reversed(outlet_messages):
                            if msg.get("role") == "assistant":
                                outlet_content = msg.get("content", "")
                                break

                        # If the outlet added content (confidence, trace), send it
                        if outlet_content and len(outlet_content) > len(full_content):
                            # Extract only the additions (appended by outlet)
                            additions = outlet_content[len(full_content):]
                            if additions.strip():
                                outlet_chunk = {
                                    "choices": [{
                                        "delta": {"content": additions},
                                        "finish_reason": None,
                                    }]
                                }
                                yield f"data: {json.dumps(outlet_chunk)}\n\n"

        # Signal stream end
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# --- Routes -------------------------------------------------------------------

@app.post("/api/regos/query", response_model=None)
async def regos_query(req: RegOSRequest):
    """
    Query the RegOS Compliance Copilot.

    Automatically routes through the full pipeline:
    inlet filters (graph retrieval, context injection) -> LLM -> outlet filters
    (confidence scoring, threshold evaluation, audit logging).

    Set `stream: true` for Server-Sent Events streaming.
    Set `model` to override the default model (see GET /api/regos/models).
    Set `tool_ids` to enable MCP tools (see GET /api/regos/tools).
    """
    if req.stream:
        return await _query_streaming(req)
    return await _query_blocking(req)


@app.get("/api/regos/models", response_model=list[ModelInfo])
async def list_models():
    """
    List all custom models defined in the Open WebUI instance.

    Returns only custom models (those with a base_model_id — i.e. models
    created via the Open WebUI admin panel or the RegOS installer, NOT
    raw base models like 'gpt-4o' or 'llama3'). Use the `id` field as
    the `model` parameter in /api/regos/query.
    """
    headers = _auth_headers()
    all_models: list[ModelInfo] = []

    def _extract(item: dict) -> None:
        """Append a ModelInfo from an Open WebUI model record if it's a custom model."""
        if not isinstance(item, dict):
            return
        base_model = item.get("base_model_id")
        if not base_model:
            return
        meta = item.get("meta") or {}
        all_models.append(ModelInfo(
            id=item.get("id", ""),
            name=item.get("name", item.get("id", "")),
            description=meta.get("description"),
            base_model_id=base_model,
            is_active=item.get("is_active", True),
            tags=meta.get("tags"),
        ))

    # Open WebUI's paginated custom-models endpoint is mounted at /api/v1/models
    # (NOT /api/models — that top-level path is the flat compatibility list).
    url = f"{OPENWEBUI_URL}/api/v1/models/list"

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
            page = 1
            while True:
                async with session.get(url, headers=headers, params={"page": page}) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        raise HTTPException(
                            status_code=resp.status,
                            detail=f"Upstream {url} returned {resp.status}: {error_text[:500]}",
                        )
                    data = await resp.json()

                # Tolerate both paginated dict ({items, total}) and flat list shapes
                if isinstance(data, dict):
                    items = data.get("items") or []
                    for item in items:
                        _extract(item)
                    total = data.get("total", 0)
                    if not items or page * 30 >= total:
                        break
                    page += 1
                elif isinstance(data, list):
                    for item in data:
                        _extract(item)
                    break
                else:
                    raise HTTPException(
                        status_code=502,
                        detail=f"Unexpected response shape from {url}: {type(data).__name__}",
                    )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("[MODELS] Failed to list models")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list models: {type(e).__name__}: {e}",
        )

    logger.info(f"[MODELS] Found {len(all_models)} custom models")
    return all_models


@app.get("/api/regos/tools", response_model=list[ToolInfo])
async def list_tools():
    """
    List all tools available in the Open WebUI instance.

    Returns tool functions and MCP server tools. Use the `id` field
    in the `tool_ids` array of /api/regos/query to enable tools for
    a request. MCP tools have IDs prefixed with 'server:mcp:'.
    """
    headers = _auth_headers()
    all_tools: list[ToolInfo] = []

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
            # 1. Fetch tool functions (user-defined Python tools)
            try:
                async with session.get(
                    f"{OPENWEBUI_URL}/api/v1/tools/",
                    headers=headers,
                ) as resp:
                    if resp.status == 200:
                        tools_data = await resp.json()
                        if isinstance(tools_data, list):
                            for tool in tools_data:
                                if not isinstance(tool, dict):
                                    continue
                                # meta can be explicitly null in Open WebUI responses;
                                # `tool.get("meta", {})` would keep the None — guard with `or {}`.
                                meta = tool.get("meta") or {}
                                description = meta.get("description")
                                if not description:
                                    content = tool.get("content")
                                    if isinstance(content, str) and content:
                                        description = content[:200]
                                all_tools.append(ToolInfo(
                                    id=tool.get("id", ""),
                                    name=tool.get("name", tool.get("id", "")),
                                    type="function",
                                    description=description,
                                ))
                        else:
                            logger.warning(
                                f"[TOOLS] /api/v1/tools/ returned unexpected shape: "
                                f"{type(tools_data).__name__}"
                            )
                    else:
                        logger.warning(f"[TOOLS] Failed to fetch tool functions: HTTP {resp.status}")
            except Exception as inner:
                logger.warning(f"[TOOLS] Tool functions fetch failed: {type(inner).__name__}: {inner}")

            # 2. Fetch tool server connections (MCP + OpenAPI servers).
            # This endpoint is version-dependent — treat ANY non-200 as "not available"
            # so a missing/renamed route doesn't bring down the whole /tools response.
            try:
                async with session.get(
                    f"{OPENWEBUI_URL}/api/v1/tools/servers",
                    headers=headers,
                ) as resp:
                    if resp.status == 200:
                        servers_data = await resp.json()
                        if isinstance(servers_data, list):
                            for server in servers_data:
                                if not isinstance(server, dict):
                                    continue
                                server_type = server.get("type", "openapi")
                                server_info = server.get("info") or {}
                                server_id = server_info.get("id", "")

                                if server_type == "mcp":
                                    tool_id = f"server:mcp:{server_id}"
                                else:
                                    tool_id = f"server:{server_id}"

                                all_tools.append(ToolInfo(
                                    id=tool_id,
                                    name=server_info.get("name", server_id),
                                    type=server_type,
                                    description=server_info.get("description"),
                                ))
                        else:
                            logger.info(
                                f"[TOOLS] /api/v1/tools/servers returned non-list shape "
                                f"({type(servers_data).__name__}); skipping"
                            )
                    else:
                        logger.info(f"[TOOLS] /api/v1/tools/servers not available (HTTP {resp.status})")
            except Exception as inner:
                logger.info(f"[TOOLS] /api/v1/tools/servers fetch failed: {type(inner).__name__}: {inner}; skipping")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("[TOOLS] Failed to list tools")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list tools: {type(e).__name__}: {e}",
        )

    logger.info(f"[TOOLS] Found {len(all_tools)} tools")
    return all_tools


@app.get("/api/regos/health")
async def health_check():
    """Check that the sidecar can reach Open WebUI."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{OPENWEBUI_URL}/api/config",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status == 200:
                    return {"status": "healthy", "openwebui": "connected", "default_model": REGOS_MODEL_ID}
                return {"status": "degraded", "openwebui": f"HTTP {resp.status}"}
    except Exception as e:
        return {"status": "unhealthy", "openwebui": str(e)}


@app.get("/api/regos/info")
async def info():
    """Return sidecar configuration."""
    return {
        "version": "2.0.0",
        "default_model": REGOS_MODEL_ID,
        "openwebui_url": OPENWEBUI_URL,
        "streaming_supported": True,
        "reasoning_supported": True,
        "tool_calling_supported": True,
        "endpoints": {
            "query": "POST /api/regos/query",
            "models": "GET /api/regos/models",
            "tools": "GET /api/regos/tools",
            "health": "GET /api/regos/health",
            "info": "GET /api/regos/info",
        },
    }


# --- Main ---------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
