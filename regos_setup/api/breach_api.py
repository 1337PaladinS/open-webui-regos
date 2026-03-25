"""
RegOS Breach Data API
=====================
FastAPI endpoint for the dashboard to pull threshold evaluation data.

Endpoints:
  GET /api/breaches/summary         — Dashboard summary (counts, rates, top params)
  GET /api/breaches                 — List breach records (filterable)
  GET /api/breaches/evaluations     — List all evaluations (breach + compliant)
  POST /api/breaches/check          — Run a threshold check (same as chat tool)
  GET /api/breaches/parameters      — List available parameters
  GET /api/breaches/verify/{hash}   — Verify an evidence hash against a record

Usage:
  # Standalone (for development/testing):
  uvicorn api.breach_api:app --port 8100

  # Or import into an existing FastAPI app:
  from api.breach_api import router
  app.include_router(router, prefix="/api/breaches")
"""

import os
import sys
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Add parent dir to path so we can import functions/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from functions.threshold_eval import (
    ThresholdEvaluationService,
    BreachDB,
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


# ── REQUEST/RESPONSE MODELS ─────────────────────────────────────────────

class ThresholdCheckRequest(BaseModel):
    parameter: str
    value: float
    unit: Optional[str] = None
    user_id: Optional[str] = ""
    chat_id: Optional[str] = ""
    query_text: Optional[str] = ""


class VerifyResponse(BaseModel):
    valid: bool
    record: Optional[dict] = None
    message: str


# ── FASTAPI APP ──────────────────────────────────────────────────────────

app = FastAPI(
    title="RegOS Breach Data API",
    description="Threshold evaluation and breach tracking for Miami-Dade Chapter 24",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Also create a router for embedding in larger apps
from fastapi import APIRouter
router = APIRouter(tags=["breaches"])


@router.get("/summary")
def get_summary():
    """Dashboard summary: evaluation counts, breach rate, top breached parameters."""
    svc = get_service()
    return svc.breach_db.get_summary()


@router.get("/")
def list_breaches(
    since: Optional[str] = Query(None, description="ISO timestamp filter (e.g., 2026-01-01T00:00:00)"),
    limit: int = Query(50, ge=1, le=500),
):
    """List breach records, newest first."""
    svc = get_service()
    return svc.breach_db.get_breaches(since=since, limit=limit)


@router.get("/evaluations")
def list_evaluations(
    since: Optional[str] = Query(None, description="ISO timestamp filter"),
    limit: int = Query(100, ge=1, le=500),
):
    """List all evaluations (breach + compliant + borderline)."""
    svc = get_service()
    return svc.breach_db.get_all_evaluations(since=since, limit=limit)


@router.post("/check")
def check_threshold(req: ThresholdCheckRequest):
    """Run a threshold check. Same logic as the chat tool."""
    svc = get_service()
    results = svc.evaluate(
        parameter=req.parameter,
        value=req.value,
        unit=req.unit,
        user_id=req.user_id or "",
        chat_id=req.chat_id or "",
        query_text=req.query_text or "",
    )
    return {"results": results}


@router.get("/parameters")
def list_parameters():
    """List all available regulatory parameters."""
    svc = get_service()
    params = svc.list_parameters()
    return {"parameters": params, "count": len(params)}


@router.get("/thresholds/{parameter}")
def get_thresholds(parameter: str):
    """Get all thresholds for a specific parameter."""
    svc = get_service()
    thresholds = svc.get_thresholds_for_parameter(parameter)
    if not thresholds:
        raise HTTPException(404, f"No thresholds found for '{parameter}'")
    return {"parameter": parameter, "thresholds": thresholds}


@router.get("/verify/{evidence_hash}")
def verify_hash(evidence_hash: str):
    """Verify an evidence hash against stored records.

    Looks up the record by hash and confirms it hasn't been tampered with.
    """
    svc = get_service()
    # Search all evaluations for this hash
    try:
        import sqlite3
        conn = sqlite3.connect(_BREACH_DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM threshold_evaluations WHERE evidence_hash = ?",
            (evidence_hash,)
        ).fetchone()
        conn.close()

        if not row:
            return VerifyResponse(
                valid=False,
                message="No record found with this evidence hash.",
            )

        record = dict(row)

        # Recompute hash to verify integrity
        recomputed = compute_evidence_hash({
            "parameter": record["parameter"],
            "user_value": record["user_value"],
            "threshold_value": record["threshold_value"],
            "threshold_direction": record["threshold_direction"],
            "threshold_unit": record["threshold_unit"],
            "status": record["status"],
            "timestamp": record["timestamp"],
            "section_ref": record["section_ref"],
        })

        if recomputed == evidence_hash:
            return VerifyResponse(
                valid=True,
                record=record,
                message="Record verified. Evidence hash matches stored data.",
            )
        else:
            return VerifyResponse(
                valid=False,
                record=record,
                message="INTEGRITY VIOLATION: Recomputed hash does not match. Record may have been tampered with.",
            )

    except Exception as e:
        raise HTTPException(500, f"Verification failed: {str(e)}")


# Mount router on app for standalone mode
app.include_router(router, prefix="/api/breaches")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8100)
