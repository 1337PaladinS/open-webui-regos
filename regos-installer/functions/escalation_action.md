# escalation_action.py — Manual Escalation Action

## Status: Active (v1.0.0)

An Open WebUI **Action** that allows users to manually flag any RegOS response for expert compliance review. Registered as a clickable action button on chat messages.

## What It Does

When triggered by a user:

1. Builds a full-context case packet (user info, query, response, conversation history, GraphRAG citations, confidence data, escalation reason)
2. POSTs the case packet to the n8n escalation workflow via configurable webhook URL
3. Writes an audit trail entry to the SQLite audit database
4. Generates a case reference (REG-YYYYMMDD-XXXX) using SHA-256 hash

## Relationship to Automatic Escalation

This is the **manual** complement to the automatic escalation in `graphrag_filter.py` (Feature 5, v0.9.0+). Automatic escalation triggers on low confidence scores; this Action lets users escalate even when confidence is high but they have domain-specific concerns.

## Configuration (Valves)

- `escalation_webhook_url` — n8n webhook endpoint
- `audit_db_path` — path to SQLite audit database
- `escalation_target` — default target label (e.g., "compliance-review")
