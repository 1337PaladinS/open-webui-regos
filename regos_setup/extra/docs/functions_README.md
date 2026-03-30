# RegOS Custom Functions & Services

## What is RegOS?

RegOS is a regulatory compliance system built on Open WebUI that combines retrieval-augmented generation (RAG) with graph-based knowledge representation to help organizations navigate complex regulatory requirements. The system is designed for compliance officers, legal teams, and operational staff who need trustworthy, auditable answers to regulatory questions.

RegOS integrates compliance knowledge bases with confidence scoring, threshold evaluation, and complete audit trails. Instead of generic AI responses, RegOS provides evidence-backed recommendations with clear confidence levels and regulatory context. Every query and response is logged with full metadata for compliance auditing.

This folder contains the custom functions that power RegOS—the filters, pipes, and tools that implement confidence scoring, threshold checking, escalation logic, and audit logging. Functions are deployed by pasting their code into the Open WebUI admin UI rather than being loaded from this folder directly. This folder serves as the source of truth and version history for all custom function code.

Each function has a dedicated `.md` file with full documentation. This README provides an overview, explains how the functions work together, and documents the deployment architecture.

---

## What Are Open WebUI Functions?

Open WebUI functions are custom code that extends the platform's behavior. They intercept and process messages at different points in the chat pipeline:

**Filters** are functions that run at strategic points in the message flow:
- **Inlet Filters** receive messages as they arrive from the user and can modify them, check requirements, or enrich context before the LLM sees them
- **Outlet Filters** process the LLM's response before sending it back to the user, allowing for logging, confidence scoring, redaction, or escalation

**Pipes** are custom interfaces (like tools) that extend the chat interface. They can be called by the LLM or by users directly.

**Tools** are special functions exposed to the LLM that it can call during reasoning. The LLM decides when and how to use them based on the task.

**Valves** are configuration parameters that let you adjust function behavior without editing code. Each function can expose settings like logging level, model name, API keys, or thresholds.

**Priority Ordering** matters when multiple filters are enabled. Open WebUI processes filters in order: inlet filters from first to last, then the LLM, then outlet filters from first to last. This ordering allows you to chain operations.

---

## Functions Overview

| Function | Type | File | Version | Status | Purpose |
|----------|------|------|---------|--------|---------|
| **Audit Logger** | Filter (Outlet) | `audit_logger.py` | v0.4.0 | Deployed | Records every query/response with full metadata to SQLite database |
| **GraphRAG Filter** | Filter (Inlet/Outlet) | `graphrag_filter.py` | v0.16.0 | Deployed | Graph-enhanced RAG with confidence scoring, escalation, guardrails, and integrated threshold evaluation |
| **Threshold Eval** | Tool | `threshold_eval.py` | v0.1.0 | Superseded | Checks values against Ch.24 thresholds via LLM tool calling (functionality integrated into GraphRAG Filter v0.14.0+) |
| **GraphRAG Pipe** | Pipe | `graphrag_pipe.py` | — | Superseded | Original Pipe version for reference only |

**Detailed documentation:**

- [graphrag_filter.md](graphrag_filter.md) — GraphRAG Filter deep-dive
- [audit_logger.md](audit_logger.md) — Audit Logger deep-dive
- [confidence_scoring.md](confidence_scoring.md) — Confidence scoring algorithm details
- [graphrag_vs_rag.md](graphrag_vs_rag.md) — GraphRAG advantages and differences from standard RAG
- [README.md](README.md) — This file

---

## Function Details

### Audit Logger (v0.4.0)
**Type:** Outlet Filter
**Problem it solves:** In regulated environments, you need complete traceability of every interaction with the system. Who asked what question? What answer did the system provide? When? What confidence level? What guardrail checks ran?

**How it works:** The Audit Logger is an outlet filter that intercepts every response before it reaches the user. It extracts metadata from the message, user session, and message dictionary, then writes a complete audit record to a SQLite database. This creates an immutable log suitable for compliance reviews, incident investigation, and system monitoring.

**Key capabilities:**
- Captures user ID, session ID, timestamp, query text, response text
- Records confidence scores and escalation flags from GraphRAG Filter
- Logs guardrail violations and threshold check results
- Creates searchable, indexed audit trails for compliance review

