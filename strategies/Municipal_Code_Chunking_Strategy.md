# Municipal Code Chunking Strategy
## A Research-Backed Approach for GraphRAG-Ready PDF Extraction

**Date:** March 16, 2026
**Scope:** Opa-Locka FL Code of Ordinances (948 pages) + Miami-Dade Chapter 24 Environmental Protection (316 pages)
**Purpose:** Define a one-size-fits-all chunking strategy that preserves legal structure, supports both RAG and GraphRAG retrieval, and generalises across municipal code formats.

---

## 1. Why "Just Split by Section" Is Not Enough

After scanning both documents and reviewing the latest research (15+ papers from 2024-2026), the evidence is clear: **naive section-based splitting is a starting point, not a solution.** Three structural realities in these documents break it:

**Problem 1: Wild variation in section length.** In Opa-Locka, § 22-186 (Tree Preservation) runs 6+ pages of deeply nested subsections, while § 21-79 (Excess Water Charges) is two sentences. In Chapter 24, § 24-5 (Definitions) spans 30+ pages with 300+ numbered definitions. Splitting "by section" gives you chunks ranging from 50 tokens to 15,000 tokens — useless for consistent embedding quality.

**Problem 2: Cross-references everywhere.** Chapter 24 § 24-4(2) says "shall comply with Section 24-5 (Nuisance); Section 24-42 (Toxic waste discharges); Section 24-41 (Black smoke emissions)." If § 24-4 and § 24-5 are separate chunks, the retriever has no way to know they're connected. This is the **Document-Level Retrieval Mismatch (DRM)** problem identified in arXiv:2510.06999.

**Problem 3: Definitions are separated from usage.** Both documents define terms in one section (§ 24-5 in Chapter 24, § 22-186 definitions in Opa-Locka) and use them hundreds of pages later. An LLM answering "What counts as a nuisance under environmental law?" needs § 24-5(217) and § 24-27/§ 24-28 together — but they're far apart structurally.

**The research consensus** (LegalBench-RAG benchmark, 2024; ICNLSP-2025; Anthropic Contextual Retrieval, 2024): no single chunking method dominates. The best systems combine **structure-aware splitting** with **contextual enrichment** and **hierarchical metadata**.

---

## 2. Document Structure Analysis

### Opa-Locka Code of Ordinances (948 pages)

```
Code of Ordinances
├── Part I: Charter and Related Laws
├── Part II: Code of Ordinances
│   ├── Chapter 1: General Provisions (§§ 1-1 to 1-10)
│   ├── Chapter 2: Administration (§§ 2-1 to 2-654)
│   │   ├── Article I: In General
│   │   ├── Article II: City Commission
│   │   │   ├── Division 1: Generally
│   │   │   ├── Division 2: Meetings
│   │   │   └── ...
│   │   └── ...
│   ├── ... (Chapters 3-21)
│   └── Chapter 21: Water, Sewer and Stormwater
│       ├── Division 3: Service Rates and Charges
│       │   └── § 21-77: Schedule of rates (TABLES)
│       └── ...
└── Land Development Regulations (Chapter 22)
    ├── Article I: General Provisions (§§ 22-1 to 22-30)
    ├── Article II: Administrative Provisions
    ├── Article III: Districts and Development Standards
    ├── ...
    └── Article XIV: Green Standards
```

**Content types identified:** Legal prose, fee schedules with dollar amounts, rate tables (water/sewer/stormwater), numbered definitions, enumerated lists, cross-reference-heavy enforcement sections, index/TOC pages.

### Chapter 24: Environmental Protection (316 pages)

```
Chapter 24: Environmental Protection
├── Article I: In General
│   ├── Division 1: General Provisions (§§ 24-1 to 24-24)
│   │   ├── § 24-1: Short title
│   │   ├── § 24-2: Legislative intent (2 pages)
│   │   ├── § 24-5: Definitions (30+ pages, 300+ terms)
│   │   └── ...
│   ├── Division 2: State and Federal Adoptions
│   ├── Division 3: Enforcement (§§ 24-27 to 24-31)
│   └── Division 4: Trusts and Fees
├── Article II: Air Quality (§§ 24-41 to 24-41.16)
├── Article III: Water and Soil Quality
│   ├── Division 1: Water Quality / Wastewater
│   ├── Division 2: Wellfield Protection
│   ├── Division 3: Contaminated Site Cleanups
│   └── Division 4: Underground Storage
├── Article IV: Natural Resources / Stormwater
│   ├── Division 1: Canal Rights-of-Way, Wetlands
│   ├── Division 2: Tree Preservation
│   └── Division 3: Endangered Lands
└── Article V: Stormwater Utility
```

