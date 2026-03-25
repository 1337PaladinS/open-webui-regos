"""
Legal PDF Chunking Dashboard — FastAPI Backend
"""
import os
import json
import uuid
import time
import shutil
import threading
from pathlib import Path
from datetime import datetime, timezone

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.services import extraction, chunker, enrichment, neo4j_service, logger

app = FastAPI(title="Legal Chunking Dashboard API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_DIR = os.environ.get("DATA_DIR", "/data")
JOBS_DIR = os.path.join(DATA_DIR, "jobs")
EXPORT_DIR = os.environ.get("EXPORT_DIR", os.path.join(DATA_DIR, "exports"))
os.makedirs(JOBS_DIR, exist_ok=True)
os.makedirs(EXPORT_DIR, exist_ok=True)

# In-memory job state (persisted to disk as JSON)
jobs: dict = {}


def load_jobs():
    """Load persisted job states from disk."""
    global jobs
    for job_dir in Path(JOBS_DIR).iterdir():
        if job_dir.is_dir():
            state_file = job_dir / "state.json"
            if state_file.exists():
                with open(state_file) as f:
                    jobs[job_dir.name] = json.load(f)


def save_job(job_id: str):
    """Persist job state to disk."""
    job_dir = os.path.join(JOBS_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)
    with open(os.path.join(job_dir, "state.json"), "w") as f:
        json.dump(jobs[job_id], f, indent=2, default=str)


@app.on_event("startup")
async def startup():
    load_jobs()


# ─── Upload ─────────────────────────────────────────────────────────

def _log(job_id: str, msg: str, start_time: float):
    """Print timestamped log and store as status_detail for frontend polling."""
    elapsed = time.time() - start_time
    line = f"[{job_id}] {elapsed:6.1f}s | {msg}"
    print(line, flush=True)
    jobs[job_id]["status_detail"] = msg
    jobs[job_id]["elapsed_s"] = round(elapsed, 1)


def process_pdf(job_id: str, pdf_path: str, filename: str, enrich: bool):
    """Background worker: extract (batched Docling) → chunk → (optionally) enrich."""
    job_dir = os.path.join(JOBS_DIR, job_id)
    start_time = time.time()

    try:
        # Step 1: Extract with batched Docling
        jobs[job_id]["status"] = "extracting"
        jobs[job_id]["progress"] = 0.02
        _log(job_id, f"Starting Docling extraction for {filename}...", start_time)
        save_job(job_id)

        # Get page count for progress calculation
        total_page_count = extraction.get_page_count(pdf_path)
        _log(job_id, f"PDF has {total_page_count} pages", start_time)

        def log_cb(msg):
            _log(job_id, msg, start_time)
            # Parse batch progress from the message to update progress bar
            if "Batch " in msg and "/" in msg:
                try:
                    # Extract "Batch X/Y" to compute progress
                    parts = msg.split("Batch ")[1].split("/")
                    batch_num = int(parts[0])
                    total_batches = int(parts[1].split(" ")[0])
                    # Extraction is 0.02 to 0.50 of total progress
                    jobs[job_id]["progress"] = 0.02 + (batch_num / total_batches) * 0.48
                except Exception:
                    pass
            save_job(job_id)

        result = extraction.extract_pdf(pdf_path, job_dir, log_fn=log_cb)
        total_pages = result.get("total_pages", 0)

        jobs[job_id]["progress"] = 0.50
        _log(job_id, f"Extraction done: {total_pages} pages, {len(result.get('elements', []))} elements", start_time)
        save_job(job_id)

        # Step 2: Parse hierarchy & chunk
        jobs[job_id]["status"] = "chunking"
        jobs[job_id]["progress"] = 0.52
        _log(job_id, "Parsing document hierarchy...", start_time)
        save_job(job_id)

        elements = chunker.build_hierarchy_from_docling(result)

        _log(job_id, f"Found {len(elements)} elements, building chunks...", start_time)

        # Detect jurisdiction from filename
        fn_lower = filename.lower()
        if "opa" in fn_lower or "locka" in fn_lower:
            jurisdiction = "Opa-Locka, FL"
        elif "chapter 24" in fn_lower or "ch24" in fn_lower:
            jurisdiction = "Miami-Dade County, FL"
        else:
            jurisdiction = "Unknown"

        chunks = chunker.chunk_elements(
            elements, document_name=filename, jurisdiction=jurisdiction
        )

        jobs[job_id]["progress"] = 0.55
        _log(job_id, f"Created {len(chunks)} chunks (jurisdiction: {jurisdiction})", start_time)
        save_job(job_id)

        # Step 3: Enrich (optional)
        if enrich and os.environ.get("OPENROUTER_API_KEY"):
            jobs[job_id]["status"] = "enriching"
            jobs[job_id]["progress"] = 0.60
            _log(job_id, f"Starting LLM enrichment for {len(chunks)} chunks...", start_time)
            save_job(job_id)

            def enrich_progress(current, total):
                jobs[job_id]["progress"] = 0.60 + (current / total) * 0.30
                _log(job_id, f"Enriching chunk {current}/{total}...", start_time)
                if current % 5 == 0 or current == total:
                    save_job(job_id)

            chunks = enrichment.enrich_chunks(chunks, progress_callback=enrich_progress)
            _log(job_id, "Enrichment complete", start_time)
        elif enrich:
            _log(job_id, "Skipping enrichment: no OPENROUTER_API_KEY set", start_time)

        # Step 4: Compute stats & save
        jobs[job_id]["progress"] = 0.95
        _log(job_id, "Computing stats and saving results...", start_time)
        save_job(job_id)

        stats = chunker.compute_stats(chunks, total_pages)

        # Save chunks
        with open(os.path.join(job_dir, "chunks.json"), "w") as f:
            json.dump(chunks, f, indent=2, default=str)

        # Save stats
        with open(os.path.join(job_dir, "stats.json"), "w") as f:
            json.dump(stats, f, indent=2)

        duration = time.time() - start_time

        jobs[job_id]["status"] = "done"
        jobs[job_id]["progress"] = 1.0
        jobs[job_id]["stats"] = stats
        jobs[job_id]["chunk_count"] = len(chunks)
        jobs[job_id]["page_count"] = total_pages
        jobs[job_id]["duration"] = round(duration, 2)
        _log(job_id, f"DONE in {duration:.1f}s — {len(chunks)} chunks, {total_pages} pages", start_time)
        save_job(job_id)

        # Update log
        logger.update_log_entry(
            job_id,
            page_count=total_pages,
            chunk_count=len(chunks),
            processing_duration_s=round(duration, 2),
            status="done",
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        duration = time.time() - start_time
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(e)
        _log(job_id, f"ERROR: {e}", start_time)
        save_job(job_id)
        logger.update_log_entry(
            job_id,
            processing_duration_s=round(duration, 2),
            status="error",
            error_message=str(e),
        )


@app.post("/upload")
async def upload_pdf(
    file: UploadFile = File(...),
    enrich: bool = Form(default=True),
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are accepted")

    job_id = str(uuid.uuid4())[:8]
    job_dir = os.path.join(JOBS_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)

    # Save uploaded file
    pdf_path = os.path.join(job_dir, file.filename)
    with open(pdf_path, "wb") as f:
        content = await file.read()
        f.write(content)

    # Initialize job state
    jobs[job_id] = {
        "job_id": job_id,
        "filename": file.filename,
        "status": "pending",
        "progress": 0.0,
        "upload_time": datetime.now(timezone.utc).isoformat(),
        "pdf_path": pdf_path,
        "enrich": enrich,
        "stats": None,
        "chunk_count": 0,
        "page_count": 0,
        "error": None,
        "pushed_to_neo4j": False,
    }
    save_job(job_id)

    # Create log entry
    logger.create_log_entry(job_id, file.filename, enrichment_enabled=enrich)

    # Start background processing
    thread = threading.Thread(
        target=process_pdf,
        args=(job_id, pdf_path, file.filename, enrich),
        daemon=True,
    )
    thread.start()

    return {"job_id": job_id, "status": "pending", "filename": file.filename}


# ─── Jobs ───────────────────────────────────────────────────────────

@app.get("/jobs")
async def list_jobs():
    return list(jobs.values())


@app.get("/jobs/{job_id}")
async def get_job(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")
    return jobs[job_id]


@app.get("/jobs/{job_id}/stats")
async def get_job_stats(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")
    job = jobs[job_id]
    if job["status"] != "done":
        return {"status": job["status"], "progress": job["progress"]}

    stats_file = os.path.join(JOBS_DIR, job_id, "stats.json")
    if os.path.exists(stats_file):
        with open(stats_file) as f:
            return json.load(f)
    return job.get("stats", {})


@app.get("/jobs/{job_id}/chunks")
async def get_job_chunks(
    job_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    content_type: str = Query(None),
    search: str = Query(None),
):
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")

    chunks_file = os.path.join(JOBS_DIR, job_id, "chunks.json")
    if not os.path.exists(chunks_file):
        raise HTTPException(404, "Chunks not yet available")

    with open(chunks_file) as f:
        all_chunks = json.load(f)

    # Filter
    filtered = all_chunks
    if content_type:
        filtered = [c for c in filtered if c["metadata"]["content_type"] == content_type]
    if search:
        search_lower = search.lower()
        filtered = [
            c for c in filtered
            if search_lower in c["text"].lower()
            or search_lower in c["metadata"]["breadcrumb"].lower()
        ]

    # Paginate
    total = len(filtered)
    start = (page - 1) * page_size
    end = start + page_size
    page_chunks = filtered[start:end]

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "chunks": page_chunks,
    }


@app.get("/jobs/{job_id}/tree")
async def get_hierarchy_tree(job_id: str):
    """Return the full hierarchy tree for the tree view component."""
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")

    chunks_file = os.path.join(JOBS_DIR, job_id, "chunks.json")
    if not os.path.exists(chunks_file):
        raise HTTPException(404, "Chunks not yet available")

    with open(chunks_file) as f:
        all_chunks = json.load(f)

    # Build nested tree
    tree = {}
    for chunk in all_chunks:
        h = chunk["metadata"]["hierarchy"]
        ch = h.get("chapter", "") or "Unknown"
        art = h.get("article", "")
        div = h.get("division", "")
        sec = h.get("section", "")
        title = h.get("section_title", "")

        if ch not in tree:
            tree[ch] = {"children": {}, "chunk_count": 0}
        tree[ch]["chunk_count"] += 1

        if art:
            if art not in tree[ch]["children"]:
                tree[ch]["children"][art] = {"children": {}, "chunk_count": 0}
            tree[ch]["children"][art]["chunk_count"] += 1

            if div:
                if div not in tree[ch]["children"][art]["children"]:
                    tree[ch]["children"][art]["children"][div] = {"children": {}, "chunk_count": 0}
                tree[ch]["children"][art]["children"][div]["chunk_count"] += 1

                if sec:
                    label = f"{sec} {title}".strip()
                    tree[ch]["children"][art]["children"][div]["children"][label] = {
                        "chunk_count": 1,
                        "content_type": chunk["metadata"]["content_type"],
                        "token_count": chunk["metadata"]["token_count"],
                    }
            elif sec:
                label = f"{sec} {title}".strip()
                tree[ch]["children"][art]["children"][label] = {
                    "chunk_count": 1,
                    "content_type": chunk["metadata"]["content_type"],
                    "token_count": chunk["metadata"]["token_count"],
                }

    return tree


# ─── Export ─────────────────────────────────────────────────────────

@app.post("/jobs/{job_id}/export")
async def export_chunks(job_id: str):
    """Export chunks + stats to the host-mounted EXPORT_DIR."""
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")
    if jobs[job_id]["status"] != "done":
        raise HTTPException(400, "Job not complete yet")

    job_dir = os.path.join(JOBS_DIR, job_id)
    chunks_file = os.path.join(job_dir, "chunks.json")
    stats_file = os.path.join(job_dir, "stats.json")

    if not os.path.exists(chunks_file):
        raise HTTPException(404, "Chunks not available")

    # Create export directory named after the source document
    safe_name = jobs[job_id]["filename"].rsplit(".", 1)[0]
    safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in safe_name).strip()
    export_subdir = os.path.join(EXPORT_DIR, f"{safe_name}_{job_id}")
    os.makedirs(export_subdir, exist_ok=True)

    # Copy chunks and stats
    exported_files = []
    for src_name in ["chunks.json", "stats.json", "state.json"]:
        src = os.path.join(job_dir, src_name)
        if os.path.exists(src):
            dst = os.path.join(export_subdir, src_name)
            shutil.copy2(src, dst)
            exported_files.append(src_name)

    # Also copy the docling extraction if available
    docling_file = os.path.join(job_dir, "docling_extraction.json")
    if os.path.exists(docling_file):
        shutil.copy2(docling_file, os.path.join(export_subdir, "docling_extraction.json"))
        exported_files.append("docling_extraction.json")

    # Update job state
    jobs[job_id]["exported"] = True
    jobs[job_id]["export_path"] = export_subdir
    save_job(job_id)

    return {
        "success": True,
        "export_path": export_subdir,
        "files": exported_files,
        "chunk_count": jobs[job_id].get("chunk_count", 0),
    }


@app.get("/jobs/{job_id}/download")
async def download_chunks(job_id: str):
    """Download chunks.json directly as a file response."""
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")

    chunks_file = os.path.join(JOBS_DIR, job_id, "chunks.json")
    if not os.path.exists(chunks_file):
        raise HTTPException(404, "Chunks not available")

    from fastapi.responses import FileResponse
    safe_name = jobs[job_id]["filename"].rsplit(".", 1)[0]
    return FileResponse(
        chunks_file,
        media_type="application/json",
        filename=f"{safe_name}_chunks.json",
    )


@app.get("/export-dir")
async def get_export_dir():
    """Return the current export directory path (for display in frontend)."""
    return {"export_dir": EXPORT_DIR}


# ─── Neo4j ──────────────────────────────────────────────────────────

@app.get("/neo4j/status")
async def neo4j_status():
    return neo4j_service.check_connection()


@app.post("/jobs/{job_id}/push")
async def push_to_neo4j(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")
    if jobs[job_id]["status"] != "done":
        raise HTTPException(400, "Job not complete yet")

    chunks_file = os.path.join(JOBS_DIR, job_id, "chunks.json")
    if not os.path.exists(chunks_file):
        raise HTTPException(404, "Chunks not available")

    with open(chunks_file) as f:
        all_chunks = json.load(f)

    job = jobs[job_id]
    jobs[job_id]["status"] = "pushing"
    save_job(job_id)

    try:
        # Detect jurisdiction
        fn_lower = job["filename"].lower()
        if "opa" in fn_lower or "locka" in fn_lower:
            jurisdiction = "Opa-Locka_FL"
        elif "chapter 24" in fn_lower or "ch24" in fn_lower:
            jurisdiction = "Miami-Dade_FL"
        else:
            jurisdiction = "Unknown"

        stats = neo4j_service.push_chunks_to_neo4j(
            chunks=all_chunks,
            document_name=job["filename"],
            jurisdiction=jurisdiction,
            job_id=job_id,
        )

        jobs[job_id]["status"] = "done"
        jobs[job_id]["pushed_to_neo4j"] = True
        jobs[job_id]["neo4j_stats"] = stats
        save_job(job_id)

        logger.mark_pushed(job_id)

        return {"success": True, "stats": stats}

    except Exception as e:
        jobs[job_id]["status"] = "done"  # Revert to done (push failed but chunks exist)
        jobs[job_id]["push_error"] = str(e)
        save_job(job_id)
        raise HTTPException(500, f"Neo4j push failed: {e}")


@app.post("/neo4j/query")
async def run_cypher_query(body: dict):
    query = body.get("query", "")
    if not query:
        raise HTTPException(400, "No query provided")
    # Safety: only allow read queries
    q_upper = query.strip().upper()
    if not q_upper.startswith(("MATCH", "RETURN", "CALL", "WITH")):
        raise HTTPException(400, "Only read queries are allowed (MATCH, RETURN, CALL, WITH)")
    try:
        results = neo4j_service.run_cypher(query)
        # Serialize Neo4j types
        serialized = []
        for r in results:
            row = {}
            for k, v in r.items():
                if hasattr(v, "__dict__"):
                    row[k] = str(v)
                else:
                    row[k] = v
            serialized.append(row)
        return {"results": serialized}
    except Exception as e:
        raise HTTPException(500, f"Query failed: {e}")


@app.delete("/jobs/{job_id}/neo4j")
async def clear_neo4j_data(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")
    try:
        neo4j_service.clear_document(job_id)
        jobs[job_id]["pushed_to_neo4j"] = False
        save_job(job_id)
        return {"success": True}
    except Exception as e:
        raise HTTPException(500, f"Clear failed: {e}")


# ─── Logs ───────────────────────────────────────────────────────────

@app.get("/logs")
async def get_logs():
    return logger.get_all_logs()


# ─── Health ─────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}
