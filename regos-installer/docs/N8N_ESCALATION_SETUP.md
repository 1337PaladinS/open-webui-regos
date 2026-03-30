# RegOS Escalation Pipeline — n8n Setup Guide

**Pipeline version:** 1.1.0
**Compatible with:** n8n Cloud & Self-hosted (v1.x+)
**Workflow file:** `regos_escalation_workflow.json`

---

## Overview

This n8n workflow receives escalation case packets from the RegOS GraphRAG filter (v0.10.0) and processes them through two parallel branches:

```
[GraphRAG Filter]
      │
      │ POST /regos-escalation (full context: conversation history,
      │   GraphRAG citations, KB sources, entity matches, confidence)
      ▼
┌─────────────────────────┐
│  Webhook: Receive        │
│  Escalation              │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  Code: Validate &        │
│  Enrich                  │
└────────┬────────┬───────┘
         │        │
    Branch 1   Branch 2
         │        │
         ▼        ▼
┌──────────┐ ┌──────────────┐
│ Generate │ │ Respond:     │
│ Raw Case │ │ Confirmation │
│ File     │ │ (JSON back   │
│          │ │  to webhook) │
└────┬─────┘ └──────────────┘
     │
     ▼
┌──────────┐
│ AI:      │
│ Generate │
│ Case     │
│ Brief    │
└────┬─────┘
     │
     ▼
┌──────────┐
│ No-Op    │
│ (future  │
│ actions) │
└──────────┘
```

**Branch 1 (Store + Summarize):** Generates a raw case file with complete context (downloadable JSON), then passes it to an AI node that compresses everything into a structured 1-page case brief. Both the raw dump and the AI brief are available in execution history.

**Branch 2 (Respond):** Immediately returns a JSON confirmation to the GraphRAG filter so the webhook call completes quickly.

---

## Quick Start: Import the Workflow

1. Open your n8n instance
2. Go to **Workflows** → click **"+"** (new workflow) → click the **"..."** menu → **Import from File**
3. Select `regos_escalation_workflow.json`
4. The workflow appears with all 6 nodes pre-configured
5. Click **Save**, then toggle the workflow to **Active**
6. Copy the webhook URL (shown in the Webhook node) — you'll need it for Open WebUI

---

## Connect to Open WebUI

Once the workflow is active, copy the production webhook URL from the Webhook node. It will look like:

```
https://your-instance.app.n8n.cloud/webhook/regos-escalation
```

In Open WebUI:

1. Go to **Admin** → **Functions** → **RegOS GraphRAG Filter**
2. Open **Valves**
3. Paste the webhook URL into **`escalation_webhook_url`**
4. Save

That's it. The next time a query triggers low-confidence escalation, the case packet will flow to n8n.

---

## Node-by-Node Guide

### Node 1: Webhook — Receive Escalation

**Type:** `n8n-nodes-base.webhook`
**Method:** POST
**Path:** `/regos-escalation`
**Response Mode:** Using "Respond to Webhook" node

This is the entry point. The GraphRAG filter POSTs a JSON case packet here whenever escalation triggers. The response mode is set to "Using Respond to Webhook node" so we can process the data before responding.

**Incoming payload structure (v1.1.0 — full context):**

```json
{
  "case_ref": "REG-20260224-7A3F",
  "timestamp": "2026-02-24T14:30:00Z",
  "user": { "id": "...", "email": "...", "name": "...", "role": "..." },
  "query": "What are the BOD limits for industrial discharge?",
  "response": "The LLM's full response...",
  "confidence": { "score": 0.32, "band": "LOW", "signals": { ... } },
  "escalation": { "reason": "...", "target": "compliance-review", "threshold": 0.5 },
  "conversation_history": [
    { "role": "user", "content": "Earlier question..." },
    { "role": "assistant", "content": "Earlier answer..." },
    { "role": "user", "content": "Follow-up that triggered escalation..." },
    { "role": "assistant", "content": "Low-confidence response..." }
  ],
  "retrieval_context": {
    "graphrag_citations": [ { "index": 1, "section": "Sec. 24-42.4...", "content": "Full text..." } ],
    "kb_sources": [ { "name": "Chapter 24 chunk...", "content": "KB text..." } ],
    "entity_matches": [ { "name": "BOD", "score": 6.74, "summary": "..." } ],
    "graph_context_injected": "The full context block that was injected into the LLM..."
  },
  "context": { "chat_id": "...", "message_id": "...", "model": "..." }
}
```

The payload includes **complete context**: the full conversation history (all user/assistant turns in the chat), all GraphRAG citations with full section text, any KB sources from ChromaDB, entity matches from the graph search, and the assembled graph context that was injected into the LLM prompt.

### Node 2: Code — Validate & Enrich

**Type:** `n8n-nodes-base.code`

Validates that the required fields are present (case_ref, timestamp, user, query, confidence, escalation) and enriches the packet with pipeline metadata:

