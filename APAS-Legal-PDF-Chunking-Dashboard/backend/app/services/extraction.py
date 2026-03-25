"""
PDF extraction service using batched Docling.

Strategy: Split large PDFs into small batches, run Docling on each batch,
report progress after every batch. No more 30-minute black holes.
"""
import os
import json
import subprocess
import time
import tempfile
from pathlib import Path

from pypdf import PdfReader, PdfWriter

# How many pages per Docling batch. Smaller = more frequent progress updates.
# 10 pages is a good balance between progress granularity and overhead.
DEFAULT_BATCH_SIZE = 10

DOCLING_TYPE_MAP = {
    "sectionheaderitem": "section_header",
    "textitem": "text",
    "listitem": "list_item",
    "tableitem": "table",
    "captionitem": "caption",
    "footnoteitem": "footnote",
    "pageheaderitem": "page_header",
    "pagefooteritem": "page_footer",
    "titleitem": "title",
}


def _extract_table_text(element_obj) -> str:
    """
    Convert a Docling TableItem into a clean markdown table.
    Falls back to export_to_markdown() if available, otherwise manually
    builds a table from the TableData grid.
    """
    # Try Docling's built-in markdown export first
    if hasattr(element_obj, "export_to_markdown"):
        try:
            md = element_obj.export_to_markdown()
            if md and md.strip():
                return md.strip()
        except Exception:
            pass

    # Manual extraction from TableData
    if hasattr(element_obj, "data") and element_obj.data is not None:
        data = element_obj.data
        num_rows = getattr(data, "num_rows", 0)
        num_cols = getattr(data, "num_cols", 0)
        grid = getattr(data, "grid", None)

        if grid and num_rows > 0 and num_cols > 0:
            rows = []
            for row_idx in range(num_rows):
                row_cells = []
                for col_idx in range(num_cols):
                    try:
                        cell = grid[row_idx][col_idx]
                        cell_text = getattr(cell, "text", "").strip()
                        row_cells.append(cell_text)
                    except (IndexError, AttributeError):
                        row_cells.append("")
                rows.append(row_cells)

            if rows:
                lines = []
                # Header row
                lines.append("| " + " | ".join(rows[0]) + " |")
                lines.append("| " + " | ".join(["---"] * num_cols) + " |")
                # Data rows
                for row in rows[1:]:
                    lines.append("| " + " | ".join(row) + " |")
                return "\n".join(lines)

        # Fallback: extract from table_cells list
        cells = getattr(data, "table_cells", [])
        if cells:
            # Group cells by row
            row_map = {}
            for cell in cells:
                row_idx = getattr(cell, "start_row_offset_idx", 0)
                col_idx = getattr(cell, "start_col_offset_idx", 0)
                cell_text = getattr(cell, "text", "").strip()
                if row_idx not in row_map:
                    row_map[row_idx] = {}
                row_map[row_idx][col_idx] = cell_text

            if row_map:
                max_col = max(max(cols.keys()) for cols in row_map.values()) + 1
                lines = []
                for row_idx in sorted(row_map.keys()):
                    row_cells = [row_map[row_idx].get(c, "") for c in range(max_col)]
                    lines.append("| " + " | ".join(row_cells) + " |")
                    if row_idx == min(row_map.keys()):
                        lines.append("| " + " | ".join(["---"] * max_col) + " |")
                return "\n".join(lines)

    return ""


def _get_element_text(element_obj) -> str:
    """
    Extract clean text from any Docling element.
    Handles tables specially to avoid dumping raw Python objects.
    """
    label = type(element_obj).__name__.lower()

    # Tables need special handling
    if label == "tableitem":
        table_text = _extract_table_text(element_obj)
        if table_text:
            return table_text
        # If table extraction failed, try .text
        if hasattr(element_obj, "text") and element_obj.text and element_obj.text.strip():
            return element_obj.text.strip()
        # Last resort — don't use str() which dumps the raw repr
        return "[Table could not be extracted]"

    # For all other elements, use .text
    if hasattr(element_obj, "text") and element_obj.text:
        return element_obj.text

    return ""


