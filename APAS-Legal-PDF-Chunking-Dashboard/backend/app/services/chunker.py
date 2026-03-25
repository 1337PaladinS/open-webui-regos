"""
Hierarchical structure-aware chunker for legal PDFs.
Chunks by section/subsection — one chunk per legal provision, regardless of size.
Mirrors the Chapter 24 approach: each Sec. X-Y or Sec. X-Y.Z becomes its own chunk.

Also includes:
  - Hierarchical metadata with breadcrumbs
  - Cross-reference extraction
  - Content-type detection
  - FEA entity extraction (thresholds, penalties, roles, standards, obligations)
"""
import re
import hashlib
from typing import Optional

import tiktoken

enc = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(enc.encode(text))


# ─── Hierarchy Parsing ─────────────────────────────────────────────

SECTION_PATTERN = re.compile(
    r"(?:§|Sec(?:tion)?\.?)\s*(\d+[\-\.]\d+(?:\.\d+)*)"
)
SUBSECTION_PATTERN = re.compile(
    r"\((\d+|[a-z]|[ivxlc]+)\)"
)
ARTICLE_PATTERN = re.compile(
    r"Article\s+([IVXLC]+|[0-9]+)[\.:]\s*(.*)", re.IGNORECASE
)
DIVISION_PATTERN = re.compile(
    r"Division\s+(\d+)[\.:]\s*(.*)", re.IGNORECASE
)
CHAPTER_PATTERN = re.compile(
    r"Chapter\s+(\d+)[\.:]\s*(.*)", re.IGNORECASE
)
DEFINITION_ENTRY = re.compile(
    r"^\s*\((\d+)\)\s+(.+?)(?:\s+shall\s+mean|\s+means|\s+is\s+defined)",
    re.IGNORECASE | re.MULTILINE,
)
RESERVED_PATTERN = re.compile(
    r"Sec(?:s|tion)?\.?\s*[\d\-\.]+(?:\s*[—–-]\s*[\d\-\.]+)?\.\s*Reserved",
    re.IGNORECASE,
)
CROSS_REF_PATTERN = re.compile(
    r"(?:§|[Ss]ec(?:tion)?\.?)\s*(\d+[\-\.]\d+(?:\.\d+)?(?:\(\d+\))?)"
)
ORDINANCE_PATTERN = re.compile(
    r"Ord(?:\.|inance)\s*No\.\s*([\d\-]+)"
)
DOLLAR_PATTERN = re.compile(r"\$[\d,]+(?:\.\d{2})?")
DATE_PATTERN = re.compile(
    r"\d{1,2}[\-/]\d{1,2}[\-/]\d{2,4}"
)

# FEA regex patterns for entity extraction
THRESHOLD_PATTERN = re.compile(
    r"(\d+[\.,]?\d*)\s*(mg/[lL]|ppm|percent|%|feet|foot|inches|gallons|acres|days|hours|minutes|years|months)",
    re.IGNORECASE,
)
PENALTY_PATTERN = re.compile(
    r"\$[\d,]+(?:\.\d{2})?\s*(?:per\s+(?:day|violation|offense))?",
    re.IGNORECASE,
)
ROLE_KEYWORDS = [
    "Director", "Board", "Property Owner", "Tenant", "Industrial User",
    "Inspector", "Operator", "Transporter", "Contractor", "Consultant",
    "Department", "County Manager", "applicant", "permittee", "licensee",
]
STANDARD_PATTERN = re.compile(
    r"\d+\s*(?:CFR|C\.F\.R\.)|Chapter\s+\d+.*?Florida Statutes|EPA Method|ASTM|ANSI",
    re.IGNORECASE,
)
OBLIGATION_PATTERN = re.compile(
    r"(?:shall|must|is required|it shall be unlawful|no person shall|is prohibited)[^.]*\.",
    re.IGNORECASE,
)


def detect_content_type(text: str) -> str:
    """Classify a text block's content type."""
    lower = text.lower().strip()
    if RESERVED_PATTERN.search(text):
        return "reserved"
    if DEFINITION_ENTRY.search(text):
        return "definition"
    if "shall mean" in lower or "means " in lower[:100]:
        return "definition"
    lines = text.split("\n")
    pipe_lines = sum(1 for l in lines if l.count("|") >= 2)
    if pipe_lines >= 3:
        return "table"
    list_items = re.findall(r"^\s*\([a-z0-9]+\)", text, re.MULTILINE)
    if len(list_items) >= 4:
        return "list"
    if len(DOLLAR_PATTERN.findall(text)) >= 3:
        return "fee_schedule"
    if THRESHOLD_PATTERN.search(text) and len(text) > 500:
        return "technical"
    return "prose"


