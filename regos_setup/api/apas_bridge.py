"""
RegOS ↔ APAS Telemetry Bridge
==============================
Polls the APAS Telemetry API for SCADA sensor readings, maps metrics
to Chapter 24 regulatory parameters, evaluates each against thresholds,
and streams compliance determinations through the RegOS SCADA pipeline.

Architecture:
  APAS (TimescaleDB + 123SCADA) → [this bridge] → ThresholdEvaluationService
                                                 → BreachDB + SSE broadcast
                                                 → WebSocket / REST consumers

The bridge is a pull-based poller (APAS doesn't push). It authenticates
via JWT, polls /api/telemetry/query at a configurable interval, and feeds
results into the existing scada_stream.py infrastructure.

Usage:
  # Standalone (runs the polling loop)
  python api/apas_bridge.py

  # As a FastAPI sub-app (mounts poller + management endpoints)
  from api.apas_bridge import apas_router, start_poller
  app.include_router(apas_router, prefix="/api/apas")
  start_poller()

  # With environment variables
  APAS_BASE_URL=http://10.0.1.50:8000 \
  APAS_EMAIL=regos@apas.local \
  APAS_PASSWORD=secret \
  APAS_POLL_INTERVAL=30 \
  python api/apas_bridge.py

Author: APAS AI
Version: 0.1.0
"""

import asyncio
import fnmatch
import json
import logging
import os
import re
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx
from pydantic import BaseModel, Field

# Add parent dir for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from api.scada_stream import (
    ScadaReading,
    broadcast_determination,
    evaluate_reading,
    get_service,
    _state as stream_state,
)

# ── LOGGING ──────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("apas_bridge")

# ── CONFIG ───────────────────────────────────────────────────────────────

APAS_BASE_URL = os.environ.get("APAS_BASE_URL", "http://localhost:8000")
APAS_EMAIL = os.environ.get("APAS_EMAIL", "")
APAS_PASSWORD = os.environ.get("APAS_PASSWORD", "")
APAS_POLL_INTERVAL = int(os.environ.get("APAS_POLL_INTERVAL", "30"))  # seconds
APAS_PAGE_SIZE = int(os.environ.get("APAS_PAGE_SIZE", "1000"))
APAS_LOOKBACK_SECONDS = int(os.environ.get("APAS_LOOKBACK_SECONDS", "60"))

_MAPPINGS_PATH = os.environ.get(
    "APAS_MAPPINGS_PATH",
    os.path.join(os.path.dirname(__file__), "..", "data", "apas_metric_mappings.json"),
)


# ── METRIC MAPPING ──────────────────────────────────────────────────────

class MetricMapping:
    """Maps an APAS metric to a RegOS threshold parameter."""

    def __init__(self, data: dict):
        self.apas_source_id: str = data["apas_source_id"]
        self.apas_metric_pattern: str = data["apas_metric"]
        self.regos_parameter: Optional[str] = data.get("regos_parameter")
        self.regos_unit: Optional[str] = data.get("regos_unit")
        self.evaluate: bool = data.get("evaluate", False)
        self.description: str = data.get("description", "")
        self.unit_conversion: Optional[dict] = data.get("unit_conversion")

    def matches(self, source_id: str, metric_name: str) -> bool:
        """Check if an APAS metric matches this mapping (supports * wildcards)."""
        if source_id != self.apas_source_id:
            return False
        return fnmatch.fnmatch(metric_name, self.apas_metric_pattern)

    def convert_value(self, value: float) -> float:
        """Apply unit conversion if configured."""
        if not self.unit_conversion:
            return value
        formula = self.unit_conversion.get("formula", "value")
        # Safe eval of simple arithmetic formulas
        try:
            return eval(formula, {"__builtins__": {}}, {"value": value})
        except Exception:
            return value


