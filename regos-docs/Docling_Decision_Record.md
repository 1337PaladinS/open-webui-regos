# Decision Record: PDF Extraction Tool Selection

**Decision:** IBM Docling (local, free) selected over GPT-4o Vision (cloud, paid) for municipal code PDF extraction in the RegOS GraphRAG pipeline.

**Date:** March 2026
**Status:** Final — implemented in production pipeline

---

## Context

RegOS ingests municipal regulatory codes (PDF format) into a Neo4j knowledge graph via a GraphRAG pipeline. The extraction step converts PDF pages into structured text that feeds section-based chunking, entity extraction, and graph construction.

The source document for benchmarking was the Opa-locka, FL Code of Ordinances (948 pages, 5.4 MB) — representative of the class of legal PDFs RegOS processes.

## Candidates Evaluated

**IBM Docling** — Open-source library running locally. Converts PDF to structured JSON with element labels (section_header, text, list_item, table, page_header, page_footer). Also outputs markdown. Cost: $0.00.

**GPT-4o Vision** — OpenAI multimodal model via OpenRouter API. Each page converted to 200 DPI image, base64-encoded, sent to GPT-4o with a municipal code extraction prompt. Cost: ~$0.009/page.

## Benchmark Methodology

Five page ranges selected to cover distinct content types: table of contents (pages 1-2), dense legal text with nested subsections (pages 100-101), fee schedules with indented pricing (pages 200-201), rate tables with columns (pages 500-501), and land development code with lettered subsections (pages 750-751).

Three evaluation dimensions scored against a `pdftotext` baseline:

1. **Content Recovery** (order-independent) — unigram overlap, bigram overlap, character recovery
2. **Structural Fidelity** — section numbers, article headers, subsection labels, cross-references, ordinance citations, dollar amounts, table structure detected via regex scoring
3. **GraphRAG Chunk Quality** — chunk count, average size (ideal 500-2000 chars), section boundary alignment

---

## Results

### Aggregate Scores

| Metric                    | Docling     | GPT-4o      | Winner   |
| ------------------------- | ----------- | ----------- | -------- |
| Avg unigram overlap       | 92.3%       | 77.5%       | Docling  |
| Avg bigram overlap        | 79.7%       | 68.6%       | Docling  |
| Avg character recovery    | 114.3%      | 88.5%       | Docling  |
| Avg structural fidelity   | 87.8%       | 100.7%      | GPT-4o   |
| Cost per page             | $0.00       | $0.009      | Docling  |
| Cost full document (948p) | $0.00       | $8.47       | Docling  |

### Per-Content-Type Breakdown

**Pages 1-2 (Table of Contents):**
Docling captured 72.3% of unigrams; GPT-4o captured only 3.4%. GPT-4o failed almost entirely on this content type — the vision model could not transcribe the structured ToC/instruction pages. Docling produced an oversized single chunk (61K chars) but recovered the content.

**Pages 100-101 (Dense legal text — core use case):**
Docling: 98.5% unigram, 97.4% bigram, 92.9% structural, 5 chunks averaging 1,712 chars.
GPT-4o: 89.7% unigram, 85.5% bigram, 95.0% structural, 4 chunks averaging 1,828 chars.
Both performed well. Docling had higher content recovery; GPT-4o had slightly higher structural fidelity. Chunk quality comparable.

**Pages 200-201 (Fee schedules):**
Near parity on content (98.2% vs 98.9% unigram). GPT-4o significantly better on structure (110.7% vs 78.6%) and produced better chunk sizes (2 chunks at 3,051 chars vs 1 chunk at 6,082 chars). GPT-4o handled fee schedule formatting better.

**Pages 500-501 (Rate tables):**
Near parity (94.6% vs 96.9% unigram). GPT-4o slightly better on structure (89.3% vs 85.3%). GPT-4o produced more granular chunks (10 at 692 chars vs 8 at 949 chars).

**Pages 750-751 (Land Development Code):**
GPT-4o slightly better on content (98.8% vs 97.7% unigram) and structure (108.7% vs 92.9%). Docling produced better-sized chunks (2 at 1,947 chars vs 4 at 1,008 chars).

---

## Decision Rationale

Docling was selected for the following reasons:

**1. Content recovery is the priority metric.** The GraphRAG pipeline depends on extracting regulatory text as completely as possible. Missing text means missing regulations in the knowledge graph. Docling's 92.3% average unigram overlap (vs 77.5% for GPT-4o) means fewer regulatory provisions lost during extraction.

**2. The core use case (dense legal text) strongly favors Docling.** Pages 100-101 — representative of the bulk of a municipal code — showed 98.5% content recovery with good chunk quality. This is the content type that matters most for RegOS.

**3. Zero marginal cost enables full-document processing.** At $0.00/page, Docling can process entire 948-page codes without budget consideration. GPT-4o at $8.47 per document adds up when processing multiple municipal codes across jurisdictions.

**4. Structured JSON output directly supports GraphRAG.** Docling's JSON output includes element labels (section_header, text, list_item, table) that can drive intelligent section-based chunking without additional NLP processing.

**5. Local execution eliminates API dependency.** No rate limits, no API keys, no network latency, no data leaving the infrastructure. Important for municipal codes that may contain sensitive regulatory information.

**6. GPT-4o's structural advantage is addressable.** GPT-4o's higher structural fidelity (100.7% vs 87.8%) can be partially compensated through post-processing rules on Docling's output — regex-based section numbering, header detection, and table reconstruction.

**Known trade-offs accepted:**

- Docling sometimes produces oversized chunks on ToC and fee schedule pages. Mitigated by post-processing chunking logic that splits on section boundaries.
- GPT-4o produces more consistently sized chunks across all content types. This advantage is modest and doesn't outweigh the cost and content recovery differences.
- For future multi-jurisdiction expansion, if fee schedule and table-heavy codes become a larger proportion of the corpus, a hybrid approach (Docling for text, GPT-4o for complex tables) could be considered.

---

## Implementation

Docling is used in the production RegOS pipeline for all PDF extraction. The `pdf_benchmark.py` script and `benchmark/` directory contain the full benchmark infrastructure, results, and scoring code that produced these findings. The benchmark can be re-run on new documents if extraction quality needs to be re-evaluated.