**Content types identified:** Dense legal prose, massive definitions section with nested sub-definitions, ordinance citation chains, geographic/technical descriptions (basin boundaries, coordinates), scientific/technical standards (EPA methods, sampling procedures), permit application requirements.

---

## 3. The Strategy: Hierarchical Structure-Aware Chunking + Contextual Enrichment

### 3.1 Chunk Unit: The "Legal Provision"

**Do not chunk by fixed token count. Do not chunk by page. Chunk by legal provision.**

A "legal provision" is the smallest self-contained unit of legal meaning:
- A section (§ 24-1) if it's short (< 800 tokens)
- A subsection with its sub-items if the section is long (e.g., § 24-5 definition #63 with its 7 sub-points)
- A single definition entry in a definitions section
- A table with its header and caption as one unit
- A "Reserved" section as a minimal marker chunk

**Target chunk size: 300-1,000 tokens.** This range is backed by:
- LegalBench-RAG (2024): 256 tokens optimal for contracts, but municipal codes are denser
- NVIDIA benchmark (2024): page-level chunking wins at 0.648 accuracy for structured documents
- Community consensus (Stack Overflow, Reddit): 600-1,000 tokens for legal text with 10-20% overlap
- Our own benchmark: Docling's ideal chunk range was 300-3,000 characters (~75-750 tokens)

**If a provision exceeds 1,000 tokens:** Split at the next subsection boundary. Never split mid-sentence or mid-enumerated-item.

**If a provision is under 100 tokens:** Merge with the next provision at the same hierarchy level (e.g., consecutive "Reserved" sections become one chunk).

### 3.2 Hierarchical Metadata (The Breadcrumb)

Every chunk gets a structured metadata header. This is **not optional** — research shows 15-20% accuracy loss when metadata is stripped (Medium: Metadata-Aware Chunking, 2025).

**Schema:**

```json
{
  "chunk_id": "opalocka_ch21_div3_s21-77",
  "document": "Opa-Locka, FL Code of Ordinances",
  "jurisdiction": "Opa-Locka, FL",
  "hierarchy": {
    "part": "Part II: Code of Ordinances",
    "chapter": "Chapter 21: Water, Sewer and Stormwater Utilities",
    "article": null,
    "division": "Division 3: Service Rates and Charges",
    "section": "§ 21-77",
    "section_title": "Schedule of rates generally",
    "subsection": null
  },
  "breadcrumb": "Ch.21 Water/Sewer > Div.3 Rates > § 21-77 Schedule of rates",
  "content_type": "table",
  "ordinance_citations": ["Ord. No. 14-17", "Ord. No. 18-13"],
  "cross_references": ["§ 21-78", "§ 32-66"],
  "effective_dates": ["10/1/2015", "10/1/2018"],
  "dollar_amounts_present": true,
  "definitions_referenced": [],
  "page_range": "500-501"
}
```

**The breadcrumb field is the key innovation.** It gets prepended to the chunk text before embedding, so the vector captures hierarchical context. This is the approach validated by Anthropic's Contextual Retrieval (2024) — reduces retrieval errors by up to 67%.

### 3.3 Contextual Enrichment (Summary-Augmented Chunking)

For each chunk, generate a 1-2 sentence context prefix using an LLM. This solves the DRM problem (arXiv:2510.06999).

**Example — before enrichment:**
```
(a) Water and sewer service, water only service, or sewer only service:
[table of deposit amounts by meter size]
```

**After enrichment:**
```
[Context: This subsection of § 21-80 (Deposits) in the Opa-Locka Water, Sewer and Stormwater Utilities chapter specifies the deposit amounts required for new water/sewer service connections, broken down by meter size for both residential and commercial customers.]

(a) Water and sewer service, water only service, or sewer only service:
[table of deposit amounts by meter size]
```

**Cost:** ~$1 per million tokens (Anthropic estimate). For both documents (~1.2M tokens combined), this is roughly $1.20 — trivial.

### 3.4 Special Handling by Content Type

| Content Type | Chunking Rule | Example |
|---|---|---|
| **Standard legal prose** | Split at section/subsection boundary, target 300-1,000 tokens | § 24-2 Legislative Intent |
| **Definitions section** | One chunk per definition entry (including all sub-definitions) | § 24-5(63) "Comprehensive environmental impact statement" with its 7 sub-points |
| **Fee schedules / Rate tables** | Keep entire table + header + caption as one chunk, even if > 1,000 tokens | § 21-77 water rate tables |
| **Enumerated lists** | Keep the full list together if < 1,500 tokens; split at top-level item boundaries if larger | § 24-4 subsections (1)-(4) |
| **Ordinance citation chains** | Attach to the provision they modify, not as separate chunks | "(Ord. No. 04-214, §§ 1, 5, 12-2-04)" stays with its section |
| **Reserved/placeholder sections** | Merge consecutive reserved sections into one minimal chunk | "Secs. 21-67—21-76. Reserved." |
| **Cross-reference-heavy sections** | Tag all referenced sections in metadata; consider dual-embedding (see §3.5) | § 24-4(2) referencing §§ 24-5, 24-42, 24-41 |
| **Geographic/technical descriptions** | Keep as single chunk with content_type="technical" | Basin boundary descriptions in § 24-5 |
| **Index/TOC pages** | Exclude from chunking (structural metadata only) | Pages 1-2, LDR index |

### 3.5 Cross-Reference Resolution

This is where section-only chunking fundamentally breaks. Two complementary approaches:

**Approach A: Metadata linking.** Every chunk's `cross_references` field lists the section numbers it references. At retrieval time, if a chunk references § 24-5(217), the system can pull that definition chunk alongside the primary result. This is cheap and deterministic.

**Approach B: Definition injection.** For the definitions section specifically (§ 24-5 in Ch.24, various definition sections in Opa-Locka), create a lookup table of term → definition text. When a chunk uses a defined term, append a compact reference: `[Defined: "Nuisance" — see § 24-5(217)]`. This helps the embedding model capture the relationship.

**Approach C (Advanced): Graph edges.** If using GraphRAG, cross-references become explicit edges in the knowledge graph: `§ 24-4 --cites--> § 24-5`, `§ 24-4 --cites--> § 24-42`. This enables multi-hop retrieval that no flat chunking can match.

---

## 4. Alternatives Beyond Section-Based Chunking

The research surfaced several approaches that go beyond traditional chunking. Here's what's worth considering for RegOS:

### 4.1 Late Chunking (Jina AI, arXiv:2409.04701)

**What:** Embed the entire document with a long-context model first, then split the embedding sequence into chunks. Each chunk's vector retains awareness of the full document context.

**Why for municipal codes:** 12-18% retrieval improvement on documents with heavy cross-references. A definition in § 24-5 and its usage in § 24-42 share embedding context even though they're in different chunks.

**Trade-off:** Requires a long-context embedding model (jina-embeddings-v2 supports 8K tokens). A 316-page document needs to be processed in overlapping windows. Higher compute cost at indexing time, but retrieval quality is significantly better.

**Verdict:** Worth benchmarking. Use Jina's reference implementation at github.com/jina-ai/late-chunking.

### 4.2 Proposition-Based Decomposition (Chen et al., arXiv:2503.19574)

**What:** Instead of chunks, decompose the document into atomic propositions — self-contained factual statements. "§ 24-5(217)(1) defines nuisance as emission of dust, fume, gas, mist, odor, smoke or vapor detectable by a considerable number of persons."

**Why for municipal codes:** Definitions and rules are naturally propositional. Each rule, each fine amount, each permit requirement is an atomic fact. Propositions are individually verifiable and auditable.

**Trade-off:** Expensive to generate (LLM call per chunk). Reconstructing full context from propositions at generation time is harder. Best for definitions and simple rules; less suited for narrative legal prose.

**Verdict:** Use selectively — decompose the definitions section into propositions, keep prose sections as structural chunks.

### 4.3 Ontology-Driven Graph RAG (arXiv:2505.00039)

**What:** Build a legal ontology (not just a knowledge graph) that captures the formal structure of legislation: hierarchical relationships (chapter contains article contains section), temporal relationships (amended by, repealed by, effective date), and normative relationships (grants, prohibits, requires, exceptions_to).

**Why for municipal codes:** Municipal codes ARE ontological by nature. "§ 24-27 grants enforcement power" → "§ 24-28 defines penalties" → "§ 24-31 provides appeal process" is a normative chain. An ontology captures this; flat chunks don't.

**Trade-off:** Significant upfront engineering. Entity extraction from legal text is error-prone (HalluGraph, arXiv:2512.01659, specifically addresses hallucination in legal graph construction). Requires validation.

**Verdict:** This is the long-term play for RegOS. Start with structured chunks + metadata (§3), add graph edges for cross-references (§3.5C), evolve toward full ontology as the system matures.

### 4.4 Cross-Document Topic-Aligned Chunking (CDTA, arXiv:2601.05265)

**What:** Align chunks across multiple jurisdictions by topic. "Water rates" chunks from Opa-Locka, Miami-Dade, and other cities are aligned so comparative queries work.

**Performance:** 94% faithfulness, 93% citation accuracy — best-in-class for multi-document regulatory retrieval. 18% improvement over contextual chunking, 40% over recursive, 62% over fixed-size.

**Why for RegOS:** If the goal is processing hundreds of municipal codes, CDTA enables "Compare water rate structures across all Florida municipalities" — a query that no single-document chunking strategy can answer.

**Verdict:** Critical for scale. Implement after single-document chunking is stable.

---

## 5. Recommended Implementation Phases

### Phase 1: Structure-Aware Extraction (Now)

Use Docling (validated in our benchmark) to extract both documents with element-type metadata. Docling provides: `section_header`, `list_item`, `text`, `table`, `caption`, `footnote`, `page_header`, `page_footer`.

**Pipeline:**
1. Extract with Docling → JSON with element types
2. Parse hierarchy from section numbers (regex: `§ \d+-\d+(\.\d+)?`)
3. Build chunk boundaries at provision level (§3.1 rules)
4. Attach hierarchical metadata (§3.2 schema)
5. Generate contextual prefixes with LLM (§3.3)
6. Store in vector DB with metadata filters

**Deliverable:** Chunks with breadcrumbs, metadata, and contextual enrichment. Ready for basic RAG.

### Phase 2: Cross-Reference Graph (Next)

Build a lightweight graph of cross-references extracted from chunk text.

**Pipeline:**
1. Regex-extract all `§ X-Y` references from each chunk
2. Create edges: `chunk_A --references--> chunk_B`
3. At retrieval time, expand results to include 1-hop referenced chunks
4. Store graph in Neo4j or similar

**Deliverable:** Cross-reference-aware retrieval. When a user asks about § 24-4 compliance, the system also pulls the referenced §§ 24-5, 24-41, 24-42.

### Phase 3: Late Chunking + Propositions (Enhancement)

Re-embed chunks using late chunking for improved contextual awareness. Decompose definitions section into propositions for fine-grained retrieval.

**Pipeline:**
1. Re-process documents with Jina late-chunking
2. Extract propositions from definitions sections
3. Dual-index: structural chunks (for prose queries) + propositions (for definition/rule queries)

**Deliverable:** Best-in-class retrieval for both "what does this section say?" and "what is the definition of X?" queries.

### Phase 4: Multi-Jurisdiction Alignment (Scale)

Apply CDTA to align chunks across municipal codes by topic.

**Pipeline:**
1. Topic-classify each chunk (zoning, water, fees, enforcement, etc.)
2. Align corresponding chunks across jurisdictions
3. Enable comparative queries

**Deliverable:** "Compare tree preservation requirements across all indexed municipalities."

---

## 6. Concrete Example: How Chapter 24 § 24-5(217) Gets Chunked

**Raw text (from Docling extraction):**

```
(217) Nuisance shall mean and include the use of any property, facilities, equipment,
processes, products or compounds, or the commission of any acts or any work that causes
or materially contributes to:
(1) The emission into the outdoor air of dust, fume, gas, mist, odor, smoke or vapor...
(2) The discharge into any of the waters of this County of any organic or inorganic matter...
(3) Any violation of provisions of this chapter which becomes detrimental to health...
(4) Adverse environmental impact to a coastal or freshwater wetlands.
(5) Cumulative adverse environmental impact to a coastal or freshwater wetlands.
(6) Adverse environmental impact to environmentally-sensitive tree resources.
(7) Cumulative adverse environmental impact to environmentally-sensitive tree resources.
```

**Resulting chunk:**

```json
{
  "chunk_id": "ch24_art1_div1_s24-5_def217",
  "breadcrumb": "Ch.24 Environmental > Art.I General > Div.1 General Provisions > § 24-5 Definitions > (217) Nuisance",
  "content_type": "definition",
  "text": "[Context: This is the definition of 'Nuisance' within the Miami-Dade County Environmental Protection Ordinance (Chapter 24). This definition is referenced by § 24-27 (enforcement) and § 24-28 (penalties) as the basis for violation determinations.]\n\n(217) Nuisance shall mean and include the use of any property, facilities, equipment, processes, products or compounds, or the commission of any acts or any work that causes or materially contributes to:\n(1) The emission into the outdoor air of dust, fume, gas, mist, odor, smoke or vapor...\n(2) The discharge into any of the waters of this County...\n(3) Any violation of provisions of this chapter...\n(4) Adverse environmental impact to a coastal or freshwater wetlands.\n(5) Cumulative adverse environmental impact to a coastal or freshwater wetlands.\n(6) Adverse environmental impact to environmentally-sensitive tree resources.\n(7) Cumulative adverse environmental impact to environmentally-sensitive tree resources.",
  "hierarchy": {
    "chapter": "Chapter 24: Environmental Protection",
    "article": "Article I: In General",
    "division": "Division 1: General Provisions",
    "section": "§ 24-5",
    "section_title": "Definitions",
    "subsection": "(217)"
  },
  "cross_references": ["§ 24-27", "§ 24-28", "§ 24-5(217)"],
  "defined_term": "Nuisance",
  "token_count": 287
}
```

---

## 7. Research Sources

### Academic Papers (2024-2026)

1. **LegalBench-RAG** — First legal-domain RAG benchmark. arXiv:2408.10343
2. **Summary-Augmented Chunking (SAC)** — Solves Document-Level Retrieval Mismatch. arXiv:2510.06999
3. **Late Chunking** — Contextual chunk embeddings via long-context models. arXiv:2409.04701
4. **Recursive Semantic Chunking** — RAPTOR enhancement, ICNLSP-2025. aclanthology.org/2025.icnlsp-1.15
5. **Cross-Document Topic-Aligned Chunking (CDTA)** — 94% faithfulness on multi-doc legal. arXiv:2601.05265
6. **Ontology-Driven Graph RAG for Legal Norms** — Hierarchical, temporal, deterministic. arXiv:2505.00039
7. **HalluGraph** — Hallucination detection for legal GraphRAG. arXiv:2512.01659
8. **S2 Chunking** — Spatial + semantic hybrid. arXiv:2501.05485
9. **HiQA** — Hierarchical contextual augmentation for multi-doc QA. arXiv:2402.01767
10. **HiChunk** — Evaluating hierarchical retrieval. arXiv:2509.11552
11. **Overlapping Chunks for Legal Texts** — uBERT architecture. arXiv:2410.19184
12. **Context-Efficient Retrieval with Factual Decomposition** — Propositions approach. arXiv:2503.19574
13. **Multi-Layered Embedding for Legal Knowledge** — Hierarchical embeddings. arXiv:2411.07739
14. **RegGuard** — Pharmaceutical regulatory compliance RAG. arXiv:2601.17826

### Industry Research

15. **Anthropic Contextual Retrieval** — 67% error reduction. anthropic.com/engineering/contextual-retrieval
16. **NVIDIA Chunking Benchmark** — 7 strategies, 5 datasets. developer.nvidia.com/blog
17. **Weaviate Chunking Strategies** — Production RAG guide. weaviate.io/blog/chunking-strategies-for-rag
18. **GraphRAG Official Chunking Guide** — graphrag.com/guides/chunking
19. **LightRAG** — Simplified graph RAG. arXiv:2410.05779, github.com/HKUDS/LightRAG
20. **Jina AI Late Chunking Implementation** — github.com/jina-ai/late-chunking

### Community / Production Case Studies

21. **Legal AI Search Engine** — Article-level chunking for legislation. decodingai.com
22. **Stack Overflow: Chunking in RAG** — Production experiences. stackoverflow.blog/2024/12/27
23. **Metadata-Aware Chunking** — 15-20% accuracy loss without metadata. medium.com/@asimsultan2

---

## 8. Decision Required

This strategy is ready for review. Before execution, we need alignment on:

1. **Phase 1 scope:** Start with both documents, or one first?
2. **Vector DB choice:** What's the target storage? (Affects metadata schema)
3. **GraphRAG path:** LightRAG (simpler, faster) or Microsoft GraphRAG (more powerful, costlier)?
4. **Context prefix generation:** Use GPT-4o-mini (cheap, fast) or Claude Haiku (better legal understanding)?
5. **Cross-reference graph:** Neo4j, or lighter-weight (NetworkX + JSON)?
