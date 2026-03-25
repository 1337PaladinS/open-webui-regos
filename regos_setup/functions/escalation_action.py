"""
title: RegOS Manual Escalation
description: Flag any RegOS response for expert compliance review. Builds a case packet and sends it to the n8n escalation workflow via webhook. Writes an audit trail entry to the audit SQLite DB.
author: APAS AI
version: 1.0.0
required_open_webui_version: 0.4.0
icon_url: data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCA1NzYgNTEyIj48cGF0aCBmaWxsPSIjMURBMUQ0IiBkPSJNMTYwIDBjLTE3LjcgMC0zMiAxNC4zLTMyIDMyczE0LjMgMzIgMzIgMzJoNTAuN0w5LjQgMjY1LjRjLTEyLjUgMTIuNS0xMi41IDMyLjggMCA0NS4zczMyLjggMTIuNSA0NS4zIDBMMjU2IDEwOS4zVjE2MGMwIDE3LjcgMTQuMyAzMiAzMiAzMnMzMi0xNC4zIDMyLTMyVjMyYzAtMTcuNy0xNC4zLTMyLTMyLTMySDE2MHpNNTc2IDgwYzAtMjYuNS0yMS41LTQ4LTQ4LTQ4cy00OCAyMS41LTQ4IDQ4czIxLjUgNDggNDggNDhzNDgtMjEuNSA0OC00OHpNNDQ4IDIwOGMwLTI2LjUtMjEuNS00OC00OC00OHMtNDggMjEuNS00OCA0OHMyMS41IDQ4IDQ4IDQ4czQ4LTIxLjUgNDgtNDh6TTQwMCAzODRjMjYuNSAwIDQ4LTIxLjUgNDgtNDhzLTIxLjUtNDgtNDgtNDhzLTQ4IDIxLjUtNDggNDhzMjEuNSA0OCA0OCA0OHptNDggODBjMC0yNi41LTIxLjUtNDgtNDgtNDhzLTQ4IDIxLjUtNDggNDhzMjEuNSA0OCA0OCA0OHM0OC0yMS41IDQ4LTQ4em0xMjggMGMwLTI2LjUtMjEuNS00OC00OC00OHMtNDggMjEuNS00OCA0OHMyMS41IDQ4IDQ4IDQ4czQ4LTIxLjUgNDgtNDh6TTI3MiAzODRjMjYuNSAwIDQ4LTIxLjUgNDgtNDhzLTIxLjUtNDgtNDgtNDhzLTQ4IDIxLjUtNDggNDhzMjEuNSA0OCA0OCA0OHptNDggODBjMC0yNi41LTIxLjUtNDgtNDgtNDhzLTQ4IDIxLjUtNDggNDhzMjEuNSA0OCA0OCA0OHM0OC0yMS41IDQ4LTQ4ek0xNDQgNTEyYzI2LjUgMCA0OC0yMS41IDQ4LTQ4cy0yMS41LTQ4LTQ4LTQ4cy00OCAyMS41LTQ4IDQ4czIxLjUgNDggNDggNDh6TTU3NiAzMzZjMC0yNi41LTIxLjUtNDgtNDgtNDhzLTQ4IDIxLjUtNDggNDhzMjEuNSA0OCA0OHM0OC0yMS41IDQ4LTQ4em0tNDgtODBjMjYuNSAwIDQ4LTIxLjUgNDgtNDhzLTIxLjUtNDgtNDgtNDhzLTQ4IDIxLjUtNDggNDhzMjEuNSA0OCA0OCA0OHoiLz48L3N2Zz4=
"""

from pydantic import BaseModel, Field
import json
import re
import time
import hashlib
import sqlite3
import uuid
import urllib.request


