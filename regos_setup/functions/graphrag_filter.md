# GraphRAG Filter — RegOS Chapter 24

**Type:** Filter (inlet + outlet)
**Version:** 0.17.3
**Status:** Production. FEA schema with document fulltext search, entity matching, concept expansion, and 6-signal confidence scoring. Full audit trail support.
**File:** `graphrag_filter.py`
**Depends on:** Neo4j Aura (online), `neo4j` Python package in container, `regulatory_thresholds.json` in container at `/app/backend/data/`
**Companion file:** `system_prompt.md` — the custom model's system prompt (handles identity, tone, response structure, threshold data handling)

---

## What it does

The GraphRAG Filter intercepts every user message, searches a Neo4j knowledge graph for relevant Miami-Dade County Chapter 24 regulatory sections, and injects them into the user's message as additional context. The LLM then answers using both this graph-retrieved context AND the Knowledge Base (ChromaDB) context that Open WebUI injects separately.

After retrieval, the filter:

1. **Computes a confidence score** (0.0–1.0) based on 6 weighted signals from the retrieval pipeline
2. **Displays confidence** as a clean percentage in the compliance disclaimer footer
3. **Writes confidence data** to the audit database via a hidden HTML comment
4. **Injects GraphRAG sources** into the Sources Panel so they appear alongside KB sources with `[G1]`, `[G2]` nomenclature
5. **Appends a retrieval trace** (optional) showing the full 4-step pipeline output with a human-readable confidence breakdown

---

## Architecture: System Prompt + Filter (v0.7.0+)

Starting in v0.7.0, the enterprise formatting responsibilities are split between two files:

| Responsibility | Where | Why |
|---|---|---|
| Identity, tone, persona awareness | `system_prompt.md` (custom model system prompt) | These are stable instructions that define RegOS's personality and response structure. They don't change per-request. |
| Citation mechanics (`[G1]`, `[G2]`, etc.) | `graphrag_filter.py` (`_enterprise_format_instructions()`) | These are dynamic — they only apply when graph context is retrieved, and reference the specific sections found. |
| Confidence badge, disclaimer, trace | `graphrag_filter.py` (outlet) | These are computed per-request from retrieval signals. |
| Sources Panel entries | `graphrag_filter.py` (outlet) | GraphRAG sources are appended to the message's existing sources list. |

The system prompt handles: 3 personas (Citizen, Consultant, Regulator), response structure (Summary → Regulatory Analysis → Applicable Sections → What You Need To Do → Gaps & Limitations), scope boundaries, honesty rules, conversational handling, and tone.

The filter handles: everything that depends on the actual retrieval results.

---

## How it works — the 4-step retrieval pipeline

When a user asks a question, the filter runs a 4-step pipeline against the Neo4j knowledge graph (FEA schema v0.17.3). Here's a real trace from the query **"What are the BOD limits for industrial discharge?"** (total time: 826ms):

### Step 1: Document Fulltext Search (287ms)

The filter takes the user's question and runs a fulltext search against the `ch24_doc_fulltext` index, which indexes **Ch24Document** nodes by title and content. This finds regulatory document sections directly by text relevance.

**Real output:**

| # | Section | Score | Result Type |
|---|---|---|---|
| 1 | Sec. 24-42.4 Sanitary sewer discharge limitations | 8.62 | sectionId, title, content |
| 2 | Sec. 24-42.1 Tertiary treatment requirements | 7.51 | sectionId, title, content |
| 3 | Sec. 24-44.2 Compliance tests | 6.28 | sectionId, title, content |
| 4 | Sec. 24-42 Prohibitions against water pollution | 5.94 | sectionId, title, content |
| 5 | Sec. 24-20 Abnormal occurrences | 5.42 | sectionId, title, content |

**Key difference from v0.16:** Steps 1–2 are now a single consolidated document search (no separate entity search table first).

### Step 2a: Entity Name Matching (98ms)

The filter extracts key terms from the query ("BOD", "industrial", "discharge") and matches them against **Ch24Entity.value** properties. This step identifies the regulatory concepts involved.

**Real output:**

| # | Entity Name | Type | Match Confidence |
|---|---|---|---|
| 1 | BOD | Concept | High |
| 2 | Industrial user | Actor | High |
| 3 | industrial waste treatment plant | Entity | Medium |

### Step 2b: Entity → Document Traversal (142ms)

The filter traverses **MENTIONS_ENTITY** relationships backward from matched Ch24Entity nodes to find which Ch24Document sections mention these entities. This is pure graph traversal with no text search.

**Real output:**

| # | Section | Mentioned Entities | Count |
|---|---|---|---|
| 1 | Sec. 24-42.4 Sanitary sewer discharge limitations | Industrial user, BOD, Categorical industrial user | 3 |
| 2 | **Sec. 24-42.1 Tertiary treatment requirements** | **BOD, nutrient removal, industrial waste treatment plant** | **3** |
| 3 | Sec. 24-44.2 Compliance tests | BOD, sampling | 2 |

### Step 2c: Concept Expansion (199ms)

The filter takes the top 3 document matches from Step 2b, finds their **RELATES_TO_CONCEPT** connections to **Ch24Class** nodes, then searches for sibling documents connected to the same concepts. Documents are included if their concept similarity is >= 0.3.

**Real output — concept bridge discovery:**

From Sec. 24-42.1's concepts, the filter discovers:
- Sec. 24-42.4 also relates to "discharge limitations" (similarity: 0.78) ← **conceptually linked**
- Sec. 24-44.2 also relates to "compliance testing" (similarity: 0.65) ← **added context**
- Sec. 24-22 relates to "pretreatment" (similarity: 0.42) ← **borderline relevance**

**This is where the graph adds maximum value.** Documents are connected not just by entities, but by the regulatory concepts they regulate. A text search for "BOD limits" might miss Sec. 24-42.4 (which focuses on "discharge limitations"), but the concept graph bridges them.

### Step 3: Direct Fulltext Search (102ms)

As a safety net, the filter also runs a second fulltext search on the same `ch24_doc_fulltext` index with a different query formulation (synonyms, phrase variants). This catches documents that Steps 1–2c might have missed.

**Real output:**

| # | Section | Score |
|---|---|---|
| 1 | Sec. 24-42.4 Sanitary sewer discharge limitations | 6.94 |
| 2 | Sec. 24-42.1 Tertiary treatment requirements | 6.18 |
| 3 | Sec. 24-21 Operating records | 4.67 |

### Step 4: Context Assembly (198ms)

The filter combines results from Steps 2b, 2c, and 3, deduplicates by sectionId, and takes the top N sections (configurable, default 5).

**Final assembly:**

- **[G1]** Sec. 24-42.4 — Sanitary sewer discharge limitations and pretreatment standards
- **[G2]** Sec. 24-42.1 — Tertiary treatment requirements ← **the key section with BOD limits**
- **[G3]** Sec. 24-44.2 — Compliance tests, sampling points and methods
- **[G4]** Sec. 24-22 — Circumvention unlawful
- **[G5]** Sec. 24-21 — Operating records

---

## Sources Panel Integration (v0.8.0)

GraphRAG-retrieved sections now appear in Open WebUI's **Sources button** (the expandable panel below each response) alongside Knowledge Base sources. This gives users a unified view of all retrieval sources.

### How it looks

When a user asks a regulatory question, the Sources panel shows:

- **Items 1–7** (typical): KB sources from ChromaDB embedding similarity
- **Items 8–12** (typical): GraphRAG sources labeled `[G1] Sec. 24-42.4 ...`, `[G2] Sec. 24-42.1 ...`, etc.

Each GraphRAG source entry includes the full section content, making it expandable and readable in the UI.

### How it works (technically)

The outlet method directly sets `body["messages"][-1]["sources"]` on the assistant's message. By the time the outlet runs, KB sources are already populated on the message. The filter reads the existing list, appends GraphRAG source objects, and writes it back.

```python
# In outlet — after KB sources are already on the message
existing_sources = messages[i].get("sources", [])
for c in self._citations:
    existing_sources.append({
        "source": {
            "id": f"graphrag_{c.get('id', c.get('uuid', str(c['index'])))}",
            "name": f"[G{c['index']}] {c['section']}",
        },
        "document": [c.get("content", "")],
        "metadata": [{"source": c["section"], "name": f"[G{c['index']}] {c['section']}"}],
    })
messages[i]["sources"] = existing_sources
```

### Source object format

Open WebUI expects each source to have this structure:

```json
{
    "source": {"id": "graphrag_<uuid>", "name": "[G1] Sec. 24-42.4 ..."},
    "document": ["<full section text>"],
    "metadata": [{"source": "Sec. 24-42.4 ...", "name": "[G1] Sec. 24-42.4 ..."}]
}
```

### Why this approach works (and 5 others didn't)

Getting GraphRAG sources into the Sources panel was the hardest integration challenge in this project. Six approaches were attempted over multiple sessions before finding the working solution. See the **Sources Panel — Development Journey** section at the end of this document for the full narrative.

