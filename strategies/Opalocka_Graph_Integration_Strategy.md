# Opa-locka Ordinance Graph Integration Strategy

**Date:** March 20, 2026 | **Status:** Draft for review
**Objective:** Process the Opa-locka FL Code of Ordinances through the existing chunking dashboard, build a knowledge graph, and integrate it with the live Miami-Dade Chapter 24 graph to create a multi-jurisdiction regulatory intelligence layer.

---

## Current Assets

| Asset | Status | Location |
|-------|--------|----------|
| Opa-locka Code of Ordinances PDF | On disk (5.4 MB) | `Opa-locka, FL Code of Ordinances.pdf` |
| APAS Legal PDF Chunking Dashboard | Working (Docker) | `APAS-Legal-PDF-Chunking-Dashboard/` |
| Chapter 24 Neo4j Graph | Live | 141 Ch24Document + 455 Ch24Entity + 97 Ch24Class nodes |
| FEA Schema v0.17.3 | Deployed | 3-layer: Concepts → Documents → Entities |
| GraphRAG Filter | v0.17.3 deployed | 4-step retrieval pipeline in `graphrag_filter.py` |
| Concepts Ontology | 30 regulatory concepts | `regos_setup/data/concepts.json` |
| Municipal Code Chunking Strategy | Documented | `strategies/Municipal_Code_Chunking_Strategy.md` |

---

## Phase 0: Dashboard Modification — Custom Export Path

**Problem:** The dashboard currently stores all output in a hardcoded Docker volume (`/data/jobs/{job_id}/`). There is no way to choose where chunks are saved, and no export mechanism to get chunks out of the container in a machine-readable format for downstream processing.

**What needs to change in the codebase:**

### 0.1 Add a configurable export directory

**File:** `backend/app/main.py`

- Add an environment variable `EXPORT_DIR` (default: `/data/exports`)
- Mount this as a host volume in `docker-compose.yml` so chunks land on the host filesystem at a user-chosen path
- After chunking completes (Stage 2), auto-copy `chunks.json` to `$EXPORT_DIR/{job_id}/chunks.json`

**docker-compose.yml change:**
```yaml
backend:
  volumes:
    - shared-data:/data
    - ${EXPORT_PATH:-./exports}:/data/exports   # NEW: host-mounted export dir
```

**User workflow:** Set `EXPORT_PATH=/path/to/wherever` in `.env` before `docker compose up`. Every job's chunks automatically appear on the host.

### 0.2 Add a one-click export button in the frontend

**File:** `frontend/src/app/page.tsx` (Chunks Explorer tab)

- Add "Export Chunks" button next to the existing "Push to Neo4j" button
- Calls new backend endpoint: `GET /jobs/{id}/export` → returns `chunks.json` as download
- Also triggers copy to `$EXPORT_DIR` on the server side

### 0.3 Add a bulk export endpoint

**File:** `backend/app/main.py`

- `POST /jobs/{id}/export` — copies chunks.json + stats.json + docling_extraction.json to `$EXPORT_DIR/{id}/`
- Returns the export path for confirmation
- Optionally accepts a `target_dir` parameter to override the default

### Estimated effort: ~40 lines backend + ~20 lines frontend. Half a day.

---

## Phase 1: Chunk the Opa-locka Ordinance

**Tool:** APAS Legal PDF Chunking Dashboard (with Phase 0 modifications)

### 1.1 Process the PDF

1. Start the dashboard: `docker compose up -d --build`
2. Upload `Opa-locka, FL Code of Ordinances.pdf` via the dashboard UI
3. Enable LLM enrichment (context prefix generation) — this adds ~$0.16 and dramatically improves retrieval quality
4. The dashboard will:
   - Extract text via Docling (batched, 10 pages at a time)
   - Detect legal structure (chapters, articles, sections via regex)
   - Chunk by legal provision (one chunk = one section, not fixed token count)
   - Extract FEA entities per chunk: thresholds, penalties, roles, standards, obligations
   - Generate context prefixes via LLM enrichment
5. Export chunks to host via the new export button (Phase 0)

### 1.2 Verify chunking quality

- Review the Chunks Explorer tab — check that sections are properly delineated
- Verify the document structure tree shows correct hierarchy
- Spot-check FEA entity extraction on 5-10 chunks (are thresholds/penalties captured?)
- Compare token distribution against Chapter 24 — expect similar shape if both are municipal codes

