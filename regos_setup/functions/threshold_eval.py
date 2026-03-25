"""
title: RegOS Threshold Evaluation Service
description: Checks user-provided values against Chapter 24 regulatory thresholds. Returns compliance determinations with SHA-256 evidence hashes for tamper-proof audit trails. Can be called by the LLM as a tool or queried via the dashboard API.
author: APAS AI
version: 0.1.0
"""

import hashlib
import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


# ── DATA PATH ────────────────────────────────────────────────────────────
# Thresholds file location — adjust if deployed differently
_THRESHOLDS_PATH = os.environ.get(
    "REGOS_THRESHOLDS_PATH",
    os.path.join(os.path.dirname(__file__), "..", "data", "regulatory_thresholds.json"),
)
_BREACH_DB_PATH = os.environ.get(
    "REGOS_BREACH_DB",
    "/app/backend/data/regos_breaches.db",
)


# ── THRESHOLD REGISTRY ───────────────────────────────────────────────────

class ThresholdEntry:
    """A single regulatory threshold from the curated table."""

    def __init__(self, data: dict):
        self.value = float(data["value"].replace(",", ""))
        self.value_raw = data["value"]
        self.unit = data["unit"]
        self.parameter = data["parameter"]
        self.direction = data["direction"]  # max, min, exact, within
        self.context = data["context"]
        self.section_ref = data["section_ref"]
        self.type = data["type"]

    def check(self, user_value: float) -> dict:
        """Evaluate a user-provided value against this threshold.

        Returns a determination dict with:
          status: COMPLIANT | BREACH | BORDERLINE
          margin: how far from the limit (positive = safe, negative = breach)
          pct_of_limit: user value as percentage of threshold
        """
        if self.direction == "max":
            margin = self.value - user_value
            status = "COMPLIANT" if user_value <= self.value else "BREACH"
            if 0 < margin <= (self.value * 0.10):
                status = "BORDERLINE"
        elif self.direction == "min":
            margin = user_value - self.value
            status = "COMPLIANT" if user_value >= self.value else "BREACH"
            if 0 < margin <= (self.value * 0.10):
                status = "BORDERLINE"
        elif self.direction == "exact":
            margin = 0.0
            status = "COMPLIANT" if abs(user_value - self.value) < 0.001 else "BREACH"
        else:
            margin = self.value - user_value
            status = "COMPLIANT" if user_value <= self.value else "BREACH"

        pct_of_limit = (user_value / self.value * 100) if self.value != 0 else 0

        return {
            "status": status,
            "margin": round(margin, 4),
            "pct_of_limit": round(pct_of_limit, 1),
        }


class ThresholdRegistry:
    """Loads and indexes the curated threshold table."""

    def __init__(self, path: str = _THRESHOLDS_PATH):
        self._entries: list[ThresholdEntry] = []
        self._by_parameter: dict[str, list[ThresholdEntry]] = {}
        self._by_section: dict[str, list[ThresholdEntry]] = {}
        self._by_type: dict[str, list[ThresholdEntry]] = {}
        self._load(path)

    def _load(self, path: str):
        resolved = Path(path).resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"Threshold table not found: {resolved}")
        with open(resolved) as f:
            raw = json.load(f)
        for item in raw:
            try:
                entry = ThresholdEntry(item)
                self._entries.append(entry)
                param_key = entry.parameter.lower()
                self._by_parameter.setdefault(param_key, []).append(entry)
                self._by_section.setdefault(entry.section_ref, []).append(entry)
                self._by_type.setdefault(entry.type, []).append(entry)
            except (ValueError, KeyError):
                continue  # Skip malformed entries

    @property
    def count(self) -> int:
        return len(self._entries)

    def find_by_parameter(self, parameter: str) -> list[ThresholdEntry]:
        """Fuzzy match on parameter name."""
        param_lower = parameter.lower()
        results = []
        for key, entries in self._by_parameter.items():
            if param_lower in key or key in param_lower:
                results.extend(entries)
        return results

    def find_by_section(self, section_ref: str) -> list[ThresholdEntry]:
        return self._by_section.get(section_ref, [])

    def find_by_type(self, threshold_type: str) -> list[ThresholdEntry]:
        return self._by_type.get(threshold_type, [])

    def all_entries(self) -> list[ThresholdEntry]:
        return self._entries

    def list_parameters(self) -> list[str]:
        return sorted(set(e.parameter for e in self._entries))