def extract_cross_references(text: str, own_section: str = "") -> list[str]:
    """Extract all section cross-references from text."""
    refs = CROSS_REF_PATTERN.findall(text)
    unique = list(dict.fromkeys(refs))
    return [r for r in unique if r != own_section]


def extract_fea_entities(text: str) -> dict:
    """Extract FEA Layer 3 entities."""
    entities = {
        "thresholds": [],
        "penalties": [],
        "roles": [],
        "standards": [],
        "obligations": [],
    }

    for m in THRESHOLD_PATTERN.finditer(text):
        entities["thresholds"].append({
            "value": m.group(1),
            "unit": m.group(2),
            "context": text[max(0, m.start() - 50): m.end() + 50].strip(),
        })

    for m in PENALTY_PATTERN.finditer(text):
        entities["penalties"].append({
            "amount": m.group(0).strip(),
            "context": text[max(0, m.start() - 50): m.end() + 50].strip(),
        })

    for keyword in ROLE_KEYWORDS:
        if re.search(r"\b" + re.escape(keyword) + r"\b", text, re.IGNORECASE):
            entities["roles"].append(keyword)
    entities["roles"] = list(set(entities["roles"]))

    for m in STANDARD_PATTERN.finditer(text):
        entities["standards"].append(m.group(0).strip())
    entities["standards"] = list(set(entities["standards"]))

    for m in OBLIGATION_PATTERN.finditer(text):
        otext = m.group(0).strip()
        if len(otext) > 20:
            otype = "prohibition" if any(
                w in otext.lower() for w in ["shall not", "unlawful", "prohibited"]
            ) else "obligation" if any(
                w in otext.lower() for w in ["shall", "must", "is required"]
            ) else "permission"
            entities["obligations"].append({"text": otext[:500], "type": otype})

    return entities


# ─── Section-Based Chunking (Chapter 24 Style) ────────────────────

def _is_section_header(text: str) -> Optional[str]:
    """Check if text is a section header, return section number or None."""
    m = re.match(
        r"(?:§|Sec(?:tion)?\.?)\s*(\d+[\-\.]\d+(?:\.\d+)*)\s*[\.\-:—–]?\s*(.*)",
        text.strip(),
    )
    if m:
        return m.group(1)
    return None


def _get_section_title(text: str) -> str:
    """Extract the title part after the section number."""
    m = re.match(
        r"(?:§|Sec(?:tion)?\.?)\s*\d+[\-\.]\d+(?:\.\d+)*\s*[\.\-:—–]?\s*(.*)",
        text.strip(),
    )
    if m:
        return m.group(1).strip().rstrip(".")[:150]
    return ""


def build_hierarchy_from_docling(doc_json: dict) -> list[dict]:
    """
    Parse Docling JSON output into a flat list of elements with hierarchy info.
    Each element gets: type, text, hierarchy dict, page.
    """
    elements = []
    current_hierarchy = {
        "chapter": "",
        "article": "",
        "division": "",
        "section": "",
        "section_title": "",
        "subsection": "",
    }

    items = doc_json if isinstance(doc_json, list) else doc_json.get("items", doc_json.get("elements", []))

    for item in items:
        etype = item.get("type", item.get("label", "text"))
        text = item.get("text", "")
        page = item.get("page", item.get("prov", [{}])[0].get("page", 0) if item.get("prov") else 0)

        if not text.strip():
            continue

        # Update hierarchy based on headers
        if etype in ("section_header", "title"):
            cm = CHAPTER_PATTERN.match(text)
            am = ARTICLE_PATTERN.match(text)
            dm = DIVISION_PATTERN.match(text)
            sm = SECTION_PATTERN.search(text)

            if cm:
                current_hierarchy["chapter"] = f"Chapter {cm.group(1)}: {cm.group(2).strip()}"
                current_hierarchy["article"] = ""
                current_hierarchy["division"] = ""
                current_hierarchy["section"] = ""
                current_hierarchy["section_title"] = ""
                current_hierarchy["subsection"] = ""
            elif am:
                current_hierarchy["article"] = f"Article {am.group(1)}: {am.group(2).strip()}"
                current_hierarchy["division"] = ""
                current_hierarchy["section"] = ""
                current_hierarchy["section_title"] = ""
                current_hierarchy["subsection"] = ""
            elif dm:
                current_hierarchy["division"] = f"Division {dm.group(1)}: {dm.group(2).strip()}"
                current_hierarchy["section"] = ""
                current_hierarchy["section_title"] = ""
                current_hierarchy["subsection"] = ""
            elif sm:
                sec_num = sm.group(1)
                current_hierarchy["section"] = f"§ {sec_num}"
                title_part = text[sm.end():].strip().lstrip(".-: ")
                current_hierarchy["section_title"] = title_part[:120] if title_part else ""
                current_hierarchy["subsection"] = ""

        elements.append({
            "type": etype,
            "text": text,
            "page": page,
            "hierarchy": dict(current_hierarchy),
        })

    return elements