def get_page_count(pdf_path: str) -> int:
    """Quick page count using pypdf (no subprocess needed)."""
    try:
        reader = PdfReader(pdf_path)
        return len(reader.pages)
    except Exception:
        pass
    # Fallback to pdfinfo
    try:
        result = subprocess.run(
            ["pdfinfo", pdf_path],
            capture_output=True, text=True, timeout=30,
        )
        for line in result.stdout.split("\n"):
            if line.startswith("Pages:"):
                return int(line.split(":")[1].strip())
    except Exception:
        pass
    return 0


def split_pdf(pdf_path: str, output_dir: str, batch_size: int = DEFAULT_BATCH_SIZE) -> list[dict]:
    """
    Split a PDF into batches of N pages.
    Returns list of {path, start_page, end_page, page_count}.
    """
    reader = PdfReader(pdf_path)
    total = len(reader.pages)
    batches = []

    for start in range(0, total, batch_size):
        end = min(start + batch_size, total)
        writer = PdfWriter()
        for i in range(start, end):
            writer.add_page(reader.pages[i])

        batch_path = os.path.join(output_dir, f"batch_{start+1}_{end}.pdf")
        with open(batch_path, "wb") as f:
            writer.write(f)

        batches.append({
            "path": batch_path,
            "start_page": start + 1,  # 1-indexed
            "end_page": end,
            "page_count": end - start,
        })

    return batches


def extract_batch_with_docling(batch_path: str, page_offset: int, converter) -> list[dict]:
    """
    Run Docling on a single batch PDF.
    Returns list of elements with page numbers adjusted to absolute position.
    """
    result = converter.convert(batch_path)
    doc = result.document
    elements = []

    for item in doc.iterate_items():
        element_obj, _level = item if isinstance(item, tuple) else (item, 0)

        text = _get_element_text(element_obj)
        if not text or not text.strip():
            continue

        label = type(element_obj).__name__.lower()
        etype = DOCLING_TYPE_MAP.get(label, "text")

        page = 0
        if hasattr(element_obj, "prov") and element_obj.prov:
            page = element_obj.prov[0].page_no if hasattr(element_obj.prov[0], "page_no") else 0

        # Adjust page number to absolute position in the full document
        elements.append({
            "type": etype,
            "text": text,
            "page": page + page_offset,
        })

    return elements


