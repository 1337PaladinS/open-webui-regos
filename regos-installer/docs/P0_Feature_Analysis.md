# P0 Feature Analysis & Implementation Recommendations

This document extracts the 8 core features from the RegOS P0 Blueprint and recommends how each should be implemented within Open WebUI's extension architecture.

---

## Quick Reference: Open WebUI Extension Points

Before diving into features, here's how Open WebUI lets you add custom logic:

| Extension Type | What It Does | How It's Registered |
|---|---|---|
| **Function (Pipe)** | Replaces the LLM endpoint entirely — you control the full request/response cycle | Python module with `pipe()` method, registered via Admin > Functions |
| **Function (Filter)** | Intercepts messages before (inlet) and after (outlet) the LLM, can transform both | Python module with `inlet()`/`outlet()` methods |
| **Tool** | Adds callable functions the LLM can invoke (function calling) | Python module with typed functions + docstrings |
| **Pipeline** | External HTTP service that filters requests/responses (like middleware) | External service registered by URL |
| **Skill** | Pre-written prompt template users invoke via commands | Text template, no code execution |
| **Custom Vector DB** | New retrieval backend implementing the `VectorDBBase` interface | Python class in `retrieval/vector/dbs/` |
| **Frontend Component** | Custom Svelte UI components | Components in `src/lib/components/` |

---

## The 8 P0 Features

### Feature 1: Knowledge Graph + RAG Integration (GraphRAG Pipeline)

**What it is:** Replace the current vector-only retrieval (ChromaDB top-K → rerank → LLM) with a hybrid pipeline where Neo4j acts as the query planner and ChromaDB provides semantic ranking on top.

**The chain:** User question → entity linking → Cypher generation → Neo4j traversal → graph candidate filtering → ChromaDB vector ranking → context + citation assembly → LLM → answer validation → response

**Current state:** Neo4j and ChromaDB exist independently. No graph-guided retrieval.

**Recommended implementation: Function (Pipe)**

This is the single biggest piece of work and it needs a custom **Pipe function** — a Python module that completely replaces the default chat completion flow. Here's why: the default Open WebUI RAG flow is hardwired to do vector retrieval → rerank → LLM. You need to intercept before vector retrieval happens and run graph traversal first. A Pipe gives you full control over the entire chain.

The Pipe function would:

1. Receive the user's message via `pipe(body, ...)`
2. Run entity linking (extract section refs, defined terms, obligations, jurisdictions from the question)
3. Generate parameterized Cypher queries from the extracted entities
4. Execute against Neo4j to get structurally relevant candidate sections, definitions, cross-refs, exceptions
5. Pass the graph candidate set to ChromaDB for semantic ranking
6. Assemble the ranked context with full citation metadata
7. Call the underlying LLM (via OpenAI-compatible API) with the assembled context
8. Validate the response against graph dependencies (all referenced sections present, no dangling citations)
9. Compute a confidence score from retrieval quality signals
10. Format into enterprise response template and return

