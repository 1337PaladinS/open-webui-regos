"""
RegOS SCADA Streaming API
=========================
Real-time ingestion and compliance evaluation of SCADA sensor data against
Miami-Dade Chapter 24 regulatory thresholds.

Transport modes:
  WebSocket  /ws/scada           — Full-duplex: send readings, receive determinations
  SSE        /stream/scada       — Server-Sent Events push (POST readings, GET stream)
  REST       /api/scada/ingest   — Batch POST with immediate response
  REST       /api/scada/status   — Connection and throughput status

The external product (SCADA source) transmits sensor readings. We evaluate
each reading against our curated threshold table and stream back compliance
determinations (COMPLIANT / BREACH / BORDERLINE) with SHA-256 evidence hashes.

Usage:
  # Standalone
  uvicorn api.scada_stream:app --port 8200

  # Import into existing FastAPI app
  from api.scada_stream import scada_router
  app.include_router(scada_router, prefix="/api/scada")

Author: APAS AI
Version: 0.1.0
"""

import asyncio
import json
import os
import sys
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

# Add parent dir to path for functions/ imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from functions.threshold_eval import (
    ThresholdEvaluationService,
    compute_evidence_hash,
)


# ── CONFIG ───────────────────────────────────────────────────────────────

_THRESHOLDS_PATH = os.environ.get(
    "REGOS_THRESHOLDS_PATH",
    os.path.join(os.path.dirname(__file__), "..", "data", "regulatory_thresholds.json"),
)
_BREACH_DB_PATH = os.environ.get(
    "REGOS_BREACH_DB",
    "/app/backend/data/regos_breaches.db",
)

# Rate limiting / back-pressure
MAX_READINGS_PER_SECOND = int(os.environ.get("SCADA_MAX_RPS", "100"))
MAX_QUEUE_SIZE = int(os.environ.get("SCADA_MAX_QUEUE", "10000"))

# API key for external product auth (simple bearer token)
SCADA_API_KEY = os.environ.get("SCADA_API_KEY", "")


# ── SERVICE INIT ─────────────────────────────────────────────────────────

_service = None


def get_service() -> ThresholdEvaluationService:
    global _service
    if _service is None:
        _service = ThresholdEvaluationService(
            thresholds_path=_THRESHOLDS_PATH,
            breach_db_path=_BREACH_DB_PATH,
        )
    return _service


# ── REQUEST / RESPONSE MODELS ───────────────────────────────────────────

class ScadaReading(BaseModel):
    """A single SCADA sensor reading from the external product."""
    sensor_id: str = Field(..., description="Unique sensor identifier")
    parameter: str = Field(..., description="What is being measured (e.g., 'BOD', 'dissolved oxygen')")
    value: float = Field(..., description="The measured value")
    unit: Optional[str] = Field(None, description="Unit of measurement (e.g., 'mg/l')")
    timestamp: Optional[str] = Field(None, description="ISO timestamp of the reading (defaults to now)")
    location: Optional[str] = Field(None, description="Sensor location / facility ID")
    metadata: Optional[dict] = Field(None, description="Additional sensor metadata")


class ScadaBatchRequest(BaseModel):
    """Batch of SCADA readings for bulk ingestion."""
    readings: list[ScadaReading]
    source_id: Optional[str] = Field(None, description="External product / source identifier")


class ScadaDetermination(BaseModel):
    """Compliance determination for a single reading."""
    sensor_id: str
    parameter: str
    value: float
    unit: Optional[str]
    reading_timestamp: str
    status: str  # COMPLIANT | BREACH | BORDERLINE | NO_THRESHOLD_FOUND
    threshold_value: Optional[float] = None
    threshold_direction: Optional[str] = None
    threshold_unit: Optional[str] = None
    section_ref: Optional[str] = None
    margin: Optional[float] = None
    pct_of_limit: Optional[float] = None
    context: Optional[str] = None
    evidence_hash: Optional[str] = None
    evaluated_at: str = ""
    location: Optional[str] = None


# ── IN-MEMORY STATE (per-process) ────────────────────────────────────────

