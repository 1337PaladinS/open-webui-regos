# Removal Candidates

Files and directories removed during the 2026-03-20 inventory review. **All items below were deleted on 2026-03-20 after user confirmation.** This document is retained as an audit trail.

---

## Directories

| Path                             | Reason                                                                                                     | Pre-removal Action                          |
| -------------------------------- | ---------------------------------------------------------------------------------------------------------- | ------------------------------------------- |
| `gtihub-regos-installer/`        | Dead weight. Fully superseded by `regos-installer/` (v2).                                                  | None needed — no unique content.            |
| `benchmark/`                     | One-time PDF extraction benchmark. Results documented in `regos-docs/Docling_Decision_Record.md`.          | Decision document created. Safe to remove.  |
| `RegOS_Integration_Package/`     | One-time deliverable. May be recreated in future.                                                          | None — JSON data copies exist in regos_setup/data/. |

## Root-Level Files

| File                                            | Reason                                                                                   |
| ----------------------------------------------- | ---------------------------------------------------------------------------------------- |
| `graphrag_filter.py`                             | Root-level copy. Canonical version in `regos_setup/functions/`.                          |
| `regulatory_thresholds.json`                     | Root-level copy. Canonical version in `regos_setup/data/`.                               |
| `neo4j_query_table_data_2026-1-15 (1).json`     | 237 MB raw graph export. Canonical graph in `regos_setup/data/chaptor_24_graph.json`.    |
| `pdf_benchmark.py`                               | Benchmark runner. Results documented in decision record. Remove with `benchmark/`.       |
| `RAG_Pipeline_Expansion_Mockup.html`             | One-time UI mockup. No longer relevant.                                                  |
| `demo_reset.py`                                  | Root copy. Canonical in `regos-installer/scripts/`.                                      |
| `demo_show_records.py`                           | Root copy. Canonical in `regos-installer/scripts/`.                                      |
| `demo_tamper.py`                                 | Root copy. Canonical in `regos-installer/scripts/`.                                      |
| `verify_hashes.py`                               | Root copy. Canonical in `regos-installer/scripts/`.                                      |
| `diag_hash.py`                                   | Diagnostic artifact. No canonical use.                                                   |
| `diag_hash2.py`                                  | Diagnostic artifact. No canonical use.                                                   |

## Already Handled

These items were moved rather than removed during the reorganization:

- n8n artifacts (email_preview.html, format_email_node_v3.js, parsed_response.html) -> moved to `regos_setup/n8n/`
- All root .docx/.xlsx/.pptx/.svg/.drawio files -> moved to `regos-docs/`
- Strategy documents -> moved to `strategies/`
- `legal-chunking-dashboard/` -> renamed to `APAS-Legal-PDF-Chunking-Dashboard/` (to be extracted to separate repo)
- `.env` -> already in `.gitignore`