class MappingRegistry:
    """Loads and indexes metric mappings from config file."""

    def __init__(self, path: str = _MAPPINGS_PATH):
        self.mappings: list[MetricMapping] = []
        self._load(path)

    def _load(self, path: str):
        try:
            with open(path) as f:
                data = json.load(f)
            for item in data.get("mappings", []):
                self.mappings.append(MetricMapping(item))
            log.info("Loaded %d metric mappings from %s", len(self.mappings), path)
        except FileNotFoundError:
            log.warning("Metric mappings file not found: %s — no metrics will be evaluated", path)
        except Exception as e:
            log.error("Failed to load metric mappings: %s", e)

    def find_mapping(self, source_id: str, metric_name: str) -> Optional[MetricMapping]:
        """Find the first matching mapping for an APAS metric."""
        for m in self.mappings:
            if m.matches(source_id, metric_name):
                return m
        return None

    @property
    def evaluable_count(self) -> int:
        return sum(1 for m in self.mappings if m.evaluate)


# ── APAS API CLIENT ─────────────────────────────────────────────────────

class APASClient:
    """HTTP client for the APAS Telemetry API with JWT authentication."""

    def __init__(self, base_url: str, email: str, password: str):
        self.base_url = base_url.rstrip("/")
        self.email = email
        self.password = password
        self._token: Optional[str] = None
        self._token_obtained_at: float = 0.0
        self._client = httpx.Client(timeout=30.0)

    def _authenticate(self) -> bool:
        """Obtain a JWT token from APAS /api/auth/login."""
        try:
            resp = self._client.post(
                f"{self.base_url}/api/auth/login",
                json={"email": self.email, "password": self.password},
            )
            if resp.status_code == 200:
                data = resp.json()
                self._token = data.get("access_token")
                self._token_obtained_at = time.time()
                log.info("Authenticated with APAS successfully")
                return True
            else:
                log.error("APAS auth failed: %d %s", resp.status_code, resp.text[:200])
                return False
        except Exception as e:
            log.error("APAS auth request failed: %s", e)
            return False

    @property
    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    def ensure_authenticated(self) -> bool:
        """Authenticate if not already done or if token is old (>50 min)."""
        if self._token and (time.time() - self._token_obtained_at) < 3000:
            return True
        return self._authenticate()

    def query_telemetry(
        self,
        metrics: list[dict],
        start: str,
        end: str,
        page_size: int = 1000,
        cursor: Optional[str] = None,
    ) -> Optional[dict]:
        """Call POST /api/telemetry/query and return the response."""
        if not self.ensure_authenticated():
            return None

        body = {
            "metrics": metrics,
            "start": start,
            "end": end,
            "page_size": page_size,
            "cursor": cursor,
        }

        try:
            resp = self._client.post(
                f"{self.base_url}/api/telemetry/query",
                json=body,
                headers=self._headers,
            )

            if resp.status_code == 401:
                log.warning("APAS token expired, re-authenticating...")
                self._token = None
                if not self._authenticate():
                    return None
                resp = self._client.post(
                    f"{self.base_url}/api/telemetry/query",
                    json=body,
                    headers=self._headers,
                )

            if resp.status_code == 200:
                return resp.json()
            else:
                log.error("APAS query failed: %d %s", resp.status_code, resp.text[:300])
                return None
        except Exception as e:
            log.error("APAS query request failed: %s", e)
            return None

    def get_catalog(self, source_id: Optional[str] = None, limit: int = 500) -> Optional[dict]:
        """Call GET /api/telemetry/catalog to discover available metrics."""
        if not self.ensure_authenticated():
            return None

        params = {"limit": limit}
        if source_id:
            params["source_id"] = source_id

        try:
            resp = self._client.get(
                f"{self.base_url}/api/telemetry/catalog",
                params=params,
                headers=self._headers,
            )
            if resp.status_code == 200:
                return resp.json()
            else:
                log.error("APAS catalog failed: %d %s", resp.status_code, resp.text[:200])
                return None
        except Exception as e:
            log.error("APAS catalog request failed: %s", e)
            return None

    def close(self):
        self._client.close()


# ── ASYNC APAS CLIENT (for use inside async poller) ─────────────────────