**Documentation:** See `audit_logger.md` for detailed valve configuration and database schema.

---

### GraphRAG Filter (v0.16.0)
**Type:** Inlet/Outlet Filter
**Problem it solves:** Standard RAG can hallucinate, provide outdated information, or confidently assert facts it doesn't actually know. GraphRAG Filter combines retrieval-augmented generation with graph-based knowledge representation and confidence scoring to ensure regulatory answers are grounded in evidence, clearly tagged with confidence levels, and escalated when they fall below safety thresholds.

**How it works:** GraphRAG Filter operates in two phases:

1. **Inlet Phase** (before the LLM):
   - Receives the user's query
   - Retrieves relevant documents from the knowledge base using graph-enhanced search
   - Ranks results by relevance and facility context (for multi-facility organizations)
   - Disambiguates facility context from conversation history
   - Builds an enriched prompt that includes top search results, confidence thresholds, and compliance guardrails
   - Passes the enhanced query to the LLM with clear instructions on how to reason about confidence

2. **Outlet Phase** (after the LLM):
   - Evaluates the response text for confidence indicators
   - Applies integrated threshold evaluation (NEW in v0.16.0) to check if values meet Ch.24 regulatory thresholds
   - Flags responses below confidence thresholds for escalation
   - Identifies guardrail violations (unsafe recommendations, contradictions)
   - Marks the message with metadata flags for audit logging
   - Optionally redacts or modifies unsafe responses

**New in v0.16.0:**
- **Integrated Threshold Evaluation:** No longer requires a separate tool call. The filter evaluates regulatory thresholds in-line during outlet processing
- **Facility Context Disambiguation:** Understands multi-facility deployments and clarifies which facility's data is being discussed
- **Conversation-Aware Context:** Draws on conversation history to provide richer context for graph-enhanced search

**Key capabilities:**
- Graph-enhanced retrieval that understands relationships between concepts
- Confidence scoring with explicit confidence labels (high/medium/low/unknown)
- Automatic escalation flagging for responses below safety thresholds
- Integrated threshold checking against regulatory limits
- Guardrail checking for unsafe or contradictory recommendations
- Conversation history awareness for follow-up questions
- Multi-facility context disambiguation

**Message Dictionary Pattern:** GraphRAG Filter communicates with downstream functions (like Audit Logger) via message dictionary keys:
- `message["metadata"]["confidence"]` — Confidence score (0-100)
- `message["metadata"]["escalation_flag"]` — True if threshold breach detected
- `message["metadata"]["guardrail_violations"]` — List of any policy violations
- `message["metadata"]["threshold_results"]` — Results from Ch.24 threshold evaluation
- `message["metadata"]["facility_context"]` — Which facility's data was used

This pattern allows data to flow through the entire pipeline without message mutation, enabling the Audit Logger to capture complete context without requiring separate API calls.

**Documentation:** See `graphrag_filter.md` for detailed inlet/outlet logic, confidence scoring methodology, and valve configuration.

---

### Threshold Eval (v0.1.0)
**Type:** Tool (Superseded)
**Status:** Functionality integrated into GraphRAG Filter v0.14.0+

Previously, threshold evaluation was a standalone tool that the LLM could call during reasoning. As of GraphRAG Filter v0.14.0, this functionality was integrated directly into the filter's outlet phase, eliminating the need for separate tool calls and improving performance.

**Reason for superseding:** Integrated threshold evaluation is faster, provides clearer audit trails, and reduces the number of LLM tool calls required.

**Documentation:** See `graphrag_filter.md` for details on the integrated threshold evaluation feature.

---

### GraphRAG Pipe (Superseded)
**Type:** Pipe
**Status:** Superseded

The original GraphRAG Pipe provided graph-enhanced search as a user-callable interface. It has been superseded by the integrated GraphRAG Filter approach, which provides better context awareness and more seamless integration with the chat pipeline.

This file is retained in the repository for reference and historical context.

---

## Message Dictionary Transport Pattern

Open WebUI passes messages through the pipeline as dictionaries. Functions communicate by setting and reading keys in `message["metadata"]`:

