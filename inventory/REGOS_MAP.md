# RegOS Custom Work Map

Everything in this repository that is NOT stock Open WebUI. Organized by functional area.

---

## 1. Filter Functions (Open WebUI Filters)

These run inside Open WebUI as inlet/outlet filters on every chat message.

| File                                          | Version  | Purpose                                                                                                                                                                                                                                                                                                                                             |
| --------------------------------------------- | -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `regos_setup/functions/graphrag_filter.py`    | v0.17.3  | Core retrieval engine. 4-step pipeline: document fulltext, entity matching, concept expansion, direct search. Includes confidence scoring (6 signals), guardrails (keyword, zero-retrieval, jurisdiction), escalation (auto-flag + n8n webhook), threshold evaluation (regex detection of 35+ parameters against 96 limits), Sources Panel injection, conditional disclaimers. FEA v2 schema (Ch24Class/Ch24Document/Ch24Entity). |
| `regos_setup/functions/audit_logger.py`       | v0.4.0   | Logs every chat to SQLite (audit.db). Captures: user, chat, query, response, model, confidence score/band/signals, escalation metadata, guardrail metadata. Reads data from message dict keys set by graphrag_filter.                                                                                                                               |
| `regos_setup/functions/escalation_action.py`  | v1.0.0   | Manual escalation Action. User-triggered expert compliance review. Builds case packet, POSTs to n8n webhook, writes audit trail. Complement to automatic escalation in graphrag_filter.                                                                                                                                                              |
| `regos_setup/functions/threshold_eval.py`     | ---      | [OBSOLETE --- unused in production] Early Tools-based threshold evaluation. Abandoned because base model (Nemotron) doesn't support tool-calling. Superseded by integrated threshold eval in graphrag_filter.py (v0.14.0). Retained for future redesign.                                                                                             |
| `regos_setup/functions/graphrag_pipe.py`      | v0.1.0   | [OBSOLETE --- abandoned] Original Pipe approach that replaced the LLM endpoint. Caused deadlock. Superseded by the Filter pattern in graphrag_filter.py (v0.3.0+).                                                                                                                                                                                  |

Every .py file has a companion .md file alongside it with detailed documentation and status.

---

## 2. APIs (Sidecar Services)

Standalone FastAPI services that run alongside Open WebUI.

| File                                  | Purpose                                                                                                                                   |
| ------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `regos_setup/api/breach_api.py`       | REST API for compliance dashboard --- summary, list breaches, run checks, verify evidence hashes. 7 endpoints.                            |
| `regos_setup/api/scada_stream.py`     | SCADA streaming ingestion --- WebSocket (full-duplex), SSE (monitoring), REST batch. Rate limiting, auth, real-time threshold evaluation.  |
| `regos_setup/api/apas_bridge.py`      | APAS Telemetry polling bridge --- JWT auth against APAS API, metric mapping via config, unit conversion, feeds into SCADA pipeline. 30s poll interval. |
| `regos-installer/api/regos_api.py`    | RegOS API wrapper used by the installer for function registration and model creation.                                                     |

---

## 3. Data Files

| File                                            | Contents                                                                                                         |
| ----------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `regos_setup/data/regulatory_thresholds.json`   | 96 regulatory thresholds from Chapter 24 --- concentration limits, timeframes, distances, percentages, penalties. |
| `regos_setup/data/concepts.json`                | Ontology concepts for the FEA knowledge graph.                                                                   |
| `regos_setup/data/apas_metric_mappings.json`    | Maps APAS metric names to RegOS threshold parameters. 8 active + 14 effluent sensor templates.                   |
| `regos_setup/data/chaptor_24_graph.json`        | Full Neo4j graph export --- 693 nodes, 2,351 relationships (FEA v2 schema).                                      |
| `regos_setup/cypher/batch_01.cypher`            | Cypher statements for batch-loading the graph into Neo4j.                                                        |

**Root-level copies:** `regulatory_thresholds.json` and `neo4j_query_table_data_2026-1-15 (1).json` (237 MB raw graph export) also exist at root for convenience.

---

## 4. System Prompt & Prompts