### 1.3 Jurisdiction detection

The dashboard already has jurisdiction auto-detection in `chunker.py`:
- Filename contains "opa" or "locka" → detected as **Opa-Locka, FL**
- Breadcrumbs will be formatted accordingly (e.g., "Opa-Locka Code > Chapter 21 > § 21-80")

### Expected output: `chunks.json` with 200-400 chunks (depending on ordinance size), each with breadcrumb, content_type, token_count, cross_references, and FEA entities.

---

## Phase 2: Build the Opa-locka Graph

**Two options — use the one that matches our speed requirement:**

### Option A: Push to Neo4j via the dashboard (fastest, 5 minutes)

The dashboard already has a full Neo4j push pipeline in `neo4j_service.py`:

1. Open the dashboard's Neo4j tab
2. Verify connection to the same Neo4j instance running the Chapter 24 graph
3. Click "Push to Neo4j" on the Opa-locka job

**What the push creates:**
- `OpalockaDocument` nodes (one per chunk) — title, text, breadcrumb, content_type, token_count
- `OpalockaEntity` nodes — thresholds, penalties, roles, standards from FEA extraction
- `MENTIONS_ENTITY` relationships — document → entity
- `REFERENCES` relationships — cross-reference edges between sections
- Fulltext index on document title + text

**Problem:** The current push uses generic `Document`, `Entity` labels. We need namespace separation.

**Required modification to `neo4j_service.py`:**
- Prefix all labels with jurisdiction: `OpalockaDocument`, `OpalockaEntity` (instead of generic `Document`)
- This prevents name collisions with `Ch24Document`, `Ch24Entity`
- ~20 lines of changes in the `push_to_neo4j()` function

### Option B: Generate Cypher batch files (more control)

Write a Python script that reads `chunks.json` and generates Cypher files following the same pattern as `regos_setup/cypher/batch_01.cypher`:

```cypher
CREATE CONSTRAINT IF NOT EXISTS FOR (s:OpalockaSection) REQUIRE s.number IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (d:OpalockaDocument) REQUIRE d.sectionId IS UNIQUE;

MERGE (d:OpalockaDocument {sectionId: 'opl-21-80'})
SET d.title = '§ 21-80 Deposit for new connections',
    d.text = '...',
    d.breadcrumb = 'Opa-Locka Code > Chapter 21 > § 21-80',
    d.content_type = 'prose',
    d.token_count = 342;
```

**Advantage:** Full control, auditable, repeatable. Can generate FEA entity nodes with proper typing.
**Disadvantage:** More work. ~2 hours to write the script.

### Recommendation: Option A (dashboard push) for speed, then refine with Option B if needed.

---

## Phase 3: Cross-Jurisdiction Graph Integration

**This is the high-value step.** Connect the Opa-locka graph to the Chapter 24 graph so queries against either jurisdiction surface relevant provisions from both.

### 3.1 Shared Ontology Layer (Concept Bridge)

The existing `concepts.json` contains 30 regulatory concepts (SEWER_DISCHARGE_LIMITS, FOG_CONTROL, STORMWATER_MANAGEMENT, etc.). These concepts are **domain-generic** — they apply to any Florida municipal code, not just Miami-Dade.

**Action:** Connect Opa-locka documents to the SAME Ch24Class concept nodes:

```cypher
// For each Opa-locka document, compute embedding similarity to concepts
// and create RELATES_TO_CONCEPT edges where similarity > 0.35
MATCH (d:OpalockaDocument), (c:Ch24Class)
WHERE gds.similarity.cosine(d.embedding, c.embedding) > 0.35
MERGE (d)-[r:RELATES_TO_CONCEPT]->(c)
SET r.similarity = gds.similarity.cosine(d.embedding, c.embedding)
```

**Result:** Both Ch24Document and OpalockaDocument nodes connect to the same concept layer. A query about "sewer discharge limits" will now traverse:

```
Query → SEWER_DISCHARGE_LIMITS concept
         ├→ Ch24Document (24-42, 24-42.4, 24-42.5)  [Miami-Dade]
         └→ OpalockaDocument (§ 21-XX, § 21-YY)     [Opa-locka]
```

This is where the maximum value lives — the concept layer becomes a **cross-jurisdiction bridge**.

### 3.2 Entity Alignment (Shared Actors & Standards)

