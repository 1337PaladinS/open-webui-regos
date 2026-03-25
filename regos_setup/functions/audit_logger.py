"""
title: RegOS Audit Logger
description: Captures structured audit records for every query — stores query metadata, retrieval context, citations, model info, and timestamps in a dedicated SQLite database. This is the foundation that all other P0 features write to.
author: APAS AI
version: 0.4.0
"""

from pydantic import BaseModel, Field
from typing import Optional
import json
import time
import uuid
import sqlite3
import hashlib
import re


class Filter:
    class Valves(BaseModel):
        priority: int = Field(
            default=5,
            description="Filter execution priority. Set to 5 so this runs AFTER the GraphRAG filter (priority 0) in the outlet. The audit logger reads guardrail, confidence, and escalation data from the message dict — that data is set by the GraphRAG filter's outlet, so the GraphRAG outlet must run first."
        )
        db_path: str = Field(
            default="/app/backend/data/audit.db",
            description="Path to the audit SQLite database file."
        )
        enabled: bool = Field(
            default=True,
            description="Enable or disable audit logging."
        )

    def __init__(self):
        self.valves = self.Valves()
        self._db_initialized = False

    def _ensure_db(self):
        if self._db_initialized:
            return
        conn = sqlite3.connect(self.valves.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_records (
                id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                epoch REAL NOT NULL,
                user_id TEXT,
                user_email TEXT,
                user_name TEXT,
                user_role TEXT,
                chat_id TEXT,
                message_id TEXT,
                session_id TEXT,
                model TEXT,
                query_text TEXT,
                message_count INTEGER,
                full_messages TEXT,
                response_text TEXT,
                response_model TEXT,
                retrieval_record TEXT,
                citations TEXT,
                confidence_score REAL,
                confidence_signals TEXT,
                escalation_triggered INTEGER DEFAULT 0,
                escalation_target TEXT,
                case_packet_ref TEXT,
                guardrail_triggered INTEGER DEFAULT 0,
                guardrail_type TEXT,
                guardrail_reason TEXT,
                record_hash TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_records(epoch)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_records(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_chat ON audit_records(chat_id)")
        conn.commit()
        conn.close()
        self._db_initialized = True

    def _compute_hash(self, data: dict) -> str:
        hashable = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(hashable.encode()).hexdigest()

    async def inlet(
        self,
        body: dict,
        __user__: dict = None,
        __chat_id__: str = None,
        __message_id__: str = None,
        __session_id__: str = None,
        __metadata__: dict = None,
    ) -> dict:
        if not self.valves.enabled:
            return body

        try:
            self._ensure_db()

            messages = body.get("messages", [])
            query_text = ""
            if messages:
                last_msg = messages[-1]
                if isinstance(last_msg.get("content"), str):
                    query_text = last_msg["content"]
                elif isinstance(last_msg.get("content"), list):
                    query_text = " ".join(
                        p.get("text", "") for p in last_msg["content"]
                        if isinstance(p, dict) and p.get("type") == "text"
                    )

            record_id = str(uuid.uuid4())
            now = time.time()
            user = __user__ or {}

            # ── Detect injection guardrail from counter-instruction ──
            # When the GraphRAG filter detects prompt injection, it replaces the
            # user message with a counter-instruction starting with this marker.
            # We detect it here in the inlet and pre-flag the audit record.
            inlet_guardrail_triggered = 0
            inlet_guardrail_type = None
            inlet_guardrail_reason = None
            if query_text.startswith("[SECURITY OVERRIDE"):
                inlet_guardrail_triggered = 1
                inlet_guardrail_type = "injection_detected"
                inlet_guardrail_reason = "Counter-instruction detected in inlet (original query replaced by GraphRAG filter)"

            conn = sqlite3.connect(self.valves.db_path)
            conn.execute("""
                INSERT INTO audit_records (
                    id, timestamp, epoch, user_id, user_email, user_name, user_role,
                    chat_id, message_id, session_id, model, query_text, message_count,
                    full_messages, response_text, response_model,
                    guardrail_triggered, guardrail_type, guardrail_reason,
                    record_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', '',
                          ?, ?, ?,
                          ?)
            """, [
                record_id,
                time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
                now,
                user.get("id", ""),
                user.get("email", ""),
                user.get("name", ""),
                user.get("role", ""),
                __chat_id__ or "",
                __message_id__ or "",
                __session_id__ or "",
                body.get("model", ""),
                query_text,
                len(messages),
                json.dumps(messages[-5:]) if messages else "[]",
                inlet_guardrail_triggered,
                inlet_guardrail_type,
                inlet_guardrail_reason,
                self._compute_hash({"id": record_id, "query": query_text, "time": now}),
            ])
            conn.commit()
            conn.close()
        except Exception:
            pass

        return body

    async def outlet(
        self,
        body: dict,
        __user__: dict = None,
        __chat_id__: str = None,
        __message_id__: str = None,
        __session_id__: str = None,
        __metadata__: dict = None,
    ) -> dict:
        if not self.valves.enabled:
            return body

        try:
            self._ensure_db()

            messages = body.get("messages", [])
            response_text = ""
            if messages:
                for msg in reversed(messages):
                    if msg.get("role") == "assistant":
                        content = msg.get("content", "")
                        if isinstance(content, str):
                            response_text = content
                        break

            if not response_text:
                return body

            # ── Extract confidence data from message dict or HTML comment ────
            confidence_score = None
            confidence_signals = None
            response_text_clean = response_text
            conf_match = None

            # Preferred: read from message dict (set by GraphRAG filter outlet)
            for msg in reversed(messages):
                if msg.get("role") == "assistant" and "graphrag_confidence" in msg:
                    conf_data = msg.pop("graphrag_confidence", {})
                    confidence_score = conf_data.get("score")
                    confidence_signals = json.dumps(conf_data.get("signals", {}), default=str)
                    break

            # Fallback: parse legacy HTML comment (for backward compatibility)
            if confidence_score is None:
                conf_match = re.search(
                    r'<!-- GRAPHRAG_CONFIDENCE:(.*?) -->',
                    response_text, re.DOTALL
                )
                if conf_match:
                    try:
                        conf_data = json.loads(conf_match.group(1))
                        confidence_score = conf_data.get("score")
                        confidence_signals = json.dumps(conf_data.get("signals", {}))
                    except (json.JSONDecodeError, AttributeError):
                        pass
                    response_text_clean = re.sub(
                        r'\n<!-- GRAPHRAG_CONFIDENCE:.*? -->', '',
                        response_text, flags=re.DOTALL
                    )

            # ── Extract escalation data from message dict (set by GraphRAG filter) ──
            escalation_triggered = 0
            escalation_target = None
            case_packet_ref = None

            for msg in reversed(messages):
                if msg.get("role") == "assistant" and "graphrag_escalation" in msg:
                    esc_data = msg.pop("graphrag_escalation", {})
                    escalation_triggered = 1 if esc_data.get("triggered") else 0
                    escalation_target = esc_data.get("target")
                    case_packet_ref = json.dumps({
                        "case_ref": esc_data.get("case_ref"),
                        "reason": esc_data.get("reason"),
                        "confidence_score": esc_data.get("confidence_score"),
                        "confidence_band": esc_data.get("confidence_band"),
                    })
                    break

            # ── Extract guardrail data from message dict (set by GraphRAG filter outlet) ──
            guardrail_triggered = 0
            guardrail_type = None
            guardrail_reason = None

            # Method 1: Check assistant message dict (works when outlets are chained)
            for msg in reversed(messages):
                if msg.get("role") == "assistant" and "graphrag_guardrail" in msg:
                    grd_data = msg.pop("graphrag_guardrail", {})
                    guardrail_triggered = 1 if grd_data.get("triggered") else 0
                    guardrail_type = grd_data.get("type")
                    guardrail_reason = grd_data.get("reason")
                    break

            # Method 2: Detect guardrail from response text patterns (fallback).
            # If the GraphRAG filter appended a guardrail notice to the response,
            # we can detect it even if the message dict key wasn't passed through.
            if guardrail_triggered == 0 and response_text:
                import re as _re
                # Security Notice = injection detected
                if "Your query was flagged by RegOS security screening" in response_text:
                    guardrail_triggered = 1
                    guardrail_type = "injection_detected"
                    ref_match = _re.search(r'Ref:\s*(GRD-[\w-]+)', response_text)
                    guardrail_reason = f"Detected via response text (ref: {ref_match.group(1)})" if ref_match else "Detected via response text"
                # Outside Regulatory Scope
                elif "RegOS identified this question as outside its current scope" in response_text:
                    guardrail_triggered = 1
                    guardrail_type = "out_of_scope"
                    ref_match = _re.search(r'Ref:\s*(GRD-[\w-]+)', response_text)
                    guardrail_reason = f"Detected via response text (ref: {ref_match.group(1)})" if ref_match else "Detected via response text"
                # Outside Jurisdiction
                elif "RegOS identified this question as referencing a jurisdiction outside" in response_text:
                    guardrail_triggered = 1
                    guardrail_type = "jurisdiction"
                    ref_match = _re.search(r'Ref:\s*(GRD-[\w-]+)', response_text)
                    guardrail_reason = f"Detected via response text (ref: {ref_match.group(1)})" if ref_match else "Detected via response text"
                # Knowledge Graph Offline
                elif "knowledge graph (Neo4j) is currently unreachable" in response_text:
                    guardrail_triggered = 1
                    guardrail_type = "neo4j_connection_failure"
                    guardrail_reason = "Detected via response text"
                # Query Too Long
                elif "Your query exceeds the maximum allowed length" in response_text:
                    guardrail_triggered = 1
                    guardrail_type = "input_limit_exceeded"
                    guardrail_reason = "Detected via response text"
                # Rate limit
                elif "too many requests in a short period" in response_text:
                    guardrail_triggered = 1
                    guardrail_type = "rate_limit_exceeded"
                    guardrail_reason = "Detected via response text"

            user_id = (__user__ or {}).get("id", "")
            conn = sqlite3.connect(self.valves.db_path)

            # Find the most recent inlet record for this user that has no response yet
            row = conn.execute("""
                SELECT id FROM audit_records
                WHERE user_id = ? AND response_text = '' AND query_text != ''
                ORDER BY epoch DESC LIMIT 1
            """, [user_id]).fetchone()

            if row:
                record_id = row[0]

                # Only update guardrail fields if the outlet detected something.
                # If guardrail_triggered is still 0, the inlet may have already
                # set it (e.g., injection counter-instruction detected). In that
                # case, preserve the inlet's values by using COALESCE/MAX.
                if guardrail_triggered:
                    conn.execute("""
                        UPDATE audit_records
                        SET response_text = ?,
                            response_model = ?,
                            confidence_score = ?,
                            confidence_signals = ?,
                            escalation_triggered = ?,
                            escalation_target = ?,
                            case_packet_ref = ?,
                            guardrail_triggered = ?,
                            guardrail_type = ?,
                            guardrail_reason = ?,
                            record_hash = ?
                        WHERE id = ?
                    """, [
                        response_text_clean,
                        body.get("model", ""),
                        confidence_score,
                        confidence_signals,
                        escalation_triggered,
                        escalation_target,
                        case_packet_ref,
                        guardrail_triggered,
                        guardrail_type,
                        guardrail_reason,
                        self._compute_hash({"id": record_id, "response": response_text_clean}),
                        record_id,
                    ])
                else:
                    # Don't overwrite guardrail fields — preserve inlet values
                    conn.execute("""
                        UPDATE audit_records
                        SET response_text = ?,
                            response_model = ?,
                            confidence_score = ?,
                            confidence_signals = ?,
                            escalation_triggered = ?,
                            escalation_target = ?,
                            case_packet_ref = ?,
                            record_hash = ?
                        WHERE id = ?
                    """, [
                        response_text_clean,
                        body.get("model", ""),
                        confidence_score,
                        confidence_signals,
                        escalation_triggered,
                        escalation_target,
                        case_packet_ref,
                        self._compute_hash({"id": record_id, "response": response_text_clean}),
                        record_id,
                    ])
            else:
                # No matching inlet record — store as standalone
                record_id = str(uuid.uuid4())
                now = time.time()
                conn.execute("""
                    INSERT INTO audit_records (
                        id, timestamp, epoch, user_id, user_email, user_name, user_role,
                        chat_id, message_id, session_id, model, query_text, message_count,
                        full_messages, response_text, response_model,
                        escalation_triggered, escalation_target, case_packet_ref,
                        guardrail_triggered, guardrail_type, guardrail_reason,
                        record_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', 0, '', ?, ?,
                              ?, ?, ?, ?, ?, ?, ?)
                """, [
                    record_id,
                    time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
                    now,
                    user_id,
                    (__user__ or {}).get("email", ""),
                    (__user__ or {}).get("name", ""),
                    (__user__ or {}).get("role", ""),
                    __chat_id__ or "",
                    __message_id__ or "",
                    __session_id__ or "",
                    body.get("model", ""),
                    response_text_clean,
                    body.get("model", ""),
                    escalation_triggered,
                    escalation_target,
                    case_packet_ref,
                    guardrail_triggered,
                    guardrail_type,
                    guardrail_reason,
                    self._compute_hash({"id": record_id, "response": response_text_clean}),
                ])

            conn.commit()
            conn.close()

            # Strip any legacy HTML confidence comments from the response
            # (new approach uses message dict, but keep fallback cleanup)
            if conf_match:
                for msg in reversed(messages):
                    if msg.get("role") == "assistant":
                        c = msg.get("content", "")
                        if isinstance(c, str) and "GRAPHRAG_CONFIDENCE" in c:
                            msg["content"] = re.sub(
                                r'\n<!-- GRAPHRAG_CONFIDENCE:.*? -->', '',
                                c, flags=re.DOTALL
                            )
                        break
                body["messages"] = messages
        except Exception:
            pass

        return body