def build_hierarchy_from_text(raw_text: str, filename: str = "") -> list[dict]:
    """
    Parse raw text into elements, splitting at section boundaries.
    Each section header starts a new element group.
    """
    elements = []
    current_hierarchy = {
        "chapter": "",
        "article": "",
        "division": "",
        "section": "",
        "section_title": "",
        "subsection": "",
    }

    lines = raw_text.split("\n")
    current_block = []
    current_page = 1

    for line in lines:
        if "\f" in line:
            current_page += line.count("\f")
            line = line.replace("\f", "")

        stripped = line.strip()
        if not stripped:
            if current_block:
                block_text = "\n".join(current_block)
                elements.append({
                    "type": detect_content_type(block_text),
                    "text": block_text,
                    "page": current_page,
                    "hierarchy": dict(current_hierarchy),
                })
                current_block = []
            continue

        cm = CHAPTER_PATTERN.match(stripped)
        am = ARTICLE_PATTERN.match(stripped)
        dm = DIVISION_PATTERN.match(stripped)
        sm = re.match(r"(?:§|Sec(?:tion)?\.?)\s*(\d+[\-\.]\d+(?:\.\d+)?)\s*[\.\-:]\s*(.*)", stripped)

        if cm:
            if current_block:
                elements.append({
                    "type": detect_content_type("\n".join(current_block)),
                    "text": "\n".join(current_block),
                    "page": current_page,
                    "hierarchy": dict(current_hierarchy),
                })
                current_block = []
            current_hierarchy["chapter"] = f"Chapter {cm.group(1)}: {cm.group(2).strip()}"
            current_hierarchy["article"] = ""
            current_hierarchy["division"] = ""
            current_hierarchy["section"] = ""
            current_hierarchy["section_title"] = ""
            elements.append({
                "type": "section_header",
                "text": stripped,
                "page": current_page,
                "hierarchy": dict(current_hierarchy),
            })
        elif am:
            if current_block:
                elements.append({
                    "type": detect_content_type("\n".join(current_block)),
                    "text": "\n".join(current_block),
                    "page": current_page,
                    "hierarchy": dict(current_hierarchy),
                })
                current_block = []
            current_hierarchy["article"] = f"Article {am.group(1)}: {am.group(2).strip()}"
            current_hierarchy["division"] = ""
            current_hierarchy["section"] = ""
            current_hierarchy["section_title"] = ""
            elements.append({
                "type": "section_header",
                "text": stripped,
                "page": current_page,
                "hierarchy": dict(current_hierarchy),
            })
        elif dm:
            if current_block:
                elements.append({
                    "type": detect_content_type("\n".join(current_block)),
                    "text": "\n".join(current_block),
                    "page": current_page,
                    "hierarchy": dict(current_hierarchy),
                })
                current_block = []
            current_hierarchy["division"] = f"Division {dm.group(1)}: {dm.group(2).strip()}"
            current_hierarchy["section"] = ""
            current_hierarchy["section_title"] = ""
            elements.append({
                "type": "section_header",
                "text": stripped,
                "page": current_page,
                "hierarchy": dict(current_hierarchy),
            })
        elif sm:
            if current_block:
                elements.append({
                    "type": detect_content_type("\n".join(current_block)),
                    "text": "\n".join(current_block),
                    "page": current_page,
                    "hierarchy": dict(current_hierarchy),
                })
                current_block = []
            current_hierarchy["section"] = f"§ {sm.group(1)}"
            current_hierarchy["section_title"] = sm.group(2).strip()[:120]
            current_hierarchy["subsection"] = ""
            elements.append({
                "type": "section_header",
                "text": stripped,
                "page": current_page,
                "hierarchy": dict(current_hierarchy),
            })
        else:
            current_block.append(line)

    if current_block:
        elements.append({
            "type": detect_content_type("\n".join(current_block)),
            "text": "\n".join(current_block),
            "page": current_page,
            "hierarchy": dict(current_hierarchy),
        })

    return elements