Many FEA entities are shared across jurisdictions:
- **Roles:** DEP (Florida Dept of Environmental Protection), EPA, Board
- **Standards:** EPA Method 624, 40 CFR 403, ANSI standards
- **Activities:** discharge, pretreatment, inspection

**Action:** Merge shared entities instead of creating duplicates:

```cypher
// Find matching entities between jurisdictions
MATCH (e1:Ch24Entity), (e2:OpalockaEntity)
WHERE toLower(e1.value) = toLower(e2.value)
MERGE (e1)-[:SAME_AS]->(e2)
```

This creates explicit cross-jurisdiction entity links. When the GraphRAG filter matches an entity, it can now traverse to documents in BOTH jurisdictions.

### 3.3 Cross-Reference Detection

Municipal codes frequently reference state and federal regulations. Both Chapter 24 and Opa-locka likely reference:
- Florida Administrative Code (F.A.C.) Chapter 62
- 40 CFR 403 (federal pretreatment standards)
- Florida Statutes Chapter 403

**Action:** Extract external references from both graphs and link them:

```cypher
// Create shared external standard nodes
MATCH (d1:Ch24Document) WHERE d1.text CONTAINS '40 CFR 403'
MATCH (d2:OpalockaDocument) WHERE d2.text CONTAINS '40 CFR 403'
MERGE (s:ExternalStandard {name: '40 CFR 403'})
MERGE (d1)-[:CITES]->(s)
MERGE (d2)-[:CITES]->(s)
```

### 3.4 Threshold Comparison Layer

The highest regulatory value: comparing actual numeric thresholds between jurisdictions.

```cypher
// Find thresholds for the same parameter in both jurisdictions
MATCH (t1:Ch24Threshold {parameter: 'BOD'})
MATCH (t2:OpalockaThreshold {parameter: 'BOD'})
MERGE (t1)-[r:COMPARED_WITH]->(t2)
SET r.ch24_value = t1.value,
    r.opalocka_value = t2.value,
    r.stricter = CASE WHEN t1.value < t2.value THEN 'Miami-Dade' ELSE 'Opa-locka' END
```

**Regulatory intelligence use case:** "Which jurisdiction has stricter BOD limits?" becomes a single Cypher query.

---

## Phase 4: Update GraphRAG Filter for Multi-Jurisdiction

### 4.1 Extend the 4-step retrieval pipeline

The current pipeline only queries `Ch24Document` and `Ch24Entity`. After integration:

- **Step 2b (entity traversal):** Also match against `OpalockaDocument` nodes
- **Step 2c (concept expansion):** Already works — Opa-locka documents will be found via shared concept nodes
- **Step 3 (fulltext):** Add fulltext index on OpalockaDocument, query both indexes

### 4.2 Add jurisdiction tagging in responses

When the filter retrieves sections from multiple jurisdictions, the confidence disclaimer should indicate which jurisdiction each citation comes from:

```
[G1] Miami-Dade Ch. 24 § 24-42.4 — BOD limit: 300 mg/L
[G2] Opa-locka Code § 21-XX — BOD limit: 250 mg/L
```

### 4.3 Comparative query support

New query pattern: "Compare [topic] between Miami-Dade and Opa-locka" triggers a comparative retrieval mode that explicitly queries both jurisdiction graphs and presents results side-by-side.

---

## Execution Order (Summary)

| Phase | What | Effort | Depends On |
|-------|------|--------|------------|
| **0** | Modify dashboard: add export path + host volume mount | Half day | Nothing |
| **1** | Chunk Opa-locka PDF via dashboard | 30 min (hands-on) + processing time | Phase 0 |
| **2** | Push Opa-locka chunks to Neo4j (namespaced labels) | 2-3 hours | Phase 1 |
| **3** | Cross-jurisdiction integration (concept bridge + entity alignment + threshold comparison) | 1-2 days | Phase 2 + Neo4j access |
| **4** | Update GraphRAG filter for multi-jurisdiction retrieval | 1 day | Phase 3 |

**Total estimated effort:** 3-4 days

---

## What I Need From You

1. **Neo4j credentials** — to inspect the live Chapter 24 graph and verify the concept layer before building integration queries
2. **Confirmation on namespace strategy** — `OpalockaDocument` / `OpalockaEntity` prefix, or a different convention?
3. **Priority call:** Do all water/sewer chapters of Opa-locka, or start with the one chapter most comparable to Chapter 24?