**Key files to reference:**
- `backend/open_webui/functions.py` — how Pipe functions are loaded and executed
- `backend/open_webui/retrieval/vector/factory.py` — how vector DB clients are instantiated (you'll call ChromaDB directly from your Pipe)
- `backend/open_webui/utils/payload.py` — how system prompts are applied (your Pipe handles this itself)

**External dependencies:** Neo4j Python driver, a small NLP model or LLM call for entity linking

---

### Feature 2: Enterprise Output Formatting

**What it is:** Every response follows a standardized template: compliance determination header, citation block with section/jurisdiction/version, system confidence score, escalation indicator, and structured refusal when applicable.

**Current state:** Raw LLM text in the chat bubble. No structured formatting.

**Recommended implementation: Outlet Filter Function + Frontend Component**

Two pieces:

**A. Outlet Filter Function (backend):** A Filter function with an `outlet()` method that post-processes every LLM response. It takes the raw response from the GraphRAG Pipe (which should return structured JSON metadata alongside the text), and formats it into a standardized markdown/HTML block with the determination header, citation block, confidence score badge, and escalation indicator.

Alternatively, if the GraphRAG Pipe (Feature 1) already formats its own output, you may not need a separate outlet filter — the Pipe can handle formatting directly. The choice depends on whether you want formatting to be decoupled from retrieval logic (cleaner) or bundled (simpler).

**B. Frontend Component (optional but recommended):** A custom Svelte component in `src/lib/components/chat/Messages/Message/` that recognizes the structured response format and renders it with proper visual hierarchy — colored status badges, collapsible citation blocks, confidence gauge, escalation banner. This is what makes the demo look polished vs. just styled markdown.

**Key files to reference:**
- `src/lib/components/chat/Messages/` — message rendering components
- `src/lib/components/common/` — reusable UI elements

---

### Feature 3: Regulatory Threshold Evaluation Engine

**What it is:** Automatically evaluate incoming sensor readings against Chapter 24 regulatory thresholds. When breached, identify the exact clause, preserve the determination with SHA-256 evidence hashing.

**Current state:** No automated evaluation exists. No breach detection.

**Recommended implementation: Standalone Backend Service + Tool**

This doesn't fit neatly into Open WebUI's chat flow — it's a background process, not a query-response interaction. Recommended approach:

**A. Standalone service** (Python, runs alongside Open WebUI): Listens for incoming sensor data from the Pump Station Ontology pipeline (via API or message queue). Evaluates each reading against a curated table of Chapter 24 thresholds. On breach: identifies the clause, computes SHA-256 hash of the determination record, stores in a dedicated database table.

**B. Open WebUI Tool:** Register a Tool function that the LLM can call to query breach status. Functions like `get_active_breaches()`, `get_breach_history(station_id)`, `get_threshold_for_parameter(parameter_name)`. This lets the GraphRAG chat answer questions like "Are there any active breaches at Station 5?"

**C. API endpoint** for the dashboard (Feature 7) to pull breach data for display.

**Key consideration:** The threshold table (parameter → limit value → Chapter 24 clause) needs to be manually curated from the regulatory text, or extracted via structured extraction. This is a data task, not an engineering task.

**Cross-team dependency:** Pump Station Ontology team must deliver normalized sensor readings.

---

### Feature 4: Confidence Scoring Engine

**What it is:** A system-computed confidence score on every response, derived from retrieval quality signals — not LLM self-reported, not user-entered.

**Current state:** Semantic retrieval scoring exists at the chunk level. Response-level confidence is manual.

**Recommended implementation: Built into the GraphRAG Pipe (Feature 1)**

This lives inside the Pipe function as Step 9 of the query chain. The confidence score is a composite of signals available at retrieval time:

- **Retrieval relevance scores** — how well did the top-ranked chunks match the query?
- **Coverage completeness** — did the graph find all expected cross-references and definitions?
- **Graph dependency satisfaction** — were all structural relationships resolved?
- **Reranker scores** — what were the bge-reranker-v2-m3 scores on the final context set?

The Pipe computes this score, includes it in the response metadata, and the outlet filter / frontend component (Feature 2) displays it. The score also feeds into the escalation trigger (Feature 5).

**Key design decision needed:** The blueprint mentions a "clarity call with Soham" to resolve the scoring approach. This must happen before implementation begins — the specific signals and their weights need to be agreed on.

---

### Feature 5: Escalation Workflow

**What it is:** When confidence is below a configurable threshold, automatically generate a structured case packet and route it to a reviewer.

**Current state:** An n8n pipeline node routes low-confidence answers to the internal APAS team, but with no structured case packet and no configurable thresholds.

**Recommended implementation: Built into the GraphRAG Pipe + n8n upgrade**

**A. Case packet generation (in the Pipe):** After the confidence score is computed (Step 9), if it falls below the threshold, the Pipe bundles: the original query, full retrieval set (which chunks were used, their scores), all citations, the confidence score, the draft response, and a recommended action. This packet is stored as a structured record.

**B. Escalation trigger:** The Pipe calls the existing n8n webhook, but now sends the full case packet instead of just the response text. The n8n pipeline is upgraded to accept and attach the structured packet.

**C. Configurable threshold:** Store the confidence threshold as a Valve on the Pipe function. Admins can adjust it per-workspace via the Open WebUI admin UI. Open WebUI's Valve system is designed exactly for this — admin-configurable settings on functions.

**D. User-facing indicator:** The response template (Feature 2) includes an escalation banner when triggered.

---

### Feature 6: Structured Audit Logging

**What it is:** Every query generates a structured audit record: query metadata, retrieval record, citation record, confidence record, escalation record, guardrail record. Queryable via admin API.

**Current state:** Raw interaction data in the OpenWebUI database. Manual SQL queries to access it.

**Recommended implementation: Dedicated audit table + API endpoint**

**A. Audit schema:** Create a new database table (or a separate SQLite/PostgreSQL database) with a JSON-structured audit record per query. The GraphRAG Pipe (Feature 1) emits this record at the end of every query chain execution.

**B. Integration with Open WebUI's DB:** You can extend Open WebUI's existing SQLAlchemy models by adding a new model in `backend/open_webui/models/` and a new router in `backend/open_webui/routers/` for the audit API. This keeps it inside the same codebase and deployment. Alternatively, write to a separate database to avoid coupling audit data with Open WebUI's internal tables (cleaner for regulatory compliance).

**C. Admin API:** A simple REST endpoint: `GET /api/audit/records?query_id=...&user_id=...&date_range=...` that returns structured audit records. For P0, this is sufficient — the full chat-based audit query is P2.

**Key files to reference:**
- `backend/open_webui/models/` — existing SQLAlchemy models to follow as patterns
- `backend/open_webui/routers/` — existing routers to follow as patterns
- `backend/open_webui/main.py` — where routers are registered

---

### Feature 7: Compliance Dashboard

**What it is:** A single-page dashboard showing compliance status (green/amber/red), active breach alerts, and an embedded chat interface.

**Current state:** No dashboard exists. Only the chat interface.

**Recommended implementation: New Svelte page in the frontend**

**Option A — Build inside Open WebUI (recommended for demo):** Add a new route in `src/routes/` (e.g., `/dashboard`) with a custom Svelte page. It pulls data from:
- The threshold evaluation engine API (Feature 3) for breach alerts
- A compliance status API that aggregates current posture
- Embeds the existing chat component (`src/lib/components/chat/`) for inline Q&A

This keeps everything in one app — the prospect doesn't switch between tools.

**Option B — Standalone frontend:** Build a separate React/Svelte app that calls Open WebUI's API for chat and the threshold engine API for breach data. More decoupled, but adds deployment complexity for the demo.

For P0/demo purposes, Option A is faster and more cohesive.

**Key files to reference:**
- `src/routes/` — existing page routes (follow the pattern)
- `src/lib/components/admin/Analytics.svelte` — existing dashboard-like page with charts
- `src/lib/components/chat/Chat.svelte` — the chat component to embed

---

### Feature 8: Refusal Behavior & Guardrails

**What it is:** Structured refusal when the system can't answer, formatted using the enterprise template. All guardrail triggers logged in the audit record. Validated by an adversarial test suite.

**Current state:** Refusal works via system prompts. Recommendations are given. But not structured/logged.

**Recommended implementation: System prompt refinement + Pipe logic + test suite**

This is the lightest workstream — the foundation is solid.

**A. System prompt:** Refine the existing system prompt to instruct the LLM to output refusals in the structured enterprise format (Feature 2). The system prompt is configured in the model's `params.system` field.

**B. Pipe-level guardrails:** The GraphRAG Pipe (Feature 1) can add hard guardrails: if the graph traversal returns zero relevant sections, or if jurisdiction doesn't match, the Pipe short-circuits and returns a structured refusal directly — without even calling the LLM. This is more reliable than relying on the LLM to refuse correctly.

**C. Audit logging:** Every guardrail trigger (refusal, jurisdiction boundary, out-of-scope detection) is recorded in the audit record (Feature 6).

**D. Adversarial test suite:** A set of 20+ test queries designed to probe guardrail robustness: out-of-scope questions, jurisdiction mixing, citation fabrication attempts, etc. This is a test script, not a deployed component.

---

## Implementation Architecture Summary

```
┌─────────────────────────────────────────────────────────┐
│                    FRONTEND (Svelte)                      │
│                                                           │
│  ┌─────────────┐  ┌──────────────────────────────────┐   │
│  │  Dashboard   │  │     Chat Interface                │   │
│  │  (Feature 7) │  │  ┌────────────────────────────┐  │   │
│  │  • Status    │  │  │ Enterprise Response Template│  │   │
│  │  • Breaches  │  │  │ (Feature 2 - frontend)     │  │   │
│  │  • Chat embed│  │  └────────────────────────────┘  │   │
│  └─────────────┘  └──────────────────────────────────┘   │
└───────────────────────────┬─────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────┐
│                  OPEN WEBUI BACKEND                       │
│                                                           │
│  ┌────────────────────────────────────────────────────┐  │
│  │  GraphRAG Pipe Function (Features 1, 3-chain, 4, 5)│  │
│  │                                                      │  │
│  │  1. Entity Linking                                   │  │
│  │  2. Cypher Generation                                │  │
│  │  3. Neo4j Traversal                                  │  │
│  │  4. ChromaDB Vector Ranking                          │  │
│  │  5. Context + Citation Assembly                      │  │
│  │  6. LLM Call                                         │  │
│  │  7. Answer Validation                                │  │
│  │  8. Confidence Scoring (Feature 4)                   │  │
│  │  9. Escalation Check (Feature 5)                     │  │
│  │  10. Enterprise Formatting (Feature 2)               │  │
│  │  11. Audit Record Emission (Feature 6)               │  │
│  │  12. Guardrail Enforcement (Feature 8)               │  │
│  └────────────────────────────────────────────────────┘  │
│                                                           │
│  ┌──────────────────┐  ┌──────────────────────────────┐  │
│  │  Audit API        │  │  Breach Query Tool           │  │
│  │  (Feature 6)      │  │  (Feature 3 - tool)          │  │
│  └──────────────────┘  └──────────────────────────────┘  │
└───────────────────────────┬─────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────┐
│                   EXTERNAL SERVICES                       │
│                                                           │
│  ┌──────────┐  ┌──────────┐  ┌────────────────────────┐ │
│  │  Neo4j   │  │ ChromaDB │  │ Threshold Eval Service │ │
│  │          │  │          │  │ (Feature 3 - engine)   │ │
│  └──────────┘  └──────────┘  └────────────────────────┘ │
│                                                           │
│  ┌──────────┐  ┌──────────────────────────────────────┐  │
│  │  n8n     │  │  Pump Station Ontology (external)    │  │
│  │          │  │  (sensor data feed)                   │  │
│  └──────────┘  └──────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

## What Goes Where — Summary Table

| P0 Feature | Implementation Type | Where It Lives |
|---|---|---|
| **1. GraphRAG Pipeline** | Pipe Function | `Admin > Functions` (Python module) |
| **2. Enterprise Formatting** | Outlet logic in Pipe + Svelte component | Pipe function + `src/lib/components/` |
| **3. Threshold Evaluation** | Standalone service + Tool function | Separate Python service + `Admin > Tools` |
| **4. Confidence Scoring** | Built into Pipe (Step 8) | Inside the GraphRAG Pipe function |
| **5. Escalation Workflow** | Pipe logic + n8n upgrade | Pipe function + n8n pipeline |
| **6. Audit Logging** | New DB model + API router | `backend/open_webui/models/` + `routers/` |
| **7. Dashboard** | New Svelte route | `src/routes/dashboard/` |
| **8. Refusal & Guardrails** | System prompt + Pipe logic + test suite | Model config + Pipe function + test scripts |

## Recommended Build Order

This aligns with the blueprint's phasing but maps to concrete Open WebUI implementation work:

**Phase 1 (Weeks 1-3):** Build the GraphRAG Pipe skeleton, entity linker, Cypher generator. Design the audit schema. Resolve confidence scoring approach.

**Phase 2 (Weeks 3-6):** Complete the Pipe with full 10-step chain. Build enterprise response template (backend + frontend). Instrument audit logging. Build confidence engine.

**Phase 3 (Weeks 5-8):** Build threshold evaluation service. Wire escalation with case packets. Build dashboard. Run adversarial tests. End-to-end integration testing.