```json
"pipeline": {
  "received_at": "2026-02-24T14:30:01Z",
  "workflow_version": "1.0.0",
  "status": "received",
  "reviewer_assigned": null,
  "resolution": null
}
```

If required fields are missing, the node throws an error — this will show up in n8n's execution history as a failed execution, making it easy to debug.

### Node 3: Code — Generate Raw Case File (Branch 1)

**Type:** `n8n-nodes-base.code`

Generates a complete raw case file with all context and creates a downloadable JSON binary:

- Full conversation history (all turns, with injected graph context stripped)
- All GraphRAG citations with full section text
- KB sources from ChromaDB
- Entity matches from graph search
- Confidence signals and escalation reason
- Truncated response preview + full response

The output has both `json` (visible in execution data) and `binary` (downloadable as `REG-YYYYMMDD-XXXX_raw.json`).

### Node 4: AI — Generate Case Brief (Branch 1 continued)

**Type:** `n8n-nodes-base.code` (uses `fetch` to call an AI API)

Takes the complete raw dump and compresses it into a structured case brief using an AI model. The brief has 6 sections:

1. **One-Line Summary** — What the user asked and why it was escalated
2. **Risk Assessment** — What could go wrong if the response is incorrect
3. **What the AI Got Right** — Parts supported by citations
4. **What's Missing or Wrong** — Gaps, unsupported claims, errors
5. **Recommended Reviewer Action** — What to check or do
6. **Suggested Response Improvement** — How RegOS should ideally answer

**SETUP REQUIRED:** Edit the Code node and set three variables at the top:

```javascript
const AI_API_URL = 'https://api.openai.com/v1/chat/completions'  // or Anthropic, Google, etc.
const AI_API_KEY = 'sk-...'  // your API key
const AI_MODEL = 'gpt-4o-mini'  // or 'claude-sonnet-4-20250514', etc.
```

If no AI API is configured, the node generates a placeholder brief with basic stats (conversation turns, citation count, etc.) and passes through. The raw data is always preserved regardless.

**Cost note:** Each case brief uses ~1000-2000 input tokens and ~500 output tokens. At GPT-4o-mini pricing, this is roughly $0.001-0.002 per escalation.

### Node 5: Respond — Confirmation (Branch 2)

**Type:** `n8n-nodes-base.respondToWebhook`

Returns a JSON response to the GraphRAG filter:

```json
{
  "status": "received",
  "case_ref": "REG-20260224-7A3F",
  "message": "Case received. A reviewer will be assigned within 24 hours.",
  "timestamp": "2026-02-24T14:30:01Z"
}
```

This response is currently captured by the filter but not displayed to users. In a future version, the response could include a reviewer name or ticket URL.

### Node 6: No Operation (Placeholder)

**Type:** `n8n-nodes-base.noOp`

A placeholder at the end of Branch 1 for future expansion. At this point, the item has both `raw_case_file` (complete dump) and `case_brief` (AI-generated summary). You can replace or extend this with:

- **Email node:** Send the AI brief + raw file to the review team
- **Slack node:** Post the one-line summary to `#compliance-review`
- **HTTP Request node:** Create a ticket in Jira/Linear/Asana with the brief as description
- **Database node:** Write to PostgreSQL/MySQL for a proper case management system

---

## Testing the Pipeline

### Test 1: Manual webhook test from n8n

1. Open the Webhook node
2. Click **"Listen for test event"** (or use the Test tab)
3. In a terminal, run:

```bash
curl -X POST https://your-instance.app.n8n.cloud/webhook-test/regos-escalation \
  -H "Content-Type: application/json" \
  -d '{
    "case_ref": "REG-20260224-TEST",
    "timestamp": "2026-02-24T12:00:00Z",
    "user": {
      "id": "test-user-001",
      "email": "test@apas.ai",
      "name": "Test Reviewer",
      "role": "admin"
    },
    "query": "What are the BOD limits?",
    "response": "Based on the retrieved regulatory context, the BOD limits for industrial discharge are governed by Section 24-42.4...",
    "confidence": {
      "score": 0.32,
      "band": "LOW",
      "signals": {
        "entity_scores": [6.74, 5.53],
        "entity_count": 2,
        "section_entity_counts": [1],
        "final_section_count": 1,
        "score": 0.32,
        "band": "LOW"
      }
    },
    "escalation": {
      "reason": "Low retrieval confidence (32%): weak entity matching, sparse section retrieval",
      "target": "compliance-review",
      "threshold": 0.5
    },
    "conversation_history": [
      { "role": "user", "content": "I need help with our industrial discharge permit" },
      { "role": "assistant", "content": "I can help with Miami-Dade Chapter 24 industrial discharge requirements. What specific aspect are you looking at?" },
      { "role": "user", "content": "What are the BOD limits?" },
      { "role": "assistant", "content": "Based on the retrieved regulatory context, the BOD limits for industrial discharge are governed by Section 24-42.4..." }
    ],
    "retrieval_context": {
      "graphrag_citations": [
        {
          "index": 1,
          "section": "Sec. 24-42.4 Sanitary sewer discharge limitations",
          "content": "No user shall discharge wastewater containing in excess of the following daily maximum allowable concentrations..."
        }
      ],
      "kb_sources": [
        {
          "name": "Chapter 24 - Section 42 - Prohibitions",
          "content": "It shall be unlawful for any person to throw, drain, run or otherwise discharge..."
        }
      ],
      "entity_matches": [
        { "name": "BOD", "score": 6.74, "summary": "Biochemical oxygen demand - measure of organic pollution in wastewater" },
        { "name": "Industrial user", "score": 5.53, "summary": "A source of indirect discharge that introduces pollutants" }
      ],
      "graph_context_injected": "=== GRAPH-RETRIEVED REGULATORY CONTEXT === ..."
    },
    "context": {
      "chat_id": "test-chat-001",
      "message_id": "test-msg-001",
      "model": "gemini-2.5-pro"
    }
  }'
```

