# RegOS Development Changelog

A chronological record of every feature, fix, and design decision made during the RegOS build. This document captures the full journey — what worked, what didn't, and why.

---

## Session 1: Foundation (Features 1–3)

### Feature 1: Audit Logging

Built `audit_logger.py` — a filter that logs every chat interaction to a local SQLite database (`/app/backend/data/audit.db` inside the container).

**Records captured:** user ID, chat ID, message ID, query text, response text, timestamp, model used, confidence score, confidence signals.

**Key decisions:**
- Uses SQLite for zero-dependency deployment (no external DB needed)
- Audit logger runs as a separate filter instance from GraphRAG (can't share memory)
- Confidence data crosses the filter boundary via the message dict (originally used HTML comments — changed in v0.8.1, see Session 3)

**Access command:**
```bash
docker exec open-webui python3 -c "
import sqlite3, json
conn = sqlite3.connect('/app/backend/data/audit.db')
for row in conn.execute('SELECT timestamp, user_id, query, confidence_score FROM audit_records ORDER BY timestamp DESC LIMIT 20'):
    print(row)
conn.close()
"
```

### Feature 2: GraphRAG Pipeline

Built `graphrag_filter.py` — the core retrieval engine. See `graphrag_filter.md` for full technical documentation.

**Evolution:**
- v0.1.0: Started as a Pipe (replaced LLM endpoint) — caused deadlock, abandoned
- v0.3.0: Restructured as a Filter (inlet + outlet) — works WITH any model
- v0.4.0: Moved context from system message to user message (KB was overwriting system messages)
- v0.5.0: Added `[G1]` citation prefixes, trace mode, entity names in context header

### Feature 3: Confidence Scoring (v0.6.0)

Added a 6-signal weighted composite score (0.0–1.0) that reflects retrieval quality. See `confidence_scoring.md` and the Confidence Scoring section of `graphrag_filter.md`.

---

## Session 2: Enterprise Features (Feature 4 + Sources Panel)

### Demo Script

Created `demo_script.md` — a 4-act, ~10-minute demo covering Features 1–3 (Audit Logging, GraphRAG Pipeline, Confidence Scoring).

### Audit Log Docker Command

User tried to query the audit DB from Mac terminal — path was container-internal. Fixed with `docker exec`. Then sqlite3 wasn't in the container — switched to Python one-liner.

### Feature 4: Enterprise Output Formatting (v0.7.0)

**Problem:** User had no vision for output formatting. Needed help figuring out what to build.

**Discovery process:**
1. Asked clarifying questions: audience (both internal + external), pain points (messy citations, no structure, missing disclaimers, can't export clean), desired style ("consultant's review, professionally yet conversationally worded")
2. Designed initial structure with Summary → Regulatory Analysis → Applicable Sections table
3. User asked: "Do you think a system prompt would help us more?" — agreed to split responsibilities

**System prompt split (major architecture decision):**

| Component | Location | Handles |
|---|---|---|
| Identity, tone, persona, response structure | `system_prompt.md` (custom model) | Stable, per-model instructions |
| Citation mechanics ([G1], [G2]) | `graphrag_filter.py` | Dynamic, per-retrieval instructions |

**Expert interview integration:**
User uploaded a PDF from a practicing consultant interview (RegOS Expert-Mode Workflow Spec). Key insights incorporated:
- Three personas: Citizen, Consultant, Regulator
- Source of truth discipline — every requirement needs citation
- Actionable guidance — "What You Need To Do" section added
- Gap awareness — "Gaps & Limitations" section added (NEVER skip)
- Draft framing — not final compliance determination

**Output formatting fixes (iterative):**

| Issue | Fix |
|---|---|
| Disclaimer showing at end of response | Initially moved to trace, then user changed mind — moved back to main response |
| `<details><summary>` HTML tags showing as raw text | Open WebUI doesn't render these properly. Removed all HTML, switched to pure markdown headers |
| HTML comment `<!-- GRAPHRAG_CONFIDENCE:... -->` visible to users | Audit logger needs higher priority number to run after GraphRAG filter and strip the comment |
| Confidence display `🟡 MEDIUM (0.67)` looked unprofessional | Changed to clean italicized text: `Source confidence: 67%` |
| Trace confidence section was just raw numbers | Added human-readable breakdown table with columns: "What we measured", "Result", "Contribution", "Why it matters" |

### Sources Panel Integration (v0.8.0) — The Hardest Problem

**Goal:** Make GraphRAG-retrieved sections appear in Open WebUI's Sources button alongside KB sources, with `[G1]`, `[G2]` nomenclature.

**This took 7 attempts across multiple hours.** Here's every approach tried:

#### Attempt 1: Inlet event emission
- **What:** Used `__event_emitter__` in inlet to emit `{"type": "source"}` events
- **Result:** ONLY GraphRAG sources showed, KB sources disappeared
- **Why failed:** Inlet runs before KB pipeline; GraphRAG sources get set, KB overwrites them

#### Attempt 2: Outlet event emission
- **What:** Moved `__event_emitter__` to outlet
- **Result:** NO GraphRAG sources appeared
- **Why failed:** By outlet time, frontend already rendered sources from streaming response

#### Attempt 3: Metadata injection
- **What:** Filter wrote `__metadata__["filter_sources"]`, middleware read it
- **Result:** Key was missing
- **Why failed:** Middleware recreates metadata dict at line ~2192: `metadata = {**metadata, ...}`

#### Attempt 4: form_data injection
- **What:** Filter wrote `body["graphrag_sources"]`, middleware read `form_data.pop("graphrag_sources")`
- **Result:** Key was missing
- **Why failed:** `form_data` gets reassigned by `chat_memory_handler`, `chat_web_search_handler`, etc.

#### Attempt 5: Inside chat_completion_files_handler
- **What:** Moved pickup into the files handler function, right before return
- **Result:** Still didn't work
- **Why failed:** `body` parameter is a different reference due to dict reassignment chain

#### Attempt 6: Local variable capture (early in middleware)
- **What:** Captured `form_data.pop("graphrag_sources", [])` immediately after filter inlet returned (before any reassignment)
- **Result:** Didn't work after restart
- **Why failed:** Unknown — theoretically sound but something in the reference chain broke

#### Attempt 7 (WORKING): Direct outlet mutation
- **What:** In outlet, append to `body["messages"][-1]["sources"]` directly
- **Result:** Both KB and GraphRAG sources appear together
- **Why it works:** By outlet time, the message dict already has KB sources. Mutating the list directly persists because it's the same Python object that gets saved to the database
- **Source:** Confirmed by [Open WebUI community (Discussion #16099)](https://github.com/open-webui/open-webui/discussions/16099)

**Key lesson:** Don't fight the middleware pipeline. The outlet's `body["messages"]` is the canonical representation — mutate it directly.

**Middleware status:** Fully rolled back to stock. Zero modifications. All 6 previous middleware changes were removed.

---

## Session 3: Disclaimer Strategy & Confidence Transport Fix

### Disclaimer Research

Researched industry standards for professional AI tool disclaimers. Key findings:

- Peer-reviewed study (5,000+ participants, 13 experiments) found AI disclaimers actively erode professional trust
- No leading legal/compliance AI tool (Harvey AI, CoCounsel, Westlaw) uses "consult a professional" language
- Professional tools frame verification as standard workflow, not a product deficiency
- Legal/insurance/regulatory requirements mean you can't remove disclaimers entirely — EU AI Act (Aug 2026), FTC disclosure mandate (Oct 2024), AI vendor liability precedent (Workday case 2025)

Created `disclaimer_research.md` documenting all findings, 4 options (A–D), sources, and recommendation.

### Conditional Disclaimer System (v0.8.1)

**Problem:** Static disclaimer said "consult qualified professionals before acting on this guidance" — counterproductive when the users ARE the consultants and APAS IS the AI company.

**Solution:** 3-state conditional disclaimer that adapts based on confidence band and retrieval completeness. Amalgam of Options A (confidence-based), B (professional workflow framing), and D (engagement-level split).

| State | Trigger | Language |
|---|---|---|
| HIGH | confidence ≥80% AND sections = max | Minimal, confident. "Review cited sections for your specific facility context." |
| MEDIUM | confidence 50–79% OR partial retrieval | Acknowledges gaps. "Some applicable sections may not have been retrieved." |
| LOW | confidence <50% OR ≤1 section | Honest about limits. "Verify this analysis against the full Chapter 24 text." |

No state ever says "consult qualified professionals" or "not a final compliance determination."

**Implementation:** Added `_build_disclaimer()` method to `graphrag_filter.py`. Replaced hardcoded static disclaimer in outlet with conditional call.

### Confidence Data Transport Fix (v0.8.1)

**Problem:** The `<!-- GRAPHRAG_CONFIDENCE:{...} -->` HTML comment was visible to users as raw text. Open WebUI doesn't reliably treat HTML comments as invisible.

**Root cause:** The audit logger was supposed to strip this comment, but only if it ran after the GraphRAG filter (priority-dependent). Even with correct priority, Open WebUI's rendering engine sometimes showed the raw comment.

**Fix:** Replaced HTML comment embedding entirely. Now stores confidence data directly on the message dict:

```python
# GraphRAG filter outlet
messages[i]["graphrag_confidence"] = {
    "score": self._confidence_score,
    "band": self._confidence_band,
    "signals": self._confidence_signals,
}

# Audit logger outlet
for msg in reversed(messages):
    if msg.get("role") == "assistant" and "graphrag_confidence" in msg:
        conf_data = msg.pop("graphrag_confidence", {})
        # ... extract and store
```

The `pop()` removes the key after reading. Audit logger retains legacy HTML comment parsing as a backward-compatible fallback.

**Key lesson:** Non-standard keys on the message dict object are never rendered by Open WebUI's frontend. This is the same pattern used for Sources Panel injection — direct mutation of the message object in the outlet is the safest data transport mechanism between filters.

---

## Session 4: Escalation Workflow (Feature 5)

### Feature 5: Automatic Escalation (v0.9.0)

**Problem:** Low-confidence responses need human review, but there's no mechanism to flag them. Users receive the response without knowing it might be unreliable.

**Design decisions:**
- Automatic triggers only (no manual user-initiated escalation)
- Audit DB flagging for future Dashboard (Feature 7)
- Visible notice appended to the response so users know the query was flagged

**Implementation approach:** Extended the two existing filters instead of creating a third. GraphRAG filter already has confidence data in memory; audit logger already has the DB connection and three prepared escalation columns. Same message dict mutation pattern (`graphrag_escalation`) as confidence transport.

**Escalation triggers (any of these):**
- Confidence score < `escalation_threshold` (default 0.5)
- Zero sections retrieved (no regulatory context at all)
- Confidence band is LOW

**Signal-aware reason generation:** The `_escalation_reason()` method inspects the 6 confidence signals to explain WHY escalation triggered, not just that it triggered. Examples: "Low retrieval confidence (32%): weak entity matching, sparse section retrieval" vs. "No regulatory sections retrieved for this query."

**Case reference format:** `REG-YYYYMMDD-XXXX` — deterministic 4-char hex from SHA-256 of (user_id + chat_id + epoch). Human-readable, collision-resistant without a counter.

### Feature 5 Upgrade: n8n Webhook Integration (v0.10.0)

**Problem:** v0.9.0 only flagged the audit DB — no external notification, not demo-ready. Needed an end-to-end pipeline that customers could see working.

**Solution:** Added n8n webhook integration. When escalation triggers, the GraphRAG filter now:

1. **Builds a full-context case packet** — rich JSON with user info, query, response, full conversation history, all GraphRAG citations with section text, KB sources from ChromaDB, entity matches from graph search, assembled graph context, all 6 confidence signals, and escalation reason
2. **POSTs to n8n** — configurable webhook URL (`escalation_webhook_url` Valve). Uses `urllib.request` (stdlib). Fire-and-forget on failure — never blocks the chat.
3. **n8n generates AI case brief** — an AI node compresses the full dump into a structured 1-page brief (risk assessment, gap analysis, recommended actions). Raw dump also preserved for download.
4. **Shows structured notice** — replaces the disclaimer (not stacked) with a professional escalation notice including case reference, status, and user's contact email from their Open WebUI profile
5. **Flags audit DB** — unchanged from v0.9.0

**Key design change:** Escalation notice now REPLACES the disclaimer via `if/elif` instead of stacking both. When escalation triggers, the user sees the escalation notice; when it doesn't, they see the normal conditional disclaimer.

**What the user sees (v0.10.0):**

```
---
**Expert Review Initiated**

This analysis has been flagged for compliance review due to limited regulatory context.

**Case:** REG-20260224-7A3F | **Status:** Under review
**Contact:** We'll reach out to you at analyst@company.com once our review is complete.

*If this isn't your preferred contact email, please update your Open WebUI profile.*
```

**n8n pipeline (two branches):**
- Branch 1: Stores the case file for reviewer access
- Branch 2: Returns confirmation message to the webhook

**What gets stored in the audit DB:**
- `escalation_triggered` = 1
- `escalation_target` = valve-configured target (default "compliance-review")
- `case_packet_ref` = JSON with case_ref, reason, confidence_score, confidence_band

**What this does NOT include (deferred):**
- Manual user-initiated escalation
- Dashboard UI (Feature 7)
- Escalation resolution workflow (marking cases as "reviewed")

---

## Files Created/Modified (All Sessions)

| File | Action | Description |
|---|---|---|
| `functions/graphrag_filter.py` | Modified | v0.14.0 → v0.17.3. FEA schema migration: complete retrieval pipeline rewrite, Cypher injection fix, confidence scoring rebalance for concept expansion |
| `functions/graphrag_filter.md` | Modified | Updated to v0.11.0. Sources Panel docs, architecture split, conditional disclaimer system, escalation workflow + webhook docs, guardrail feature docs |
| `functions/audit_logger.py` | Modified | v0.2.0 → v0.4.0. Confidence extraction via message dict, escalation metadata extraction, guardrail metadata extraction and DB writes |
| `functions/audit_logger.md` | Modified | Added confidence transport, escalation transport, guardrail transport, version history |
| `system_prompt.md` | Modified | Custom model system prompt for RegOS (3 personas, response structure, citation rules, scope, honesty, tone). Added structured refusal formatting instructions (v0.11.0). |
| `tests/adversarial_guardrails.md` | Created | 28 test queries across 7 categories for guardrail verification |
| `disclaimer_research.md` | Created | Industry research on professional AI disclaimers, 4 options, sources, recommendation, decision record |
| `demo_script.md` | Created | 4-act demo script covering Features 1–3 |
| `REGOS_CHANGELOG.md` | Created | This file — full development journey |
| `n8n/regos_escalation_workflow.json` | Created | Importable n8n workflow for escalation pipeline (webhook → validate → case file + confirmation) |
| `n8n/N8N_ESCALATION_SETUP.md` | Created | Setup guide: import instructions, node-by-node explanation, testing, troubleshooting |
| `api/scada_stream.py` | Created | SCADA streaming API: WebSocket, SSE, REST batch ingestion with real-time threshold evaluation |
| `api/apas_bridge.py` | Created | APAS Telemetry polling bridge: JWT auth, metric mapping, unit conversion, feeds into SCADA pipeline |
| `data/apas_metric_mappings.json` | Created | Metric-to-parameter mapping config: 8 active mappings + 14 effluent sensor templates |
| `backend/open_webui/utils/middleware.py` | Modified → Rolled back | 6 different modifications attempted and removed. File is now fully stock. |

---

## Feature Status

| # | Feature | Status | Version | Notes |
|---|---|---|---|---|
| 1 | Audit Logging | Done | 0.4.0 | SQLite-based, reads confidence + escalation + guardrail data from message dict |
| 2 | GraphRAG Pipeline | Done | 0.17.3 | FEA schema: 4-step retrieval (document search → entity traversal → concept expansion → direct search), confidence scoring, threshold evaluation, guardrails, escalation |
| 3 | Confidence Scoring | Done | 0.6.0+ | 6-signal composite, percentage display, trace breakdown |
| 4 | Enterprise Output Formatting | Done | 0.7.0+ | Expert-informed, system prompt + filter split |
| 4b | Sources Panel Integration | Done | 0.8.0 | GraphRAG sources in Sources button alongside KB |
| 4c | Conditional Disclaimers | Done | 0.8.1 | 3-state confidence-adaptive, no "consult professionals" |
| 5 | Escalation Workflow | Done | 0.10.0 | Auto-flag on low confidence, n8n webhook integration, structured notice replaces disclaimer, case packet with full context |
| 6 | Threshold Evaluation | Done | 0.13.0 | (A) Confidence weight tuning: 600-config sweep, accuracy 60%→80%. (B) Regulatory threshold table: 96 thresholds from Ch.24. (C) Threshold eval service with SHA-256 evidence hashing. (D) Open WebUI tool (check_threshold, list_thresholds, get_breach_summary). (E) REST API for dashboard. |
| 7 | Dashboard | Deprioritized | — | Replaced by SCADA streaming API as primary integration point |
| 7b | SCADA Streaming API | Done | 0.1.0 | WebSocket + SSE + REST batch, rate limiting, auth, real-time threshold evaluation |
| 7c | APAS Telemetry Bridge | Done | 0.1.0 | Polling bridge: JWT auth, metric mapping, unit conversion, feeds into SCADA pipeline |
| 8 | Refusal & Guardrails | Done | 0.12.0 | Hard guardrails (out-of-scope keywords, zero-retrieval, jurisdiction mismatch), professional notices with support contact, confidence suppression, audit logging, adversarial test suite |
| 9 | Integrated Threshold Eval | Done | 0.14.0 | Threshold detection + evaluation embedded in GraphRAG filter. Works with ANY model (no tool-calling needed). Regex detection for 35+ parameters, evaluates against 96 Ch.24 thresholds, injects determination + evidence hash into LLM context, compliance badge in outlet, breach DB logging. 42/42 tests. |

---

## Session 5: Refusal & Guardrails (Feature 8)

### Feature 8: Refusal & Guardrails (v0.11.0)

**Problem:** The system relied entirely on the LLM's system prompt to refuse out-of-scope questions. This is a soft boundary — the LLM can be bypassed via prompt injection or just occasionally fail to refuse. Additionally, guardrail events were never logged to the audit DB (columns existed but were empty).

**Solution:** Hard guardrails in the GraphRAG filter that fire before the LLM sees the query, plus structured refusal formatting and full audit logging.

**Sub-features implemented:**

**A. Hard Guardrail Detection (inlet):**
- Out-of-scope keyword check: runs BEFORE the graph search. A configurable `guardrail_exclusion_keywords` Valve lists topics outside Chapter 24 (building codes, zoning, OSHA, EPA federal, immigration, criminal law, etc.). If any keyword matches, the GraphRAG pipeline is skipped entirely and the LLM responds naturally with the system prompt's refusal instructions.
- Zero-retrieval detection: runs AFTER graph+vector search. If both entity search and section search return zero results, the guardrail triggers. The LLM still responds but the guardrail notice is appended.
- Jurisdiction mismatch: stubbed for future multi-jurisdiction support. Always returns False.

**B. Structured Refusal Formatting (outlet):**
- New `_build_guardrail_notice()` method produces a professional notice with title, explanation, actionable suggestion, and guardrail reference ID (GRD-YYYYMMDD-XXXX).
- Two notice templates: "Outside Regulatory Scope" (for out-of-scope) and "No Regulatory Context Found" (for zero-retrieval).
- Guardrail notice replaces the disclaimer — same priority pattern as escalation: guardrail > escalation > disclaimer.

**C. Guardrail Data Transport & Audit Logging:**
- GraphRAG filter stores `graphrag_guardrail` on the message dict (same pattern as confidence and escalation).
- Audit logger v0.4.0 reads the data and writes to `guardrail_triggered`, `guardrail_type`, `guardrail_reason` columns.

**D. System Prompt Refinement:**
- Added "Refusal Formatting" section to `system_prompt.md` with structured refusal template: Summary → Why This Is Outside Scope → What You Should Do Instead.
- Refusals are kept concise (no Applicable Sections table or Gaps section).
- Never says "consult a professional" — names specific authorities instead.

**E. Adversarial Test Suite:**
- Created `tests/adversarial_guardrails.md` with 28 test queries across 7 categories: out-of-scope (6), zero-retrieval (3), jurisdiction mixing (3), citation fabrication (3), prompt injection (4), legitimate queries (6), edge cases (4).
- Each test has expected behavior, guardrail type, and audit DB verification.
- Includes audit DB query command for batch verification.
- Documents known limitations (blunt keyword matching, stub jurisdiction detection, system-prompt-only injection defense).

**Priority chain in outlet:**
```
guardrail triggered? → guardrail notice (skip escalation & disclaimer)
  else escalation triggered? → escalation notice (skip disclaimer)
    else has confidence? → conditional disclaimer
```

### Guardrail Notice Refinement (v0.11.1)

**Problem:** When a guardrail triggered, a confidence disclaimer (e.g., "60% confidence ratio") could still appear alongside the guardrail notice. The confidence data was being stored on the message dict independently of the guardrail/escalation/disclaimer chain, meaning the audit logger could pick up stale confidence data even on guardrailed queries.

**Fix:**
- Moved confidence data storage (`graphrag_confidence` on message dict) from before the priority chain to inside the escalation and disclaimer branches only. When a guardrail fires, no confidence data is stored — because it's meaningless for an out-of-scope or zero-retrieval query.
- Redesigned `_build_guardrail_notice()` with professional enterprise wording based on industry patterns (Westlaw, ServiceNow, enterprise SaaS).
- Added `guardrail_support_contact` Valve — configurable support contact (email or phone) shown in guardrail notices. Defaults to a generic "contact our support team" message if not set.
- Notice now includes: scope statement, actionable next steps, and customer service contact for users who believe the determination is incorrect.

**What the user sees (v0.11.1):**

```
---
**Outside Regulatory Scope**

RegOS identified this question as outside its current scope. RegOS is designed to support compliance with Miami-Dade County Chapter 24 (Environmental Quality Control Board) and does not cover the topic referenced in your query.

**Next steps:** If your question relates to Chapter 24, try rephrasing with specific regulatory terms (e.g., effluent limits, pretreatment, discharge permits). For topics outside Chapter 24, consult the relevant regulatory authority directly.

If you believe this determination is incorrect, please contact our support team at support@regos.ai for further assistance.
Ref: GRD-20260224-A1B2
```

### Jurisdiction Mismatch Detection (v0.12.0)

**Problem:** Queries like "What regulations apply to a pump station in Saudi Arabia?" were NOT triggering any guardrail. The out-of-scope keyword list only catches topic mismatches (building codes, zoning, OSHA), not geographic mismatches. The zero-retrieval guardrail didn't fire because "pump station" and "regulations" matched entities in the graph (8 entities, 5 sections retrieved). So the user saw a confidence disclaimer ("60% confidence") alongside the LLM's correct but unguarded refusal.

**Solution:** Implemented `_check_jurisdiction_mismatch()` — a text-based heuristic that runs on the raw query BEFORE graph search (same priority as out-of-scope keywords).

**Detection strategy:**
1. If query mentions an allowlisted term (miami, miami-dade, dade county, south florida, florida) → NOT flagged
2. If query mentions a foreign country (built-in list of 60+ countries) → flagged
3. If query mentions a US state other than Florida (built-in list of 49 states) → flagged
4. If query mentions a custom blocklisted term (configurable Valve) → flagged
5. If both an allowlisted term AND a foreign location appear → NOT flagged (allowlist wins — user is likely asking a relevant comparison)

**New Valves:**
- `guardrail_jurisdiction_enabled` (default: True)
- `guardrail_jurisdiction_allowlist` (default: "miami,miami-dade,dade county,south florida,florida")
- `guardrail_jurisdiction_blocklist` (default: empty — for adding custom locations)

---

## Session 6: Threshold Evaluation (Feature 6)

### Feature 6: Threshold Evaluation (v0.13.0)

**Problem:** The confidence scoring weights and escalation threshold were hardcoded guesses (all set during the initial v0.6.0 implementation). Queries that should have triggered escalation (composting odor complaints, food truck greywater, stormwater during dry season) scored 67–81% and never escalated, because the escalation threshold (0.5) was too low and the scoring weights rewarded quantity over quality.

**Approach:** Built a threshold evaluation harness (`tools/threshold_evaluation.py`) with 12 test cases reconstructed from real RegOS testing sessions. Each test case includes observed Lucene scores, entity counts, section counts, and expected behavior (band classification + escalation decision). Swept 600 weight configurations varying the two most impactful weights (avg_entity and max_overlap), escalation threshold, and HIGH band cutoff.

**Results:**
- Current production (v0.12.0): **60% overall accuracy** (6/10 non-guardrail cases correct)
- Recommended config: **80% overall accuracy** (8/10 correct)
- Key improvement: escalation accuracy jumped from 70% to 90%

**Changes applied:**
- `escalation_threshold`: 0.50 → **0.65** (biggest single improvement — catches MEDIUM-scored queries that should escalate)
- `w_max_overlap` (best-section bridging weight): 0.25 → **0.35** (primary confidence signal — a section connected by many entities is the strongest relevance indicator)
- `w_entity_count`: 0.15 → **0.12** (entity count alone rewards breadth, which inflates scores for vague queries)
- `w_section_count`: 0.15 → **0.12** (same issue — finding 5 sections is easy and shouldn't count as much)
- `w_graph_exclusive`: 0.10 → **0.08** (minor adjustment)
- `w_avg_direct`: 0.10 → **0.08** (minor adjustment)
- HIGH band cutoff: 0.80 → **0.75** (slightly more generous for genuinely strong matches)

**Remaining misses (2/10):**
1. Food truck greywater scores 73% (MEDIUM) but doesn't escalate at 0.65 threshold — "mobile food service operation" is an actual entity scoring 17.24. Would need semantic relevance (FEA graph) to fix.
2. Noise complaint scores 45% (LOW) but expected MEDIUM — acceptable since it correctly escalates.

**Test harness:** `tools/threshold_evaluation.py` can be re-run as new test cases are added. Supports `--sweep` for weight optimization and `--report` for current analysis.

### Feature 6B: Regulatory Threshold Evaluation Service (v0.13.0)

**Problem:** Users ask questions like "Is our BOD level of 45 mg/L compliant?" and the LLM has to guess based on context. There's no machine-readable table of Chapter 24 thresholds and no way to programmatically check compliance.

**Solution — 5 sub-tasks completed:**

**A. Curated threshold table (data/regulatory_thresholds.json):**
- 96 regulatory thresholds extracted from Chapter 24 sections via regex
- Covers: concentration limits (45), timeframes (16), distances (13), percentages (12), penalties (3), volumes (3), areas (3)
- Key sections covered: 24-42 (effluent), 24-42.4 (discharge), 24-42.6 (FOG), 24-43.4 (distances), 24-49.2 (trees), 24-30/31 (penalties), 24-41 (air), 24-42.1 (tertiary)
- Each entry has: value, unit, parameter, direction (max/min/exact), context, section_ref, type

**B. Threshold evaluation service (functions/threshold_eval.py):**
- `ThresholdRegistry`: loads and indexes thresholds by parameter, section, and type. Fuzzy matching on parameter names.
- `ThresholdEvaluationService.evaluate()`: takes a parameter + value, returns COMPLIANT / BREACH / BORDERLINE with margin and percentage-of-limit.
- BORDERLINE = within 10% of the limit (approaching violation).

**C. SHA-256 evidence hashing:**
- Every determination gets a `compute_evidence_hash()` covering: parameter, user_value, threshold_value, direction, unit, status, timestamp, section_ref.
- Hash is stored alongside the determination in the breach DB.
- The `/verify/{hash}` API endpoint recomputes and compares — detects tampering.

**D. Open WebUI tool registration (functions/threshold_eval.py → Tools class):**
- `check_threshold(parameter, value, unit)` — LLM calls this when users provide measurements
- `list_thresholds(parameter)` — LLM calls to show what limits apply
- `get_breach_summary()` — LLM calls to report compliance history
- Registered as an Open WebUI Tool (same pattern as other tools)

**E. Dashboard API (api/breach_api.py):**
- `GET /api/breaches/summary` — counts, breach rate, top breached params
- `GET /api/breaches` — list breach records (filterable by date)
- `GET /api/breaches/evaluations` — all evaluations (breach + compliant)
- `POST /api/breaches/check` — run threshold check via API
- `GET /api/breaches/parameters` — list available parameters
- `GET /api/breaches/thresholds/{param}` — get thresholds for a parameter
- `GET /api/breaches/verify/{hash}` — verify evidence hash integrity
- FastAPI with CORS, can run standalone or be mounted in existing app

---

## Session 7: SCADA Streaming API

### SCADA Streaming API (v0.1.0)

**Problem:** An external product transmits SCADA (Supervisory Control and Data Acquisition) sensor data. RegOS needs to receive these readings in real-time, evaluate each against Chapter 24 regulatory thresholds, and stream back compliance determinations. The dashboard (Feature 7) was deprioritized — this streaming API replaces it as the primary integration point.

**Solution:** Built `api/scada_stream.py` — a FastAPI service with three transport modes for different integration patterns:

**A. WebSocket (`/ws/scada`):**
- Full-duplex streaming — external product sends readings, receives determinations in real-time
- Protocol: JSON messages with `type` field (`reading`, `batch`, `ping`, `auth`)
- Supports single readings and batches in the same connection
- Authentication via query parameter or initial auth message
- Ping/pong keepalive for connection health monitoring

**B. Server-Sent Events (`/api/scada/stream`):**
- One-way push channel for monitoring clients
- Filterable by status (`BREACH`, `BORDERLINE`, `COMPLIANT`) and parameter name
- 30-second keepalive timeout with automatic reconnect support
- Separate from ingestion — SSE clients subscribe, POST/WebSocket clients send data

**C. REST Batch (`/api/scada/ingest`):**
- Batch POST for polling-style integrations
- Single-reading shortcut at `/api/scada/ingest/single`
- Immediate synchronous response with all determinations
- Suitable for products that can't maintain persistent connections

**Infrastructure features:**
- Token-bucket rate limiting (configurable `SCADA_MAX_RPS`, default 100/s)
- Bearer token authentication via `SCADA_API_KEY` env var (open in dev mode)
- In-memory recent determinations buffer (last 200, queryable via `/api/scada/recent`)
- Throughput metrics and connection counts via `/api/scada/status`
- Health check endpoint at `/api/scada/health`
- All determinations logged to breach DB with SHA-256 evidence hashes (reuses Feature 6B infrastructure)

**Integration with existing infrastructure:**
- Uses `ThresholdEvaluationService.evaluate()` from `functions/threshold_eval.py`
- Writes to the same breach SQLite DB as the chat tool and REST API
- Evidence hashes are identical whether evaluation comes from chat, REST, or SCADA stream
- Broadcasts determinations to all connected SSE subscribers for real-time monitoring

**Testing:** 15 tests covering health, status, parameters, single ingest (compliant/breach/borderline), batch ingest, no-threshold-found, recent buffer, WebSocket single/batch/ping, evidence hash integrity, and counter incrementing. All pass.

### APAS Telemetry Bridge (v0.1.0)

**Problem:** The external SCADA data source is the APAS Telemetry Analytics platform, which stores 123SCADA sensor data in TimescaleDB and exposes it via a REST API with JWT auth. APAS doesn't push data — it's pull-based. RegOS needs to poll APAS for new readings, map SCADA metrics to Chapter 24 parameters, apply unit conversions, and evaluate compliance.

**Solution:** Built `api/apas_bridge.py` — a polling bridge that connects the APAS Telemetry API to the RegOS threshold evaluation pipeline.

**Components:**

**A. Metric Mapping Registry (`data/apas_metric_mappings.json`):**
- Maps APAS metric names (e.g., `rtu.*.temperature`) to RegOS threshold parameters (e.g., `Temperature`)
- Supports wildcard patterns via `fnmatch` for device ID flexibility
- Configurable unit conversions (e.g., °C → °F with formula `value * 9/5 + 32`)
- `evaluate` flag controls which metrics get threshold-checked vs. ignored
- Currently 8 mappings (1 evaluable: temperature). Includes 14 ready-to-activate effluent sensor templates.

**B. APAS API Client (sync + async):**
- JWT authentication with auto-refresh (re-auth on 401, proactive refresh at 50 min)
- Wraps `/api/telemetry/query`, `/api/telemetry/catalog`
- Handles APAS pagination (cursor-based) and 10-metric-per-query batching
- Exponential backoff on consecutive errors (1s → 2s → 4s → 8s → 16s cap)

**C. Polling Loop:**
- Configurable interval (default 30s, matching SCADA poll frequency)
- Each cycle: fetch catalog → filter to evaluable metrics → query latest readings → map → convert → evaluate → broadcast
- Feeds directly into `scada_stream.py`'s `evaluate_reading()` and `broadcast_determination()`

**D. Management API:**
- `GET /api/apas/status` — poller state, throughput, error tracking
- `POST /api/apas/start` / `POST /api/apas/stop` — control the poller
- `GET /api/apas/mappings` — list all metric mappings
- `GET /api/apas/catalog` — proxy APAS catalog with RegOS mapping annotations
- `POST /api/apas/test-poll` — execute one poll cycle manually

**Testing:** 12 tests — all pass.

---

## Session 8: Integrated Threshold Evaluation (Feature 9)

### Feature 9: Integrated Threshold Evaluation in GraphRAG Filter (v0.14.0)

**Problem:** The threshold evaluation service (`threshold_eval.py`) was built as an Open WebUI Tool that the LLM calls via function/tool calling. However, the base model powering RegOS (Nemotron 3 Nano 30B) does NOT support tool calling. When users asked "Is our BOD level of 45 mg/L compliant?", the LLM answered purely from GraphRAG-retrieved regulatory text — it never invoked the threshold tool, produced no JSON determination, no evidence hash, and no breach DB entry.

**Solution:** Embedded the threshold evaluation logic directly inside `graphrag_filter.py` so it works with ANY model. The filter now detects numeric measurements in queries via regex, evaluates them against Chapter 24 thresholds programmatically, and injects the determination into the LLM context — all before the model sees the message.

**How it works:**

1. **Detection (inlet):** A regex-based detector scans the user's query for known parameter names (35+ aliases: BOD, TSS, dissolved oxygen, temperature, pH, copper, lead, zinc, etc.) paired with numeric values and optional units. Uses a two-step approach: find parameter mentions → find nearby numbers → pair by proximity (within 120 chars).

2. **Evaluation (inlet):** Loads `regulatory_thresholds.json` (96 thresholds), fuzzy-matches the parameter name, checks value against limit (direction-aware: max, min, exact), and returns COMPLIANT / BREACH / BORDERLINE with margin, percentage-of-limit, and SHA-256 evidence hash.

3. **Context injection (inlet):** Determination data is injected alongside the GraphRAG context in the user message. Includes explicit instructions telling the LLM to report the exact status, threshold value, margin, and evidence hash.

4. **Compliance badge (outlet):** A structured "Compliance Determination" table is appended to the response with parameter, measured value, regulatory limit, status, margin, and truncated evidence hash.

5. **Breach DB logging:** Every evaluation is logged to the same SQLite breach DB used by the standalone threshold service and SCADA bridge. Evidence hashes are computed identically.

6. **System prompt update:** Added "Threshold Evaluation Data" section instructing the LLM that automated threshold data takes precedence over text interpretation.

**New Valves:**
- `threshold_check_enabled` (default: True)
- `thresholds_path` (default: `/app/backend/data/regulatory_thresholds.json`)
- `breach_db_path` (default: `/app/backend/data/regos_breaches.db`)

**Testing:** 42 tests covering detection (5 query patterns), evaluation (BREACH/COMPLIANT/BORDERLINE/min-direction), context builder, compliance badge, breach DB logging, pH edge case, and end-to-end. All pass.

**Files changed:**
- `functions/graphrag_filter.py` — v0.13.0 → v0.14.0
- `system_prompt.md` — added Threshold Evaluation Data section
- `functions/graphrag_filter.md` — updated version history

---

## Session 9: FEA Graph Migration & Retrieval Pipeline Rewrite

### Knowledge Graph Rebuild — FEA v2 (v0.15.0–v0.16.0)

**Problem:** The original graph (876 nodes, 2 labels, 3,240 relationships) used a flat Entity/Episodic schema. While it had hidden richness (898 distinct named RELATES_TO relationships, 1,024-dim embeddings on nodes AND edges), it lacked structural hierarchy. The FEA (Fixed Entity Architecture) v2 methodology was adopted to provide a 3-layer ontology-document-entity graph.

**New graph schema (v0.16.0):**
- 3 labels: Ch24Class (ontology concepts), Ch24Document (regulatory sections), Ch24Entity (extracted entities)
- 4 relationship types: RELATES_TO_CONCEPT, MENTIONS_ENTITY, SUBCLASS_OF, CH24_RELATIONSHIP
- 693 nodes, 2,351 relationships
- Fulltext index: ch24_doc_fulltext on Ch24Document (text + title)
- Vector index: ch24_doc_vector (128-dim, cosine — TF-IDF + SVD embeddings, not neural)

### Retrieval Pipeline Rewrite (v0.17.0)

**Problem:** After the graph rebuild, the retrieval pipeline in graphrag_filter.py was querying old schema labels (Entity, Episodic, MENTIONS) that no longer existed. Every query returned zero results.

**Solution:** Complete rewrite of 5 retrieval methods:
- `_search_documents()` — fulltext search on Ch24Document via ch24_doc_fulltext index
- `_search_entities_by_name()` — term matching against Ch24Entity.value with parameterized queries
- `_get_sections_for_matched_entities()` — MENTIONS_ENTITY traversal from entities back to documents
- `_get_sections_via_concepts()` — concept expansion through ontology (RELATES_TO_CONCEPT → sibling documents)
- `_search_sections_direct()` — direct fulltext fallback

**New 4-step pipeline:**
1. Document fulltext search (title + text)
2. Entity name matching → MENTIONS_ENTITY traversal back to documents + Concept expansion via ontology
3. Direct fulltext search (separate path for merge)
4. Context assembly with sectionId-based dedup

### Bug Fixes (v0.17.1–v0.17.2)

**v0.17.1 — Cypher injection fix:**
- Raw user input was interpolated via f-string into Cypher queries in `_search_entities_by_name`
- Apostrophes in queries (e.g., "what's the permit") broke Cypher syntax
- Fixed with parameterized `$terms` list: `any(term IN $terms WHERE toLower(e.value) CONTAINS term)`
- Added try/except to all 5 Neo4j methods

**v0.17.2 — Stale variable references:**
- `entities` variable no longer existed after rename to `doc_matches`/`entity_matches`
- Trace output, debug_info, and system prompt builder all referenced stale names
- Fixed all references across inlet, outlet, trace, and system prompt

**Other fixes:**
- `KeyError: 'uuid'` in outlet source injection — Ch24Document uses `sectionId` not `uuid`
- Ch24Entity nodes have no `uuid` property — switched to `elementId(e)` for entity identification

### Confidence Scoring Rebalance (v0.17.3)

**Problem:** The "Best section match" signal (weight 0.35) was based on `section_entity_counts` which was always near-zero in the FEA schema. Ch24Entity values are statute references and agencies — rarely overlap per section like old Entity nodes did. Every query showed "0 entities → 0%" on this signal.

**Solution:** Replaced entity overlap with concept expansion as the primary graph signal. New weights:
- avg_doc_score: 0.30 (was avg_entity_score: 0.25)
- doc_count: 0.15 (was entity_count: 0.12)
- concept_expansion: 0.25 (NEW — replaces max_entity_overlap: 0.35)
- section_count: 0.12 (unchanged)
- has_graph_exclusive: 0.10 (was 0.08)
- avg_direct_score: 0.08 (unchanged)

Band cutoffs lowered: HIGH >= 0.70 (was 0.75), MEDIUM >= 0.45 (was 0.50)

---

## Key Technical Lessons

1. **Open WebUI filters can't inject data through the middleware pipeline reliably.** Dicts get recreated, form_data gets reassigned, metadata gets rebuilt. The only reliable path is mutating the message body directly in the outlet.

2. **System prompt + filter is better than filter-only for formatting.** Stable instructions (identity, tone, structure) belong in the system prompt. Dynamic instructions (citation mechanics referencing specific retrieved sections) belong in the filter.

3. **The outlet's `body["messages"]` is the canonical representation.** Anything set on it persists to the database. This is the standard pattern confirmed by the Open WebUI community for custom source injection.

4. **HTML rendering in Open WebUI is limited.** `<details>`, `<summary>`, and HTML comments may render as raw text. Use pure markdown for all user-visible formatting.

5. **Filter priority ordering matters.** The audit logger must have a higher priority number than the GraphRAG filter to run after it in the outlet phase.

6. **Don't embed data in response text for inter-filter communication.** HTML comments (`<!-- ... -->`) can render as visible text in Open WebUI. Store data on the message dict instead — non-standard keys are never rendered but persist through the outlet pipeline.

7. **Conditional disclaimers are a product feature, not just legal cover.** Research shows blanket disclaimers erode trust. Confidence-adaptive language that changes based on what the system actually knows differentiates the product.