| File                                                 | Purpose                                                                                                                                                                                                          |
| ---------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `regos_setup/system_prompt.md`                       | RegOS Compliance Copilot system prompt. Defines 3 personas (Citizen, Consultant, Regulator), response structure, citation rules, scope boundaries, refusal formatting, threshold evaluation instructions. Applied to the custom model. |
| `regos_setup/prompts/graph_extraction_prompt.md`     | Prompt template for extracting entities/relationships from regulatory text into the knowledge graph.                                                                                                              |

---

## 5. Installer & Deployment

| Directory                  | Purpose                                                                                                                                                                                                           |
| -------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `regos-installer/`         | **Current installer** (v2). 10-step automated deployment. Includes source patches (apply-patches.py --- 15 patches + 3 new Svelte files), shell libraries, config, and full documentation bundle. See SOURCE_PATCHES.md for details. |
| `gtihub-regos-installer/`  | **Earlier installer** (v1). 8 steps, no guest access or admin panel patches. Kept for reference.                                                                                                                  |
| `regos_setup/setup/`       | Setup scripts and README for fresh deployment from scratch (RunPod, Docker, etc.).                                                                                                                                |

---

## 6. Source Patches (Modified Stock Files)

15 patches across 13 stock Open WebUI files. Adds: RegOS admin panel, guest access with email + rate limiting, disclaimer modal, confidence display config, role-based user filtering, neo4j dependency. See `SOURCE_PATCHES.md` for the complete file-by-file breakdown.

---

## 7. Benchmarks

| File/Dir                          | Purpose                                                                                                          |
| --------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `benchmark/`                      | Dockerized PDF extraction benchmark comparing Docling vs GPT-4o on the Opa-locka municipal code.                 |
| `benchmark/benchmark_gpt4o.py`    | GPT-4o extraction script                                                                                         |
| `benchmark/score_and_report.py`   | Scoring and report generation                                                                                    |
| `benchmark/results/`              | Output: baseline text, Docling JSON/MD, GPT-4o per-page and combined, sample PDFs, benchmark_report.json         |
| `pdf_benchmark.py` (root)         | Docling benchmark runner                                                                                         |
| `benchmark_strategy.md` (root)    | Benchmark strategy document                                                                                      |

---

## 8. Standalone Applications

| Directory                              | Purpose                                                                                                                                                                             |
| -------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `APAS-Legal-PDF-Chunking-Dashboard/`   | Full-stack app for visualizing legal PDF chunking. Backend: FastAPI with chunker, enrichment, extraction, neo4j_service. Frontend: Next.js + Tailwind. Docker Compose deployment. Planned for extraction to separate repo. |

---

## 9. Documentation

### regos-docs/ (consolidated from root --- 33 .docx, 2 .xlsx, 1 .pptx, 1 .svg, 2 .drawio, 1 .zip, 1 .md)

All RegOS documentation files consolidated into `regos-docs/`. Organized by category:

**Architecture & Technical:** RegOS_Architecture, RegOS_API_Architecture, RegOS_API_Sample_Response, RegOS_Infrastructure_Diagram.svg, RegOS_Infrastructure_v2.drawio, RegOS_expanded.drawio, Dashboard_Technical_Overview_and_Costs

**Features:** RegOS_Escalation_Feature_Documentation, RegOS_Escalation_Workflow_Scope_P1_P2, RegOS_Disclaimer_GuestMode_Build_Documentation, RegOS_Neo4j_Failover_Documentation, RegOS_Security_v019_Documentation

**Security:** RegOS_Security_Phase1_Phase2_Implementation_Plan, RegOS_Security_Research_Backlog_Item5, RegOS_Security_Research_Revised, RegOS_Security_Test_Results

**Research:** RegOS_Research_Backlog_Item9_Confidence_Feedback_Loop (+ Reviewed), RegOS_PDF_Parsing_Research, RegOS_Discovery_Document

**Deployment & Operations:** RegOS_Setup_Guide, RegOS_Deployment_Guide, RegOS_Installer_Explanation

**Knowledge Transfer:** APAS_Knowledge_Transfer_Program, Module_1_The_Platform_Facilitator_Guide, RegOS_Document_Analysis_KT, RegOS_Sidecar_API_KT, RegOS_Sidecar_Testing_Guide

**Demo & Presentation:** RegOS_Demo_Script, RegOS_P0_Full_Demo, RegOS_SHA256_Demo, Legal_PDF_Dashboard_Demo_Script.pptx

