# RegOS — Regulatory Compliance Copilot

An AI-powered compliance copilot for Miami-Dade County Chapter 24 (Environmental Quality Control), built as a set of filter functions for [Open WebUI](https://github.com/open-webui/open-webui).

RegOS combines Graph-RAG retrieval, automated threshold evaluation, confidence scoring, and tamper-evident audit logging to deliver grounded, cited regulatory analysis.

## Architecture

```
User Query
    │
    ▼
┌──────────────────────┐
│   GraphRAG Filter     │  ← inlet: entity search → graph traversal → context injection
│   (graphrag_filter.py)│  ← outlet: confidence scoring, threshold eval, escalation, guardrails
└──────────┬───────────┘
           │
    ▼              ▼
┌──────────┐  ┌──────────────┐
│  Neo4j   │  │ Open WebUI   │
│  Aura    │  │ Knowledge    │
│  (Graph) │  │ Base (Vector)│
└──────────┘  └──────────────┘
           │
           ▼
┌──────────────────────┐
│   Audit Logger        │  ← captures query, response, confidence, escalation, guardrails
│   (audit_logger.py)   │  ← SHA-256 tamper-evident hashing
└───────────────────────┘
```

## Repository Structure

```
regos_setup/
├── README.md                          # This file
├── system_prompt.md                   # LLM system prompt (regulatory persona)
├── REGOS_CHANGELOG.md                 # Version history
│
├── functions/                         # Open WebUI filter functions
│   ├── graphrag_filter.py             # Core: Graph-RAG + threshold eval + confidence
│   ├── audit_logger.py                # Audit trail with tamper-evident hashing
│   ├── graphrag_pipe.py               # Alternative pipe-mode implementation
│   └── threshold_eval.py              # Standalone threshold evaluation module
│
├── data/                              # Runtime data files
│   ├── regulatory_thresholds.json     # Chapter 24 threshold definitions
│   ├── apas_metric_mappings.json      # APAS metric → regulation mappings
│   ├── chaptor_24_graph.json          # Chapter 24 knowledge graph export
│   └── concepts.json                  # Graph concept definitions
│
├── api/                               # External integrations
│   ├── apas_bridge.py                 # APAS platform bridge
│   ├── breach_api.py                  # Breach record API
│   └── scada_stream.py                # SCADA data stream handler
│
├── scripts/                           # Utility & demo scripts
│   ├── verify_hashes.py               # SHA-256 hash verification tool
│   ├── demo_show_records.py           # Demo: show compliance records
│   ├── demo_tamper.py                 # Demo: simulate tamper event
│   └── demo_reset.py                  # Demo: reset demo database
│
├── setup/                             # Fresh instance setup
│   ├── README.md                      # Setup guide
│   ├── regos_setup.sh                 # Master script (runs both steps)
│   ├── regos_backend_setup.sh         # Step 1: copy data files into Docker
│   └── regos_register_functions.sh    # Step 2: register functions via API
│
├── prompts/                           # LLM prompt templates
│   └── graph_extraction_prompt.md     # Knowledge graph extraction prompt
│
├── cypher/                            # Neo4j Cypher queries
│   └── batch_01.cypher                # Graph query templates
│
├── n8n/                               # Workflow automation
│   └── regos_escalation_workflow.json # n8n escalation workflow
│
├── tests/                             # Test suites
│   └── adversarial_guardrails.md      # Adversarial test cases for guardrails
│
└── extra/                             # Documentation & reference materials
    ├── docs/                          # Reports, specs, analysis documents
    ├── trackers/                      # Project tracking spreadsheets
    ├── chapter_24_source/             # Raw Chapter 24 regulation text
    └── diagnostics/                   # Diagnostic & debug scripts
```

## Quick Start

### Prerequisites

- Docker with `open-webui` container running
- Admin auth token from Open WebUI (JWT from browser cookie or API key — see `setup/README.md` for details)
- Neo4j Aura instance with Chapter 24 knowledge graph
- Python 3 on the host machine

### Setup

```bash
cd regos_setup/setup/

# Set environment variables
# Token: grab the JWT from your browser cookie (Developer Tools → Application → Cookies → "token")
export OPENWEBUI_URL=http://localhost:3000
export OPENWEBUI_TOKEN=eyJhbGciOiJIUzI1NiIs...
export NEO4J_PASSWORD=your-neo4j-password

# Run complete setup in one go
chmod +x regos_setup.sh
./regos_setup.sh
```

### Post-Setup

1. Verify both filters are enabled globally in **Admin → Functions**
2. Set the Neo4j password valve on `graphrag_filter` if not set via env var
3. Upload Chapter 24 documents to a Knowledge Base collection
4. Select **"RegOS Compliance Copilot"** as your model in the chat

### Test

```
"What are the BOD limits for industrial wastewater?"
"My BOD reading is 45 mg/L — am I compliant?"
```

## Key Features

| Feature | Description |
|---------|-------------|
| **Graph-RAG Retrieval** | 4-step pipeline: document fulltext → entity traversal → concept expansion → direct search via Neo4j FEA graph |
| **Threshold Evaluation** | Automated compliance checks against regulatory_thresholds.json with breach logging |
| **Confidence Scoring** | 6 weighted signals (v0.17.3) producing a 0–1 score with HIGH/MEDIUM/LOW bands |
| **Escalation Workflow** | Low-confidence responses auto-generate case packets for human review |
| **Guardrails** | Out-of-scope detection, zero-retrieval handling, structured refusal formatting |
| **Audit Logging** | Every query/response pair logged with SHA-256 tamper-evident hashing |
| **Enterprise Formatting** | Structured response template with citations, disclaimers, and regulatory metadata |

## Runtime Databases (Auto-Created)

These databases are created automatically inside the Docker container on first use:

- `audit.db` — Full audit trail of all queries and responses
- `regos_breaches.db` — Threshold evaluation breach records with evidence hashing

## License

Internal — APAS AI