class AsyncAPASClient:
    """Async HTTP client for the APAS Telemetry API."""

    def __init__(self, base_url: str, email: str, password: str):
        self.base_url = base_url.rstrip("/")
        self.email = email
        self.password = password
        self._token: Optional[str] = None
        self._token_obtained_at: float = 0.0
        self._client = httpx.AsyncClient(timeout=30.0)

    async def _authenticate(self) -> bool:
        try:
            resp = await self._client.post(
                f"{self.base_url}/api/auth/login",
                json={"email": self.email, "password": self.password},
            )
            if resp.status_code == 200:
                data = resp.json()
                self._token = data.get("access_token")
                self._token_obtained_at = time.time()
                log.info("Authenticated with APAS successfully")
                return True
            else:
                log.error("APAS auth failed: %d %s", resp.status_code, resp.text[:200])
                return False
        except Exception as e:
            log.error("APAS auth request failed: %s", e)
            return False

    @property
    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    async def ensure_authenticated(self) -> bool:
        if self._token and (time.time() - self._token_obtained_at) < 3000:
            return True
        return await self._authenticate()

    async def query_telemetry(
        self,
        metrics: list[dict],
        start: str,
        end: str,
        page_size: int = 1000,
        cursor: Optional[str] = None,
    ) -> Optional[dict]:
        if not await self.ensure_authenticated():
            return None

        body = {
            "metrics": metrics,
            "start": start,
            "end": end,
            "page_size": page_size,
            "cursor": cursor,
        }

        try:
            resp = await self._client.post(
                f"{self.base_url}/api/telemetry/query",
                json=body,
                headers=self._headers,
            )

            if resp.status_code == 401:
                log.warning("APAS token expired, re-authenticating...")
                self._token = None
                if not await self._authenticate():
                    return None
                resp = await self._client.post(
                    f"{self.base_url}/api/telemetry/query",
                    json=body,
                    headers=self._headers,
                )

            if resp.status_code == 200:
                return resp.json()
            else:
                log.error("APAS query failed: %d %s", resp.status_code, resp.text[:300])
                return None
        except Exception as e:
            log.error("APAS query request failed: %s", e)
            return None

    async def get_catalog(self, source_id: Optional[str] = None, limit: int = 500) -> Optional[dict]:
        if not await self.ensure_authenticated():
            return None

        params = {"limit": limit}
        if source_id:
            params["source_id"] = source_id

        try:
            resp = await self._client.get(
                f"{self.base_url}/api/telemetry/catalog",
                params=params,
                headers=self._headers,
            )
            if resp.status_code == 200:
                return resp.json()
            else:
                log.error("APAS catalog failed: %d", resp.status_code)
                return None
        except Exception as e:
            log.error("APAS catalog request failed: %s", e)
            return None

    async def close(self):
        await self._client.aclose()


# ── BRIDGE STATE ─────────────────────────────────────────────────────────

class BridgeState:
    """Tracks the state of the APAS polling bridge."""

    def __init__(self):
        self.is_running: bool = False
        self.polls_completed: int = 0
        self.readings_fetched: int = 0
        self.readings_evaluated: int = 0
        self.readings_skipped: int = 0  # unmapped or evaluate=false
        self.last_poll_at: Optional[str] = None
        self.last_poll_duration_ms: float = 0.0
        self.last_error: Optional[str] = None
        self.consecutive_errors: int = 0
        self.catalog_metrics: int = 0
        self.mapped_metrics: int = 0
        self.start_time: float = 0.0
        self._last_poll_end: Optional[str] = None  # watermark for dedup

    @property
    def uptime_seconds(self) -> float:
        return time.time() - self.start_time if self.start_time > 0 else 0.0


_bridge_state = BridgeState()


# ── CORE POLLING LOGIC ──────────────────────────────────────────────────

def extract_device_id(metric_name: str) -> str:
    """Extract device ID from APAS metric name pattern like 'wetwell.66602.level'."""
    parts = metric_name.split(".")
    if len(parts) >= 2:
        return parts[1]
    return ""