def chunk_elements(
    elements: list[dict],
    document_name: str,
    jurisdiction: str = "Unknown",
    **kwargs,
) -> list[dict]:
    """
    Convert parsed elements into chunks — Chapter 24 style.

    Rules:
    - Each section (Sec. X-Y) becomes its own chunk
    - Each subsection (Sec. X-Y.Z) becomes its own chunk
    - NO merging of small chunks — a 50-token section stays as one chunk
    - NO splitting of large chunks — a 5000-token section stays as one chunk
    - The legal structure IS the chunk structure
    - Reserved sections are still grouped together (they carry no content)
    """
    chunks = []
    current_section = ""
    current_section_elements = []
    reserved_buffer = []

    def _make_chunk(elems: list[dict]) -> dict:
        """Build a chunk from a list of elements belonging to one section."""
        combined_text = "\n".join(e["text"] for e in elems)
        tokens = count_tokens(combined_text)
        hierarchy = elems[0]["hierarchy"]
        pages = sorted(set(e["page"] for e in elems if e["page"]))
        page_range = f"{pages[0]}-{pages[-1]}" if len(pages) > 1 else str(pages[0]) if pages else ""

        section_num = hierarchy.get("section", "").replace("§ ", "")
        content_type = detect_content_type(combined_text)
        cross_refs = extract_cross_references(combined_text, section_num)
        fea = extract_fea_entities(combined_text)
        ord_citations = ORDINANCE_PATTERN.findall(combined_text)
        dates = DATE_PATTERN.findall(combined_text)
        has_dollars = bool(DOLLAR_PATTERN.search(combined_text))

        # Build breadcrumb
        parts = []
        if hierarchy.get("chapter"):
            parts.append(hierarchy["chapter"].split(":")[0])
        if hierarchy.get("article"):
            parts.append(hierarchy["article"].split(":")[0])
        if hierarchy.get("division"):
            parts.append(hierarchy["division"].split(":")[0])
        if hierarchy.get("section"):
            sec = hierarchy["section"]
            title = hierarchy.get("section_title", "")
            parts.append(f"{sec} {title}".strip())
        breadcrumb = " > ".join(parts)

        slug = re.sub(r"[^a-z0-9]+", "_", breadcrumb.lower()).strip("_")[:80]
        chunk_hash = hashlib.md5(combined_text[:200].encode()).hexdigest()[:6]
        chunk_id = f"{slug}_{chunk_hash}"

        return {
            "metadata": {
                "chunk_id": chunk_id,
                "document": document_name,
                "jurisdiction": jurisdiction,
                "breadcrumb": breadcrumb,
                "content_type": content_type,
                "hierarchy": hierarchy,
                "cross_references": cross_refs,
                "ordinance_citations": ord_citations,
                "effective_dates": dates,
                "dollar_amounts_present": has_dollars,
                "page_range": page_range,
                "token_count": tokens,
                "fea_entities": fea,
            },
            "text": combined_text,
            "context_prefix": None,
            "enriched_text": None,
        }

    def flush_section():
        """Flush accumulated section elements as one chunk."""
        nonlocal current_section_elements
        if not current_section_elements:
            return
        chunks.append(_make_chunk(current_section_elements))
        current_section_elements = []

    def flush_reserved():
        """Flush reserved sections as a single grouped chunk."""
        nonlocal reserved_buffer
        if not reserved_buffer:
            return
        chunks.append(_make_chunk(reserved_buffer))
        reserved_buffer = []

    for elem in elements:
        etype = elem["type"]
        text = elem["text"]
        section = elem["hierarchy"].get("section", "")

        # Check if this element is a reserved section
        if RESERVED_PATTERN.search(text):
            flush_section()
            reserved_buffer.append(elem)
            continue

        # If we hit a non-reserved element, flush any reserved buffer
        if reserved_buffer:
            flush_reserved()

        # Section header = start of a new chunk
        if etype == "section_header":
            flush_section()
            current_section = section
            # Include the header text in the chunk
            current_section_elements.append(elem)
            continue

        # If section changed without a header (rare but possible)
        if section and section != current_section and current_section_elements:
            flush_section()
            current_section = section

        # Accumulate into current section
        current_section_elements.append(elem)

    # Final flushes
    flush_section()
    flush_reserved()

    return chunks