4. You should see the execution complete successfully with both branches
5. Click the "Code: Generate Case File" node output to see the formatted case
6. The response should be:

```json
{
  "status": "received",
  "case_ref": "REG-20260224-TEST",
  "message": "Case received. A reviewer will be assigned within 24 hours.",
  "timestamp": "..."
}
```

### Test 2: End-to-end from Open WebUI

1. Set `escalation_webhook_url` in GraphRAG filter Valves to your production webhook URL
2. Ask a vague query in Open WebUI (e.g., "tell me about water" — should trigger LOW confidence)
3. Check that:
   - The escalation notice appears in the chat (not the disclaimer)
   - n8n shows a successful execution
   - The case file is generated with all fields populated

### Test 3: Failure resilience

1. Set `escalation_webhook_url` to an invalid URL (e.g., `https://invalid.example.com/webhook`)
2. Ask a low-confidence query
3. Verify:
   - The chat still works (not blocked)
   - The escalation notice still appears
   - The audit DB still gets flagged
   - No error is visible to the user

---

## Reviewing Escalation Cases

Until a full dashboard (Feature 7) is built, reviewers can access cases through n8n:

1. Open your n8n instance
2. Go to **Executions** (left sidebar)
3. Filter by the "RegOS Escalation Pipeline" workflow
4. Each execution = one escalation case
5. Click an execution to see:
   - **Webhook node output:** Raw case packet from Open WebUI (full context)
   - **Validate & Enrich output:** Enriched data with pipeline metadata
   - **Generate Raw Case File output:** Complete dump + downloadable JSON
   - **AI: Generate Case Brief output:** The `case_brief` field contains the AI-compressed summary with risk assessment, gap analysis, and recommended actions
6. Download the raw case file from the binary output of "Generate Raw Case File"
7. Read the AI brief directly in the "AI: Generate Case Brief" node output — no download needed

---

## Expanding the Pipeline

The workflow is designed to be extended. Common next steps:

### Add email notifications

Replace the No-Op node with an **Email Send** node:
- To: `compliance-team@apas.ai`
- Subject: `Escalation: {{ $json.case_ref }} — {{ $json.escalation_reason }}`
- Body: Include query, confidence score, and a link to the n8n execution

### Add Slack notifications

Add a **Slack** node after Generate Case File:
- Channel: `#compliance-review`
- Message: Case ref, user email, query preview, confidence score

### Add persistent database storage

Replace Write Binary File with a **PostgreSQL/MySQL** node:
- Table: `escalation_cases`
- Fields: case_ref, timestamp, user_email, query, confidence_score, reason, status

### Add reviewer assignment

Add a **Code** node that assigns cases round-robin to a list of reviewers, then sends targeted notifications.

---

## Troubleshooting

**Webhook returns 404:**
The workflow isn't active. Toggle it to Active in n8n.

**Webhook returns 500:**
Check the execution history for errors. Most likely a required field is missing from the case packet.

**No executions appearing:**
Verify the webhook URL in Open WebUI Valves matches the production URL (not the test URL). Production URLs don't have `-test` in them.

**Case file not downloadable:**
On n8n Cloud, filesystem writes are not available. The case file is stored as a binary attachment on the "Generate Raw Case File" node output — download it from the execution history.

**AI brief says "not configured":**
Edit the "AI: Generate Case Brief" Code node and set `AI_API_URL`, `AI_API_KEY`, and `AI_MODEL` at the top of the script. The node works as a passthrough with a placeholder brief until configured.

**GraphRAG filter not sending:**
Check that `escalation_webhook_url` is set in Valves, `escalation_enabled` is true, and the query actually triggers LOW confidence. Try a very vague query like "water" or "regulations."