async def poll_and_evaluate(
    client: AsyncAPASClient,
    mappings: MappingRegistry,
    lookback_seconds: int = APAS_LOOKBACK_SECONDS,
    page_size: int = APAS_PAGE_SIZE,
) -> dict:
    """Execute one poll cycle: fetch from APAS, evaluate against thresholds.

    Returns a summary dict with counts.
    """
    now = datetime.now(timezone.utc)
    start = (now - timedelta(seconds=lookback_seconds)).isoformat()
    end = now.isoformat()

    # Build the metrics list from catalog (or use all known patterns)
    # For now, query with a broad metric set — APAS returns only what exists
    catalog = await client.get_catalog()
    if not catalog:
        return {"error": "Failed to fetch APAS catalog", "fetched": 0, "evaluated": 0}

    available_metrics = catalog.get("metrics", [])
    _bridge_state.catalog_metrics = len(available_metrics)

    # Filter to only metrics that have evaluable mappings
    query_metrics = []
    metric_mapping_cache: dict[str, MetricMapping] = {}

    for m in available_metrics:
        source_id = m["source_id"]
        metric_name = m["metric_name"]
        mapping = mappings.find_mapping(source_id, metric_name)
        if mapping and mapping.evaluate:
            query_metrics.append({"source_id": source_id, "metric_name": metric_name})
            metric_mapping_cache[f"{source_id}::{metric_name}"] = mapping

    _bridge_state.mapped_metrics = len(query_metrics)

    if not query_metrics:
        log.debug("No evaluable metrics found in APAS catalog")
        return {"fetched": 0, "evaluated": 0, "skipped": 0}

    # APAS allows max 10 metrics per query — batch if needed
    all_data_points = []
    for batch_start in range(0, len(query_metrics), 10):
        batch = query_metrics[batch_start:batch_start + 10]
        cursor = None

        while True:
            result = await client.query_telemetry(
                metrics=batch,
                start=start,
                end=end,
                page_size=page_size,
                cursor=cursor,
            )
            if not result:
                break

            all_data_points.extend(result.get("data", []))

            pagination = result.get("pagination", {})
            if not pagination.get("has_more", False):
                break
            cursor = pagination.get("next_cursor")

    _bridge_state.readings_fetched += len(all_data_points)

    # Evaluate each data point
    evaluated = 0
    skipped = 0

    for point in all_data_points:
        source_id = point.get("source_id", "")
        metric_name = point.get("metric_name", "")
        cache_key = f"{source_id}::{metric_name}"
        mapping = metric_mapping_cache.get(cache_key)

        if not mapping or not mapping.evaluate or not mapping.regos_parameter:
            skipped += 1
            continue

        # Extract the value — prefer raw 'value', fall back to 'avg' (aggregated)
        raw_value = point.get("value")
        if raw_value is None:
            raw_value = point.get("avg")
        if raw_value is None:
            skipped += 1
            continue

        # Apply unit conversion
        value = mapping.convert_value(float(raw_value))

        # Build a ScadaReading for the existing pipeline
        device_id = extract_device_id(metric_name)
        reading = ScadaReading(
            sensor_id=f"{source_id}::{metric_name}",
            parameter=mapping.regos_parameter,
            value=value,
            unit=mapping.regos_unit,
            timestamp=point.get("time"),
            location=f"device:{device_id}" if device_id else source_id,
            metadata={
                "apas_source_id": source_id,
                "apas_metric": metric_name,
                "original_value": raw_value,
                "unit_converted": mapping.unit_conversion is not None,
            },
        )

        # Evaluate through the existing SCADA pipeline
        determinations = evaluate_reading(reading)
        for det in determinations:
            await broadcast_determination(det)
        evaluated += 1

    _bridge_state.readings_evaluated += evaluated
    _bridge_state.readings_skipped += skipped

    return {
        "fetched": len(all_data_points),
        "evaluated": evaluated,
        "skipped": skipped,
        "catalog_total": len(available_metrics),
        "mapped_evaluable": len(query_metrics),
    }


# ── POLLING LOOP ─────────────────────────────────────────────────────────

_poller_task: Optional[asyncio.Task] = None