class Action:
    """Open WebUI Action function for manual escalation.

    Appears as a flag icon button on every assistant message.
    When clicked on a RegOS-processed message:
      1. Extracts conversation context from the message body
      2. Builds a case packet (same schema as automatic escalation)
      3. POSTs to the n8n escalation webhook
      4. Writes an audit trail entry to the audit SQLite DB
      5. Returns a toast confirmation with the case reference

    On non-RegOS messages, shows an informational message that
    manual escalation is only available for RegOS-processed responses.
    """

    class Valves(BaseModel):
        priority: int = Field(
            default=5,
            description="Button display order (lower = further left in toolbar).",
        )
        escalation_webhook_url: str = Field(
            default="",
            description=(
                "n8n webhook URL for escalation. "
                "Must match the URL configured in graphrag_filter valves."
            ),
        )
        escalation_target: str = Field(
            default="compliance-review",
            description="Review team or queue that receives escalated cases.",
        )
        audit_db_path: str = Field(
            default="/app/backend/data/audit.db",
            description="Path to the audit SQLite database.",
        )
        review_email: str = Field(
            default="sysadmin1@regos.ai",
            description="Email address shown in the confirmation toast.",
        )
        enabled: bool = Field(
            default=True,
            description="Enable or disable the manual escalation button.",
        )

    def __init__(self):
        self.valves = self.Valves()

    # ──────────────────────────────────────────────────────────
    #  Core action handler
    # ──────────────────────────────────────────────────────────

    async def action(
        self,
        body: dict,
        __user__=None,
        __event_emitter__=None,
        __event_call__=None,
        __model__=None,
        __request__=None,
        __id__=None,
    ) -> dict | None:
        """Called when the user clicks the flag icon on a message."""

        if not self.valves.enabled:
            return {"content": "Manual escalation is currently disabled."}

        # ── Extract message context ──
        messages = body.get("messages", [])
        message_id = body.get("id", "")

        # The body for an action contains the full message list up to and
        # including the clicked assistant message.  Find the last assistant
        # message — that's the one the user flagged.
        flagged_msg = None
        for msg in reversed(messages):
            if msg.get("role") == "assistant":
                flagged_msg = msg
                break

        if not flagged_msg:
            return {"content": "No assistant message found to escalate."}

        # ── Check if this is a RegOS-processed message ──
        # The graphrag_filter stores metadata on assistant messages it processes.
        # We check for graphrag_confidence OR graphrag_escalation (already auto-escalated).
        confidence_data = flagged_msg.get("graphrag_confidence", {})
        existing_escalation = flagged_msg.get("graphrag_escalation", {})

        # If the message has no GraphRAG metadata at all, it's not a RegOS response.
        if not confidence_data and not existing_escalation:
            # Still allow flagging — the user might see something wrong that
            # the system didn't flag.  We just won't have confidence data.
            confidence_data = {}

        # ── Prevent double-flagging ──
        manual_flag = flagged_msg.get("graphrag_manual_escalation", {})
        if manual_flag.get("flagged"):
            case_ref = manual_flag.get("case_ref", "unknown")
            return {
                "content": (
                    f"This message was already flagged for review.\n\n"
                    f"**Case:** {case_ref}\n"
                    f"**Status:** Under review"
                ),
            }

        # ── Ask user for their concern ──
        user_reason = ""
        if __event_call__:
            user_reason = await __event_call__(
                {
                    "type": "input",
                    "data": {
                        "title": "Escalate for Review",
                        "message": "Describe your concern with this response:",
                        "placeholder": "e.g. The cited section numbers don't match, BOD limit seems wrong, missing permit requirements...",
                        "value": "",
                    },
                }
            )
            # User cancelled the dialog
            if user_reason is None or (isinstance(user_reason, str) and user_reason.strip() == ""):
                return None

            user_reason = user_reason.strip() if isinstance(user_reason, str) else ""

        # ── Status: processing ──
        if __event_emitter__:
            await __event_emitter__(
                {
                    "type": "status",
                    "data": {
                        "description": "Preparing escalation case...",
                        "done": False,
                    },
                }
            )

        # ── Build identifiers ──
        user = __user__ or {}
        user_id = user.get("id", "")
        user_email = user.get("email", "")
        chat_id = body.get("chat_id", "") or ""
        model = body.get("model", "") or (__model__ or "")
        case_ref = self._generate_case_ref(user_id, chat_id)

        # ── Extract the user's original query ──
        query = self._extract_last_user_query(messages)

        # ── Extract the flagged response text ──
        response_text = flagged_msg.get("content", "")

        # ── Build the case packet (same schema as automatic escalation) ──
        case_packet = self._build_case_packet(
            case_ref=case_ref,
            reason="manual_user_flag",
            user_info=user,
            query=query,
            response=response_text,
            messages=messages,
            chat_id=chat_id,
            message_id=message_id,
            model=model,
            confidence_data=confidence_data,
            user_reason=user_reason,
        )

        # ── Send to n8n webhook ──
        webhook_result, webhook_error = self._send_webhook(case_packet)
        webhook_ok = webhook_result is not None

        # ── Write audit trail ──
        self._write_audit_record(
            case_ref=case_ref,
            user=user,
            chat_id=chat_id,
            message_id=message_id,
            model=model,
            query=query,
            confidence_data=confidence_data,
            webhook_ok=webhook_ok,
        )

        # ── Mark message as flagged (prevents double-click) ──
        flagged_msg["graphrag_manual_escalation"] = {
            "flagged": True,
            "case_ref": case_ref,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "user_id": user_id,
        }

        # ── Toast notification via event emitter ──
        if __event_emitter__:
            if webhook_ok:
                n8n_msg = webhook_result.get("message", "") if isinstance(webhook_result, dict) else ""
                toast_text = f"Escalation {case_ref} submitted successfully"
                if n8n_msg:
                    toast_text += f"\n{n8n_msg}"
                await __event_emitter__(
                    {
                        "type": "notification",
                        "data": {
                            "type": "success",
                            "content": toast_text,
                        },
                    }
                )
            else:
                error_detail = webhook_error or "Unknown error"
                await __event_emitter__(
                    {
                        "type": "notification",
                        "data": {
                            "type": "error",
                            "content": (
                                f"Escalation {case_ref} failed to send\n"
                                f"Reason: {error_detail}\n"
                                f"Case was logged locally for retry."
                            ),
                        },
                    }
                )

        # ── Clear the inline status spinner ──
        if __event_emitter__:
            await __event_emitter__(
                {
                    "type": "status",
                    "data": {
                        "description": f"Escalation {case_ref} — {'sent' if webhook_ok else 'failed'}",
                        "done": True,
                        "hidden": True,
                    },
                }
            )

    # ──────────────────────────────────────────────────────────
    #  Case reference generator
    # ──────────────────────────────────────────────────────────

    def _generate_case_ref(self, user_id: str = "", chat_id: str = "") -> str:
        """Generate a deterministic, human-readable case reference.

        Format: REG-YYYYMMDD-XXXX where XXXX is a 4-char hex derived
        from a SHA-256 hash of user_id + chat_id + epoch.
        """
        date_str = time.strftime("%Y%m%d", time.gmtime())
        hash_input = f"{user_id}:{chat_id}:{time.time()}"
        short_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:4].upper()
        return f"REG-{date_str}-{short_hash}"

    # ──────────────────────────────────────────────────────────
    #  Query extraction
    # ──────────────────────────────────────────────────────────

    def _extract_last_user_query(self, messages: list[dict]) -> str:
        """Extract the last user message, stripping injected graph context."""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str):
                    marker = "\n\n---\n[GRAPH KNOWLEDGE CONTEXT"
                    idx = content.find(marker)
                    return content[:idx].strip() if idx != -1 else content.strip()
                elif isinstance(content, list):
                    return " ".join(
                        p.get("text", "")
                        for p in content
                        if isinstance(p, dict) and p.get("type") == "text"
                    ).strip()
        return ""

    # ──────────────────────────────────────────────────────────
    #  Fallback extraction from response text
    # ──────────────────────────────────────────────────────────

    def _extract_confidence_from_response(self, response: str) -> dict:
        """Extract confidence score and band from the response disclaimer text.

        The graphrag_filter appends a disclaimer like:
          *This response is partially supported (composite confidence: 70%).*
          *...well-supported... (composite confidence: 92%).*

        This data should come from the message's graphrag_confidence property,
        but Open WebUI's frontend doesn't persist custom properties on message
        objects through the database cycle. So when the user clicks the
        escalation button, graphrag_confidence is gone. This method recovers
        it from the rendered response text as a reliable fallback.
        """
        if not response:
            return {}

        # Pattern: "composite confidence: XX%"
        match = re.search(r'composite confidence:\s*(\d+)%', response)
        if not match:
            return {}

        pct = int(match.group(1))
        score = round(pct / 100.0, 2)

        if score >= 0.85:
            band = "HIGH"
        elif score >= 0.60:
            band = "MODERATE"
        else:
            band = "LOW"

        return {"score": score, "band": band, "signals": {}}

    def _extract_citations_from_response(self, response: str) -> list[dict]:
        """Extract GraphRAG citation references from the response text.

        The response contains citation markers like [G1], [G2], and an
        Applicable Sections table with section references. This recovers
        the citation list so the email can display them even when the
        message's graphrag_citations property didn't persist.
        """
        if not response:
            return []

        # Find all [G<n>] markers
        markers = sorted(set(re.findall(r'\[G(\d+)\]', response)))
        if not markers:
            return []

        # Try to extract section titles from the Applicable Sections table
        # Pattern: | [G1] | §24-XX.XX | Description |
        section_map = {}
        table_pattern = re.compile(
            r'\|\s*\[G(\d+)\]\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|'
        )
        for m in table_pattern.finditer(response):
            idx = m.group(1)
            section_ref = m.group(2).strip()
            relevance = m.group(3).strip()
            section_map[idx] = {
                "index": int(idx),
                "section": section_ref,
                "id": section_ref,
                "content": relevance[:200],
            }

        # Also try heading-style citations: **Title** ([G1]):
        heading_pattern = re.compile(
            r'\*\*(.+?)\*\*\s*\(\[G(\d+)\]\)'
        )
        for m in heading_pattern.finditer(response):
            title = m.group(1).strip()
            idx = m.group(2)
            if idx not in section_map:
                section_map[idx] = {
                    "index": int(idx),
                    "section": title,
                    "id": f"G{idx}",
                    "content": "",
                }

        # Build citation list in order
        citations = []
        for idx_str in markers:
            if idx_str in section_map:
                citations.append(section_map[idx_str])
            else:
                citations.append({
                    "index": int(idx_str),
                    "section": f"Section G{idx_str}",
                    "id": f"G{idx_str}",
                    "content": "",
                })

        return citations

    # ──────────────────────────────────────────────────────────
    #  Case packet builder
    # ──────────────────────────────────────────────────────────

    def _build_case_packet(
        self,
        case_ref: str,
        reason: str,
        user_info: dict,
        query: str,
        response: str,
        messages: list[dict],
        chat_id: str,
        message_id: str,
        model: str,
        confidence_data: dict,
        user_reason: str = "",
    ) -> dict:
        """Build the case packet JSON for the n8n webhook.

        Matches the schema used by graphrag_filter's automatic escalation
        so both paths produce identical payloads for the reviewer.
        """
        # Clean conversation history (strip injected graph context)
        conversation_history = []
        for msg in (messages or []):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if isinstance(content, str):
                marker = "\n\n---\n[GRAPH KNOWLEDGE CONTEXT"
                idx = content.find(marker)
                if idx != -1:
                    content = content[:idx].strip()
            elif isinstance(content, list):
                content = " ".join(
                    p.get("text", "")
                    for p in content
                    if isinstance(p, dict) and p.get("type") == "text"
                )
            if content and role in ("user", "assistant", "system"):
                conversation_history.append({"role": role, "content": content})

        # Extract KB sources from the flagged assistant message
        kb_sources = []
        for msg in reversed(messages or []):
            if msg.get("role") == "assistant" and "sources" in msg:
                for src in msg["sources"]:
                    src_id = (src.get("source") or {}).get("id", "")
                    if src_id.startswith("graphrag_"):
                        continue
                    kb_sources.append(
                        {
                            "name": (src.get("source") or {}).get("name", "Unknown"),
                            "content": (src.get("document") or [""])[0][:2000],
                        }
                    )
                break

        # Extract GraphRAG citations stored on the message
        # (the filter stores these on the message dict during outlet)
        flagged_msg = None
        for msg in reversed(messages or []):
            if msg.get("role") == "assistant":
                flagged_msg = msg
                break

        graphrag_citations = []
        entity_matches = []
        graph_context = ""
        if flagged_msg:
            # Citations may be stored as graphrag_citations on the message
            graphrag_citations = flagged_msg.get("graphrag_citations", [])
            entity_matches = flagged_msg.get("graphrag_entity_matches", [])
            graph_context = flagged_msg.get("graphrag_context_injected", "")

        # ── Fallback: extract confidence from response text ──
        # Open WebUI's frontend doesn't persist custom properties
        # (graphrag_confidence) on message objects through the DB cycle.
        # When the user clicks escalate, that data is gone. Recover it
        # from the disclaimer text the filter appended to the response.
        conf_score = confidence_data.get("score")
        conf_band = confidence_data.get("band", "N/A")
        conf_signals = confidence_data.get("signals", {})

        if conf_score is None:
            fallback_conf = self._extract_confidence_from_response(response)
            if fallback_conf:
                conf_score = fallback_conf["score"]
                conf_band = fallback_conf["band"]
                conf_signals = fallback_conf.get("signals", {})

        # ── Fallback: extract citations from response text ──
        # Same persistence issue — recover [G1]...[Gn] references
        # and section titles from the rendered response.
        if not graphrag_citations:
            graphrag_citations = self._extract_citations_from_response(response)

        return {
            "case_ref": case_ref,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "user": {
                "id": user_info.get("id", ""),
                "email": user_info.get("email", ""),
                "name": user_info.get("name", ""),
                "role": user_info.get("role", ""),
            },
            "query": query,
            "response": response,
            "confidence": {
                "score": conf_score,
                "band": conf_band,
                "signals": conf_signals,
            },
            "escalation": {
                "reason": reason,
                "trigger": "manual",
                "target": self.valves.escalation_target,
                "threshold": None,  # Not applicable for manual
                "user_concern": user_reason,
            },
            "conversation_history": conversation_history,
            "retrieval_context": {
                "graphrag_citations": graphrag_citations,
                "kb_sources": kb_sources,
                "entity_matches": entity_matches,
                "graph_context_injected": graph_context,
            },
            "context": {
                "chat_id": chat_id,
                "message_id": message_id,
                "model": model,
            },
        }

    # ──────────────────────────────────────────────────────────
    #  Webhook sender
    # ──────────────────────────────────────────────────────────

    def _send_webhook(self, case_packet: dict) -> tuple[dict | None, str | None]:
        """POST case packet to the configured n8n webhook.

        Returns (parsed_response, None) on success,
        or (None, error_description) on failure.
        Fire-and-forget — 5-second timeout, never blocks the UI.
        """
        if not self.valves.escalation_webhook_url:
            return None, "No webhook URL configured — set it in Admin > Functions > Valves"
        try:
            data = json.dumps(case_packet, default=str).encode("utf-8")
            req = urllib.request.Request(
                self.valves.escalation_webhook_url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read().decode()), None
        except urllib.error.URLError as e:
            reason = str(e.reason) if hasattr(e, "reason") else str(e)
            return None, f"Connection failed: {reason}"
        except TimeoutError:
            return None, "Webhook timed out after 5 seconds"
        except Exception as e:
            return None, f"{type(e).__name__}: {str(e)}"

    # ──────────────────────────────────────────────────────────
    #  Audit trail writer
    # ──────────────────────────────────────────────────────────

    def _write_audit_record(
        self,
        case_ref: str,
        user: dict,
        chat_id: str,
        message_id: str,
        model: str,
        query: str,
        confidence_data: dict,
        webhook_ok: bool,
    ) -> None:
        """Write a manual escalation record to the audit SQLite DB.

        Uses the same audit_records table as the audit_logger filter,
        with escalation_triggered=1 and source='manual' in the
        case_packet_ref field.
        """
        try:
            conn = sqlite3.connect(self.valves.audit_db_path)

            # Ensure the table exists (idempotent — matches audit_logger schema)
            conn.execute(
                """
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
                """
            )

            record_id = str(uuid.uuid4())
            now = time.time()
            timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))

            # Build a hash for integrity
            hash_input = json.dumps(
                {"id": record_id, "case_ref": case_ref, "time": now},
                sort_keys=True,
                default=str,
            )
            record_hash = hashlib.sha256(hash_input.encode()).hexdigest()

            conn.execute(
                """
                INSERT INTO audit_records (
                    id, timestamp, epoch, user_id, user_email, user_name, user_role,
                    chat_id, message_id, session_id, model, query_text,
                    message_count, full_messages, response_text, response_model,
                    retrieval_record, citations,
                    confidence_score, confidence_signals,
                    escalation_triggered, escalation_target, case_packet_ref,
                    guardrail_triggered, guardrail_type, guardrail_reason,
                    record_hash
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?,
                    ?, ?,
                    ?, ?, ?,
                    ?, ?, ?,
                    ?
                )
                """,
                [
                    record_id,
                    timestamp,
                    now,
                    user.get("id", ""),
                    user.get("email", ""),
                    user.get("name", ""),
                    user.get("role", ""),
                    chat_id,
                    message_id,
                    "",  # session_id — not available in action context
                    model,
                    query,
                    0,  # message_count — not primary concern for manual escalation
                    "[]",  # full_messages — stored in case packet, not duplicated
                    "",  # response_text — stored in case packet
                    "",  # response_model
                    "",  # retrieval_record
                    "",  # citations
                    confidence_data.get("score"),
                    json.dumps(confidence_data.get("signals", {}), default=str),
                    1,  # escalation_triggered = True
                    self.valves.escalation_target,
                    json.dumps(
                        {
                            "case_ref": case_ref,
                            "source": "manual",
                            "webhook_sent": webhook_ok,
                            "timestamp": timestamp,
                        },
                        default=str,
                    ),
                    0,  # guardrail_triggered
                    None,  # guardrail_type
                    None,  # guardrail_reason
                    record_hash,
                ],
            )
            conn.commit()
            conn.close()
        except Exception:
            pass  # Never block the UI on audit failure