class StreamState:
    """Tracks connected clients, throughput, and the SSE event bus."""

    def __init__(self):
        self.ws_clients: dict[str, WebSocket] = {}
        self.sse_queues: dict[str, asyncio.Queue] = {}
        self.readings_processed: int = 0
        self.breaches_detected: int = 0
        self.borderlines_detected: int = 0
        self.start_time: float = time.time()
        self.last_reading_time: float = 0.0
        self.recent_determinations: deque = deque(maxlen=200)
        self._rate_window: deque = deque(maxlen=MAX_READINGS_PER_SECOND)

    def check_rate_limit(self) -> bool:
        """Token-bucket style rate limiter. Returns True if allowed."""
        now = time.time()
        # Remove entries older than 1 second
        while self._rate_window and self._rate_window[0] < now - 1.0:
            self._rate_window.popleft()
        if len(self._rate_window) >= MAX_READINGS_PER_SECOND:
            return False
        self._rate_window.append(now)
        return True

    @property
    def uptime_seconds(self) -> float:
        return time.time() - self.start_time

    @property
    def throughput_rps(self) -> float:
        elapsed = self.uptime_seconds
        return round(self.readings_processed / elapsed, 2) if elapsed > 0 else 0.0


_state = StreamState()


# ── CORE EVALUATION LOGIC ───────────────────────────────────────────────

def evaluate_reading(reading: ScadaReading) -> list[ScadaDetermination]:
    """Evaluate a single SCADA reading against all matching thresholds.

    Returns a list of ScadaDetermination (one per matching threshold).
    If no threshold matches, returns a single NO_THRESHOLD_FOUND determination.
    """
    svc = get_service()
    reading_ts = reading.timestamp or datetime.now(timezone.utc).isoformat()

    results = svc.evaluate(
        parameter=reading.parameter,
        value=reading.value,
        unit=reading.unit,
        user_id=f"scada:{reading.sensor_id}",
        chat_id=reading.location or "",
        query_text=f"SCADA reading from sensor {reading.sensor_id}",
    )

    determinations = []
    for r in results:
        det = ScadaDetermination(
            sensor_id=reading.sensor_id,
            parameter=reading.parameter,
            value=reading.value,
            unit=reading.unit,
            reading_timestamp=reading_ts,
            status=r.get("status", "UNKNOWN"),
            threshold_value=r.get("threshold_value"),
            threshold_direction=r.get("threshold_direction"),
            threshold_unit=r.get("threshold_unit"),
            section_ref=r.get("section_ref"),
            margin=r.get("margin"),
            pct_of_limit=r.get("pct_of_limit"),
            context=r.get("context"),
            evidence_hash=r.get("evidence_hash"),
            evaluated_at=datetime.now(timezone.utc).isoformat(),
            location=reading.location,
        )
        determinations.append(det)

    # Update state counters
    _state.readings_processed += 1
    _state.last_reading_time = time.time()
    for d in determinations:
        if d.status == "BREACH":
            _state.breaches_detected += 1
        elif d.status == "BORDERLINE":
            _state.borderlines_detected += 1
        _state.recent_determinations.append(d.model_dump())

    return determinations


async def broadcast_determination(determination: ScadaDetermination):
    """Push a determination to all connected SSE subscribers."""
    data = json.dumps(determination.model_dump())
    dead_queues = []
    for client_id, queue in _state.sse_queues.items():
        try:
            queue.put_nowait(data)
        except asyncio.QueueFull:
            dead_queues.append(client_id)
    for cid in dead_queues:
        _state.sse_queues.pop(cid, None)


# ── AUTH HELPER ──────────────────────────────────────────────────────────

def validate_api_key(provided: Optional[str]) -> bool:
    """Validate the SCADA API key if one is configured."""
    if not SCADA_API_KEY:
        return True  # No key configured = open (dev mode)
    return provided == SCADA_API_KEY


# ── FASTAPI APP ──────────────────────────────────────────────────────────

