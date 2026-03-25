# Legal PDF Chunking Dashboard

A purpose-built tool for ingesting legal PDFs, extracting structured content using IBM Docling v2, chunking by legal section hierarchy (not token count), optionally enriching with LLM-generated context prefixes, and pushing the result into a Neo4j knowledge graph with typed entity extraction.

Built for regulatory compliance documents — currently targeting Miami-Dade Chapter 24 and Opa-Locka municipal code.

## What This Does

Upload a legal PDF → the system extracts text with ML models → parses the legal hierarchy (Chapter → Article → Division → Section) → creates one chunk per section/subsection regardless of size → optionally adds LLM context prefixes → pushes everything to Neo4j as a knowledge graph with entities (thresholds, penalties, roles, standards, obligations) and cross-reference edges.

```
PDF Upload ──► Docling Extraction ──► Section-Based Chunking ──► [LLM Enrichment] ──► Neo4j Graph
                (10-page batches)     (one chunk = one section)    (optional)         (FEA schema)
```

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  Frontend (Next.js 14 · port 3080)                               │
│  4 tabs: Upload & Analyze │ Chunks Explorer │ Neo4j │ Activity   │
└───────────────────────────────┬──────────────────────────────────┘
                                │ REST API
┌───────────────────────────────▼──────────────────────────────────┐
│  Backend (FastAPI · port 8000)                                    │
│  extraction.py → chunker.py → enrichment.py → neo4j_service.py  │
└──────────┬──────────────────────────────┬────────────────────────┘
           │                              │
     ┌─────▼─────┐                 ┌──────▼──────┐
     │  /data     │                 │  Neo4j 5    │
     │  (SQLite + │                 │  (port 7474 │
     │   JSON)    │                 │   + 7687)   │
     └────────────┘                 └─────────────┘
```

### Services

| Service | Port | Purpose |
|---------|------|---------|
| backend | 8000 | FastAPI — PDF processing, chunking, Neo4j operations |
| frontend | 3080 | Next.js — Dashboard UI |
| neo4j | 7474 (browser), 7687 (bolt) | Graph database (optional, runs via Docker profile) |

## Quick Start

### Prerequisites

- Docker and Docker Compose installed
- At least 4 GB free disk space (Docling ML models are ~1 GB, downloaded at build time)
- (Optional) An OpenRouter API key if you want LLM enrichment

### 1. Clone and configure

```bash
cd APAS-Legal-PDF-Chunking-Dashboard
cp .env.example .env
```

Edit `.env`:

```env
# Export directory — where chunk exports land on the host filesystem
# Set this to any absolute path on your machine
EXPORT_PATH=~/open-webui-regos/chunks

# Neo4j mode: "internal" bundles Neo4j in Docker, "external" connects to your own instance
NEO4J_MODE=internal
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=changeme123

# LLM enrichment (optional — leave blank to skip)
OPENROUTER_API_KEY=
LLM_MODEL=openai/gpt-4o-mini
LLM_BASE_URL=https://openrouter.ai/api/v1
```

### 2. Build and run

There are three modes. **The Neo4j service is behind a Docker Compose profile** — it does NOT start by default. You must explicitly enable it with `--profile neo4j-internal`.

**Mode 1: With bundled Neo4j (recommended for first run):**

```bash
docker compose --profile neo4j-internal up -d --build
```

> **IMPORTANT:** The `--profile neo4j-internal` flag is REQUIRED to start the bundled Neo4j container. Without it, the Neo4j tab in the dashboard will show "Cannot resolve address neo4j:7687" because the Neo4j service is not running. This is by design — the profile keeps Neo4j optional for users who only need extraction and chunking.

**Mode 2: Without Neo4j (extraction, chunking, and export only):**

```bash
docker compose up -d --build
```

In this mode the Neo4j tab will not work. Upload, chunking, LLM enrichment, and chunk export all work fine.

**Mode 3: With an external Neo4j instance:**

Set `NEO4J_MODE=external` and `NEO4J_URI=bolt://your-host:7687` in `.env`, then:

```bash
docker compose up -d --build
```

Do NOT use `--profile neo4j-internal` — you don't want two Neo4j instances.

### 3. Open the dashboard