**The key insight:** The outlet can directly mutate `body["messages"][-1]["sources"]` because by that point, the message object is the same Python dict that gets persisted. No middleware changes are needed. This approach was confirmed by the [Open WebUI community](https://github.com/open-webui/open-webui/discussions/16099).

### Zero middleware modifications

This feature requires **no changes to middleware.py**. The entire integration lives in the filter's outlet method. This is critical for maintainability — Open WebUI upgrades won't break the integration.

---

## Confidence Scoring (v0.6.0)

After retrieval completes, the filter computes a confidence score that reflects how well the retrieval pipeline matched the user's query. This score is:

1. **Displayed as a clean percentage** in the compliance disclaimer (e.g., `Source confidence: 73%`)
2. **Injected into the LLM context** so the model knows how confident the retrieval is (LOW confidence triggers hedging language)
3. **Written to the audit database** via a hidden HTML comment that the audit logger parses
4. **Explained in trace mode** with a human-readable breakdown table showing how each signal contributed

### The 6 Scoring Signals

Each signal is normalized to 0.0–1.0, then combined with fixed weights:

| Signal | Weight | What it measures | How it's normalized |
|---|---|---|---|
| `avg_doc_score` | **0.30** | Average fulltext search score from Step 1 (document search). Higher scores = strong textual relevance to regulatory content. | `min(avg(scores) / 10.0, 1.0)` — Neo4j fulltext scores above 10 are excellent |
| `doc_count` | **0.15** | How many unique documents were found across all steps. More documents = broader coverage. | `min(count / max_results, 1.0)` — capped at configured limit (default 5–8) |
| `concept_expansion` | **0.25** | The graph advantage: ratio of documents found via concept bridging (Step 2c) to total documents. High ratio = strong concept connectivity. | `min(concept_count / doc_count, 1.0)` if doc_count > 0, else `0.0` |
| `section_count` | **0.12** | How many unique sections were assembled into final context. 5/5 = full coverage, 1/5 = sparse. | `min(count / max_sections, 1.0)` |
| `has_graph_exclusive` | **0.10** | Whether the entity traversal (Step 2b) or concept expansion (Step 2c) found sections that direct text search (Steps 1 & 3) did NOT find. Pure graph-added value. | `1.0` if graph found exclusive sections, `0.0` otherwise |
| `avg_direct_score` | **0.08** | Average relevance score from Step 3 (direct fulltext search). Confirms the query has redundant text-level relevance. | `min(avg(scores) / 10.0, 1.0)` |

### The Formula

```
confidence = 0.30 × avg_doc_score
           + 0.15 × doc_count
           + 0.25 × concept_expansion
           + 0.12 × section_count
           + 0.10 × has_graph_exclusive
           + 0.08 × avg_direct_score
```

The result is clamped to [0.0, 1.0] and rounded to 2 decimal places.

### Confidence Bands

| Range | Band | Meaning |
|---|---|---|
| 0.70–1.00 | HIGH | Strong document scores, excellent concept connectivity, good coverage. The retrieval found highly relevant sections with graph-assisted discovery. |
| 0.45–0.69 | MEDIUM | Decent document matches but gaps in concept expansion or coverage. Answer is likely useful but may miss related content or nuance. |
| 0.00–0.44 | LOW | Weak text or concept signals, minimal graph advantage. The LLM is told to hedge its answer and recommend verifying with original regulatory text. |

### Confidence display

The confidence score appears in two places:

1. **In the response disclaimer** — clean italicized text: `Source confidence: 73%`
2. **In the trace** (when `show_trace` is ON) — a human-readable breakdown table with columns: "What we measured", "Result", "Contribution", "Why it matters". Each row explains one of the 6 signals in plain English.

### How Confidence Reaches the Audit Database

The GraphRAG filter and audit logger are separate filter instances — they can't share memory. Starting in v0.17.3, confidence data is transported via **message metadata dict** (primary) with HTML comment fallback (legacy):

**Primary transport (v0.17.3+) — metadata dict:**
```python
# GraphRAG filter sets this on the message object
messages[-1]["metadata"]["graphrag_confidence"] = {
    "score": 0.67,
    "band": "MEDIUM",
    "signals": {
        "avg_doc_score": 0.72,
        "doc_count": 0.80,
        "concept_expansion": 0.65,
        "section_count": 0.60,
        "has_graph_exclusive": 1.0,
        "avg_direct_score": 0.55
    }
}
```

**Legacy transport (fallback) — HTML comment:**
```
[LLM response text]
<!-- GRAPHRAG_CONFIDENCE:{"score":0.67,"band":"MEDIUM","signals":{...}} -->

---
*This is an AI-generated draft analysis... Source confidence: 67%...*
```

The audit logger's outlet:
1. Checks for `messages[-1]["metadata"]["graphrag_confidence"]` (preferred)
2. Falls back to regex-parsing `<!-- GRAPHRAG_CONFIDENCE:... -->` if metadata is missing
3. Extracts `score` → writes to `audit_records.confidence_score` (REAL)
4. Extracts `signals` → writes to `audit_records.confidence_signals` (JSON TEXT)
5. If using HTML comment: strips it from the response so the user never sees it

**Note:** The audit logger must have a higher `priority` number than the GraphRAG filter to run after it in the outlet phase. If priorities are misconfigured, the HTML comment may be visible to users.

---

## Enterprise Output Formatting (v0.7.0)

Informed by the **RegOS Expert-Mode Workflow Spec** (practicing consultant interview). The formatting is designed so that outputs serve all three RegOS personas: citizens get plain-language guidance, consultants get actionable checklists with citations, and regulators can verify every claim against the code.

When `enterprise_format` is ON (default), the LLM is instructed to produce every response in this structure:

```
**[GraphRAG + KB]**

### Summary
One-paragraph plain-English answer. No jargon without explanation.
A citizen should understand this; a consultant should be able to act on it immediately.

### Regulatory Analysis
Detailed findings with inline citations [G1], [G2], etc.
Exact regulatory language quoted for limits, requirements, definitions.
Written like a senior consultant briefing a client — not just what the code says,
but what the user needs to DO.

### Applicable Sections
| Ref | Section | Relevance |
|-----|---------|-----------|
| [G1] | Sec. 24-42.4 | Sanitary sewer discharge limitations |
| [G2] | Sec. 24-42.1 | Tertiary treatment requirements |

### What You Need To Do
- Concrete action item 1 (e.g., "Submit Form X")
- Concrete action item 2 (e.g., "Meet BOD limit of 300 mg/l per [G1]")
- ...

### Gaps & Limitations
- What this response does NOT cover
- Site-specific context that would change the answer
- Areas where engineering judgment is needed beyond the code

---
[Conditional disclaimer — see below]
```

### Conditional Disclaimer System (v0.8.1)

The disclaimer adapts to the retrieval state — confident when retrieval is strong, specific about gaps when it's not. No state ever says "consult qualified professionals" or "not a final compliance determination." RegOS is built by consultants, for consultants.

| State | Trigger | Example |
|---|---|---|
| **HIGH** | confidence ≥80% AND sections = max | *RegOS regulatory analysis — Miami-Dade Chapter 24, Sections [G1]–[G5]. Source confidence: 85%. Review cited sections for your specific facility context.* |
| **MEDIUM** | confidence 50–79% OR partial retrieval | *RegOS regulatory analysis — Miami-Dade Chapter 24. Source confidence: 67% — some applicable sections may not have been retrieved. Cross-check critical requirements against the full regulation text for completeness.* |
| **LOW** | confidence <50% OR ≤1 section retrieved | *Limited regulatory context was retrieved for this query (source confidence: 32%). Verify this analysis against the full Chapter 24 text. Provide more specific details about your compliance question for a stronger analysis.* |

The system uses two signals: `confidence_band` (HIGH/MEDIUM/LOW) and `n_sections` (number of citations retrieved vs. `max_sections` valve). The logic is implemented in `_build_disclaimer()`.

### Design principles (from Expert-Mode Workflow Spec)

The formatting enforces four principles from the consultant interview:

1. **Source of truth discipline** — every requirement must have a code citation, or explicitly say "I don't have enough information; here's what to provide."
2. **Actionable guidance** — not just "here's the law" but "here's what you need to do." The "What You Need To Do" section turns regulatory text into a compliance checklist.
3. **Gap awareness** — the "Gaps & Limitations" section forces the model to state what it does NOT know. This prevents the invisible failure mode where users assume completeness.
4. **Professional framing** — disclaimers frame verification as standard professional workflow, not a product deficiency. RegOS positions itself as a regulatory analysis tool, not a liability hedge.

When `enterprise_format` is OFF, the LLM reverts to free-form prose with no disclaimer footer.

---

## How compounding works: GraphRAG + Knowledge Base

When a user asks a question to a model that has both the GraphRAG Filter enabled and a Knowledge Base attached, the LLM receives context from two independent retrieval systems:

```
User: "What treatment standards apply to facilities near the Everglades?"
                │
                ▼
    ┌───────────────────────┐
    │   GraphRAG Filter      │
    │   (inlet)              │
    │                        │
    │   Entity search finds: │
    │   - Bird Drive Basin   │
    │     Plan (6.11)        │
    │   - industrial waste   │
    │     treatment plant    │
    │     (5.27)             │
    │   - sewage treatment   │
    │     plant (4.47)       │
    │                        │
    │   Graph traversal      │
    │   finds:               │
    │   Sec. 24-48.21 (3 ent)│
    │   Sec. 24-42.1 (2 ent) │ ← Tertiary treatment limits
    │   Sec. 24-42 (2 ent)   │
    │                        │
    │   Confidence: MEDIUM   │
    │   (0.67)               │
    │                        │
    │   Injects as [G1]–[G5] │
    │   into user message    │
    └───────────┬───────────┘
                │
                ▼
    ┌───────────────────────┐
    │   Open WebUI RAG       │
    │   (Knowledge Base)     │
    │                        │
    │   ChromaDB finds text- │
    │   similar chunks via   │
    │   embedding similarity │
    │                        │
    │   Injects as <source>  │
    │   tags in system msg   │
    └───────────┬───────────┘
                │
                ▼
    ┌───────────────────────┐
    │   LLM                  │
    │                        │
    │   Sees BOTH:           │
    │   - [G1]–[G5] from    │
    │     graph traversal    │
    │   - <source> chunks    │
    │     from KB text match │
    │                        │
    │   Synthesizes answer   │
    │   citing both sources  │
    │                        │
    │   Prefixes response:   │
    │   **[GraphRAG + KB]**  │
    └───────────┬───────────┘
                │
                ▼
    ┌───────────────────────┐
    │   GraphRAG Filter      │
    │   (outlet)             │
    │                        │
    │   1. Appends GraphRAG  │
    │      sources to the    │
    │      message's sources │
    │      list (KB sources  │
    │      already present)  │
    │                        │
    │   2. Appends hidden    │
    │      confidence HTML   │
    │      comment for audit │
    │                        │
    │   3. Appends disclaimer│
    │      with confidence % │
    │                        │
    │   4. Appends trace     │
    │      (if show_trace ON)│
    └───────────────────────┘
```

---

## Valve configuration

| Valve | Default | Description |
|---|---|---|
| `neo4j_uri` | `neo4j+s://11d95839.databases.neo4j.io` | Neo4j Aura connection URI |
| `neo4j_username` | `neo4j` | Neo4j username |
| `neo4j_password` | *(empty — must set)* | Neo4j password. Filter silently passes through if empty. |
| `neo4j_database` | `neo4j` | Neo4j database name |
| `max_sections` | `5` | Max regulatory sections to include |
| `max_section_chars` | `2000` | Max characters per section |
| `entity_search_limit` | `8` | Max entities from fulltext search |
| `min_relevance_score` | `0.5` | Minimum fulltext score threshold |
| `priority` | `0` | Filter execution priority (lower = first) |
| `enabled` | `true` | Master on/off switch |
| `debug` | `false` | Append debug info to the injected context |
| `show_trace` | `false` | Append full retrieval trace to the LLM response |
| `show_confidence` | `true` | Show confidence score badge on responses |
| `enterprise_format` | `true` | Structured consultant-style output with compliance disclaimer |
| `escalation_enabled` | `true` | Auto-flag low-confidence queries for expert review |
| `escalation_threshold` | `0.5` | Confidence score below which escalation triggers |
| `escalation_target` | `compliance-review` | Target identifier for dashboard grouping and future routing |
| `escalation_webhook_url` | *(empty)* | n8n webhook URL for escalation. If empty, escalation only flags the audit DB. |

---

## Escalation Workflow (v0.9.0 → v0.10.0)

When confidence is below the configured threshold, the filter automatically flags the query for expert review. In v0.10.0, escalation was upgraded from audit-DB-only flagging to a full end-to-end pipeline that POSTs a case packet to an n8n webhook for processing.

### What triggers escalation

Escalation fires when ANY of these conditions are true:

- Confidence score < `escalation_threshold` (default 0.5, i.e. the LOW band)
- Zero sections retrieved (no regulatory context found at all)
- Confidence band is LOW regardless of exact score

Escalation does NOT fire when:

- `escalation_enabled` is False
- No confidence data exists (non-regulatory query, GraphRAG skipped)
- Confidence is MEDIUM or HIGH

### What happens when escalation triggers

1. **Case packet is built** — `_build_case_packet()` assembles a rich JSON payload with everything a reviewer needs: user info, query, response, all 6 confidence signals, escalation reason, citations, and context.
2. **Webhook fires** — `_send_escalation_webhook()` POSTs the case packet to the configured n8n webhook URL. This is fire-and-forget — if n8n is down, the chat is unaffected.
3. **Notice replaces disclaimer** — The structured escalation notice is appended to the response INSTEAD of the normal disclaimer (not stacked on top).
4. **Audit DB flagged** — Escalation metadata is stored on the message dict for the audit logger to write.

### n8n Webhook Integration (v0.10.0)

The `escalation_webhook_url` Valve configures the n8n endpoint. When set, each escalation POSTs a JSON case packet. When empty, escalation only flags the audit DB (backward-compatible with v0.9.0 behavior).

**Case packet format (v1.1.0 — full context):**

```json
{
  "case_ref": "REG-20260224-7A3F",
  "timestamp": "2026-02-24T14:30:00Z",
  "user": { "id": "...", "email": "analyst@company.com", "name": "...", "role": "..." },
  "query": "What are the BOD limits for industrial discharge?",
  "response": "The LLM's full response text...",
  "confidence": { "score": 0.32, "band": "LOW", "signals": { ... } },
  "escalation": { "reason": "...", "target": "compliance-review", "threshold": 0.5 },
  "conversation_history": [
    { "role": "user", "content": "Earlier question..." },
    { "role": "assistant", "content": "Earlier answer..." }
  ],
  "retrieval_context": {
    "graphrag_citations": [ { "index": 1, "section": "Sec. 24-42.4...", "content": "Full text..." } ],
    "kb_sources": [ { "name": "KB chunk name", "content": "KB text..." } ],
    "entity_matches": [ { "name": "BOD", "score": 6.74, "summary": "..." } ],
    "graph_context_injected": "The full context block injected into the LLM..."
  },
  "context": { "chat_id": "...", "message_id": "...", "model": "gemini-2.5-pro" }
}
```

The packet includes **complete context**: full conversation history (all turns, with injected graph context stripped from user messages), all GraphRAG citations with section text, KB sources from ChromaDB, entity matches from graph search with scores and summaries, and the assembled graph context that was injected into the LLM prompt. This enables the n8n AI node to generate a comprehensive case brief.

The webhook uses `urllib.request` (stdlib, no extra dependencies). Timeout is 5 seconds. Any failure is silently caught — the chat experience is never interrupted.

### What the user sees

When escalation triggers, a structured notice **replaces** the disclaimer:

```
---
**Expert Review Initiated**

This analysis has been flagged for compliance review due to limited regulatory context.

**Case:** REG-20260224-7A3F | **Status:** Under review
**Contact:** We'll reach out to you at analyst@company.com once our review is complete.

*If this isn't your preferred contact email, please update your Open WebUI profile.*
```

When escalation does NOT trigger, the normal conditional disclaimer appears instead.

**Response output order:**

- **With escalation:** LLM response → Escalation notice → Trace (if enabled)
- **Without escalation:** LLM response → Conditional disclaimer → Trace (if enabled)

### What gets written to the audit database

The GraphRAG filter stores escalation data on the message dict (`messages[i]["graphrag_escalation"]`), following the same pattern used for confidence transport. The audit logger reads this with `pop()` and writes to the three escalation columns:

| Column | Value | Example |
|---|---|---|
| `escalation_triggered` | `1` | `1` |
| `escalation_target` | Valve-configured target | `"compliance-review"` |
| `case_packet_ref` | JSON with case details | `{"case_ref": "REG-20260224-7A3F", "reason": "Low retrieval confidence (32%): weak entity matching, sparse section retrieval", "confidence_score": 0.32, "confidence_band": "LOW"}` |

### Case reference format

Case references follow the pattern `REG-YYYYMMDD-XXXX` where XXXX is a 4-character hex derived from a SHA-256 hash of (user_id + chat_id + epoch). This is deterministic but collision-resistant without requiring a counter.

### Escalation reason

The `_escalation_reason()` method inspects the confidence signals to explain WHY escalation triggered:

- "No regulatory sections retrieved for this query" (zero retrieval)
- "Low retrieval confidence (32%): weak entity matching, sparse section retrieval" (signal-specific)
- "Low overall retrieval confidence (32%)" (generic fallback)

This reason is stored in both the n8n case packet and the audit DB `case_packet_ref` for the Dashboard to display to reviewers.

### How the Dashboard will consume this (Feature 7)

```sql
SELECT id, timestamp, user_email, query_text, response_text,
       confidence_score, case_packet_ref
FROM audit_records
WHERE escalation_triggered = 1
ORDER BY epoch DESC
```

---

## How to deploy

**Prerequisites:**

```bash
docker exec -it open-webui pip install neo4j
```

**Deploy:**

1. Admin Panel > Functions > **"+"** > paste `graphrag_filter.py` > Save
2. Set Valves: `neo4j_password` (required), optionally `show_trace` and `show_confidence`
3. Enable globally or per-model
4. For full compounding: also set up a Knowledge Base with Chapter 24 documents and attach it to a custom model
5. Paste `system_prompt.md` contents into the custom model's System Prompt field

---

## Neo4j graph schema

```
(Episodic: 138 nodes) ──MENTIONS (1,770)──→ (Entity: 738 nodes)
                                            (Entity) ──RELATES_TO (1,470)──→ (Entity)
```

**Episodic nodes:** Regulatory text sections with `content`, `source_description`, `uuid`
**Entity nodes:** Regulatory concepts with `name`, `summary`, `name_embedding`, `uuid`
**Fulltext indexes:** `entity_search` on Entity(name, summary), `episodic_search` on Episodic(content, source_description)

---

## Context injection method

The filter injects graph context into the **user's message** (not as a system message). This is because Open WebUI's Knowledge Base RAG runs after filters and can overwrite system messages. By embedding the graph context in the user message itself, it survives the RAG pipeline and reaches the LLM alongside the KB chunks.

Graph citations use `[G1]`, `[G2]` etc. to avoid collision with KB source IDs (`<source id="1">` etc.).

---

## Trace mode

Set `show_trace: true` in Valves to append a retrieval trace to every response. The trace is rendered in pure markdown (no HTML tags) and shows:

- All 4 pipeline steps with entity scores, traversal paths, section matches, timing
- A human-readable confidence breakdown table with columns: "What we measured", "Result", "Contribution", "Why it matters"
- A comparison of how GraphRAG differs from Knowledge Base (ChromaDB)

---

## Error handling

All retrieval logic is wrapped in try/except. If Neo4j is unreachable or a query fails, the filter passes through silently — the chat experience is never interrupted. All state (`_citations`, `_confidence_score`, `_confidence_band`, `_confidence_signals`, `_last_trace`) is cleared on error.

---

## Sources Panel — Development Journey

Getting GraphRAG sources into Open WebUI's Sources button was the most difficult integration challenge. Six approaches were attempted across multiple sessions before finding the working solution. This section documents the journey for future reference.

### Attempt 1: Inlet event emission

**Approach:** Used `__event_emitter__` in the inlet to emit `{"type": "source", "data": ...}` events for each GraphRAG source.

**Result:** ONLY GraphRAG sources appeared — KB sources disappeared entirely.

**Root cause:** The inlet runs before the KB pipeline. GraphRAG sources get set first, then KB sources overwrite them rather than merging.

### Attempt 2: Outlet event emission

**Approach:** Moved `__event_emitter__` source emission to the outlet (runs after response generation).

**Result:** NO GraphRAG sources appeared. Only KB sources showed.

**Root cause:** By the time the outlet runs, the frontend has already rendered sources from the streaming response. Late-emitted source events are ignored.

### Attempt 3: Metadata injection

**Approach:** Filter wrote `__metadata__["filter_sources"] = [...]` in the inlet. Modified middleware to read `metadata.get("filter_sources", [])`.

**Result:** Didn't work — filter_sources key was missing when middleware tried to read it.

**Root cause:** At middleware line ~2192, `metadata = {**metadata, ...}` creates a NEW dict, losing the filter_sources key that was set on the original dict.

### Attempt 4: form_data injection (middleware pickup)

**Approach:** Filter wrote `body["graphrag_sources"] = [...]` in the inlet. Modified middleware to read `form_data.pop("graphrag_sources", [])` before source collection.

**Result:** Didn't work — graphrag_sources key was missing.

**Root cause:** Between the filter inlet and source collection, `form_data` gets reassigned multiple times by intermediate handlers (`chat_memory_handler`, `chat_web_search_handler`, etc.), each creating a new dict.

### Attempt 5: Inside chat_completion_files_handler

**Approach:** Moved the `body.pop("graphrag_sources", [])` pickup to inside `chat_completion_files_handler`, right before its return statement.

**Result:** Still didn't work. Only KB sources appeared.

**Root cause:** The `body` parameter inside the files handler is a different reference than the one the filter modified, due to the same dict reassignment issue.

### Attempt 6: Local variable capture (middleware, early)

**Approach:** Captured `form_data.pop("graphrag_sources", [])` into a local variable immediately after the filter inlet returned (before any dict reassignment), then extended the sources list later.

**Result:** Didn't work after restart.

**Root cause:** Unknown — the approach was theoretically sound but the timing or reference chain was still broken.

### Attempt 7 (WORKING): Direct outlet mutation

**Approach:** In the outlet, directly append GraphRAG sources to `body["messages"][-1]["sources"]`. No middleware changes at all.

**Result:** Both KB and GraphRAG sources appear in the Sources panel.

**Why it works:** By the time the outlet runs, the assistant message already has its `sources` list populated by the KB pipeline. The outlet simply appends to that existing list. Since it's mutating the message dict directly (not going through middleware pipelines or event emitters), the changes persist to the database.

**Key insight:** Confirmed by the [Open WebUI community (Discussion #16099)](https://github.com/open-webui/open-webui/discussions/16099) — the outlet `body["messages"][-1]["sources"]` pattern is the standard way for filters to add custom sources.

**Middleware status:** Fully stock. Zero modifications. This is the most maintainable approach.

---

## Version history

| Version | Change |
|---|---|
| 0.1.0 | Initial Pipe version (replaced LLM endpoint) — caused deadlock |
| 0.3.0 | Restructured as Filter. Context injected as system message. |
| 0.4.0 | Moved context injection to user message (KB was overwriting system messages) |
| 0.5.0 | Added `[G1]` citation prefixes, `show_trace` mode, entity names in context header, `[GraphRAG + KB]` response prefix instruction |
| 0.6.0 | **Confidence scoring.** 6-signal weighted composite score (0.0–1.0). Visible badge on responses. Hidden HTML comment bridges to audit logger. LOW confidence triggers LLM hedging. Trace includes full scoring breakdown table. |
| 0.7.0 | **Enterprise output formatting.** Structured responses: Summary → Regulatory Analysis → Applicable Sections → What You Need To Do → Gaps & Limitations. Disclaimer with confidence %. System prompt split (identity/behavior to `system_prompt.md`, citation mechanics stay in filter). Expert-Mode Workflow Spec integration (4 design principles). Confidence display changed from emoji+band to clean percentage. Trace reformatted as pure markdown (removed `<details>` HTML tags). Human-readable confidence breakdown table in trace. |
| 0.8.0 | **Sources Panel integration.** GraphRAG sources now appear in Open WebUI's Sources button alongside KB sources with `[G1]`, `[G2]` nomenclature. Implemented via direct outlet mutation of `body["messages"][-1]["sources"]`. Zero middleware modifications required. Removed deprecated `body["graphrag_sources"]` injection from inlet. |
| 0.8.1 | **Conditional disclaimer system.** Replaced static "consult qualified professionals" disclaimer with 3-state confidence-adaptive footer. HIGH confidence → minimal professional footer. MEDIUM → acknowledges possible gaps. LOW → honest about limitations with query improvement hint. No state says "consult professionals." New `_build_disclaimer()` method. |
| 0.9.0 | **Escalation workflow.** Automatic flagging of low-confidence queries for expert review. Triggers on confidence < threshold (default 0.5), zero retrieval, or LOW band. Visible notice appended to response with case reference (REG-YYYYMMDD-XXXX). Escalation metadata stored on message dict (`graphrag_escalation`) for audit logger to write to DB. Signal-aware reason generation explains WHY confidence was low. Three new Valves: `escalation_enabled`, `escalation_threshold`, `escalation_target`. |
| 0.10.0 | **n8n webhook integration.** Escalation now POSTs a rich case packet to a configurable n8n webhook URL (`escalation_webhook_url` Valve). Case packet includes full conversation history, GraphRAG citations, KB sources, entity matches, confidence signals, and escalation reason. Escalation notice redesigned as structured format with case ref, status, and user contact email — now REPLACES the disclaimer instead of stacking. Uses `urllib.request` (stdlib), fire-and-forget on failure. New instance vars: `_entity_matches`, `_graph_context` (persisted from inlet for outlet). New methods: `_build_case_packet()`, `_send_escalation_webhook()`, `_extract_last_user_query()`. |
| 0.11.0 | **Refusal & Guardrails (Feature 8).** Hard guardrails that don't rely on LLM compliance. Two active guardrail types: (1) out-of-scope keyword detection — checks query against configurable exclusion keywords before graph search, skips GraphRAG pipeline if triggered; (2) zero-retrieval detection — triggers when both entity search and section search return nothing. Jurisdiction mismatch is stubbed for future multi-jurisdiction support. Structured guardrail notices replace the disclaimer (same pattern as escalation). Guardrail data transported via `graphrag_guardrail` message dict key for audit logger. New Valves: `guardrail_enabled`, `guardrail_exclusion_keywords`. New methods: `_check_out_of_scope()`, `_check_zero_retrieval()`, `_check_jurisdiction_mismatch()` (stub), `_generate_guardrail_ref()`, `_build_guardrail_notice()`. System prompt updated with structured refusal formatting instructions. Adversarial test suite created (28 test cases across 7 categories). |
| 0.11.1 | **Guardrail notice refinement.** Fixed confidence data leaking onto guardrailed queries. Moved `graphrag_confidence` storage inside the escalation/disclaimer branches only — when a guardrail fires, no confidence data is stored (meaningless for out-of-scope queries). Redesigned `_build_guardrail_notice()` with professional enterprise wording. New `guardrail_support_contact` Valve for configurable support contact in notices. |
| 0.12.0 | **Jurisdiction mismatch detection.** Implemented `_check_jurisdiction_mismatch()` — text-based heuristic on raw query. Allowlist (miami, miami-dade, south florida, florida) wins over blocklist. Detects 60+ foreign countries and 49 US states. Three new Valves: `guardrail_jurisdiction_enabled`, `guardrail_jurisdiction_allowlist`, `guardrail_jurisdiction_blocklist`. |
| 0.13.0 | **Confidence weight tuning.** 600-configuration sweep improved accuracy 60% → 80%. Key changes: `escalation_threshold` 0.50 → 0.65, `w_max_overlap` 0.25 → 0.35 (primary signal), `w_entity_count`/`w_section_count` reduced 0.15 → 0.12, HIGH band cutoff 0.80 → 0.75. Escalation accuracy improved 70% → 90%. |
| 0.14.0 | **Integrated threshold evaluation (Feature 9).** Embeds compliance checking directly in the filter — no tool-calling required. Regex-based detection of numeric measurements in queries (35+ parameter aliases including BOD, TSS, DO, temperature, pH, metals). Evaluates against 96 Chapter 24 thresholds from `regulatory_thresholds.json`. Injects determination data (status, limits, margin, evidence hash) into LLM context. Outlet appends a structured Compliance Determination badge with SHA-256 evidence hash. Logs all evaluations to breach SQLite DB. Three new Valves: `threshold_check_enabled`, `thresholds_path`, `breach_db_path`. System prompt updated with threshold data handling instructions. 42/42 tests passing. |
| 0.14.1 | **Badge positioning & LLM instruction refinement.** Compliance determination badge now appears ABOVE disclaimer/escalation/guardrail notices. LLM context instructions explicitly tell model NOT to restate threshold numbers or limits — badge handles that. Prevents response duplication. |
| 0.15.0 | **Facility context disambiguation.** New `_FACILITY_CONTEXTS` mapping with 3 facility types: wastewater (keywords: sewage, activated sludge, POTW), industrial (factory, NPDES), stormwater (MS4, runoff). `_disambiguate_thresholds()` method auto-selects facility-specific limits. When multiple facilities apply, returns `NEEDS_CLARIFICATION` status instead of guessing. Automatically resolves when query keywords match facility context. Prevents incorrect threshold determinations. |
| 0.15.1 | *Removed — v0.16.0 removes this versioned hack.* |
| 0.16.0 | **Conversation-aware threshold evaluation.** New `_build_conversation_context()` extracts all user messages from full chat history. Threshold detection uses conversation context instead of just last message for short queries (<8 words). Graph search also uses conversation context for follow-ups. Falls back to full history for facility type inference. Removes v0.15.1 workaround. Enables natural multi-turn compliance discussions. |

---

## Complete Method Reference (v0.16.0)

This section documents every method in the filter, organized by category. Each method includes: what it does (plain language), why it exists, how it works (technical), inputs/outputs, and examples where helpful.

### Initialization & Connection Management

#### `_get_driver()`

**What it does (Non-Technical)**

Establishes the connection to the Neo4j database, but only once. After the first connection, it reuses the same connection for all future queries.

**Why it exists**

Creating a database connection is expensive. By lazily initializing the driver and caching it, we avoid repeated overhead and ensure efficient pooling of database resources.

**How it works**

```python
if self._driver is None:
    self._driver = GraphDatabase.driver(
        uri=self.valves.neo4j_uri,
        auth=(self.valves.neo4j_user, self.valves.neo4j_password)
    )
return self._driver
```

**Code signature**

```python
_get_driver() -> neo4j.driver.Driver
```

**Returns**

Neo4j driver instance (cached after first call)

**Example usage**

```python
driver = self._get_driver()
# Subsequent calls return the same driver
driver = self._get_driver()  # Returns cached instance
```

---

### String Escaping & Sanitization

#### `_escape_lucene(text: str) -> str`

**What it does (Non-Technical)**

Removes special characters from user input so they don't break the search database. For example, if a user types `(discharge)?`, the system changes it to `\(discharge\)\?` so the database treats it as literal text, not a search instruction.

**Why it exists**

The search engine uses special syntax (parentheses, plus signs, colons, etc.) for advanced queries. If user input contains these characters without escaping, the query crashes or returns wrong results.

**How it works**

```
User input: "(discharge)"
↓
Regex finds: ( )
↓
Escapes each: \( \)
↓
Result: "\(discharge\)"
↓
Database sees: literal text "(discharge)" instead of a grouping operator
```

**Code signature**

```python
_escape_lucene(text: str) -> str
```

**Parameters**

- `text` (str): Raw user input

**Returns**

- `str`: Lucene-safe text with special characters escaped

**Example**

Input: `"What's the [BOD] discharge? (really!?)"`
Output: `"What's the \[BOD\] discharge\? \(really\!\?\)"`

---

### Graph Retrieval Pipeline — The 4 Steps

#### Step 1: `_search_entities(query: str) -> list[dict]`

**What it does (Non-Technical)**

The system searches for regulatory concepts (like "discharge", "BOD", "treatment") that match the user's question. Think of it as looking up keywords in an index.

**Why it exists**

Entities are the backbone of regulatory knowledge. By finding which concepts are mentioned in the user's question, we can then trace to the actual regulations that discuss those concepts.

**How it works**

```
User question: "What are the BOD limits?"
↓
Parse & escape: "BOD" → "\BOD"
↓
Query Neo4j fulltext index on Entity nodes:
  CALL db.index.fulltext.queryNodes("entity_search", "BOD")
  YIELD node, score
↓
Return top N entities (default 8) by score
```

**Code signature**

```python
_search_entities(query: str) -> list[dict]
```

**Parameters**

- `query` (str): User's question

**Returns**

List of dictionaries, each containing:
- `entity_name` (str): Name of regulatory concept
- `score` (float): Relevance score (higher = better match)
- `entity_id` (str): Neo4j node ID
- `properties` (dict): Metadata (summary, type, etc.)

**Example**

Input: "What are discharge limits for BOD?"
Output:
```python
[
  {"entity_name": "BOD", "score": 8.45, "entity_id": "uuid-123", "properties": {...}},
  {"entity_name": "discharge", "score": 7.92, "entity_id": "uuid-124", "properties": {...}},
  {"entity_name": "limits", "score": 6.55, "entity_id": "uuid-125", "properties": {...}},
]
```

---

#### Step 2: `_get_sections_for_entities(entity_ids: list[str]) -> list[dict]`

**What it does (Non-Technical)**

Takes the entity concepts from Step 1 and finds which actual regulatory documents (sections) discuss those concepts. This is the power of the graph — it traces from abstract concepts to the concrete regulations.

**Why it exists**

Entities are just concepts; sections are the actual law. By following the "is mentioned in" relationships, we connect abstract ideas to authoritative text.

**How it works**

```
Input: ["entity-BOD", "entity-discharge", "entity-limits"]
↓
For each entity, run:
  MATCH (e:Entity {id: entity_id})<-[:MENTIONS]-(s:Section)
  RETURN s, COUNT(matched_entities) as overlap
↓
Rank sections by how many input entities they mention
↓
Return top sections
```

**Code signature**

```python
_get_sections_for_entities(entity_ids: list[str]) -> list[dict]
```

**Parameters**

- `entity_ids` (list): IDs from Step 1

**Returns**

List of section dictionaries:
- `section_id` (str): Neo4j node ID
- `section_text` (str): Full regulatory text
- `section_title` (str): Section name (e.g., "Sec. 24-42.4")
- `matched_entity_count` (int): How many input entities this section mentions
- `score` (float): Combined relevance score

**Example**

Input: `["entity-BOD", "entity-discharge"]`
Output:
```python
[
  {
    "section_id": "section-456",
    "section_text": "BOD discharge limits are... (full text)",
    "section_title": "Sec. 24-42.4 — Sanitary sewer discharge limitations",
    "matched_entity_count": 2,
    "score": 8.12
  },
  {
    "section_id": "section-457",
    "section_text": "Industrial discharge standards... (full text)",
    "section_title": "Sec. 24-42.1 — Tertiary treatment requirements",
    "matched_entity_count": 1,
    "score": 6.88
  }
]
```

---

#### Step 3: `_search_sections_direct(query: str) -> list[dict]`

**What it does (Non-Technical)**

As a safety net, the system also searches the regulatory text directly for the user's keywords. If Step 1–2 missed something, this catches it.

**Why it exists**

Entity linking is powerful but not perfect. Some regulatory keywords might not be formally indexed as entities. Direct text search ensures comprehensive coverage.

**How it works**

```
User question: "What are the BOD limits?"
↓
Query Neo4j fulltext index on Section nodes:
  CALL db.index.fulltext.queryNodes("section_search", "BOD limits")
  YIELD node, score
↓
Return top N sections (default 5)
```

**Code signature**

```python
_search_sections_direct(query: str) -> list[dict]
```

**Parameters**

- `query` (str): User's question

**Returns**

List of section dictionaries (same format as Step 2)

---

#### Step 4: `_assemble_context(entities: list[dict], sections: list[dict]) -> dict`

**What it does (Non-Technical)**

Takes results from Steps 2 and 3, removes duplicates, ranks them by quality, and formats them as a numbered list (like a bibliography) that the LLM can understand and cite.

**Why it exists**

Steps 2 and 3 might return overlapping results. We need a clean, deduplicated, ranked list. The numbered format helps the LLM cite sources accurately (e.g., "According to [G1]...").

**How it works**

```
Raw sections from Steps 2 & 3:
  [s1 (score 8.12), s2 (score 9.45), s1 (score 8.05), s3 (score 7.62), ...]
↓
Deduplicate by section_id (keep highest score):
  {s1 (score 8.12), s2 (score 9.45), s3 (score 7.62), ...}
↓
Sort by score descending:
  [s2 (9.45), s1 (8.12), s3 (7.62), ...]
↓
Take top N (default 5):
  [s2, s1, s3, s4, s5]
↓
Format as markdown:
  [G1] **Sec. 24-42.4** — Sanitary sewer discharge limitations
       Full text of section...
  [G2] **Sec. 24-42.1** — Tertiary treatment requirements
       Full text of section...
  ...
```

**Code signature**

```python
_assemble_context(
    entities: list[dict],
    sections: list[dict]
) -> dict
```

**Parameters**

- `entities` (list): From Step 1
- `sections` (list): Combined from Steps 2–3

**Returns**

Dictionary containing:
- `context_text` (str): Markdown-formatted numbered list
- `context_sources` (list): Metadata for each section (for citations panel)
- `entity_count` (int): Total unique entities
- `section_count` (int): Total unique sections
- `entities_list` (list): Full entity data for confidence scoring

**Example return**

```python
{
  "context_text": """## Regulatory Context (5 sections)

[G1] **Sec. 24-42.4** — Sanitary sewer discharge limitations
     BOD discharge limits are measured in mg/L per...

[G2] **Sec. 24-42.1** — Tertiary treatment requirements
     Industrial discharge standards require...""",
  "context_sources": [
    {"id": "section-456", "title": "Sec. 24-42.4", "index": 1},
    {"id": "section-457", "title": "Sec. 24-42.1", "index": 2}
  ],
  "entity_count": 8,
  "section_count": 5,
  "entities_list": [...]
}
```

---

### Message Extraction

#### `_extract_last_user_query(messages: list[dict]) -> str`

**What it does (Non-Technical)**

Finds the most recent question the user asked. In a conversation with back-and-forth messages, this isolates the current question.

**Why it exists**

Open WebUI passes the entire conversation history. To search the graph with the user's current question, we need to extract just the latest user message.

**How it works**

```
Conversation:
  [user]      "What are BOD limits?"
  [assistant] "BOD limits are..."
  [user]      "For industrial facilities?"
  [assistant] "..."
  [user]      "What about wastewater?"  ← Extract this
↓
Iterate messages backwards
Find last message where role == "user"
Return content
```

**Code signature**

```python
_extract_last_user_query(messages: list[dict]) -> str
```

**Parameters**

- `messages` (list): Conversation history from Open WebUI

**Returns**

- `str`: Content of the last user message

**Example**

Input:
```python
[
  {"role": "user", "content": "What are BOD limits?"},
  {"role": "assistant", "content": "BOD limits..."},
  {"role": "user", "content": "For wastewater facilities?"}
]
```
Output: `"For wastewater facilities?"`

---

### Conversation Context (v0.16.0)

#### `_build_conversation_context(messages: list[dict]) -> str`

**What it does (Non-Technical)**

Reads through the entire conversation and extracts every question the user has asked. In a follow-up like "Is 45 mg/L okay?" the system looks back and remembers "you're talking about wastewater discharge from your facility."

**Why it exists**

Short follow-up messages don't contain full context. In multi-turn compliance discussions, the system needs to understand what the user is referring to from previous turns. Rather than asking the user to repeat themselves, the filter builds a complete conversational context.

**How it works**

```
Conversation:
  [user]      "We have a wastewater treatment facility"
  [assistant] "..."
  [user]      "Our BOD discharge is currently 50 mg/L"
  [assistant] "..."
  [user]      "Is that compliant?"  ← Current query (very short!)
↓
Extract all user messages:
  1. "We have a wastewater treatment facility"
  2. "Our BOD discharge is currently 50 mg/L"
  3. "Is that compliant?"
↓
Concatenate:
  "We have a wastewater treatment facility Our BOD discharge is currently 50 mg/L Is that compliant?"
↓
Use for threshold detection and facility type inference
```

**Code signature**

```python
_build_conversation_context(messages: list[dict]) -> str
```

**Parameters**

- `messages` (list): Conversation history from Open WebUI

**Returns**

- `str`: All user messages concatenated with spaces

**Integration in Pipeline**

Threshold detection now intelligently chooses between the current message and full context:

```python
last_user_query = _extract_last_user_query(messages)
conversation_context = _build_conversation_context(messages)

# For short queries, use full context
if len(last_user_query.split()) < 8:  # Fewer than 8 words
    detection_query = conversation_context
else:
    detection_query = last_user_query

detection = _detect_threshold_query(detection_query)
```

**Example**

Input:
```python
[
  {"role": "user", "content": "wastewater facility"},
  {"role": "assistant", "content": "..."},
  {"role": "user", "content": "50 mg/L BOD discharge"},
  {"role": "assistant", "content": "..."},
  {"role": "user", "content": "Is that okay?"}
]
```
Output: `"wastewater facility 50 mg/L BOD discharge Is that okay?"`

---

### Confidence Scoring

#### `_calculate_confidence(search_results: dict) -> float`

**What it does (Non-Technical)**

Scores how confident the system is in its answer, on a scale of 0 (completely unreliable) to 1 (highly confident). The score is based on six different signals.

**Why it exists**

Not all queries retrieve equally good results. The confidence score tells the user how much to trust the answer. High confidence → proceed confidently. Low confidence → verify with original sources.

**How it works**

Six signals are computed, each normalized to 0–1:

| Signal | Weight | What it measures |
|--------|--------|------------------|
| `avg_entity_score` | 0.35 | Average relevance of matched entities (higher = better query-concept match) |
| `entity_count` | 0.12 | Number of entities found (more = broader coverage) |
| `section_count` | 0.12 | Number of sections found (more = richer context) |
| `has_graph_exclusive` | 0.08 | Whether graph found sections beyond direct text search (graph's value-add) |
| `avg_direct_score` | 0.08 | Average relevance from direct section search (text-level match quality) |
| `connection_signal` | 0.25 | Whether entity→section relationships were found (implicit in final calc) |

**Formula**

```
confidence = 0.35 × avg_entity_score
           + 0.12 × entity_count_signal
           + 0.12 × section_count_signal
           + 0.08 × graph_exclusive_signal
           + 0.08 × avg_direct_score
           + 0.25 × connection_signal
```

Result is clamped to [0.0, 1.0].

**Code signature**

```python
_calculate_confidence(search_results: dict) -> float
```

**Parameters**

- `search_results` (dict): From `_assemble_context()` plus signal calculations

**Returns**

- `float`: Confidence score (0.0–1.0), rounded to 2 decimal places

**Confidence Bands**

| Score | Band | Meaning |
|-------|------|---------|
| 0.75–1.00 | HIGH | Strong entity matches, multiple sections found. High-quality retrieval. |
| 0.50–0.74 | MEDIUM | Decent matches but gaps. Answer useful but may miss nuance. |
| <0.50 | LOW | Weak retrieval. Answer unreliable. Escalation recommended. |

**Example calculation**

Query: "What are discharge limits for BOD?"
- Avg entity score: 0.92 × weight 0.35 = 0.322
- Entity count (6/8): 0.75 × weight 0.12 = 0.090
- Section count (5/5): 1.00 × weight 0.12 = 0.120
- Graph exclusive: 1.00 × weight 0.08 = 0.080
- Avg direct score: 0.88 × weight 0.08 = 0.070
- Connection signal: 1.00 × weight 0.25 = 0.250
- **Total: 0.932 → HIGH confidence**

---

### Threshold Evaluation System

#### `_detect_threshold_query(query: str) -> dict`

**What it does (Non-Technical)**

When a user mentions a number with a unit (like "50 mg/L"), the system recognizes it as a measurement and extracts the parameter name, value, and unit.

**Why it exists**

To check if a measurement complies with regulations, we first need to extract what the user is measuring and what their value is. This method uses pattern matching (regex) to find measurements in natural text.

**How it works**

```
User query: "Our BOD discharge is 50 mg/L. Is that compliant?"
↓
Regex pattern: \b(\d+(?:\.\d+)?)\s*(mg/L|mg/l|ppm|...)
↓
Match: (50, "mg/L")
↓
Extract parameter from nearby text:
  Keywords: ["discharge", "BOD"] → parameter = "discharge"
↓
Return: {
  "found": True,
  "parameter": "discharge",
  "value": 50.0,
  "unit": "mg/L",
  "raw_text": "50 mg/L"
}
```

**Code signature**

```python
_detect_threshold_query(query: str) -> dict
```

**Parameters**

- `query` (str): User's question or statement

**Returns**

Dictionary with:
- `found` (bool): Whether a measurement was detected
- `parameter` (str): Parameter name (e.g., "discharge", "temperature", "pH")
- `value` (float): Numeric value
- `unit` (str): Unit of measurement
- `raw_text` (str): Original text containing the measurement

**Example**

Input: `"We're discharging 45 mg/L of TSS daily"`
Output:
```python
{
  "found": True,
  "parameter": "discharge",
  "value": 45.0,
  "unit": "mg/L",
  "raw_text": "45 mg/L of TSS"
}
```

**Supported units**

mg/L, ppm, ppb, %, °C, °F, L, gal, cfs (cubic feet/second), gpm (gallons/minute), mgd (million gallons/day), lbs/day, kg/day, and more (regex-configurable).

**Parameter aliases** (35+ mappings)

The system normalizes alternate names to standard parameters:
- "discharge", "effluent", "wastewater", "outfall" → "discharge"
- "temperature", "thermal", "cooling water" → "temperature"
- "bod", "biochemical oxygen demand" → "bod"
- "tss", "suspended solids" → "tss"
- "ph", "acidity" → "ph"
- And more

---

#### `_load_thresholds() -> dict`

**What it does (Non-Technical)**

Loads the database of regulatory limits from a JSON file. The first time it's called, it reads from disk; afterward, it uses a cached copy.

**Why it exists**

Limits need to be centralized, versioned, and updatable without code changes. A JSON file makes them easy to maintain and audit.

**How it works**

```
First call:
  Read regulatory_thresholds.json
  Parse JSON
  Cache in self._thresholds
  Return

Subsequent calls:
  Return cached copy (no disk read)
```

**Code signature**

```python
_load_thresholds() -> dict
```

**Returns**

Nested dictionary structure:
```python
{
  "discharge": {
    "BOD": {
      "limit": 300.0,
      "unit": "mg/L",
      "source": "Sec. 24-42.1",
      "facility_types": {
        "wastewater": 250.0,
        "industrial": 300.0
      }
    },
    "TSS": { ... }
  },
  "temperature": { ... }
}
```

---

#### `_evaluate_thresholds(detection: dict, thresholds: dict, facility_type: str = None) -> dict`

**What it does (Non-Technical)**

Compares the user's measurement to the regulatory limit. If the measurement exceeds the limit, it's flagged as a compliance breach.

**Why it exists**

Once we extract a measurement and have the regulatory limit, we need to determine: Is it compliant? By how much does it exceed the limit (if at all)?

**How it works**

```
Input:
  detection = {"parameter": "discharge", "value": 50.0, "unit": "mg/L"}
  limits = {"discharge": {"BOD": {"limit": 35.0, ...}}}
  facility_type = "wastewater"
↓
Lookup limit:
  If facility_type in limits[parameter][...]["facility_types"]:
    use facility-specific limit
  Else:
    use default limit
↓
Compare:
  Is 50.0 > 35.0? YES → BREACH
  Exceeded by: 50 - 35 = 15 mg/L
  Percentage: (15 / 35) × 100 = 42.86%
↓
Return: {
  "status": "BREACH",
  "limit": 35.0,
  "measured": 50.0,
  "exceeded_by": 15.0,
  "exceeded_pct": 42.86,
  "severity": "HIGH",
  "message": "Discharge (50 mg/L) exceeds limit (35 mg/L) by 42.86%"
}
```

**Code signature**

```python
_evaluate_thresholds(
    detection: dict,
    thresholds: dict,
    facility_type: str = None
) -> dict
```

**Parameters**

- `detection` (dict): From `_detect_threshold_query()`
- `thresholds` (dict): From `_load_thresholds()`
- `facility_type` (str, optional): Facility context for facility-specific limits

**Returns**

Dictionary with:
- `status` (str): "PASS", "BREACH", or "NEEDS_CLARIFICATION"
- `limit` (float): Regulatory limit
- `measured` (float): User's measurement
- `exceeded_by` (float): Amount over limit (if breach)
- `exceeded_pct` (float): Percentage over limit
- `severity` (str): "LOW", "MEDIUM", or "HIGH"
- `message` (str): Human-readable determination
- `source` (str): Regulation citation (e.g., "Sec. 24-42.1")

**Example**

Input: discharge = 50 mg/L, limit = 35 mg/L
Output:
```python
{
  "status": "BREACH",
  "limit": 35.0,
  "measured": 50.0,
  "exceeded_by": 15.0,
  "exceeded_pct": 42.86,
  "severity": "HIGH",
  "message": "Discharge (50 mg/L) exceeds limit (35 mg/L) by 42.86%",
  "source": "Sec. 24-42.1"
}
```

---

#### `_disambiguate_thresholds(parameter: str, thresholds: dict, context_sections: list[dict], query: str) -> dict` (v0.15.0+)

**What it does (Non-Technical)**

When the same parameter has different limits for different facility types (wastewater vs. industrial), the system figures out which facility the user is talking about by looking for keywords in their question.

**Why it exists**

A 50 mg/L discharge might be legal for a wastewater facility but illegal for an industrial one. Context matters. This method auto-detects facility type to apply the right limit.

**How it works**

```
Query: "Our BOD discharge is 45 mg/L"
Parameter: "discharge"
Limits available for: wastewater (30 mg/L), industrial (45 mg/L), agricultural (60 mg/L)
↓
Check query for facility keywords:
  _FACILITY_CONTEXTS["wastewater"]["keywords"] = ["sewage", "activated sludge", "POTW", "treatment plant"]
  → Query does NOT match wastewater keywords
  _FACILITY_CONTEXTS["industrial"]["keywords"] = ["industrial", "factory", "manufacturing"]
  → Query does NOT match industrial keywords
↓
Check context sections for clues:
  Retrieved sections mention "wastewater treatment" → facility_type = "wastewater"
↓
If found: Apply wastewater limit (30 mg/L)
If NOT found: Return NEEDS_CLARIFICATION asking user to specify
```

**Code signature**

```python
_disambiguate_thresholds(
    parameter: str,
    thresholds: dict,
    context_sections: list[dict],
    query: str
) -> dict
```

**Parameters**

- `parameter` (str): Parameter name (e.g., "discharge")
- `thresholds` (dict): Full threshold database
- `context_sections` (list): Sections retrieved from graph (for contextual clues)
- `query` (str): User's question

**Returns**

Dictionary with:
- `facility_type` (str): Detected facility type, or None if ambiguous
- `selected_limit` (float): The applicable limit
- `status` (str): "DISAMBIGUATED" or "NEEDS_CLARIFICATION"
- `message` (str): Explanation for user

**Example 1: Successful disambiguation**

Query: "Our activated sludge facility discharge is 45 mg/L"
Detection: "activated sludge" matches wastewater keywords
Output:
```python
{
  "facility_type": "wastewater",
  "selected_limit": 30.0,
  "status": "DISAMBIGUATED",
  "message": "Detected wastewater facility context"
}
```

**Example 2: Needs clarification**

Query: "Our discharge is 45 mg/L"
No keywords found; retrieved sections mention multiple facility types
Output:
```python
{
  "facility_type": None,
  "selected_limit": None,
  "status": "NEEDS_CLARIFICATION",
  "message": "Please specify facility type (wastewater/industrial/agricultural) for accurate limit determination"
}
```

**Facility context mappings**

```python
_FACILITY_CONTEXTS = {
  "wastewater": {
    "keywords": [
      "wastewater", "sewage", "activated sludge", "secondary treatment",
      "aeration basin", "treatment plant", "POTW"
    ]
  },
  "industrial": {
    "keywords": [
      "industrial", "manufacturing", "factory", "plant discharge",
      "process water", "cooling water", "NPDES permit", "categorical"
    ]
  },
  "stormwater": {
    "keywords": [
      "stormwater", "runoff", "storm drain", "wet weather",
      "precipitation", "MS4"
    ]
  }
}
```

---

#### `_log_to_breach_db(query: str, parameter: str, value: float, unit: str, limit: float, status: str, facility_type: str = None) -> None`

**What it does (Non-Technical)**

Records every threshold evaluation in an audit database so there's a permanent record of what was checked and when. Regulators can audit this trail if needed.

**Why it exists**

Regulatory compliance requires audit trails. If an agency asks "Did you check measurement X on date Y?", you need proof.

**How it works**

```python
_log_to_breach_db(
  query="Our BOD discharge is 50 mg/L",
  parameter="discharge",
  value=50.0,
  unit="mg/L",
  limit=35.0,
  status="BREACH",
  facility_type="wastewater"
)
↓
Create SQLite record:
  INSERT INTO evaluations (
    timestamp, user_id, parameter, measured, unit, limit, status, query, facility_type
  ) VALUES (
    2026-02-26 14:30:00, user_123, discharge, 50.0, mg/L, 35.0, BREACH, ..., wastewater
  )
```

**Code signature**

```python
_log_to_breach_db(
    query: str,
    parameter: str,
    value: float,
    unit: str,
    limit: float,
    status: str,
    facility_type: str = None
) -> None
```

**Parameters**

- `query` (str): Original user question
- `parameter` (str): Parameter name
- `value` (float): Measured value
- `unit` (str): Unit of measurement
- `limit` (float): Regulatory limit
- `status` (str): "PASS", "BREACH", or "NEEDS_CLARIFICATION"
- `facility_type` (str, optional): Facility context

**Returns**

- None (side effect: SQLite record inserted)

**Database schema**

```sql
CREATE TABLE evaluations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
  user_id TEXT,
  parameter TEXT,
  measured REAL,
  unit TEXT,
  limit REAL,
  status TEXT,
  query TEXT,
  facility_type TEXT
)
```

---

#### `_build_threshold_context(threshold_results: dict) -> str`

**What it does (Non-Technical)**

Creates a summary of the threshold evaluation that the LLM can read. For example, if a measurement breached a limit, this builds a markdown block explaining the breach.

**Code signature**

```python
_build_threshold_context(threshold_results: dict) -> str
```

**Parameters**

- `threshold_results` (dict): From `_evaluate_thresholds()`

**Returns**

- `str`: Markdown block (empty if no thresholds detected)

**Example output**

```markdown
## Threshold Evaluation

**Parameter:** Discharge (BOD)
**Measured Value:** 50 mg/L
**Regulatory Limit:** 35 mg/L (Sec. 24-42.1)
**Status:** EXCEEDS LIMIT BY 42.86%
**Severity:** HIGH
```

---

#### `_build_compliance_badge(determination: dict) -> str`

**What it does (Non-Technical)**

Creates a visual badge that summarizes compliance in one sentence. For example, "✓ COMPLIANT" or "⚠ BREACH — exceeds limit by 42.86%".

**Why it exists**

Users need to see compliance at a glance. The badge provides instant clarity without reading the full analysis.

**Code signature**

```python
_build_compliance_badge(determination: dict) -> str
```

**Parameters**

- `determination` (dict): From `_evaluate_thresholds()`

**Returns**

- `str`: Markdown-formatted compliance badge

**Example outputs**

PASS:
```markdown
### ✓ Compliance Determination: PASS

**Parameter:** Discharge (BOD)
**Measured:** 50 mg/L
**Limit:** 35 mg/L
**Status:** WITHIN REGULATORY LIMITS
```

BREACH:
```markdown
### ⚠ Compliance Determination: BREACH

**Parameter:** Discharge (BOD)
**Measured:** 50 mg/L
**Limit:** 35 mg/L
**Status:** EXCEEDS LIMIT BY 42.86%

Immediate action required to achieve compliance.
```

---

### LLM Integration

#### `_enterprise_format_instructions(context_sources: list[dict]) -> str`

**What it does**

Generates instructions for the LLM on how to cite the retrieved regulatory sections. These tell the LLM: "When you reference section [G1], cite it like this."

**Code signature**

```python
_enterprise_format_instructions(context_sources: list[dict]) -> str
```

**Returns**

- `str`: Markdown instructions for LLM

**Example output**

```markdown
## How to Use the Regulatory Context

You have been provided 5 regulatory sections [G1]–[G5] above.

When answering:
1. Use the provided context first and foremost
2. Cite sections by number: "According to [G2], the limit is..."
3. Do NOT restate regulatory numbers or measurement thresholds — the compliance badge handles that
4. Explain what the regulations MEAN in practical terms
```

---

#### `_build_system_prompt(context: dict, enterprise_instructions: str) -> str`

**What it does**

Constructs the complete system prompt for the LLM, injecting the retrieved regulatory context and formatting instructions.

**Code signature**

```python
_build_system_prompt(
    context: dict,
    enterprise_instructions: str
) -> str
```

**Returns**

- `str`: Complete system prompt ready for LLM

---

#### `_build_disclaimer(confidence: float) -> str`

**What it does (Non-Technical)**

Creates a disclaimer that adapts to confidence level. High confidence gets a minimal footer; low confidence warns the user to verify independently.

**How it works**

```
if confidence >= 0.75:  # HIGH
    return ""  # No disclaimer
elif confidence >= 0.50:  # MEDIUM
    return "⚠ Source confidence: 67%. Cross-check critical requirements."
else:  # LOW
    return "❌ Low confidence (32%). Verify against full Chapter 24 text."
```

**Code signature**

```python
_build_disclaimer(confidence: float) -> str
```

**Parameters**

- `confidence` (float): Confidence score (0.0–1.0)

**Returns**

- `str`: Disclaimer text (may be empty for HIGH confidence)

---

### Guardrail System

#### `_check_out_of_scope(query: str) -> dict`

**What it does (Non-Technical)**

Checks whether the user's question is about regulatory compliance or something else (like investment advice or recipes). If it's off-topic, the system declines to answer.

**Code signature**

```python
_check_out_of_scope(query: str) -> dict
```

**Returns**

Dictionary with:
- `is_out_of_scope` (bool)
- `reason` (str, optional): Explanation if out-of-scope

**Example**

Input: "Can you help me pick stocks for my portfolio?"
Output:
```python
{
  "is_out_of_scope": True,
  "reason": "Investment and financial advice is outside RegOS scope"
}
```

---

#### `_check_zero_retrieval(search_results: dict) -> dict`

**What it does (Non-Technical)**

Detects when the graph search found NO matching regulatory content. In this case, the system can't provide an answer and says so.

**Code signature**

```python
_check_zero_retrieval(search_results: dict) -> dict
```

**Returns**

Dictionary with:
- `is_zero_retrieval` (bool)
- `reason` (str, optional): Explanation

**Example**

Input: Query about fictional regulation not in database
Output:
```python
{
  "is_zero_retrieval": True,
  "reason": "No regulatory content found for this query"
}
```

---

#### `_check_jurisdiction_mismatch(query: str, context_sections: list[dict]) -> dict`

**What it does (Non-Technical)**

Checks if the user is asking about a location outside RegOS scope. For example, if they ask about French regulations when RegOS covers Florida, it flags a mismatch.

**How it works**

```
Extract location from query (regex on country/state names)
Check against allowlist (Florida, Federal) and blocklist (foreign countries, non-FL states)
Return match/mismatch
```

**Code signature**

```python
_check_jurisdiction_mismatch(
    query: str,
    context_sections: list[dict]
) -> dict
```

**Returns**

Dictionary with:
- `is_mismatch` (bool)
- `reason` (str, optional)
- `detected_location` (str, optional)

---

#### `_generate_guardrail_ref() -> str`

**What it does**

Generates a unique reference ID for a guardrail violation: `GRD-YYYYMMDD-XXXX` where XXXX is a random 4-character hex.

**Code signature**

```python
_generate_guardrail_ref() -> str
```

**Returns**

- `str`: Unique guardrail reference (e.g., `"GRD-20260226-A7B2"`)

---

#### `_build_guardrail_notice(violation: dict) -> str`

**What it does**

Creates a markdown notice explaining why a guardrail was triggered.

**Code signature**

```python
_build_guardrail_notice(violation: dict) -> str
```

**Parameters**

- `violation` (dict): From one of the `_check_*()` methods

**Returns**

- `str`: Markdown notice

**Example**

```markdown
## 🛑 Guardrail: Out-of-Scope Request

**Reference:** GRD-20260226-A7B2
**Reason:** Investment advice is outside RegOS scope.

RegOS is designed for regulatory compliance assistance.
For investment guidance, please consult a financial advisor.
```

---

### Escalation System

#### `_should_escalate(confidence: float, threshold_result: dict, guardrail_result: dict) -> bool`

**What it does (Non-Technical)**

Determines whether this query should be flagged for human expert review. Escalation triggers when confidence is very low, thresholds breach, or the answer is ambiguous.

**How it works**

```
Escalation triggers when ANY are true:
  - confidence < escalation_threshold (default 0.65)
  - threshold_status == "BREACH"
  - threshold_status == "NEEDS_CLARIFICATION"
  - guardrail violations present
```

**Code signature**

```python
_should_escalate(
    confidence: float,
    threshold_result: dict,
    guardrail_result: dict
) -> bool
```

**Returns**

- `bool`: True if escalation should fire

---

#### `_escalation_reason(confidence: float, threshold_result: dict, guardrail_result: dict) -> str`

**What it does**

Generates a human-readable explanation of WHY escalation was triggered. For example: "Confidence score 0.58 is below threshold 0.65" or "Discharge measurement exceeds regulatory limit."

**Code signature**

```python
_escalation_reason(
    confidence: float,
    threshold_result: dict,
    guardrail_result: dict
) -> str
```

**Returns**

- `str`: Human-readable reason

**Example outputs**

- "Low retrieval confidence (58%): weak entity matching"
- "Threshold breach: Discharge (50 mg/L) exceeds limit (35 mg/L) by 42.86%"
- "Ambiguous threshold determination: Multiple facility types applicable"

---

#### `_generate_case_ref() -> str`

**What it does**

Generates a unique case reference for escalations: `REG-YYYYMMDD-XXXX`

**Code signature**

```python
_generate_case_ref() -> str
```

**Returns**

- `str`: Unique case reference (e.g., `"REG-20260226-X3Y8Z"`)

---

#### `_build_case_packet(user_query: str, conversation_history: list[dict], search_results: dict, confidence: float, threshold_results: dict, guardrail_results: dict) -> dict`

**What it does (Non-Technical)**

Assembles a complete information packet about the escalated query. This includes everything a human expert needs to review it: the original question, the conversation history, what the system found, confidence scores, and the reasoning.

**Why it exists**

When a query is escalated to n8n for human review, the expert needs full context. The case packet bundles everything in a structured format.

**How it works**

```
Collect:
  - User info (id, email, name, role)
  - Original query and full conversation history
  - What the graph retrieved (entities, sections)
  - Confidence score breakdown
  - Threshold evaluation results
  - Escalation reason
↓
Package as JSON with descriptive labels
↓
Include pointers to evidence (citation IDs, etc.)
```

**Code signature**

```python
_build_case_packet(
    user_query: str,
    conversation_history: list[dict],
    search_results: dict,
    confidence: float,
    threshold_results: dict,
    guardrail_results: dict
) -> dict
```

**Returns**

Case packet dictionary:
```python
{
  "case_id": "REG-20260226-X3Y8Z",
  "timestamp": "2026-02-26T14:30:00Z",
  "user_id": "user_123",
  "user_email": "analyst@company.com",
  "escalation_triggers": ["LOW_CONFIDENCE", "THRESHOLD_BREACH"],
  "confidence_score": 0.58,
  "confidence_band": "LOW",
  "last_user_query": "What about wastewater discharge?",
  "conversation_history": [...],
  "retrieved_entities": [...],
  "retrieved_sections": [...],
  "threshold_detection": {...},
  "guardrail_results": {...},
  "system_prompt_used": "...",
  "context_used": "...",
  "analyst_notes": "Low confidence due to limited entity matches"
}
```

---

#### `_send_escalation_webhook(case_packet: dict) -> bool`

**What it does (Non-Technical)**

Sends the case packet to an n8n workflow (via webhook) for automated handling. This might trigger email notifications, ticket creation, or other workflow actions.

**Why it exists**

Rather than just logging to a database, escalations can trigger real-time workflows. The webhook integration enables automated routing, notifications, and case management.

**How it works**

```python
POST to escalation_webhook_url
  Headers: {"Content-Type": "application/json", "X-Case-ID": case_packet["case_id"]}
  Body: JSON-serialized case_packet
↓
n8n receives webhook
Triggers workflow:
  1. Parse case packet
  2. Alert analyst (email/Slack)
  3. Create ticket (Jira/GitHub)
  4. Store in database
↓
Fire-and-forget: If n8n is down, chat is unaffected
```

**Code signature**

```python
_send_escalation_webhook(case_packet: dict) -> bool
```

**Parameters**

- `case_packet` (dict): From `_build_case_packet()`

**Returns**

- `bool`: Success/failure of webhook POST

**Webhook timeout**

5 seconds. If n8n doesn't respond, failure is silently caught.

---

### Main Pipeline

#### `inlet()` — Entry Point

**What it does (Non-Technical)**

Intercepts the user's message before the LLM sees it. Runs the entire retrieval and compliance pipeline in the background, and stores results for later use by the outlet.

**Why it exists**

Open WebUI's filter system provides two hooks: `inlet()` runs before LLM processing, `outlet()` runs after. The `inlet()` does all the expensive work (graph search, confidence calculation, threshold evaluation) and caches results.

**How it works**

```
inlet(body, __user__, __body__)
↓
1. Extract last user message
2. Build conversation context (v0.16.0)
3. Run 4-step graph retrieval (Steps 1–4)
4. Calculate confidence score
5. Check guardrails (out-of-scope, zero retrieval, jurisdiction)
6. Detect & evaluate thresholds (with facility disambiguation)
7. Determine escalation (confidence + threshold + guardrail)
8. Build threshold context & compliance badge
9. Store all results in body["valves"]["graphrag_filter_results"]
10. Return modified body to continue pipeline
```

**Code signature**

```python
async def inlet(
    self,
    body: dict,
    __user__: dict,
    __body__: dict
) -> dict
```

**Parameters**

- `body` (dict): Message structure with `messages` (conversation history)
- `__user__` (dict): User metadata from Open WebUI
- `__body__` (dict): Internal body (usually unused)

**Returns**

- `dict`: Modified body with results cached in `body["valves"]["graphrag_filter_results"]`

**Cached results structure**

```python
body["valves"]["graphrag_filter_results"] = {
  "retrieved_entities": [...],
  "retrieved_sections": [...],
  "context_text": "## Regulatory Context...",
  "confidence": 0.72,
  "confidence_band": "MEDIUM",
  "confidence_signals": {...},
  "threshold_detected": True,
  "threshold_results": {...},
  "guardrail_violations": [],
  "should_escalate": False,
  "escalation_reason": None,
  "case_packet": None,
  "system_prompt_override": "...",
  "disclaimer": "⚠ Source confidence: 72%...",
  "compliance_badge": "### ✓ Compliance Determination...",
  "escalation_notice": None,
  "graph_context": "...",
  "trace": "..."
}
```

---

#### `outlet()` — Exit Point

**What it does (Non-Technical)**

Runs after the LLM generates its response. Appends compliance information to the response: the compliance badge, disclaimer, sources, and any escalation notices.

**Why it exists**

Users need to see compliance information. The outlet formats and appends it to make the response complete and actionable.

**How it works**

```
outlet(body, __user__, __body__)
↓
1. Retrieve results from inlet (cached in body["valves"])
2. Build final response text by appending to LLM output:
   a. Compliance badge (if threshold evaluation happened)
   b. Escalation notice (if escalation triggered)
   c. Disclaimer (if not escalated)
   d. Sources panel (append GraphRAG sources to existing KB sources)
   e. Trace (if show_trace enabled)
3. Send escalation webhook (if escalation triggered and webhook URL configured)
4. Return modified body
```

**Badge positioning (v0.14.1+)**

Compliance badge appears **ABOVE** disclaimer and escalation notice:

```
[LLM Response Text]

### ✓ Compliance Determination: PASS
...

[Escalation Notice (if present)]

[Disclaimer (if present)]

## Sources
[G1] ...
[KB sources] ...
```

**Code signature**

```python
async def outlet(
    self,
    body: dict,
    __user__: dict,
    __body__: dict
) -> dict
```

**Parameters**

- `body` (dict): Response message structure
- `__user__` (dict): User metadata
- `__body__` (dict): Internal body

**Returns**

- `dict`: Modified body with formatted response

---

## Class-Level Data Structures

### `_PARAM_ALIASES`

**What it is**

A dictionary mapping different ways users might say a parameter to the official parameter name.

**Why it exists**

Users don't always use the exact regulatory terminology. "Effluent" means the same as "discharge"; "suspended solids" = "TSS". Aliases normalize natural language to standard terms.

**Structure** (35+ aliases)

```python
_PARAM_ALIASES = {
  # Discharge-related
  "discharge": "discharge",
  "effluent": "discharge",
  "wastewater": "discharge",
  "outfall": "discharge",
  "emissions": "discharge",

  # Temperature
  "temperature": "temperature",
  "thermal": "temperature",
  "cooling water": "temperature",

  # BOD
  "bod": "bod",
  "biochemical oxygen demand": "bod",

  # TSS
  "tss": "tss",
  "suspended solids": "tss",
  "total suspended solids": "tss",

  # pH
  "ph": "ph",
  "acidity": "ph",
  "alkalinity": "ph",

  # Dissolved Oxygen
  "do": "do",
  "dissolved oxygen": "do",

  # Metals
  "copper": "copper",
  "zinc": "zinc",
  "lead": "lead",
  "chromium": "chromium",

  # Nutrients
  "nitrogen": "nitrogen",
  "phosphorus": "phosphorus",
  "ammonia": "ammonia",
  "nitrate": "nitrate",

  # Other
  "flow": "flow",
  "gpm": "flow",
  "cfm": "flow",
  ...
}
```

---

### `_FACILITY_CONTEXTS` (v0.15.0+)

**What it is**

A mapping of facility types to keyword lists. When the user mentions certain keywords, the system knows which facility type they're referring to.

**Why it exists**

Same parameter, different limits for different facility types. If the system knows the user is talking about a wastewater facility, it applies wastewater-specific limits.

**Structure**

```python
_FACILITY_CONTEXTS = {
  "wastewater": {
    "keywords": [
      "wastewater", "sewage", "activated sludge", "secondary treatment",
      "aeration basin", "treatment plant", "POTW", "municipal",
      "sanitary sewer", "wastewater system"
    ]
  },
  "industrial": {
    "keywords": [
      "industrial", "manufacturing", "factory", "plant discharge",
      "process water", "cooling water", "NPDES permit", "categorical",
      "pretreatment", "slug", "indirect discharge"
    ]
  },
  "stormwater": {
    "keywords": [
      "stormwater", "runoff", "storm drain", "wet weather",
      "precipitation", "MS4", "municipal separate storm sewer",
      "BMP", "best management practice"
    ]
  }
}
```

---

### `_FOREIGN_COUNTRIES`

**What it is**

A list of 60+ country names for jurisdiction checking.

**Why it exists**

If a user asks about French regulations or Chinese standards when RegOS covers Florida, the system detects the jurisdiction mismatch and warns the user.

**Sample entries**

```python
_FOREIGN_COUNTRIES = [
  "Afghanistan", "Albania", "Algeria", "Andorra",
  "Argentina", "Australia", "Austria", "Azerbaijan",
  ...
  "Canada", "China", "France", "Germany", "India",
  ...
  "United Kingdom", "Vietnam", "Yemen", "Zimbabwe"
]
```

---

### `_US_STATES_EXCEPT_FL`

**What it is**

A list of 49 US states, excluding Florida.

**Why it exists**

If RegOS scope is "Florida + Federal", and the user asks about Texas regulations, the system flags it as out-of-scope.

**Sample entries**

```python
_US_STATES_EXCEPT_FL = [
  "Alabama", "Alaska", "Arizona", "Arkansas",
  "California", "Colorado", "Connecticut", "Delaware",
  ...
  "Texas", "Utah", "Vermont", "Virginia", "Washington",
  "West Virginia", "Wisconsin", "Wyoming"
]
# Notably excludes "Florida"
```

---

### `_UNIT_PATTERN`

**What it is**

A compiled regex for detecting measurements in text.

**Why it exists**

To extract measurements like "50 mg/L" or "25°C", we need a pattern that matches number + unit.

**Pattern**

```python
_UNIT_PATTERN = re.compile(
  r'\b(\d+(?:\.\d+)?)\s*'
  r'(mg/L|mg/l|ppm|ppb|%|°C|°F|L|gal|'
  r'cfs|gpm|mgd|lbs/day|kg/day|...)',
  re.IGNORECASE
)
```

---

## Valve Configuration (Complete v0.16.0 Reference)

### Retrieval Valves

| Valve | Type | Default | Purpose |
|-------|------|---------|---------|
| `neo4j_uri` | string | `neo4j+s://...` | Neo4j Aura connection URI |
| `neo4j_username` | string | `neo4j` | Database username |
| `neo4j_password` | string | *(empty)* | Database password (required) |
| `neo4j_database` | string | `neo4j` | Database name |
| `max_sections` | int | 5 | Max regulatory sections to include |
| `max_section_chars` | int | 2000 | Max characters per section |
| `entity_search_limit` | int | 8 | Max entities from fulltext search |
| `min_relevance_score` | float | 0.5 | Minimum fulltext score threshold |

### Confidence Valves

| Valve | Type | Default | Purpose |
|-------|------|---------|---------|
| `confidence_threshold_high` | float | 0.75 | Score cutoff for HIGH confidence badge |
| `confidence_threshold_medium` | float | 0.50 | Score cutoff for MEDIUM confidence |
| `escalation_threshold` | float | 0.65 | Below this, trigger escalation |
| `w_max_overlap` | float | 0.35 | Weight for max entity overlap signal |
| `w_entity_count` | float | 0.12 | Weight for entity count signal |
| `w_section_count` | float | 0.12 | Weight for section count signal |
| `w_graph_exclusive` | float | 0.08 | Weight for graph exclusivity signal |
| `w_avg_direct` | float | 0.08 | Weight for average direct signal |

### Threshold Valves

| Valve | Type | Default | Purpose |
|-------|------|---------|---------|
| `threshold_check_enabled` | bool | `true` | Enable threshold evaluation |
| `thresholds_path` | string | `regulatory_thresholds.json` | Path to threshold definitions |
| `breach_db_path` | string | `breach_log.db` | SQLite database for audit log |

### Guardrail Valves

| Valve | Type | Default | Purpose |
|-------|------|---------|---------|
| `guardrail_enabled` | bool | `true` | Enable guardrail system |
| `out_of_scope_keywords` | string | JSON array | Keywords indicating out-of-scope queries |
| `guardrail_jurisdiction_enabled` | bool | `true` | Enable jurisdiction checking |
| `guardrail_jurisdiction_allowlist` | string | JSON array | Allowed jurisdictions (e.g., Florida, Federal) |
| `guardrail_jurisdiction_blocklist` | string | JSON array | Blocked jurisdictions |
| `guardrail_support_contact` | string | Email address | Contact shown in guardrail notices |

### Escalation Valves

| Valve | Type | Default | Purpose |
|-------|------|---------|---------|
| `escalation_enabled` | bool | `true` | Enable escalation system |
| `escalation_webhook_url` | string | *(empty)* | n8n webhook URL for case packets |

### Output Formatting Valves

| Valve | Type | Default | Purpose |
|-------|------|---------|---------|
| `enterprise_format` | bool | `true` | Structured consultant-style output |
| `show_confidence` | bool | `true` | Display confidence badge on responses |
| `show_trace` | bool | `false` | Append full retrieval trace to response |
| `debug` | bool | `false` | Append debug info to context |
| `priority` | int | 0 | Filter execution priority (lower = first) |
| `enabled` | bool | `true` | Master on/off switch |

---

## Error Handling & Resilience

All retrieval logic is wrapped in try/except blocks. If Neo4j is unreachable or a query fails, the filter passes through silently — the chat experience is never interrupted.

When errors occur:
1. Error is caught and logged (internal)
2. All state is cleared (`_citations`, `_confidence_score`, etc.)
3. Filter returns modified body unchanged
4. Chat continues without graph context (graceful degradation)

This ensures RegOS never breaks the user experience, even if infrastructure fails.

---

## Neo4j Graph Schema

```
(Section: 138 nodes) ←─── MENTIONS (1,770 edges) ←─── (Entity: 738 nodes)
                                                           │
                                                           └─→ RELATES_TO (1,470) ─→ (Entity)
```

**Section nodes (Episodic)**: Regulatory text sections
- Properties: `id`, `content` (full text), `source_description` (e.g., "Sec. 24-42.1"), `uuid`
- Fulltext index: `section_search` on `content` + `source_description`

**Entity nodes**: Regulatory concepts
- Properties: `id`, `name`, `summary`, `name_embedding`, `uuid`
- Fulltext index: `entity_search` on `name` + `summary`

**Relationships**:
- `MENTIONS`: Section mentions/discusses Entity
- `RELATES_TO`: Entity relates to another Entity

---

## Conclusion

The GraphRAG Filter is a sophisticated compliance engine that:

1. **Retrieves** regulatory content via a 4-step graph pipeline
2. **Scores** confidence in answers using 6-signal composite scoring
3. **Evaluates** thresholds with facility-aware disambiguation
4. **Detects** guardrails to prevent out-of-scope answers
5. **Escalates** low-confidence and breach cases for human review
6. **Formats** responses with compliance badges, disclaimers, and audit trails

Every method prioritizes both technical robustness and non-technical transparency. Compliance officers can understand the system's decisions; developers can modify and extend it.

**Current Version:** 0.16.0
**Last Updated:** 2026-02-26
**Maintainer:** RegOS Development Team