# ── SHA-256 EVIDENCE HASHING ─────────────────────────────────────────────

def compute_evidence_hash(determination: dict) -> str:
    """Compute a SHA-256 hash of the determination for tamper-proof audit.

    The hash covers:
      - parameter checked
      - user-provided value
      - regulatory limit value + direction + unit
      - compliance status
      - timestamp
      - section reference

    This creates a verifiable chain of evidence: if anyone modifies the
    determination after the fact, the hash won't match.
    """
    canonical = json.dumps({
        "parameter": determination["parameter"],
        "user_value": determination["user_value"],
        "threshold_value": determination["threshold_value"],
        "threshold_direction": determination["threshold_direction"],
        "threshold_unit": determination["threshold_unit"],
        "status": determination["status"],
        "timestamp": determination["timestamp"],
        "section_ref": determination["section_ref"],
    }, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ── BREACH DATABASE ──────────────────────────────────────────────────────

class BreachDB:
    """SQLite store for threshold evaluation results (breach log)."""

    def __init__(self, db_path: str = _BREACH_DB_PATH):
        self._db_path = db_path
        self._ensure_table()

    def _ensure_table(self):
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS threshold_evaluations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    user_id TEXT,
                    chat_id TEXT,
                    parameter TEXT NOT NULL,
                    user_value REAL NOT NULL,
                    threshold_value REAL NOT NULL,
                    threshold_direction TEXT NOT NULL,
                    threshold_unit TEXT NOT NULL,
                    section_ref TEXT NOT NULL,
                    status TEXT NOT NULL,
                    margin REAL,
                    pct_of_limit REAL,
                    context TEXT,
                    evidence_hash TEXT NOT NULL,
                    query_text TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_eval_status
                ON threshold_evaluations (status)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_eval_timestamp
                ON threshold_evaluations (timestamp)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_eval_parameter
                ON threshold_evaluations (parameter)
            """)
            conn.commit()
            conn.close()
        except Exception:
            pass  # Non-fatal if DB not writable (e.g., testing)

    def log_evaluation(self, determination: dict):
        """Log a threshold evaluation to the breach database."""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""
                INSERT INTO threshold_evaluations
                (timestamp, user_id, chat_id, parameter, user_value,
                 threshold_value, threshold_direction, threshold_unit,
                 section_ref, status, margin, pct_of_limit, context,
                 evidence_hash, query_text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                determination["timestamp"],
                determination.get("user_id", ""),
                determination.get("chat_id", ""),
                determination["parameter"],
                determination["user_value"],
                determination["threshold_value"],
                determination["threshold_direction"],
                determination["threshold_unit"],
                determination["section_ref"],
                determination["status"],
                determination["margin"],
                determination["pct_of_limit"],
                determination.get("context", ""),
                determination["evidence_hash"],
                determination.get("query_text", ""),
            ))
            conn.commit()
            conn.close()
        except Exception:
            pass  # Non-fatal

    def get_breaches(self, since: Optional[str] = None, limit: int = 50) -> list[dict]:
        """Retrieve breach records for dashboard display."""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            if since:
                rows = conn.execute(
                    "SELECT * FROM threshold_evaluations WHERE status = 'BREACH' "
                    "AND timestamp >= ? ORDER BY timestamp DESC LIMIT ?",
                    (since, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM threshold_evaluations WHERE status = 'BREACH' "
                    "ORDER BY timestamp DESC LIMIT ?",
                    (limit,)
                ).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def get_all_evaluations(self, since: Optional[str] = None, limit: int = 100) -> list[dict]:
        """Retrieve all evaluations (breach + compliant + borderline)."""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            if since:
                rows = conn.execute(
                    "SELECT * FROM threshold_evaluations "
                    "WHERE timestamp >= ? ORDER BY timestamp DESC LIMIT ?",
                    (since, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM threshold_evaluations "
                    "ORDER BY timestamp DESC LIMIT ?",
                    (limit,)
                ).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def get_summary(self) -> dict:
        """Dashboard summary: counts by status, most common breaches."""
        try:
            conn = sqlite3.connect(self._db_path)
            total = conn.execute("SELECT COUNT(*) FROM threshold_evaluations").fetchone()[0]
            breaches = conn.execute(
                "SELECT COUNT(*) FROM threshold_evaluations WHERE status = 'BREACH'"
            ).fetchone()[0]
            borderline = conn.execute(
                "SELECT COUNT(*) FROM threshold_evaluations WHERE status = 'BORDERLINE'"
            ).fetchone()[0]
            compliant = conn.execute(
                "SELECT COUNT(*) FROM threshold_evaluations WHERE status = 'COMPLIANT'"
            ).fetchone()[0]

            # Most breached parameters
            top_params = conn.execute(
                "SELECT parameter, COUNT(*) as cnt FROM threshold_evaluations "
                "WHERE status = 'BREACH' GROUP BY parameter ORDER BY cnt DESC LIMIT 5"
            ).fetchall()

            conn.close()
            return {
                "total_evaluations": total,
                "breaches": breaches,
                "borderline": borderline,
                "compliant": compliant,
                "breach_rate": round(breaches / total * 100, 1) if total else 0,
                "top_breached_parameters": [
                    {"parameter": r[0], "count": r[1]} for r in top_params
                ],
            }
        except Exception:
            return {"total_evaluations": 0, "breaches": 0, "borderline": 0, "compliant": 0}


# ── EVALUATION SERVICE ───────────────────────────────────────────────────

class ThresholdEvaluationService:
    """Main service: takes a parameter + value, returns a determination."""

    def __init__(
        self,
        thresholds_path: str = _THRESHOLDS_PATH,
        breach_db_path: str = _BREACH_DB_PATH,
    ):
        self.registry = ThresholdRegistry(thresholds_path)
        self.breach_db = BreachDB(breach_db_path)

    def evaluate(
        self,
        parameter: str,
        value: float,
        unit: Optional[str] = None,
        user_id: str = "",
        chat_id: str = "",
        query_text: str = "",
    ) -> list[dict]:
        """Evaluate a user-provided value against all matching thresholds.

        Returns a list of determinations (one per matching threshold).
        Each determination includes the SHA-256 evidence hash.
        """
        matches = self.registry.find_by_parameter(parameter)
        if not matches:
            return [{
                "status": "NO_THRESHOLD_FOUND",
                "parameter": parameter,
                "user_value": value,
                "message": f"No regulatory threshold found for '{parameter}' in Chapter 24.",
            }]

        determinations = []
        timestamp = datetime.now(timezone.utc).isoformat()

        for entry in matches:
            # Unit mismatch check
            if unit and unit.lower() != entry.unit.lower():
                continue

            result = entry.check(value)

            determination = {
                "parameter": entry.parameter,
                "user_value": value,
                "threshold_value": entry.value,
                "threshold_value_raw": entry.value_raw,
                "threshold_direction": entry.direction,
                "threshold_unit": entry.unit,
                "section_ref": entry.section_ref,
                "status": result["status"],
                "margin": result["margin"],
                "pct_of_limit": result["pct_of_limit"],
                "context": entry.context,
                "timestamp": timestamp,
                "user_id": user_id,
                "chat_id": chat_id,
                "query_text": query_text,
            }

            # SHA-256 evidence hash
            determination["evidence_hash"] = compute_evidence_hash(determination)

            # Log to breach DB
            self.breach_db.log_evaluation(determination)

            determinations.append(determination)

        return determinations if determinations else [{
            "status": "NO_MATCHING_UNIT",
            "parameter": parameter,
            "user_value": value,
            "unit_provided": unit,
            "message": f"Thresholds exist for '{parameter}' but none match unit '{unit}'.",
        }]

    def list_parameters(self) -> list[str]:
        """List all available parameters for threshold checking."""
        return self.registry.list_parameters()

    def get_thresholds_for_parameter(self, parameter: str) -> list[dict]:
        """Get all thresholds for a parameter (for display/reference)."""
        matches = self.registry.find_by_parameter(parameter)
        return [{
            "parameter": e.parameter,
            "value": e.value_raw,
            "unit": e.unit,
            "direction": e.direction,
            "context": e.context,
            "section_ref": e.section_ref,
        } for e in matches]


# ── OPEN WEBUI TOOL (for LLM to call) ───────────────────────────────────

class Tools:
    """Open WebUI Tool class — exposes threshold evaluation to the LLM."""

    class Valves(BaseModel):
        thresholds_path: str = Field(
            default=_THRESHOLDS_PATH,
            description="Path to regulatory_thresholds.json",
        )
        breach_db_path: str = Field(
            default=_BREACH_DB_PATH,
            description="Path to breach SQLite database",
        )

    def __init__(self):
        self.valves = self.Valves()
        self._service = None

    def _get_service(self) -> ThresholdEvaluationService:
        if self._service is None:
            self._service = ThresholdEvaluationService(
                thresholds_path=self.valves.thresholds_path,
                breach_db_path=self.valves.breach_db_path,
            )
        return self._service

    def check_threshold(
        self,
        parameter: str,
        value: float,
        unit: str = "",
        __user__: dict = {},
    ) -> str:
        """Check a value against Chapter 24 regulatory thresholds.

        Use this tool when a user provides a measurement and wants to know
        if it complies with Miami-Dade County Chapter 24 limits.

        Args:
            parameter: What is being measured (e.g., "BOD", "dissolved oxygen",
                       "suspended solids", "oil and grease", "copper", "lead")
            value: The numeric value to check (e.g., 35.0)
            unit: Unit of measurement (e.g., "mg/l", "%", "°F")

        Returns:
            JSON string with compliance determination including status
            (COMPLIANT/BREACH/BORDERLINE), margin, section reference,
            and SHA-256 evidence hash.
        """
        service = self._get_service()
        results = service.evaluate(
            parameter=parameter,
            value=value,
            unit=unit if unit else None,
            user_id=__user__.get("id", ""),
            chat_id=__user__.get("chat_id", ""),
        )
        return json.dumps(results, indent=2)

    def list_thresholds(
        self,
        parameter: str = "",
        __user__: dict = {},
    ) -> str:
        """List available regulatory thresholds from Chapter 24.

        Use this tool when a user asks what limits apply to a specific parameter,
        or wants to see all available thresholds.

        Args:
            parameter: Optional filter — if provided, only show thresholds
                       matching this parameter. Leave empty to list all
                       available parameter names.

        Returns:
            JSON string with threshold details or parameter list.
        """
        service = self._get_service()
        if parameter:
            thresholds = service.get_thresholds_for_parameter(parameter)
            return json.dumps(thresholds, indent=2)
        else:
            params = service.list_parameters()
            return json.dumps({"available_parameters": params, "count": len(params)})

    def get_breach_summary(self, __user__: dict = {}) -> str:
        """Get a summary of all threshold evaluations and breaches.

        Use this tool when asked about compliance history, breach statistics,
        or overall compliance posture.

        Returns:
            JSON string with evaluation counts, breach rate, and top
            breached parameters.
        """
        service = self._get_service()
        summary = service.breach_db.get_summary()
        return json.dumps(summary, indent=2)