- Dashboard: [http://localhost:3080](http://localhost:3080)
- API docs: [http://localhost:8000/docs](http://localhost:8000/docs)
- Neo4j Browser: [http://localhost:7474](http://localhost:7474) (only if using `--profile neo4j-internal`)

### 4. Upload a PDF

Open the dashboard, drag-and-drop a legal PDF, optionally toggle LLM enrichment, and click Upload. The progress bar will show each stage: extraction → chunking → enrichment → done.

### 5. Export chunks

After processing, go to the **Chunks Explorer** tab. You have three options:

- **"Export to Disk"** — copies `chunks.json`, `stats.json`, and `state.json` to the host directory set by `EXPORT_PATH` in `.env` (default: `./exports`)
- **"Download JSON"** — browser file download of `chunks.json`
- **"Push to Neo4j"** — creates a knowledge graph in Neo4j (requires Neo4j to be running)

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `EXPORT_PATH` | `./exports` | Host directory where chunk exports are saved. Mounted as `/data/exports` inside the backend container. Set to any path on your machine (e.g., `~/open-webui-regos/chunks`) |
| `NEO4J_MODE` | `external` | `internal` = bundled Neo4j container (requires `--profile neo4j-internal`), `external` = connect to your own |
| `NEO4J_URI` | `bolt://host.docker.internal:7687` | Bolt connection URI. Use `bolt://neo4j:7687` for internal mode |
| `NEO4J_USER` | `neo4j` | Neo4j username |
| `NEO4J_PASSWORD` | `neo4j` | Neo4j password. **Change this** — Neo4j rejects the default "neo4j" password |
| `OPENROUTER_API_KEY` | (empty) | OpenRouter API key for LLM enrichment. Leave blank to skip enrichment |
| `LLM_MODEL` | `openai/gpt-4o-mini` | Model to use via OpenRouter |
| `LLM_BASE_URL` | `https://openrouter.ai/api/v1` | OpenAI-compatible API endpoint |

## The 4-Stage Pipeline

### Stage 1: Extraction (Docling v2)

Uses IBM Docling's ML-powered document converter for structured PDF parsing. Unlike simple text extractors (PyPDF, pdfminer), Docling understands document layout — it identifies headings, tables, lists, and body text as distinct element types.

**Batched processing:** Large PDFs are split into 10-page batches and processed sequentially. This prevents memory issues on 800+ page documents and allows progress reporting after each batch. Each batch returns elements with type, text content, and page number.

**Table handling:** Docling returns table objects with rich internal structure (cells, bounding boxes, grid positions). The extraction layer converts these to clean markdown tables instead of raw Python repr strings. It tries four methods in order: `export_to_markdown()`, grid-based extraction, cell list extraction, and fallback to `.text`.

### Stage 2: Section-Based Chunking

This is where the tool differs from generic chunkers. Standard RAG chunkers split by token count (e.g., 512 tokens per chunk). This chunker splits by **legal hierarchy**.

**Hierarchy detection:** Regex patterns identify structure markers:
- `Sec. 24-42`, `§ 24-42.6`, `Section 24-42`
- `Chapter 24`, `Article I`, `Division 2`

**One chunk = one section.** A 50-token definitions section stays as one chunk. A 5,000-token regulatory section stays as one chunk. Legal meaning is never split across chunk boundaries.

**Metadata per chunk:**
- Breadcrumb path: `Chapter 24 > Article 1 > Division 2 > Sec. 24-42`
- Content type: `prose`, `definition`, `table`, `list`, `reserved`, `fee_schedule`, `technical`
- Token count (tiktoken, cl100k_base encoding)
- Cross-references: extracted `§24-42.6` style references
- FEA Layer 3 entities: thresholds (`mg/L`, `%`, `feet`), penalties (`$` amounts), roles (`Director`, `Board`), standards (`CFR`, `ANSI`), obligations (`shall`, `must` patterns)
- Ordinance citations, dates, dollar amounts

### Stage 3: LLM Enrichment (Optional)

Implements Summary-Augmented Chunking (SAC) from [arXiv:2510.06999](https://arxiv.org/abs/2510.06999). For each chunk, an LLM generates a 1-2 sentence context prefix explaining where the chunk fits in the overall document. This improves downstream retrieval accuracy because the chunk carries its own context.

Uses OpenRouter (OpenAI-compatible API) with GPT-4o-mini by default. Costs approximately $0.16 for a 300-chunk document.

**Skipped entirely** if `OPENROUTER_API_KEY` is not set. The toggle in the UI also lets users skip it per upload.

### Stage 4: Neo4j Knowledge Graph

Pushes chunks into a typed graph following the Fixed Entity Architecture (FEA):

**Node types:**
- `Document` — the uploaded PDF (name, jurisdiction, chunk count)
- `Section` — legal sections with hierarchy (chapter, article, division, number, title)
- `Chunk` — individual content chunks (text, breadcrumb, content type, token count, page range)
- `Threshold` — regulatory limits (value, unit, parameter, direction)
- `Penalty` — monetary penalties (amount, context)
- `Role` — mentioned roles (Director, Board, Applicant, etc.)
- `Standard` — referenced standards (CFR, ANSI, etc.)
- `Obligation` — regulatory obligations (shall, must patterns)

**Relationships:**
- `Chunk → BELONGS_TO → Document`
- `Chunk → PART_OF → Section`
- `Section → PART_OF → Section` (subsection → parent)
- `Chunk → REFERENCES → Chunk` (cross-reference edges from §-citations)
- `Chunk → HAS_THRESHOLD → Threshold`
- `Chunk → HAS_PENALTY → Penalty`
- `Chunk → MENTIONS_ROLE → Role`
- `Chunk → CITES_STANDARD → Standard`
- `Chunk → CONTAINS_OBLIGATION → Obligation`

**Indexes and constraints:** Unique constraints on Document.id, Section.id, Chunk.chunk_id, Role.name. Fulltext index on chunk text and breadcrumb for search.

## Dashboard Tabs

### Tab 1: Upload & Analyze

Drag-drop PDF upload with optional LLM enrichment toggle. Shows real-time progress across extraction, chunking, and enrichment stages. After processing, displays a stats dashboard with 7 summary cards (pages, sections, subsections, definitions, tables, cross-refs, chunks), token distribution bar chart, content type breakdown pie chart, and an expandable document structure tree.

### Tab 2: Chunks Explorer

Browse all chunks with search and content-type filtering. Each chunk card shows breadcrumb path, content type badge, token count, page range, and expandable full text. Three action buttons: "Push to Neo4j" (creates knowledge graph), "Export to Disk" (copies chunks to `EXPORT_PATH` on host), and "Download JSON" (browser file download).

### Tab 3: Neo4j

Live connection status indicator with node/relationship counts. Cypher query editor with quick-action buttons for common queries (node counts, relationship types, top cross-referenced sections, all roles, penalty amounts). Results displayed in a table. Read-only safety — the backend validates queries and only allows `MATCH`/`RETURN`/`CALL`/`WITH` statements.

### Tab 4: Activity Log

Table of all uploads and pushes with filename, timestamp, page count, chunk count, enrichment status, Neo4j push status, processing duration, and completion status.

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/upload` | Upload PDF and start processing (form: file + enrich boolean) |
| `GET` | `/jobs` | List all processing jobs |
| `GET` | `/jobs/{id}` | Get job state and progress |
| `GET` | `/jobs/{id}/stats` | Get computed statistics |
| `GET` | `/jobs/{id}/chunks` | Paginated chunks (params: page, page_size, content_type, search) |
| `GET` | `/jobs/{id}/tree` | Hierarchical document structure tree |
| `POST` | `/jobs/{id}/export` | Export chunks + stats to host `EXPORT_PATH` directory |
| `GET` | `/jobs/{id}/download` | Download `chunks.json` as a file |
| `GET` | `/export-dir` | Returns the current export directory path |
| `POST` | `/jobs/{id}/push` | Push chunks to Neo4j knowledge graph |
| `DELETE` | `/jobs/{id}/neo4j` | Clear Neo4j data for a job |
| `GET` | `/neo4j/status` | Neo4j connection status and counts |
| `POST` | `/neo4j/query` | Execute read-only Cypher query |
| `GET` | `/logs` | Activity log |
| `GET` | `/health` | Health check |

Full interactive API docs at [http://localhost:8000/docs](http://localhost:8000/docs).

## Project Structure

```
legal-chunking-dashboard/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI app, all routes, job orchestration
│   │   ├── models/
│   │   │   └── chunk.py             # Pydantic models (ChunkMetadata, JobState, etc.)
│   │   └── services/
│   │       ├── extraction.py        # Docling batched PDF extraction + table handling
│   │       ├── chunker.py           # Hierarchical section-based chunking + FEA entity extraction
│   │       ├── enrichment.py        # OpenRouter LLM contextual prefix generation
│   │       ├── neo4j_service.py     # Neo4j graph operations (push, query, status)
│   │       └── logger.py            # SQLite activity logging
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx             # Main 4-tab dashboard SPA
│   │   │   ├── layout.tsx           # Root layout
│   │   │   └── globals.css          # Tailwind + custom dark theme
│   │   └── lib/
│   │       └── api.ts               # Backend API client
│   ├── package.json
│   ├── Dockerfile
│   ├── next.config.js
│   └── tailwind.config.js
├── docker-compose.yml               # 3 services: backend, frontend, neo4j (profile)
├── .env.example                     # Environment variable template
└── README.md                        # This file
```

## Data Storage

All processing data persists in a Docker volume mounted at `/data` inside the backend container:

```
/data/
├── jobs/
│   └── {job_id}/
│       ├── state.json               # Job status, progress, timestamps
│       ├── chunks.json              # All extracted chunks with metadata
│       ├── stats.json               # Computed statistics
│       └── docling_extraction.json  # Raw Docling output (for debugging)
├── exports/                         # Host-mounted via EXPORT_PATH
│   └── {document_name}_{job_id}/
│       ├── chunks.json              # Exported chunks
│       ├── stats.json               # Exported stats
│       └── state.json               # Exported job state
└── activity.db                      # SQLite activity log
```

The `exports/` directory is mounted to the host at whatever path `EXPORT_PATH` is set to in `.env`. Files written here are immediately accessible on the host filesystem without needing to `docker cp` them out.

Data survives container restarts. To fully reset, remove the Docker volume:

```bash
docker compose down -v
```

## Common Operations

### Rebuild after code changes

```bash
docker compose build --no-cache backend
docker compose --profile neo4j-internal up -d
```

### View backend logs

```bash
docker compose logs -f backend
```

### Reset Neo4j data

```bash
# Option 1: Clear via API (per job)
curl -X DELETE http://localhost:8000/jobs/{job_id}/neo4j

# Option 2: Nuclear — delete everything and start fresh
docker compose --profile neo4j-internal down -v
docker compose --profile neo4j-internal up -d
```

### Run without Docker (development)

**Backend:**
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

Note: Docling downloads ~1 GB of ML models on first run. This happens at Docker build time in the Dockerfile, but will happen at runtime if running natively.

## Supported Jurisdictions

Jurisdiction is auto-detected from the filename:

| Filename contains | Detected as |
|-------------------|-------------|
| `opa`, `locka` | Opa-Locka, FL |
| `chapter 24`, `ch24` | Miami-Dade County, FL (Chapter 24) |
| (anything else) | Generic |

The chunker adapts its hierarchy parsing based on jurisdiction — different codes use different section numbering schemes.

## Cost Estimates (LLM Enrichment)

Using GPT-4o-mini via OpenRouter:

| Document Size | Chunks | Estimated Cost |
|---------------|--------|----------------|
| 50 pages | ~80 chunks | ~$0.04 |
| 200 pages | ~150 chunks | ~$0.08 |
| 500 pages | ~250 chunks | ~$0.13 |
| 842 pages (Opa-Locka Code) | ~400 chunks | ~$0.21 |

Each enrichment call sends ~600 input tokens and receives ~70 output tokens.

## Troubleshooting

**Neo4j rejects password "neo4j":**
Neo4j doesn't allow the default password. Set a different password in `.env` (e.g., `changeme123`) and delete the old volume:
```bash
docker compose --profile neo4j-internal down -v
docker compose --profile neo4j-internal up -d
```

**Docling extraction is slow:**
First run downloads ~1 GB of ML models. Subsequent runs are faster. For 800+ page documents, expect 15-30 minutes — the 10-page batching shows progress so you know it's working.

**Frontend can't reach backend:**
Check that `NEXT_PUBLIC_API_URL` is set to `http://localhost:8000`. If running in Docker, the frontend container talks to the backend via the Docker network, but the browser needs to reach the backend via localhost.

**Neo4j connection fails in internal mode:**
Make sure `NEO4J_URI=bolt://neo4j:7687` (not `host.docker.internal`) when using `NEO4J_MODE=internal`. The `neo4j` hostname resolves inside the Docker network.

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.11, FastAPI 0.115, Uvicorn |
| PDF Extraction | IBM Docling 2.14 (ML-powered) |
| Token Counting | tiktoken (cl100k_base) |
| LLM | OpenRouter API (OpenAI-compatible) |
| Graph Database | Neo4j 5 Community (with APOC) |
| Frontend | Next.js 14, React 18, TailwindCSS 3 |
| Charts | Recharts 2.13 |
| Containerization | Docker Compose |