```python
# GraphRAG Filter (outlet) sets metadata
message["metadata"]["confidence"] = 85
message["metadata"]["escalation_flag"] = False
message["metadata"]["threshold_results"] = {"ch24_limit": 50, "result": 42, "status": "pass"}

# Audit Logger (outlet, runs after GraphRAG) reads metadata
confidence = message["metadata"].get("confidence", "unknown")
escalation = message["metadata"].get("escalation_flag", False)
thresholds = message["metadata"].get("threshold_results", {})

# Record to SQLite with all context
database.log_interaction(
    query=message["content"],
    response=response,
    confidence=confidence,
    escalation=escalation,
    threshold_results=thresholds,
    timestamp=datetime.now()
)
```

This pattern ensures that:
- Data flows through the pipeline without message mutation
- Each function can read what previous functions wrote
- Audit trails capture complete context from all processing stages
- No separate API calls or database queries are needed between functions

---

## Supporting services (not deployed in Open WebUI)

These are standalone FastAPI services that run alongside Open WebUI, not inside it.

| Service | File | Version | Purpose |
|---|---|---|---|
| Breach API | `api/breach_api.py` | v0.1.0 | REST endpoints for threshold evaluation and breach history |
| SCADA Streaming | `api/scada_stream.py` | v0.1.0 | WebSocket + SSE + REST ingestion of SCADA sensor data |
| APAS Bridge | `api/apas_bridge.py` | v0.1.0 | Polling bridge connecting APAS Telemetry API to RegOS threshold evaluation |

---

## Architecture & Data Flow

### Chat Pipeline with Filters

```
User Query
    ↓
┌──────────────────────────────────┐
│  Inlet Filters (in order)        │
│  - GraphRAG Filter inlet phase   │
│    • Graph-enhanced retrieval    │
│    • Facility context check      │
│    • Conversation history parse  │
│    • Prompt enrichment           │
└──────────────────────────────────┘
    ↓
┌──────────────────────────────────┐
│  LLM Processing                  │
│  (with enriched context)         │
└──────────────────────────────────┘
    ↓
┌──────────────────────────────────┐
│  Outlet Filters (in order)       │
│  1. GraphRAG Filter outlet phase │
│     • Confidence scoring         │
│     • Threshold evaluation ★NEW  │
│     • Guardrail checking         │
│     • Escalation flagging        │
│     • Metadata enrichment        │
│  2. Audit Logger                 │
│     • Records to SQLite          │
│     • Captures all metadata      │
└──────────────────────────────────┘
    ↓
Response to User
```

**Key flows:**

1. **Confidence Flow:** User query → GraphRAG inlet (enrichment) → LLM → GraphRAG outlet (scoring) → User sees confidence label
2. **Escalation Flow:** Threshold evaluation → Confidence < threshold → Escalation flag set → Audit Logger records flag → Human reviewer notified
3. **Metadata Flow:** GraphRAG sets values in `message["metadata"]` keys → Audit Logger reads those keys → SQLite record captures complete context
4. **Conversation Flow:** New query → Inlet filters read conversation history → Facility context disambiguated → Graph search enhanced with history → Better retrieval results

### SCADA/APAS Integration Pipeline

```
                            APAS Telemetry API (123SCADA)
                                      │
                                      ▼
                          ┌───────────────────────┐
                          │  APAS Bridge           │  Polls every 30s
                          │  (api/apas_bridge.py)  │  Maps metrics → parameters
                          │  JWT auth, unit conv.  │  Converts °C → °F, etc.
                          └───────────┬───────────┘
                                      │
                                      ▼
                          ┌───────────────────────┐
                          │  SCADA Stream          │  WebSocket / SSE / REST
                          │  (api/scada_stream.py) │  Rate limiting, auth
                          └───────────┬───────────┘
                                      │
                                      ▼
                          ┌───────────────────────┐
                          │  Threshold Evaluation  │  96 Ch.24 thresholds
                          │  Service               │  COMPLIANT / BREACH /
                          │  (threshold_eval.py)   │  BORDERLINE + SHA-256
                          └───────────┬───────────┘
                                      │
                                      ▼
                          ┌───────────────────────┐
                          │  Breach DB (SQLite)    │  Evidence-hashed audit trail
                          │  + SSE broadcast       │  Real-time streaming
                          └───────────────────────┘
```

---