async def _polling_loop(
    base_url: str,
    email: str,
    password: str,
    poll_interval: int,
    mappings: MappingRegistry,
):
    """The main async polling loop. Runs until cancelled."""
    client = AsyncAPASClient(base_url, email, password)
    _bridge_state.is_running = True
    _bridge_state.start_time = time.time()
    log.info("APAS Bridge poller starting — interval=%ds, base=%s", poll_interval, base_url)

    backoff = 0  # exponential backoff on consecutive errors

    try:
        while _bridge_state.is_running:
            poll_start = time.time()
            _bridge_state.last_poll_at = datetime.now(timezone.utc).isoformat()

            try:
                result = await poll_and_evaluate(client, mappings)
                _bridge_state.polls_completed += 1
                _bridge_state.last_poll_duration_ms = round((time.time() - poll_start) * 1000, 1)
                _bridge_state.last_error = None
                _bridge_state.consecutive_errors = 0
                backoff = 0

                if result.get("evaluated", 0) > 0 or result.get("error"):
                    log.info(
                        "Poll #%d: fetched=%d evaluated=%d skipped=%d (%.0fms)",
                        _bridge_state.polls_completed,
                        result.get("fetched", 0),
                        result.get("evaluated", 0),
                        result.get("skipped", 0),
                        _bridge_state.last_poll_duration_ms,
                    )

            except Exception as e:
                _bridge_state.last_error = str(e)
                _bridge_state.consecutive_errors += 1
                backoff = min(backoff + 1, 4)  # max 2^4 = 16s extra
                log.error(
                    "Poll error (consecutive=%d, backoff=%ds): %s",
                    _bridge_state.consecutive_errors,
                    2**backoff,
                    e,
                )

            # Wait for next poll (interval + backoff)
            wait = poll_interval + (2**backoff if backoff > 0 else 0)
            await asyncio.sleep(wait)

    except asyncio.CancelledError:
        log.info("APAS Bridge poller cancelled")
    finally:
        _bridge_state.is_running = False
        await client.close()
        log.info("APAS Bridge poller stopped")


def start_poller(
    base_url: str = APAS_BASE_URL,
    email: str = APAS_EMAIL,
    password: str = APAS_PASSWORD,
    poll_interval: int = APAS_POLL_INTERVAL,
    mappings_path: str = _MAPPINGS_PATH,
) -> Optional[asyncio.Task]:
    """Start the APAS polling loop as a background asyncio task.

    Call this after your event loop is running (e.g., in a FastAPI startup event).
    """
    global _poller_task

    if _bridge_state.is_running:
        log.warning("APAS Bridge poller is already running")
        return _poller_task

    mappings = MappingRegistry(mappings_path)

    loop = asyncio.get_event_loop()
    _poller_task = loop.create_task(
        _polling_loop(base_url, email, password, poll_interval, mappings)
    )
    return _poller_task


def stop_poller():
    """Stop the APAS polling loop."""
    global _poller_task
    _bridge_state.is_running = False
    if _poller_task and not _poller_task.done():
        _poller_task.cancel()
    _poller_task = None


# ── FASTAPI MANAGEMENT ENDPOINTS ────────────────────────────────────────

from fastapi import APIRouter, FastAPI, HTTPException

apas_router = APIRouter(tags=["apas-bridge"])


@apas_router.get("/status")
def apas_bridge_status():
    """Get the APAS Bridge poller status and metrics."""
    return {
        "is_running": _bridge_state.is_running,
        "uptime_seconds": round(_bridge_state.uptime_seconds, 1),
        "polls_completed": _bridge_state.polls_completed,
        "readings_fetched": _bridge_state.readings_fetched,
        "readings_evaluated": _bridge_state.readings_evaluated,
        "readings_skipped": _bridge_state.readings_skipped,
        "last_poll_at": _bridge_state.last_poll_at,
        "last_poll_duration_ms": _bridge_state.last_poll_duration_ms,
        "last_error": _bridge_state.last_error,
        "consecutive_errors": _bridge_state.consecutive_errors,
        "catalog_metrics": _bridge_state.catalog_metrics,
        "mapped_evaluable_metrics": _bridge_state.mapped_metrics,
        "poll_interval_seconds": APAS_POLL_INTERVAL,
        "apas_base_url": APAS_BASE_URL,
    }