def extract_pdf(pdf_path: str, output_dir: str, log_fn=None, batch_size: int = DEFAULT_BATCH_SIZE) -> dict:
    """
    Main extraction entry point.
    Splits the PDF into batches and processes each through Docling,
    reporting progress after every batch.
    """
    # Step 1: Get total page count (instant)
    total_pages = get_page_count(pdf_path)
    if log_fn:
        log_fn(f"PDF has {total_pages} pages — splitting into batches of {batch_size}...")

    # Step 2: Split into batches
    batch_dir = os.path.join(output_dir, "batches")
    os.makedirs(batch_dir, exist_ok=True)

    try:
        batches = split_pdf(pdf_path, batch_dir, batch_size)
    except Exception as e:
        if log_fn:
            log_fn(f"PDF split failed: {e} — trying single-pass Docling...")
        return _extract_single_pass(pdf_path, output_dir, total_pages, log_fn)

    num_batches = len(batches)
    if log_fn:
        log_fn(f"Split into {num_batches} batches, loading Docling...")

    # Step 3: Initialize Docling converter once (reuse across batches)
    # This is where models get downloaded on first run — can take minutes
    if log_fn:
        log_fn("Importing Docling (first run downloads ~1GB of ML models, please wait)...")

    import threading

    heartbeat_stop = threading.Event()

    def heartbeat():
        """Print a heartbeat every 10s so you know it's not dead."""
        count = 0
        while not heartbeat_stop.is_set():
            heartbeat_stop.wait(10)
            if not heartbeat_stop.is_set():
                count += 1
                if log_fn:
                    log_fn(f"Still loading Docling models... ({count * 10}s)")

    hb_thread = threading.Thread(target=heartbeat, daemon=True)
    hb_thread.start()

    try:
        from docling.document_converter import DocumentConverter
        if log_fn:
            log_fn("Docling imported, initializing converter...")
        converter = DocumentConverter()
    except Exception as e:
        heartbeat_stop.set()
        if log_fn:
            log_fn(f"Docling failed: {e}")
        raise RuntimeError(f"Docling not available: {e}")
    finally:
        heartbeat_stop.set()
        hb_thread.join(timeout=1)

    if log_fn:
        log_fn(f"Docling ready, processing batch 1/{num_batches}...")

    # Step 4: Process each batch
    all_elements = []
    batch_start_time = time.time()

    for i, batch in enumerate(batches):
        batch_num = i + 1
        if log_fn:
            log_fn(f"Processing batch {batch_num}/{num_batches} (pages {batch['start_page']}-{batch['end_page']})...")
        try:
            page_offset = batch["start_page"] - 1  # Docling uses 0-based internally
            elements = extract_batch_with_docling(batch["path"], page_offset, converter)
            all_elements.extend(elements)

            elapsed = time.time() - batch_start_time
            pages_done = batch["end_page"]
            pages_per_sec = pages_done / elapsed if elapsed > 0 else 0
            remaining = (total_pages - pages_done) / pages_per_sec if pages_per_sec > 0 else 0

            if log_fn:
                log_fn(
                    f"Batch {batch_num}/{num_batches} done — "
                    f"pages {batch['start_page']}-{batch['end_page']} — "
                    f"{len(elements)} elements — "
                    f"{pages_per_sec:.1f} pages/s — "
                    f"~{remaining:.0f}s remaining"
                )

        except Exception as e:
            if log_fn:
                log_fn(f"Batch {batch_num} failed (pages {batch['start_page']}-{batch['end_page']}): {e} — skipping")
            print(f"Batch {batch_num} failed: {e}", flush=True)
            continue

        # Clean up batch file to save disk
        try:
            os.remove(batch["path"])
        except Exception:
            pass

    if log_fn:
        total_elapsed = time.time() - batch_start_time
        log_fn(f"Docling complete: {len(all_elements)} elements from {total_pages} pages in {total_elapsed:.0f}s")

    # Step 5: Save extraction result
    output_path = os.path.join(output_dir, "docling_extraction.json")
    with open(output_path, "w") as f:
        json.dump({"elements": all_elements, "total_pages": total_pages}, f, indent=2)

    # Clean up batch directory
    try:
        import shutil
        shutil.rmtree(batch_dir, ignore_errors=True)
    except Exception:
        pass

    return {"elements": all_elements, "total_pages": total_pages, "method": "docling"}


def _extract_single_pass(pdf_path: str, output_dir: str, total_pages: int, log_fn=None) -> dict:
    """Fallback: process entire PDF in one Docling call (no batching)."""
    if log_fn:
        log_fn("Running single-pass Docling extraction (no progress during this step)...")

    from docling.document_converter import DocumentConverter

    converter = DocumentConverter()
    start = time.time()
    result = converter.convert(pdf_path)
    doc = result.document
    elapsed = time.time() - start

    if log_fn:
        log_fn(f"Single-pass Docling done in {elapsed:.0f}s, extracting elements...")

    elements = []
    for item in doc.iterate_items():
        element_obj, _level = item if isinstance(item, tuple) else (item, 0)
        text = _get_element_text(element_obj)
        if not text or not text.strip():
            continue

        label = type(element_obj).__name__.lower()
        etype = DOCLING_TYPE_MAP.get(label, "text")
        page = 0
        if hasattr(element_obj, "prov") and element_obj.prov:
            page = element_obj.prov[0].page_no if hasattr(element_obj.prov[0], "page_no") else 0

        elements.append({"type": etype, "text": text, "page": page})

    if not total_pages:
        if hasattr(doc, "pages"):
            total_pages = len(doc.pages)
        elif elements:
            total_pages = max(e.get("page", 0) for e in elements)

    output_path = os.path.join(output_dir, "docling_extraction.json")
    with open(output_path, "w") as f:
        json.dump({"elements": elements, "total_pages": total_pages}, f, indent=2)

    return {"elements": elements, "total_pages": total_pages, "method": "docling"}