## Knowledge Base + Neo4j: Why use both?

These two systems retrieve information in fundamentally different ways. Using both together gives you much better coverage than either alone.

**Open WebUI Knowledge Base (ChromaDB):**

- Text similarity search: finds chunks with similar words/phrases
- Great for: exact passage lookup ("what does Section 24-42.4 say?")
- Gives you Open WebUI's built-in citation UI with source highlighting
- Limitations: misses conceptually related sections that use different terminology

**Neo4j FEA Knowledge Graph:**

- Fixed Entity Architecture: 30 human-defined concepts connected to 144 sections via cosine similarity
- Relationship-aware retrieval: traverses concept → section → threshold/penalty/obligation edges
- Great for: conceptual queries ("what regulations apply to industrial discharge?")
- Finds sections connected by concept relationships even if they don't share words
- Also contains: 151 thresholds, 15 penalties, 2,363 obligations, 12 roles, 37 standards, 170 cross-references

**Combined effect:**

| Query type | KB alone | Graph alone | KB + Graph |
|---|---|---|---|
| "What does Sec 24-42.4 say?" | Exact match | May miss it | Covered |
| "BOD limits for discharge" | Finds sections mentioning BOD | Finds BOD + related concepts | Broader coverage |
| "What permits do I need?" | Finds permit sections by text | Traverses permit → entity relationships | Catches non-obvious connections |
| "Is my BOD of 45 mg/l compliant?" | Text-similar chunks | Threshold tool gives exact answer | Definitive compliance check |

**How to set up the Knowledge Base:**

1. Go to Admin Panel > Knowledge
2. Create a new Knowledge Base called "Chapter 24"
3. Upload Chapter 24 sections as separate documents (one per section for best granularity)
4. Create a custom Model in Admin > Models
5. Set the model's Knowledge Base to "Chapter 24"
6. Enable the GraphRAG Filter globally (or on this model specifically)
7. Users select this custom model in chat — they get both retrieval systems automatically

---

## Deployment checklist

### Open WebUI Functions

1. Install the `neo4j` Python driver in the container:
   ```bash
   docker exec -it open-webui pip install neo4j
   ```

2. Deploy each function in Admin > Functions (paste code, save, configure Valves):
   - `graphrag_filter.py` — filter, priority 0
   - `audit_logger.py` — filter, priority 1
   - `threshold_eval.py` — tool (enable on your RegOS model)

3. Configure Valves for each function (see individual `.md` files for details)

4. Enable functions globally or per-model as needed

### Standalone Services (SCADA/APAS)

1. Install Python dependencies:
   ```bash
   pip install fastapi uvicorn httpx websockets sse-starlette
   ```

2. Run the APAS Bridge (includes SCADA streaming endpoints):
   ```bash
   APAS_BASE_URL=http://<apas-host>:8000 \
   APAS_EMAIL=your@email.com \
   APAS_PASSWORD=yourpassword \
   uvicorn api.apas_bridge:app --port 8300
   ```

3. Or run SCADA streaming standalone (without APAS polling):
   ```bash
   uvicorn api.scada_stream:app --port 8200
   ```

---

## File inventory

```
functions/
├── README.md                  ← This file (overview + architecture)
├── audit_logger.py            ← Audit Logger Filter (v0.4.0)
├── audit_logger.md            ← Audit Logger documentation
├── graphrag_filter.py         ← GraphRAG Filter (v0.13.0)
├── graphrag_filter.md         ← GraphRAG Filter documentation
├── confidence_scoring.md      ← Confidence scoring deep-dive
├── threshold_eval.py          ← Threshold Evaluation Tool + Service (v0.1.0)
└── graphrag_pipe.py           ← Original Pipe version (superseded)

api/
├── breach_api.py              ← REST API for threshold checks and breach history (v0.1.0)
├── scada_stream.py            ← SCADA streaming: WebSocket + SSE + REST (v0.1.0)
└── apas_bridge.py             ← APAS Telemetry polling bridge (v0.1.0)

data/
├── regulatory_thresholds.json ← 96 curated Ch.24 thresholds
└── apas_metric_mappings.json  ← APAS metric → RegOS parameter mapping

tools/
└── threshold_evaluation.py    ← Confidence weight sweep harness (dev tool)
```