**Decision Records:** Docling_Decision_Record.md (self-contained benchmark decision with embedded results)

**Tracking:** RegOS_P1_P2_Backlog.xlsx, RegOS_MECE_Test_Prompts.xlsx, RegOS-Changelog-2026-03-10.docx

### strategies/ (strategy documents)

Municipal_Code_Chunking_Strategy.md, benchmark_strategy.md

### regos_setup/extra/docs/ (technical .md docs)

confidence_scoring.md, graphrag_filter.md (extended), audit_logger.md, disclaimer_research.md, graphrag_vs_rag.md, functions_README.md, GRAPH_REBUILD_QUICKSTART.md, N8N_ESCALATION_SETUP.md, P0_Feature_Analysis.md, P0_Implementation_Order.md, demo_script.md, readme1.md

---

## 10. Utility & Demo Scripts

| File                                           | Purpose                                            |
| ---------------------------------------------- | -------------------------------------------------- |
| `regos_setup/scripts/`                         | Utility scripts (setup, diagnostics)               |
| `regos-installer/scripts/demo_show_records.py` | Show audit/breach DB records                       |
| `regos-installer/scripts/demo_tamper.py`       | Tamper with evidence hash for SHA-256 demo         |
| `regos-installer/scripts/demo_reset.py`        | Reset demo environment                             |
| `regos-installer/scripts/verify_hashes.py`     | Verify evidence hash integrity                     |

Root copies of these scripts are flagged for removal (see REMOVAL_CANDIDATES.md).

---

## 11. Workflow Automation (n8n)

| File                                                     | Purpose                                                                                                                                |
| -------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| `regos_setup/n8n/regos_escalation_workflow.json`         | Importable n8n workflow --- webhook receives escalation case packet, AI generates case brief, stores case file + returns confirmation   |
| `regos_setup/n8n/email_preview.html`                     | HTML preview of escalation email (moved from root)                                                                                     |
| `regos_setup/n8n/format_email_node_v3.js`                | n8n JavaScript node for email formatting (moved from root)                                                                             |
| `regos_setup/n8n/parsed_response.html`                   | Parsed response HTML preview (moved from root)                                                                                         |

---

## 12. Test Suites

| File                                                | Purpose                                                                                                                                             |
| --------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| `regos_setup/tests/adversarial_guardrails.md`       | 28 test queries across 7 categories: out-of-scope, zero-retrieval, jurisdiction, citation fabrication, prompt injection, legitimate, edge cases      |
| `regos_setup/tests/phase1_phase2_test_results.md`   | Phase 1/2 test results                                                                                                                              |
| `RegOS_MECE_Test_Prompts.xlsx` (root)               | MECE test prompt matrix                                                                                                                             |

---

## 13. Deliverable Packages

| Directory                                  | Contents                                                                                                |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------- |
| `RegOS_Integration_Package/`               | Bundled for external delivery: RegOS_Integration_Response.docx + 3 JSON data files (thresholds, concepts, mappings) |
| `Docling_vs_GPT4o_Benchmark_Bundle.zip`    | Bundled benchmark results for distribution                                                              |

---

## Feature Version History

| #    | Feature                                    | Version  | Status |
| ---- | ------------------------------------------ | -------- | ------ |
| 1    | Audit Logging                              | v0.4.0   | Done   |
| 2    | GraphRAG Pipeline                          | v0.17.3  | Done   |
| 3    | Confidence Scoring                         | v0.6.0+  | Done   |
| 4    | Enterprise Output Formatting               | v0.7.0+  | Done   |
| 4b   | Sources Panel Integration                  | v0.8.0   | Done   |
| 4c   | Conditional Disclaimers                    | v0.8.1   | Done   |
| 5    | Escalation Workflow + n8n                  | v0.10.0  | Done   |
| 6    | Threshold Evaluation (weights + service)   | v0.13.0  | Done   |
| 7b   | SCADA Streaming API                        | v0.1.0   | Done   |
| 7c   | APAS Telemetry Bridge                      | v0.1.0   | Done   |
| 8    | Refusal & Guardrails                       | v0.12.0  | Done   |
| 9    | Integrated Threshold Eval                  | v0.14.0  | Done   |

Full development narrative: `regos_setup/REGOS_CHANGELOG.md`