app = FastAPI(
    title="RegOS SCADA Streaming API",
    description="Real-time SCADA data ingestion and Chapter 24 compliance evaluation",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi import APIRouter, Header

scada_router = APIRouter(tags=["scada"])


# ── WEBSOCKET ENDPOINT ──────────────────────────────────────────────────

@app.websocket("/ws/scada")
async def scada_websocket(websocket: WebSocket):
    """Full-duplex WebSocket for SCADA streaming.

    Protocol:
      Client sends JSON messages:
        {"type": "reading", "data": {<ScadaReading fields>}}
        {"type": "batch",   "data": [<ScadaReading>, ...]}
        {"type": "ping"}

      Server responds:
        {"type": "determination", "data": {<ScadaDetermination fields>}}
        {"type": "error", "message": "..."}
        {"type": "pong", "timestamp": "..."}
        {"type": "ack", "readings_accepted": N}

    Auth:
      Pass API key as query param: /ws/scada?api_key=YOUR_KEY
      Or as first message: {"type": "auth", "api_key": "YOUR_KEY"}
    """
    # Auth check via query param
    api_key = websocket.query_params.get("api_key")
    authenticated = validate_api_key(api_key)

    await websocket.accept()
    client_id = str(uuid.uuid4())[:8]
    _state.ws_clients[client_id] = websocket

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            msg_type = msg.get("type", "reading")

            # Auth message
            if msg_type == "auth":
                authenticated = validate_api_key(msg.get("api_key"))
                if authenticated:
                    await websocket.send_json({"type": "auth_ok"})
                else:
                    await websocket.send_json({"type": "auth_failed", "message": "Invalid API key"})
                continue

            if not authenticated:
                await websocket.send_json({"type": "error", "message": "Not authenticated. Send auth message first."})
                continue

            # Ping/pong
            if msg_type == "ping":
                await websocket.send_json({
                    "type": "pong",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                continue

            # Rate limit check
            if not _state.check_rate_limit():
                await websocket.send_json({
                    "type": "error",
                    "message": f"Rate limit exceeded ({MAX_READINGS_PER_SECOND}/s). Back off.",
                })
                continue

            # Single reading
            if msg_type == "reading":
                data = msg.get("data", msg)
                try:
                    reading = ScadaReading(**data)
                    determinations = evaluate_reading(reading)
                    for det in determinations:
                        await websocket.send_json({
                            "type": "determination",
                            "data": det.model_dump(),
                        })
                        await broadcast_determination(det)
                except Exception as e:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Evaluation failed: {str(e)}",
                    })

            # Batch of readings
            elif msg_type == "batch":
                items = msg.get("data", [])
                count = 0
                for item in items:
                    try:
                        reading = ScadaReading(**item)
                        determinations = evaluate_reading(reading)
                        for det in determinations:
                            await websocket.send_json({
                                "type": "determination",
                                "data": det.model_dump(),
                            })
                            await broadcast_determination(det)
                        count += 1
                    except Exception:
                        continue
                await websocket.send_json({
                    "type": "ack",
                    "readings_accepted": count,
                    "readings_total": len(items),
                })

    except WebSocketDisconnect:
        pass
    finally:
        _state.ws_clients.pop(client_id, None)


# ── SSE ENDPOINTS ────────────────────────────────────────────────────────

@scada_router.get("/stream")
async def scada_sse_stream(
    api_key: Optional[str] = Query(None, description="API key for authentication"),
    filter_status: Optional[str] = Query(None, description="Filter by status: BREACH, BORDERLINE, COMPLIANT"),
    filter_parameter: Optional[str] = Query(None, description="Filter by parameter name"),
):
    """Subscribe to real-time SCADA determination events via Server-Sent Events.

    Events are pushed as determinations are made. Use filter params to
    receive only breaches, specific parameters, etc.

    Example:
      curl -N "http://localhost:8200/api/scada/stream?filter_status=BREACH"
    """
    if not validate_api_key(api_key):
        raise HTTPException(401, "Invalid API key")

    client_id = str(uuid.uuid4())[:8]
    queue: asyncio.Queue = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
    _state.sse_queues[client_id] = queue

    async def event_generator():
        try:
            # Send initial connection event
            yield {
                "event": "connected",
                "data": json.dumps({
                    "client_id": client_id,
                    "filters": {
                        "status": filter_status,
                        "parameter": filter_parameter,
                    },
                }),
            }

            while True:
                data = await asyncio.wait_for(queue.get(), timeout=30.0)
                det = json.loads(data)

                # Apply filters
                if filter_status and det.get("status") != filter_status:
                    continue
                if filter_parameter and filter_parameter.lower() not in det.get("parameter", "").lower():
                    continue

                yield {
                    "event": "determination",
                    "data": data,
                }
        except asyncio.TimeoutError:
            # Send keepalive
            yield {"event": "keepalive", "data": ""}
        except asyncio.CancelledError:
            pass
        finally:
            _state.sse_queues.pop(client_id, None)

    return EventSourceResponse(event_generator())


@scada_router.post("/ingest")
async def scada_ingest(
    batch: ScadaBatchRequest,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    """Batch ingest SCADA readings and return all determinations immediately.

    This is the REST alternative to WebSocket streaming. Send a batch of
    readings, get back all compliance determinations in one response.

    Suitable for polling-style integrations or when the external product
    can't maintain a persistent connection.
    """
    if not validate_api_key(x_api_key):
        raise HTTPException(401, "Invalid API key")

    all_determinations = []
    errors = []

    for i, reading in enumerate(batch.readings):
        if not _state.check_rate_limit():
            errors.append({
                "index": i,
                "sensor_id": reading.sensor_id,
                "error": "Rate limit exceeded",
            })
            continue

        try:
            dets = evaluate_reading(reading)
            for det in dets:
                all_determinations.append(det.model_dump())
                await broadcast_determination(det)
        except Exception as e:
            errors.append({
                "index": i,
                "sensor_id": reading.sensor_id,
                "error": str(e),
            })

    # Summarize
    statuses = {}
    for d in all_determinations:
        s = d["status"]
        statuses[s] = statuses.get(s, 0) + 1

    return {
        "accepted": len(batch.readings) - len(errors),
        "total": len(batch.readings),
        "determinations": all_determinations,
        "summary": statuses,
        "errors": errors if errors else None,
        "source_id": batch.source_id,
    }


@scada_router.post("/ingest/single")
async def scada_ingest_single(
    reading: ScadaReading,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    """Ingest a single SCADA reading. Lightweight alternative to batch."""
    if not validate_api_key(x_api_key):
        raise HTTPException(401, "Invalid API key")

    if not _state.check_rate_limit():
        raise HTTPException(429, "Rate limit exceeded")

    dets = evaluate_reading(reading)
    results = [det.model_dump() for det in dets]
    for det in dets:
        await broadcast_determination(det)

    return {"determinations": results}


# ── STATUS / HEALTH ENDPOINTS ───────────────────────────────────────────

@scada_router.get("/status")
def scada_status():
    """Get SCADA streaming service status and throughput metrics."""
    return {
        "status": "online",
        "uptime_seconds": round(_state.uptime_seconds, 1),
        "readings_processed": _state.readings_processed,
        "breaches_detected": _state.breaches_detected,
        "borderlines_detected": _state.borderlines_detected,
        "throughput_rps": _state.throughput_rps,
        "connected_ws_clients": len(_state.ws_clients),
        "connected_sse_clients": len(_state.sse_queues),
        "last_reading_at": (
            datetime.fromtimestamp(_state.last_reading_time, tz=timezone.utc).isoformat()
            if _state.last_reading_time > 0 else None
        ),
        "rate_limit_rps": MAX_READINGS_PER_SECOND,
        "thresholds_loaded": get_service().registry.count,
    }


@scada_router.get("/health")
def scada_health():
    """Simple health check for load balancer / orchestrator."""
    try:
        svc = get_service()
        count = svc.registry.count
        return {"healthy": True, "thresholds_loaded": count}
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"healthy": False, "error": str(e)},
        )


@scada_router.get("/recent")
def scada_recent(
    limit: int = Query(50, ge=1, le=200),
    status: Optional[str] = Query(None, description="Filter: BREACH, BORDERLINE, COMPLIANT"),
):
    """Get recent SCADA determinations from in-memory buffer.

    Faster than querying the breach DB — shows the last 200 determinations
    held in memory since service start.
    """
    items = list(_state.recent_determinations)
    if status:
        items = [d for d in items if d.get("status") == status]
    items.reverse()  # Newest first
    return {"determinations": items[:limit], "total_in_buffer": len(_state.recent_determinations)}


@scada_router.get("/parameters")
def scada_parameters():
    """List all parameters that have regulatory thresholds.

    Use this to know what sensor types can be evaluated. Any SCADA reading
    with a parameter not in this list will get NO_THRESHOLD_FOUND.
    """
    svc = get_service()
    params = svc.list_parameters()
    return {"parameters": params, "count": len(params)}


# ── MOUNT ROUTER ─────────────────────────────────────────────────────────

app.include_router(scada_router, prefix="/api/scada")


# ── STANDALONE ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8200)