@apas_router.post("/start")
async def apas_bridge_start():
    """Start the APAS Bridge poller."""
    if _bridge_state.is_running:
        return {"status": "already_running"}
    start_poller()
    return {"status": "started", "poll_interval": APAS_POLL_INTERVAL}


@apas_router.post("/stop")
def apas_bridge_stop():
    """Stop the APAS Bridge poller."""
    if not _bridge_state.is_running:
        return {"status": "already_stopped"}
    stop_poller()
    return {"status": "stopped"}


@apas_router.get("/mappings")
def apas_bridge_mappings():
    """List all configured metric mappings."""
    registry = MappingRegistry(_MAPPINGS_PATH)
    return {
        "total": len(registry.mappings),
        "evaluable": registry.evaluable_count,
        "mappings": [
            {
                "apas_source_id": m.apas_source_id,
                "apas_metric_pattern": m.apas_metric_pattern,
                "regos_parameter": m.regos_parameter,
                "regos_unit": m.regos_unit,
                "evaluate": m.evaluate,
                "has_unit_conversion": m.unit_conversion is not None,
                "description": m.description,
            }
            for m in registry.mappings
        ],
    }


@apas_router.get("/catalog")
async def apas_bridge_catalog(source_id: Optional[str] = None):
    """Proxy the APAS catalog endpoint and show which metrics are mapped."""
    client = AsyncAPASClient(APAS_BASE_URL, APAS_EMAIL, APAS_PASSWORD)
    registry = MappingRegistry(_MAPPINGS_PATH)

    try:
        catalog = await client.get_catalog(source_id=source_id)
        if not catalog:
            raise HTTPException(502, "Failed to reach APAS Telemetry API")

        # Annotate each metric with its RegOS mapping
        annotated = []
        for m in catalog.get("metrics", []):
            mapping = registry.find_mapping(m["source_id"], m["metric_name"])
            annotated.append({
                **m,
                "regos_mapping": {
                    "is_mapped": mapping is not None,
                    "evaluate": mapping.evaluate if mapping else False,
                    "regos_parameter": mapping.regos_parameter if mapping else None,
                    "regos_unit": mapping.regos_unit if mapping else None,
                } if mapping else {"is_mapped": False, "evaluate": False},
            })

        return {
            "metrics": annotated,
            "total": catalog.get("total", len(annotated)),
            "mapped_count": sum(1 for a in annotated if a["regos_mapping"]["is_mapped"]),
            "evaluable_count": sum(1 for a in annotated if a["regos_mapping"]["evaluate"]),
        }
    finally:
        await client.close()


@apas_router.post("/test-poll")
async def apas_bridge_test_poll(lookback_seconds: int = 120):
    """Execute a single poll cycle manually (for testing). Does NOT require poller to be running."""
    client = AsyncAPASClient(APAS_BASE_URL, APAS_EMAIL, APAS_PASSWORD)
    registry = MappingRegistry(_MAPPINGS_PATH)

    try:
        result = await poll_and_evaluate(
            client, registry, lookback_seconds=lookback_seconds
        )
        return {"result": result}
    except Exception as e:
        raise HTTPException(500, f"Test poll failed: {e}")
    finally:
        await client.close()


# ── STANDALONE APP ───────────────────────────────────────────────────────

app = FastAPI(
    title="RegOS APAS Bridge",
    description="Polls APAS Telemetry API and evaluates SCADA data against Chapter 24 thresholds",
    version="0.1.0",
)

# Mount the SCADA streaming endpoints alongside the bridge
from api.scada_stream import scada_router

app.include_router(apas_router, prefix="/api/apas")
app.include_router(scada_router, prefix="/api/scada")


@app.on_event("startup")
async def startup():
    """Auto-start the poller when running standalone."""
    if APAS_EMAIL and APAS_PASSWORD:
        start_poller()
    else:
        log.warning(
            "APAS_EMAIL and APAS_PASSWORD not set — poller won't auto-start. "
            "Use POST /api/apas/start after setting credentials, or set env vars."
        )


@app.on_event("shutdown")
async def shutdown():
    stop_poller()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8300)