def compute_stats(chunks: list[dict], total_pages: int = 0) -> dict:
    """Compute dashboard statistics from chunks."""
    if not chunks:
        return {
            "total_pages": total_pages,
            "total_sections": 0,
            "total_subsections": 0,
            "total_definitions": 0,
            "total_tables": 0,
            "total_cross_references": 0,
            "total_chunks": 0,
            "avg_chunk_tokens": 0,
            "min_chunk_tokens": 0,
            "max_chunk_tokens": 0,
            "content_type_breakdown": {},
            "hierarchy_tree": {},
            "token_distribution": [],
        }

    token_counts = [c["metadata"]["token_count"] for c in chunks]
    sections = set()
    subsections = set()
    content_types = {}
    all_cross_refs = set()
    hierarchy_tree = {}

    for c in chunks:
        meta = c["metadata"]
        ct = meta["content_type"]
        content_types[ct] = content_types.get(ct, 0) + 1

        sec = meta["hierarchy"].get("section", "")
        if sec:
            sec_num = sec.replace("§ ", "")
            # Subsections have dots: e.g., 24-15.1
            if "." in sec_num:
                subsections.add(sec_num)
            else:
                sections.add(sec_num)

        for ref in meta.get("cross_references", []):
            all_cross_refs.add(ref)

        # Build tree
        h = meta["hierarchy"]
        ch = h.get("chapter", "Unknown")
        art = h.get("article", "")
        div = h.get("division", "")
        sec_key = h.get("section", "")

        if ch not in hierarchy_tree:
            hierarchy_tree[ch] = {}
        if art and art not in hierarchy_tree[ch]:
            hierarchy_tree[ch][art] = {}
        if art and div:
            if div not in hierarchy_tree[ch].get(art, {}):
                hierarchy_tree[ch][art][div] = []
            if sec_key:
                hierarchy_tree[ch][art][div].append(sec_key)
        elif art and sec_key:
            if "_sections" not in hierarchy_tree[ch].get(art, {}):
                hierarchy_tree[ch][art]["_sections"] = []
            hierarchy_tree[ch][art]["_sections"].append(sec_key)

    # Token distribution buckets — wider range since we don't constrain size
    buckets = {
        "0-100": 0, "100-300": 0, "300-500": 0, "500-1000": 0,
        "1000-2000": 0, "2000-5000": 0, "5000+": 0,
    }
    for t in token_counts:
        if t < 100:
            buckets["0-100"] += 1
        elif t < 300:
            buckets["100-300"] += 1
        elif t < 500:
            buckets["300-500"] += 1
        elif t < 1000:
            buckets["500-1000"] += 1
        elif t < 2000:
            buckets["1000-2000"] += 1
        elif t < 5000:
            buckets["2000-5000"] += 1
        else:
            buckets["5000+"] += 1

    return {
        "total_pages": total_pages,
        "total_sections": len(sections),
        "total_subsections": len(subsections),
        "total_definitions": content_types.get("definition", 0),
        "total_tables": content_types.get("table", 0),
        "total_cross_references": len(all_cross_refs),
        "total_chunks": len(chunks),
        "avg_chunk_tokens": round(sum(token_counts) / len(token_counts), 1),
        "min_chunk_tokens": min(token_counts),
        "max_chunk_tokens": max(token_counts),
        "content_type_breakdown": content_types,
        "hierarchy_tree": hierarchy_tree,
        "token_distribution": buckets,
    }
