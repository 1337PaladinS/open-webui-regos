"""
title: RegOS GraphRAG Filter
description: Graph-enhanced RAG for Chapter 24 regulatory queries. Searches Neo4j knowledge graph for relevant regulatory sections and injects them as context into the system prompt. Automatically detects uploaded documents (PDF, DOCX, XLSX, PPTX, images) and sends them to a vision model for analysis. Works with ANY model — just enable this filter globally or per-model.
author: APAS AI
version: 0.18.0
required_open_webui_version: 0.4.0
"""

from pydantic import BaseModel, Field
from typing import Optional
import json
import os
import re
import sqlite3
import time
import hashlib
import urllib.request
import urllib.error
import base64
import tempfile
import subprocess
import logging

_doc_logger = logging.getLogger("regos-doc-analyzer")


class Filter:
    """
    GraphRAG Filter for regulatory compliance queries.

    Unlike a Pipe (which replaces the LLM endpoint), this Filter works
    WITH any model. It intercepts the user's message in inlet(), searches
    Neo4j for relevant Chapter 24 regulatory sections, and prepends them
    as a system message. The LLM then answers using that context.

    Enable it globally or per-model in Admin > Functions.
    """

    class Valves(BaseModel):
        # Neo4j connection
        neo4j_uri: str = Field(
            default="neo4j+s://11d95839.databases.neo4j.io",
            description="Neo4j Aura connection URI.",
        )
        neo4j_username: str = Field(
            default="neo4j",
            description="Neo4j username.",
        )
        neo4j_password: str = Field(
            default="",
            description="Neo4j password. Set this in the admin UI.",
        )
        neo4j_database: str = Field(
            default="neo4j",
            description="Neo4j database name.",
        )

        # Retrieval settings
        max_sections: int = Field(
            default=5,
            description="Maximum number of regulatory sections to include in context.",
        )
        max_section_chars: int = Field(
            default=2000,
            description="Maximum characters per section (truncates long sections).",
        )
        entity_search_limit: int = Field(
            default=8,
            description="Maximum entities to retrieve from fulltext search.",
        )
        min_relevance_score: float = Field(
            default=0.5,
            description="Minimum fulltext search score to consider relevant.",
        )
        priority: int = Field(
            default=0,
            description="Filter execution priority. Lower runs first.",
        )

        # Feature flags
        enabled: bool = Field(
            default=True,
            description="Enable or disable the GraphRAG filter.",
        )
        debug: bool = Field(
            default=False,
            description="Append retrieval debug info to the system prompt.",
        )
        show_trace: bool = Field(
            default=False,
            description="Append a full raw retrieval trace to the LLM response. Shows exactly what Neo4j returned: entities, traversals, sections, scores. Turn this ON to see the graph retrieval pipeline output.",
        )
        show_confidence: bool = Field(
            default=True,
            description="Show a color-coded confidence banner at the bottom of each response. GREEN (≥70%) = well-supported, AMBER (45-69%) = partial coverage, RED (<45%) = limited context. Uses an HTML-styled block with colored left-border and inline badge.",
        )
        enterprise_format: bool = Field(
            default=True,
            description="Format responses as structured consultant-style analysis with Summary, Regulatory Analysis, Applicable Sections table, and compliance disclaimer.",
        )

        # Escalation settings
        escalation_enabled: bool = Field(
            default=True,
            description="Automatically flag queries for expert review when confidence is below the threshold.",
        )
        escalation_threshold: float = Field(
            default=0.65,
            description="Confidence score threshold for automatic escalation. Queries below this score are flagged for review.",
        )
        escalation_target: str = Field(
            default="compliance-review",
            description="Escalation target identifier (for dashboard grouping and future routing).",
        )
        escalation_webhook_url: str = Field(
            default="",
            description="n8n webhook URL for escalation. If empty, escalation only flags the audit DB (no external notification).",
        )

        # Guardrail settings
        guardrail_enabled: bool = Field(
            default=True,
            description="Enable hard guardrails that detect out-of-scope queries before they reach the LLM.",
        )
        guardrail_exclusion_keywords: str = Field(
            default="building code,zoning,OSHA,EPA federal,immigration,criminal law,tax code,family law,property tax,traffic violation",
            description="Comma-separated keywords/phrases that trigger the out-of-scope guardrail. Case-insensitive.",
        )
        guardrail_support_contact: str = Field(
            default="",
            description="Support contact shown in guardrail notices (e.g., 'support@regos.ai' or '(305) 555-0100'). If empty, a generic message is shown.",
        )
        guardrail_jurisdiction_enabled: bool = Field(
            default=True,
            description="Enable jurisdiction mismatch detection. Flags queries that explicitly reference locations outside Miami-Dade County.",
        )
        guardrail_jurisdiction_allowlist: str = Field(
            default="miami,miami-dade,dade county,south florida,florida",
            description="Comma-separated location terms considered in-jurisdiction. Queries mentioning these are NOT flagged.",
        )
        guardrail_jurisdiction_blocklist: str = Field(
            default="",
            description="Additional location terms that trigger jurisdiction mismatch (e.g., 'broward,palm beach'). Added on top of built-in country/state detection.",
        )
        neo4j_fallback_to_kb: bool = Field(
            default=True,
            description="When Neo4j is unreachable, fall back to Knowledge Base retrieval only (degraded mode) instead of blocking the query entirely. The response will include a notice that graph context is unavailable.",
        )

        # Threshold evaluation settings (integrated — no tool-calling required)
        threshold_check_enabled: bool = Field(
            default=True,
            description="Automatically detect numeric measurements in queries and evaluate against Chapter 24 thresholds. Works with any model — no tool-calling support needed.",
        )
        thresholds_path: str = Field(
            default="/app/backend/data/regulatory_thresholds.json",
            description="Path to the curated regulatory thresholds JSON file inside the container.",
        )
        breach_db_path: str = Field(
            default="/app/backend/data/regos_breaches.db",
            description="Path to the breach SQLite database for logging threshold evaluations.",
        )

        # Document analysis settings (vision-based)
        doc_analysis_enabled: bool = Field(
            default=True,
            description="Automatically analyze uploaded documents (PDF, DOCX, XLSX, PPTX, images) using a vision model. The analysis is injected into the conversation so the primary model can reason over document content.",
        )
        doc_vision_model: str = Field(
            default="openai/gpt-4o",
            description="Vision-capable model ID for document analysis. Use the provider's model name directly (e.g., 'openai/gpt-4o' for OpenRouter, 'gpt-4o' for OpenAI direct).",
        )
        doc_api_url: str = Field(
            default="https://openrouter.ai/api/v1/chat/completions",
            description="Vision model API endpoint URL. Calls the provider directly (NOT via Open WebUI, to avoid deadlocks). Default is OpenRouter. For OpenAI direct: https://api.openai.com/v1/chat/completions",
        )
        doc_max_pages: int = Field(
            default=20,
            description="Maximum number of PDF/document pages to send to the vision model.",
        )
        doc_analysis_detail: str = Field(
            default="high",
            description="Vision analysis detail: 'high' for full resolution, 'low' for faster/cheaper.",
        )
        doc_api_key: str = Field(
            default="",
            description="API key for the vision model provider (e.g., OpenRouter API key). Required for document analysis. Get from https://openrouter.ai/keys",
        )

    def __init__(self):
        self.valves = self.Valves()
        self.file_handler = True  # Take control of file processing from Open WebUI
        self._driver = None
        self._last_trace = None  # Stores trace for outlet to append
        self._confidence_score = None  # 0.0–1.0 composite score
        self._confidence_band = None  # HIGH / MEDIUM / LOW
        self._confidence_signals = None  # Raw signals dict for audit
        self._citations = None  # Stored for outlet to emit as sources
        self._entity_matches = None  # Entity search results (for escalation context)
        self._graph_context = None  # Assembled graph context injected into LLM
        # Guardrail state (reset each request)
        self._guardrail_triggered = False
        self._guardrail_type = None  # "out_of_scope" | "zero_retrieval" | "jurisdiction" | "neo4j_unavailable"
        self._guardrail_reason = None
        self._guardrail_ref = None  # GRD-YYYYMMDD-XXXX
        self._neo4j_degraded = False  # True when Neo4j is down but KB fallback is active
        # Threshold evaluation state (reset each request)
        self._threshold_determinations = None  # list of determination dicts
        self._threshold_service_cache = None  # lazy-loaded threshold entries
        # Document analysis state
        self._doc_analysis = None  # Stores vision model analysis text

    # ── DOCUMENT ANALYSIS HELPERS ──────────────────────────────────────

    # Extensions that need vision-based analysis (non-text documents)
    _VISUAL_EXTENSIONS = {
        ".pdf", ".docx", ".doc", ".xlsx", ".xls",
        ".pptx", ".ppt", ".png", ".jpg", ".jpeg",
        ".gif", ".bmp", ".tiff", ".tif", ".webp", ".svg",
    }

    def _file_needs_visual_analysis(self, filename: str) -> bool:
        """Check if a file needs vision-based analysis vs text extraction."""
        if not filename:
            return False
        ext = os.path.splitext(filename.lower())[1]
        return ext in self._VISUAL_EXTENSIONS

    def _get_file_type_label(self, filename: str) -> str:
        """Human-readable label for file type."""
        ext = os.path.splitext(filename.lower())[1]
        labels = {
            ".pdf": "PDF document", ".docx": "Word document", ".doc": "Word document",
            ".xlsx": "Excel spreadsheet", ".xls": "Excel spreadsheet",
            ".pptx": "PowerPoint presentation", ".ppt": "PowerPoint presentation",
            ".png": "image", ".jpg": "image", ".jpeg": "image", ".gif": "image",
            ".bmp": "image", ".tiff": "image", ".tif": "image", ".webp": "image",
        }
        return labels.get(ext, "document")

    def _convert_pdf_to_images(self, pdf_bytes: bytes) -> list:
        """Convert PDF pages to base64-encoded PNG images via pdftoppm."""
        images = []
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(pdf_bytes)
                tmp_path = tmp.name

            with tempfile.TemporaryDirectory() as out_dir:
                cmd = [
                    "pdftoppm", "-png", "-r", "200",
                    "-l", str(self.valves.doc_max_pages),
                    tmp_path, os.path.join(out_dir, "page"),
                ]
                subprocess.run(cmd, capture_output=True, timeout=120)

                page_files = sorted([
                    f for f in os.listdir(out_dir)
                    if f.startswith("page-") and f.endswith(".png")
                ])
                for pf in page_files:
                    with open(os.path.join(out_dir, pf), "rb") as img_file:
                        images.append(base64.b64encode(img_file.read()).decode("utf-8"))

            os.unlink(tmp_path)
        except Exception as e:
            _doc_logger.error(f"[DOC-ANALYZER] PDF conversion error: {e}")
        return images

    def _convert_office_to_images(self, file_bytes: bytes, extension: str) -> list:
        """Convert Office docs to images via LibreOffice → PDF → pdftoppm."""
        images = []
        try:
            with tempfile.NamedTemporaryFile(suffix=extension, delete=False) as tmp:
                tmp.write(file_bytes)
                tmp_path = tmp.name

            with tempfile.TemporaryDirectory() as out_dir:
                result = subprocess.run(
                    ["soffice", "--headless", "--convert-to", "pdf", "--outdir", out_dir, tmp_path],
                    capture_output=True, timeout=120,
                )
                if result.returncode != 0:
                    os.unlink(tmp_path)
                    return images

                pdf_files = [f for f in os.listdir(out_dir) if f.endswith(".pdf")]
                if pdf_files:
                    with open(os.path.join(out_dir, pdf_files[0]), "rb") as f:
                        images = self._convert_pdf_to_images(f.read())

            os.unlink(tmp_path)
        except Exception as e:
            _doc_logger.error(f"[DOC-ANALYZER] Office conversion error: {e}")
        return images

    def _call_vision_model(self, images_b64: list, filename: str, file_type: str,
                           user_question: str, token: str) -> str:
        """Send page images to the vision model and return structured analysis."""
        prompt = (
            f'You are analyzing an uploaded {file_type} named "{filename}".\n\n'
            "Provide a thorough, structured analysis:\n\n"
            "1. **Document Type & Purpose**: What kind of document/form is this?\n"
            "2. **Structure**: Layout — sections, tables, form fields, headers.\n"
            "3. **Content Summary**: Key content per page.\n"
            "4. **Form Fields** (if applicable):\n"
            "   - List ALL fields: name/label, filled or empty, value if filled\n"
            "   - Flag incorrectly filled or suspicious fields\n"
            "5. **Tables & Data**: Extract table contents, note numeric values/limits/thresholds\n"
            "6. **Issues or Concerns**: Anything incomplete, inconsistent, or potentially non-compliant.\n\n"
            "Be thorough and precise. Extract ALL visible text, values, and data points."
        )
        if user_question:
            prompt += f'\n\nThe user\'s question about this document: "{user_question}"'

        content_parts = [{"type": "text", "text": prompt}]
        for img_b64 in images_b64:
            content_parts.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{img_b64}",
                    "detail": self.valves.doc_analysis_detail,
                },
            })

        payload = {
            "model": self.valves.doc_vision_model,
            "messages": [{"role": "user", "content": content_parts}],
            "max_tokens": 4096,
            "stream": False,
        }

        # Call the vision provider directly (NOT via Open WebUI — that deadlocks)
        url = self.valves.doc_api_url
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = resp.read().decode("utf-8")
                result = json.loads(raw)
                content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                return content
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")[:500]
            _doc_logger.warning(f"[VISION] HTTP {e.code}: {error_body[:200]}")
            return f"[Document analysis failed: HTTP {e.code}]"
        except Exception as e:
            _doc_logger.warning(f"[VISION] {type(e).__name__}: {e}")
            return f"[Document analysis failed: {str(e)[:200]}]"

    def _analyze_uploaded_files(self, body: dict, user_question: str,
                                __user__: dict = None, __metadata__: dict = None) -> str:
        """
        Detect uploaded files in the message body, convert to images,
        send to vision model, and return the combined analysis text.
        Returns empty string if no visual files found.
        """

        files = body.get("files", [])
        metadata_files = (__metadata__ or {}).get("files", [])
        all_files = files or metadata_files

        if not all_files:
            return ""

        # Get auth token for vision API calls
        token = self.valves.doc_api_key or ""
        if not token:
            token = os.getenv("OPENWEBUI_TOKEN", "")
        if not token and __user__:
            token = __user__.get("token", "")

        analyses = []

        for idx, file_info in enumerate(all_files):
            file_data = file_info.get("file", file_info)
            filename = (
                file_data.get("filename")
                or file_data.get("name")
                or file_info.get("name")
                or "unknown"
            )
            file_id = file_data.get("id") or file_info.get("id")
            file_path = file_data.get("path") or ""

            if not self._file_needs_visual_analysis(filename):
                continue

            ext = os.path.splitext(filename.lower())[1]
            file_type = self._get_file_type_label(filename)

            # ── Get file bytes ──
            file_bytes = None

            # Method 0 (preferred): Read directly from disk path
            if file_path and os.path.isfile(file_path):
                try:
                    with open(file_path, "rb") as f:
                        file_bytes = f.read()
                except Exception as e:
                    pass

            # Method 1: Content in data field (base64 encoded)
            if not file_bytes:
                data_field = file_data.get("data", {})
                if isinstance(data_field, dict) and data_field.get("content"):
                    content = data_field["content"]
                    if isinstance(content, str):
                        try:
                            file_bytes = base64.b64decode(content)
                        except Exception:
                            file_bytes = content.encode("utf-8")
                    elif isinstance(content, bytes):
                        file_bytes = content

            # Method 2: Download via file API (needs token)
            if not file_bytes and file_id and token:
                try:
                    dl_url = f"{self.valves.doc_openwebui_url}/api/v1/files/{file_id}/content"
                    dl_req = urllib.request.Request(
                        dl_url, headers={"Authorization": f"Bearer {token}"}
                    )
                    with urllib.request.urlopen(dl_req, timeout=30) as resp:
                        file_bytes = resp.read()
                except Exception as e:
                    pass

            if not file_bytes:
                continue

            # ── Convert to images ──
            images_b64 = []
            if ext == ".pdf":
                images_b64 = self._convert_pdf_to_images(file_bytes)
            elif ext in {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff", ".tif"}:
                images_b64 = [base64.b64encode(file_bytes).decode("utf-8")]
            elif ext in {".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt"}:
                images_b64 = self._convert_office_to_images(file_bytes, ext)

            if not images_b64:
                continue

            page_count = len(images_b64)

            # ── Vision model needs a token ──
            if not token:
                analyses.append(
                    f"### Document: {filename}\n"
                    f"**Type:** {file_type} ({page_count} page{'s' if page_count > 1 else ''})\n\n"
                    f"[Document detected but analysis skipped — set doc_api_key in Valves to enable vision analysis]"
                )
                continue

            t0 = time.time()
            analysis = self._call_vision_model(
                images_b64, filename, file_type, user_question, token,
            )
            elapsed = time.time() - t0

            analyses.append(
                f"### Document: {filename}\n"
                f"**Type:** {file_type} ({page_count} page{'s' if page_count > 1 else ''})\n"
                f"**Analyzed by:** {self.valves.doc_vision_model}\n\n"
                f"{analysis}"
            )

        return "\n\n---\n\n".join(analyses) if analyses else ""

    def _inject_doc_analysis_into_message(self, messages: list) -> None:
        """Inject document analysis text into the last user message."""
        if not self._doc_analysis:
            return
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "user":
                original = messages[i].get("content", "")
                if isinstance(original, str):
                    messages[i]["content"] = (
                        f"{original}\n\n"
                        f"---\n"
                        f"[UPLOADED DOCUMENT ANALYSIS — extracted by vision model]\n"
                        f"{self._doc_analysis}\n"
                        f"---"
                    )
                break

    def _extract_search_terms_from_analysis(self, analysis: str) -> str:
        """
        Extract key regulatory terms from the document analysis to enhance
        the Neo4j graph search query. Returns a compact string of relevant
        terms that can be appended to the user's question for better retrieval.

        Uses pattern matching to find:
        - Document/form type identifiers
        - Regulatory references (section numbers, permit types)
        - Domain-specific keywords (permit, variance, violation, etc.)
        """
        terms = set()

        # Regulatory domain keywords — if these appear in the analysis,
        # they should drive graph retrieval
        _REGULATORY_KEYWORDS = [
            "permit", "variance", "violation", "notice of violation",
            "public hearing", "EQCB", "environmental quality control board",
            "application", "compliance", "non-compliance", "noncompliance",
            "zoning", "industrial", "residential", "commercial",
            "stormwater", "wastewater", "sewage", "drainage",
            "mangrove", "wetland", "shoreline", "coastal",
            "wellfield", "aquifer", "groundwater",
            "setback", "impervious", "pervious", "BMP",
            "discharge", "effluent", "pollutant", "contaminant",
            "remediation", "cleanup", "assessment",
            "construction", "demolition", "excavation", "dredging",
            "transfer of permit", "extension", "renewal",
            "recertification", "inspection",
        ]

        analysis_lower = analysis.lower()
        for kw in _REGULATORY_KEYWORDS:
            if kw.lower() in analysis_lower:
                terms.add(kw)

        # Extract section references like "24-48", "§24-48.2", "Section 24-"
        section_refs = re.findall(r'(?:§|section\s*)?24[- ]?\d+(?:\.\d+)?', analysis_lower)
        for ref in section_refs:
            clean = re.sub(r'[§\s]', '', ref).replace('24-', '24-').replace('24 ', '24-')
            terms.add(f"section {clean}")

        # Extract permit type references like "IW5-13276", "Class I", "Class II"
        permit_refs = re.findall(r'[A-Z]{1,4}\d?[- ]\d{3,6}', analysis)
        for pr in permit_refs:
            terms.add(f"permit {pr}")

        class_refs = re.findall(r'class\s+[IViv]+', analysis_lower)
        for cr in class_refs:
            terms.add(cr)

        # Cap at a reasonable length for Neo4j fulltext search
        term_list = sorted(terms)[:20]
        return " ".join(term_list)

    def _get_driver(self):
        """Lazy-initialize Neo4j driver."""
        if self._driver is None:
            from neo4j import GraphDatabase

            self._driver = GraphDatabase.driver(
                self.valves.neo4j_uri,
                auth=(self.valves.neo4j_username, self.valves.neo4j_password),
            )
        return self._driver

    def _escape_lucene(self, query: str) -> str:
        """Escape special Lucene characters."""
        safe = query.replace("\\", "\\\\")
        for ch in ["+", "-", "&&", "||", "!", "(", ")", "{", "}", "[", "]", "^", '"', "~", "*", "?", ":", "/"]:
            safe = safe.replace(ch, f"\\{ch}")
        return safe

    def _calculate_confidence(self, signals: dict) -> tuple[float, str]:
        """
        Compute a composite confidence score (0.0–1.0) from retrieval signals.

        Weights (rebalanced for FEA schema — v0.17.3):
          avg_doc_score       0.30 — how well documents match the query (fulltext)
          doc_count           0.15 — breadth of document coverage
          graph_expansion     0.25 — concept expansion found related sections (primary graph signal)
          section_count       0.12 — retrieval coverage (final assembled sections)
          has_graph_exclusive 0.10 — graph found sections text search missed
          avg_direct_score    0.08 — text-level relevance confirmation

        Band cutoffs:
          HIGH   >= 0.70
          MEDIUM >= 0.45
          LOW    <  0.45
        """
        entity_scores = signals.get("entity_scores", [])
        entity_count = signals.get("entity_count", 0)
        concept_section_count = signals.get("concept_section_count", 0)
        direct_scores = signals.get("direct_scores", [])
        final_section_count = signals.get("final_section_count", 0)
        graph_uuids = signals.get("graph_section_uuids", set())
        direct_uuids = signals.get("direct_section_uuids", set())

        # Normalize each signal to 0.0–1.0
        avg_doc = min(sum(entity_scores) / max(len(entity_scores), 1) / 10.0, 1.0) if entity_scores else 0.0
        norm_doc_count = min(entity_count / self.valves.entity_search_limit, 1.0)
        norm_concept = min(concept_section_count / max(self.valves.max_sections, 1), 1.0)
        norm_sections = min(final_section_count / max(self.valves.max_sections, 1), 1.0)
        graph_exclusive = 1.0 if (graph_uuids - direct_uuids) else 0.0
        avg_direct = min(sum(direct_scores) / max(len(direct_scores), 1) / 10.0, 1.0) if direct_scores else 0.0

        score = (
            0.30 * avg_doc
            + 0.15 * norm_doc_count
            + 0.25 * norm_concept
            + 0.12 * norm_sections
            + 0.10 * graph_exclusive
            + 0.08 * avg_direct
        )
        score = round(max(0.0, min(score, 1.0)), 2)

        if score >= 0.70:
            band = "HIGH"
        elif score >= 0.45:
            band = "MEDIUM"
        else:
            band = "LOW"

        return score, band

    def _search_documents(self, query: str) -> list[dict]:
        """Fulltext search on Ch24Document nodes (title + text)."""
        driver = self._get_driver()
        safe_query = self._escape_lucene(query)
        try:
            with driver.session(database=self.valves.neo4j_database) as session:
                result = session.run(
                    """
                    CALL db.index.fulltext.queryNodes('ch24_doc_fulltext', $search_term)
                    YIELD node, score
                    WHERE score >= $min_score
                    RETURN node.sectionId AS id,
                           node.title AS title,
                           node.text AS content,
                           score
                    ORDER BY score DESC
                    LIMIT $limit
                    """,
                    search_term=safe_query,
                    min_score=self.valves.min_relevance_score,
                    limit=self.valves.entity_search_limit,
                )
                return [dict(r) for r in result]
        except Exception:
            return []

    def _search_entities_by_name(self, query: str) -> list[dict]:
        """Search Ch24Entity nodes by matching query terms against entity values.
        Uses parameterized queries to prevent Cypher injection."""
        driver = self._get_driver()
        # Extract meaningful terms (3+ chars, skip common words) from the query
        stopwords = {"the", "and", "for", "are", "what", "how", "does", "this", "that", "with", "from", "have", "been"}
        terms = [t.lower() for t in query.split() if len(t) >= 3 and t.lower() not in stopwords]
        if not terms:
            return []
        try:
            with driver.session(database=self.valves.neo4j_database) as session:
                result = session.run(
                    """
                    MATCH (e:Ch24Entity)
                    WHERE any(term IN $terms WHERE toLower(e.value) CONTAINS term)
                    RETURN e.value AS name, e.type AS type, elementId(e) AS eid
                    LIMIT $limit
                    """,
                    terms=terms[:6],
                    limit=self.valves.entity_search_limit,
                )
                return [dict(r) for r in result]
        except Exception:
            return []

    def _get_sections_for_matched_entities(self, entity_eids: list[str]) -> list[dict]:
        """Traverse MENTIONS_ENTITY from Ch24Entity back to Ch24Document."""
        if not entity_eids:
            return []
        driver = self._get_driver()
        try:
            with driver.session(database=self.valves.neo4j_database) as session:
                result = session.run(
                    """
                    MATCH (d:Ch24Document)-[:MENTIONS_ENTITY]->(e:Ch24Entity)
                    WHERE elementId(e) IN $eids
                    WITH d, collect(DISTINCT e.value) AS matched_entities, count(DISTINCT e) AS entity_count
                    RETURN d.sectionId AS id,
                           d.text AS content,
                           d.title AS title,
                           matched_entities,
                           entity_count
                    ORDER BY entity_count DESC
                    """,
                    eids=entity_eids,
                )
                return [dict(r) for r in result]
        except Exception:
            return []

    def _get_sections_via_concepts(self, section_ids: list[str]) -> list[dict]:
        """From matched documents, expand through ontology concepts to find related sections."""
        if not section_ids:
            return []
        driver = self._get_driver()
        try:
            with driver.session(database=self.valves.neo4j_database) as session:
                result = session.run(
                    """
                    MATCH (d:Ch24Document)-[r:RELATES_TO_CONCEPT]->(c:Ch24Class)
                    WHERE d.sectionId IN $section_ids
                    WITH c, max(r.similarity) AS best_sim
                    ORDER BY best_sim DESC LIMIT 5
                    MATCH (related:Ch24Document)-[r2:RELATES_TO_CONCEPT]->(c)
                    WHERE r2.similarity >= 0.3 AND NOT related.sectionId IN $section_ids
                    RETURN DISTINCT related.sectionId AS id,
                           related.text AS content,
                           related.title AS title,
                           c.name AS concept,
                           r2.similarity AS score
                    ORDER BY r2.similarity DESC
                    LIMIT $limit
                    """,
                    section_ids=section_ids,
                    limit=self.valves.max_sections,
                )
                return [dict(r) for r in result]
        except Exception:
            return []

    def _search_sections_direct(self, query: str) -> list[dict]:
        """Direct fulltext search on Ch24Document content."""
        driver = self._get_driver()
        safe_query = self._escape_lucene(query)
        try:
            with driver.session(database=self.valves.neo4j_database) as session:
                result = session.run(
                    """
                    CALL db.index.fulltext.queryNodes('ch24_doc_fulltext', $search_term)
                    YIELD node, score
                    WHERE score >= $min_score
                    RETURN node.sectionId AS id,
                           node.text AS content,
                           node.title AS title,
                           score
                    ORDER BY score DESC
                    LIMIT $limit
                    """,
                    search_term=safe_query,
                    min_score=self.valves.min_relevance_score,
                    limit=self.valves.max_sections,
                )
                return [dict(r) for r in result]
        except Exception:
            return []

    def _assemble_context(self, sections: list[dict]) -> tuple[str, list[dict]]:
        """Deduplicate sections and build numbered context blocks."""
        seen = set()
        unique = []
        for s in sections:
            # Use sectionId (id) for dedup; fall back to uuid for backward compat
            dedup_key = s.get("id") or s.get("uuid") or s.get("title", "")
            if dedup_key and dedup_key not in seen:
                seen.add(dedup_key)
                unique.append(s)

        unique = unique[: self.valves.max_sections]
        if not unique:
            return "", []

        parts = []
        citations = []
        max_chars = self.valves.max_section_chars

        for i, s in enumerate(unique, 1):
            # New schema: use title directly; old schema fallback via source
            section_ref = s.get("title") or s.get("source", "Unknown")
            if "File: " in section_ref:
                section_ref = section_ref.split("File: ")[-1].replace(".docx", "").replace("_", " ")
            content = s.get("content", "")

            # Truncate long sections
            if len(content) > max_chars:
                content = content[:max_chars] + "\n[... section truncated ...]"

            parts.append(f"[G{i}] {section_ref}\n{content}")
            citations.append({
                "index": i,
                "section": section_ref,
                "content": content,
                "id": s.get("id", ""),
            })

        return "\n\n---\n\n".join(parts), citations

    def _enterprise_format_instructions(self) -> str:
        """Return graph-specific citation instructions.
        The main response structure, tone, and mindset are handled by the
        model's system prompt (system_prompt.md). This method only adds
        citation mechanics specific to graph-retrieved context."""
        if not self.valves.enterprise_format:
            return ""
        return """

GRAPH CITATION INSTRUCTIONS:
- The sections above were retrieved from a Neo4j knowledge graph via entity bridging.
- Cite them as [G1], [G2], etc. throughout your response.
- If Knowledge Base context is also present, cite KB sections with their existing markers and use BOTH sources.
- Every factual claim about a regulation MUST have a citation.
- Quote exact statutory language for numerical limits, deadlines, or definitions.
- If you cannot find a citation for a claim, say: "Not found in retrieved sections — verify with full code text."
- Start your answer with: "**[GraphRAG + KB]**" if you used both graph and KB context, or "**[GraphRAG]**" if only graph context was available."""

    def _build_disclaimer(self) -> str:
        """Build a color-coded confidence disclaimer using inline HTML.

        Renders a styled banner at the bottom of each response with:
          - A colored left-border block (green / amber / red) based on confidence band
          - The confidence badge line (Option B: colored inline label)
          - A plain-language explanation tailored to the band
          - Section references and actionable guidance

        Three states:
          HIGH confidence (≥70%) + full retrieval → green, confident footer
          MEDIUM confidence (45–69%) or partial   → amber, acknowledges possible gaps
          LOW confidence (<45%) or ≤1 section     → red, honest about limitations
        """
        score = self._confidence_score
        band = self._confidence_band
        pct = int(score * 100)
        n_sections = len(self._citations) if self._citations else 0
        max_sections = self.valves.max_sections

        # Build section reference string
        if n_sections > 1:
            section_refs = f"Sections [G1]\u2013[G{n_sections}]"
        elif n_sections == 1:
            section_refs = "Section [G1]"
        else:
            section_refs = ""

        # ── Band-specific colour and content ──
        if band == "HIGH" and n_sections >= max_sections:
            color = "#27AE60"       # green
            bg = "#f0faf0"
            dark_bg = "rgba(39,174,96,0.08)"
            label = "HIGH CONFIDENCE"
            body = (
                f"This response is well-supported by {n_sections} cited regulatory sections"
                f"{(' (' + section_refs + ')') if section_refs else ''}. "
                f"Review cited sections for your specific facility context."
            )
        elif band == "LOW" or n_sections <= 1:
            color = "#C0392B"       # red
            bg = "#fdf0ef"
            dark_bg = "rgba(192,57,43,0.08)"
            label = "LOW CONFIDENCE"
            hint = (
                " Provide more specific details about your compliance question for a stronger analysis."
                if n_sections <= 1
                else ""
            )
            body = (
                f"Limited regulatory context was retrieved for this query. "
                f"Verify this analysis against the full Chapter 24 text.{hint}"
            )
        else:
            color = "#E67E22"       # amber
            bg = "#fef8f0"
            dark_bg = "rgba(230,126,34,0.08)"
            label = "MODERATE CONFIDENCE"
            body = (
                f"This response is partially supported. Some applicable sections may not "
                f"have been retrieved. Cross-check critical requirements against the full "
                f"regulation text for completeness."
            )

        # ── Assemble the markdown banner ──
        if band == "HIGH":
            emoji = "\U0001f7e2"   # green circle
        elif band == "LOW":
            emoji = "\U0001f534"   # red circle
        else:
            emoji = "\U0001f7e0"   # orange circle

        return (
            f"\n\n---\n\n"
            f"> {emoji} **{label} ({pct}%)** \u2014 RegOS regulatory analysis \u2014 Miami-Dade Chapter 24\n"
            f">\n"
            f"> {body}"
        )

    # ── THRESHOLD EVALUATION (embedded — no tool-calling needed) ──

    # Parameter aliases: maps common names/abbreviations to the canonical
    # parameter name used in regulatory_thresholds.json
    _PARAM_ALIASES = {
        "bod": "Biochemical oxygen demand (BOD)",
        "biochemical oxygen demand": "Biochemical oxygen demand (BOD)",
        "tss": "Suspended solids",
        "suspended solids": "Suspended solids",
        "dissolved oxygen": "Dissolved oxygen",
        "temperature": "Temperature",
        "ph": "pH",
        "oil and grease": "Oil and grease",
        "fog": "Oil and Grease - FOG Generators",
        "fats oils and grease": "Oil and Grease - FOG Generators",
        "copper": "Copper",
        "lead": "Lead",
        "zinc": "Zinc",
        "chromium": "Chromium (Total)",
        "nickel": "Nickel",
        "cyanide": "Cyanides",
        "cyanides": "Cyanides",
        "turbidity": "Turbidity",
        "treatment efficiency": "Treatment efficiency",
        "nitrogen": "Total nitrogen",
        "total nitrogen": "Total nitrogen",
        "phosphorus": "Phosphorus (Total)",
        "total phosphorus": "Phosphorus (Total)",
        "chlorine": "Chlorine residual",
        "chlorine residual": "Chlorine residual",
        "arsenic": "Arsenic",
        "cadmium": "Cadmium",
        "mercury": "Mercury",
        "silver": "Silver",
        "fluoride": "Fluoride",
        "iron": "Iron",
        "manganese": "Manganese",
        "phenols": "Phenols",
    }

    # ── FACILITY CONTEXT DISAMBIGUATION ──────────────────────────
    # Maps section_ref prefixes to facility type labels and keywords
    # that, if present in the user's query, auto-select that context.
    _FACILITY_CONTEXTS = {
        "24_42.1": {
            "label": "Tertiary treatment plant effluent",
            "short": "tertiary effluent",
            "keywords": [
                "tertiary", "treatment plant", "effluent plant",
                "sewage plant", "wastewater plant", "wwtp",
                "nutrient removal", "tertiary treatment",
            ],
        },
        "24_42": {
            "label": "General surface water discharge",
            "short": "surface water discharge",
            "keywords": [
                "surface water", "river", "canal", "creek",
                "lake", "bay", "ocean", "waterway", "discharge to water",
                "receiving water", "outfall",
            ],
        },
        "24_42.4": {
            "label": "Industrial pretreatment (sewer discharge)",
            "short": "industrial pretreatment",
            "keywords": [
                "industrial", "pretreatment", "sewer", "potw",
                "publicly owned", "sanitary sewer", "siu",
                "significant industrial user", "trade waste",
                "industrial discharge", "factory", "manufacturing",
            ],
        },
    }

    _UNIT_PATTERN = re.compile(
        r'(mg/[lL]|mg/L|%|°[FC]|degrees?\s*[FC]|NTU|ppm|mg\s+per\s+liter)',
        re.IGNORECASE,
    )

    def _detect_threshold_query(self, query: str) -> list[dict]:
        """Detect numeric measurements + parameter names in the query.

        Uses a two-step approach:
          1. Scan for known parameter aliases in the query text
          2. Find all numbers with optional units
          3. Pair each parameter with its nearest number (within 120 chars)

        Returns list of {parameter, value, unit} dicts.
        """
        query_lower = query.lower()

        # Step 1: Find parameter mentions (longest-first to avoid partial matches)
        found_params = []
        for alias in sorted(self._PARAM_ALIASES.keys(), key=len, reverse=True):
            pos = query_lower.find(alias)
            if pos != -1:
                # Avoid double-matching (e.g., "bod" inside "biochemical oxygen demand")
                already_covered = False
                for _, _, existing_pos, existing_len in found_params:
                    if pos >= existing_pos and pos < existing_pos + existing_len:
                        already_covered = True
                        break
                if not already_covered:
                    canonical = self._PARAM_ALIASES[alias]
                    found_params.append((alias, canonical, pos, len(alias)))

        if not found_params:
            return []

        # Step 2: Find all numbers with optional units
        number_pattern = re.compile(
            r'(\d+\.?\d*)\s*(mg/[lL]|mg/L|%|°[FC]|NTU|ppm)?',
            re.IGNORECASE,
        )
        numbers = [
            (m.group(1), m.group(2), m.start())
            for m in number_pattern.finditer(query)
        ]

        if not numbers:
            return []

        # Step 3: Pair each parameter with its closest number
        detections = []
        used_numbers = set()

        for alias, canonical, param_pos, _ in found_params:
            best_num = None
            best_dist = float('inf')
            for i, (val, unit, num_pos) in enumerate(numbers):
                if i in used_numbers:
                    continue
                dist = abs(num_pos - param_pos)
                if dist < best_dist:
                    best_dist = dist
                    best_num = (val, unit, i)

            if best_num and best_dist < 120:
                val, unit, idx = best_num
                used_numbers.add(idx)
                # Normalize unit
                norm_unit = None
                if unit:
                    u = unit.lower().strip()
                    if u in ("mg/l",):
                        norm_unit = "mg/l"
                    elif u == "%":
                        norm_unit = "%"
                    elif u in ("°f", "degrees f"):
                        norm_unit = "°F"
                    elif u in ("°c", "degrees c"):
                        norm_unit = "°C"
                    elif u == "ntu":
                        norm_unit = "NTU"
                    elif u == "ppm":
                        norm_unit = "mg/l"  # ppm ≈ mg/l for water
                    else:
                        norm_unit = unit

                detections.append({
                    "parameter": canonical,
                    "value": float(val),
                    "unit": norm_unit,
                })

        return detections

    def _load_thresholds(self) -> list[dict]:
        """Lazy-load the regulatory thresholds JSON file."""
        if self._threshold_service_cache is not None:
            return self._threshold_service_cache

        try:
            path = self.valves.thresholds_path
            with open(path) as f:
                raw = json.load(f)
            entries = []
            for item in raw:
                try:
                    entries.append({
                        "value": float(str(item["value"]).replace(",", "")),
                        "value_raw": item["value"],
                        "unit": item["unit"],
                        "parameter": item["parameter"],
                        "direction": item["direction"],
                        "context": item["context"],
                        "section_ref": item["section_ref"],
                        "type": item["type"],
                    })
                except (ValueError, KeyError):
                    continue
            self._threshold_service_cache = entries
        except Exception:
            self._threshold_service_cache = []

        return self._threshold_service_cache

    def _evaluate_thresholds(
        self,
        detections: list[dict],
        user_id: str = "",
        chat_id: str = "",
        query: str = "",
    ) -> list[dict]:
        """Evaluate detected measurements against regulatory thresholds.

        For each detection {parameter, value, unit}, finds matching thresholds
        and returns determinations with SHA-256 evidence hashes.
        """
        thresholds = self._load_thresholds()
        if not thresholds:
            return []

        all_determinations = []
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        for det in detections:
            param = det["parameter"]
            value = det["value"]
            unit = det.get("unit")
            param_lower = param.lower()

            # Find matching thresholds (fuzzy match on parameter name)
            matches = [
                t for t in thresholds
                if param_lower in t["parameter"].lower()
                or t["parameter"].lower() in param_lower
            ]

            if not matches:
                all_determinations.append({
                    "status": "NO_THRESHOLD_FOUND",
                    "parameter": param,
                    "user_value": value,
                    "user_unit": unit,
                    "message": f"No regulatory threshold found for '{param}' in Chapter 24.",
                })
                continue

            # Filter by unit compatibility first
            compatible = [
                t for t in matches
                if not unit or unit.lower() == t["unit"].lower()
            ]
            if not compatible:
                compatible = matches  # fall back to all matches

            # ── FACILITY CONTEXT DISAMBIGUATION ────────────────────────
            # When multiple thresholds match the same parameter+direction+unit
            # from DIFFERENT sections, try to auto-detect the facility context
            # from the user's query. If ambiguous, return NEEDS_CLARIFICATION
            # so the LLM asks the user which context applies.
            grouped: dict[str, list] = {}
            for t in compatible:
                key = f"{t['direction']}|{t['unit']}"
                grouped.setdefault(key, []).append(t)

            primary_thresholds = []

            for key, group in grouped.items():
                if len(group) == 1:
                    primary_thresholds.append(group[0])
                else:
                    # Multiple thresholds for same param+direction+unit
                    # Try to disambiguate via context keywords in the query
                    resolved = self._disambiguate_thresholds(group, query)
                    if resolved is not None:
                        # Auto-resolved — use the matched threshold, note alternates
                        others = [t for t in group if t is not resolved]
                        resolved["_alternate_limits"] = [
                            {
                                "value_raw": a["value_raw"],
                                "value": a["value"],
                                "unit": a["unit"],
                                "section_ref": a["section_ref"],
                                "context": a["context"],
                            }
                            for a in others
                        ]
                        primary_thresholds.append(resolved)
                    else:
                        # Ambiguous — can't determine which limit applies.
                        # Return a NEEDS_CLARIFICATION determination.
                        options = []
                        for t in group:
                            ctx = self._FACILITY_CONTEXTS.get(t["section_ref"], {})
                            label = ctx.get("label", f"Sec. {t['section_ref']}")
                            options.append({
                                "section_ref": t["section_ref"],
                                "label": label,
                                "value_raw": t["value_raw"],
                                "unit": t["unit"],
                                "context": t["context"],
                            })
                        all_determinations.append({
                            "status": "NEEDS_CLARIFICATION",
                            "parameter": param,
                            "user_value": value,
                            "user_unit": unit,
                            "options": options,
                        })
                        # Skip evaluation for this group — LLM will ask user
                        continue

            for t in primary_thresholds:
                # Skip unit mismatches (but allow if user didn't specify unit)
                if unit and unit.lower() != t["unit"].lower():
                    continue

                # Evaluate
                if t["direction"] == "max":
                    margin = t["value"] - value
                    status = "COMPLIANT" if value <= t["value"] else "BREACH"
                    if status == "COMPLIANT" and 0 < margin <= (t["value"] * 0.10):
                        status = "BORDERLINE"
                elif t["direction"] == "min":
                    margin = value - t["value"]
                    status = "COMPLIANT" if value >= t["value"] else "BREACH"
                    if status == "COMPLIANT" and 0 < margin <= (t["value"] * 0.10):
                        status = "BORDERLINE"
                elif t["direction"] == "exact":
                    margin = 0.0
                    status = "COMPLIANT" if abs(value - t["value"]) < 0.001 else "BREACH"
                else:
                    margin = t["value"] - value
                    status = "COMPLIANT" if value <= t["value"] else "BREACH"

                pct = round(value / t["value"] * 100, 1) if t["value"] != 0 else 0

                determination = {
                    "parameter": t["parameter"],
                    "user_value": value,
                    "user_unit": unit or t["unit"],
                    "threshold_value": t["value"],
                    "threshold_value_raw": t["value_raw"],
                    "threshold_direction": t["direction"],
                    "threshold_unit": t["unit"],
                    "section_ref": t["section_ref"],
                    "status": status,
                    "margin": round(margin, 4),
                    "pct_of_limit": pct,
                    "context": t["context"],
                    "timestamp": timestamp,
                    "alternate_limits": t.get("_alternate_limits", []),
                }

                # SHA-256 evidence hash
                canonical = json.dumps({
                    "parameter": determination["parameter"],
                    "user_value": determination["user_value"],
                    "threshold_value": determination["threshold_value"],
                    "threshold_direction": determination["threshold_direction"],
                    "threshold_unit": determination["threshold_unit"],
                    "status": determination["status"],
                    "timestamp": determination["timestamp"],
                    "section_ref": determination["section_ref"],
                }, sort_keys=True, separators=(",", ":"))
                determination["evidence_hash"] = hashlib.sha256(canonical.encode()).hexdigest()

                # Log to breach DB
                self._log_to_breach_db(determination, user_id, chat_id, query)

                all_determinations.append(determination)

        return all_determinations

    def _disambiguate_thresholds(self, group: list[dict], query: str):
        """Try to auto-select the correct threshold from a group of duplicates.

        Scans the user's query for facility-context keywords. If exactly one
        section matches, returns that threshold. If zero or multiple match,
        returns None (ambiguous → needs clarification).
        """
        query_lower = query.lower()
        matched_sections = []

        for t in group:
            section_ref = t["section_ref"]
            ctx = self._FACILITY_CONTEXTS.get(section_ref)
            if not ctx:
                continue
            for kw in ctx["keywords"]:
                if kw in query_lower:
                    matched_sections.append(t)
                    break  # found a match for this section, move on

        if len(matched_sections) == 1:
            return matched_sections[0]
        return None  # ambiguous or no context clues

    def _build_conversation_context(self, messages: list[dict]) -> str:
        """Build a combined context string from the full conversation history.

        Extracts the raw user text from all user messages (stripping any
        injected graph context) and joins them. This gives downstream
        functions (threshold detection, disambiguation, graph search) access
        to the full conversational context — not just the latest message.

        Returns a single string combining all user messages in order.
        """
        user_texts = []
        for msg in messages:
            if msg.get("role") != "user":
                continue
            content = msg.get("content", "")
            if isinstance(content, list):
                content = " ".join(
                    p.get("text", "")
                    for p in content
                    if isinstance(p, dict) and p.get("type") == "text"
                )
            if not isinstance(content, str):
                continue
            # Strip any previously injected graph context
            raw = content.split("\n---\n[GRAPH KNOWLEDGE CONTEXT")[0].strip()
            if raw:
                user_texts.append(raw)
        return " ".join(user_texts)

    def _log_to_breach_db(self, det: dict, user_id: str, chat_id: str, query: str):
        """Log a threshold evaluation to the breach SQLite database."""
        try:
            conn = sqlite3.connect(self.valves.breach_db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS threshold_evaluations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    user_id TEXT,
                    chat_id TEXT,
                    parameter TEXT NOT NULL,
                    user_value REAL NOT NULL,
                    threshold_value REAL NOT NULL,
                    threshold_direction TEXT NOT NULL,
                    threshold_unit TEXT NOT NULL,
                    section_ref TEXT NOT NULL,
                    status TEXT NOT NULL,
                    margin REAL,
                    pct_of_limit REAL,
                    context TEXT,
                    evidence_hash TEXT NOT NULL,
                    query_text TEXT
                )
            """)
            conn.execute("""
                INSERT INTO threshold_evaluations
                (timestamp, user_id, chat_id, parameter, user_value,
                 threshold_value, threshold_direction, threshold_unit,
                 section_ref, status, margin, pct_of_limit, context,
                 evidence_hash, query_text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                det["timestamp"],
                user_id,
                chat_id,
                det["parameter"],
                det["user_value"],
                det["threshold_value"],
                det["threshold_direction"],
                det["threshold_unit"],
                det["section_ref"],
                det["status"],
                det["margin"],
                det["pct_of_limit"],
                det.get("context", ""),
                det["evidence_hash"],
                query,
            ))
            conn.commit()
            conn.close()
        except Exception:
            pass  # Non-fatal

    def _build_threshold_context(self, determinations: list[dict]) -> str:
        """Build the threshold evaluation context block for LLM injection.

        This is injected alongside the graph context so the LLM can
        reference the programmatic determination in its response.
        """
        if not determinations:
            return ""

        lines = [
            "",
            "=== AUTOMATED THRESHOLD EVALUATION (RegOS Compliance Engine) ===",
            "",
            "RegOS has programmatically evaluated the measurement(s) in your query",
            "against Chapter 24 regulatory thresholds. These are EXACT determinations",
            "computed from the curated threshold table — NOT LLM interpretations.",
            "",
            "A structured Compliance Determination table will be appended automatically",
            "to your response — DO NOT duplicate it. Instead, your role is to:",
            "  1. Lead with a SHORT one-line verdict (e.g. 'Your BOD of 45 mg/L is non-compliant.')",
            "  2. Provide regulatory CONTEXT the table cannot: why this limit exists,",
            "     which facility types it applies to, related section cross-references,",
            "     and any treatment or corrective actions required.",
            "  3. DO NOT restate the exact threshold numbers, margins, or evidence hashes",
            "     in your narrative — the appended table already contains those.",
            "  4. Keep 'What You Need To Do' focused on actionable next steps.",
            "",
        ]

        for i, det in enumerate(determinations, 1):
            status = det.get("status", "UNKNOWN")

            # ── NEEDS_CLARIFICATION: multiple limits, can't determine which applies ──
            if status == "NEEDS_CLARIFICATION":
                lines.append(f"--- Clarification Needed for {det.get('parameter', '?')} ---")
                lines.append(f"  Measured Value:   {det.get('user_value', '?')} {det.get('user_unit', '')}")
                lines.append(f"")
                lines.append(f"  Multiple regulatory limits apply to this parameter depending on")
                lines.append(f"  the facility type. You MUST ask the user which context applies")
                lines.append(f"  BEFORE providing a compliance determination.")
                lines.append(f"")
                lines.append(f"  Ask the user to clarify which of the following applies:")
                for opt in det.get("options", []):
                    sec = opt["section_ref"].replace("_", "-")
                    lines.append(f"    - {opt['label']}: {opt['value_raw']} {opt['unit']} (Sec. {sec})")
                    lines.append(f"      \"{opt['context']}\"")
                lines.append(f"")
                lines.append(f"  DO NOT guess. DO NOT evaluate against any limit. DO NOT show a")
                lines.append(f"  Compliance Determination table. Simply present the options to the")
                lines.append(f"  user in a clear numbered list and ask which facility context applies.")
                lines.append(f"  Use the standard response format but replace the Summary with a")
                lines.append(f"  clarification request.")
                lines.append("")
                continue

            if status == "BREACH":
                icon = "BREACH"
            elif status == "BORDERLINE":
                icon = "BORDERLINE"
            elif status == "COMPLIANT":
                icon = "COMPLIANT"
            else:
                icon = status

            lines.append(f"--- Determination #{i} ---")
            lines.append(f"  Parameter:       {det.get('parameter', '?')}")
            lines.append(f"  Measured Value:   {det.get('user_value', '?')} {det.get('user_unit', det.get('threshold_unit', ''))}")
            lines.append(f"  Regulatory Limit: {det.get('threshold_value_raw', det.get('threshold_value', '?'))} {det.get('threshold_unit', '')} ({det.get('threshold_direction', '?')})")
            lines.append(f"  Status:           {icon}")
            lines.append(f"  Margin:           {det.get('margin', '?')} {det.get('threshold_unit', '')} ({'within limit' if det.get('margin', 0) >= 0 else 'exceeds limit by ' + str(abs(det.get('margin', 0)))})")
            lines.append(f"  % of Limit:       {det.get('pct_of_limit', '?')}%")
            lines.append(f"  Section:          {det.get('section_ref', '?')}")
            lines.append(f"  Regulatory Text:  \"{det.get('context', '')}\"")
            lines.append(f"  Evidence Hash:    {det.get('evidence_hash', 'N/A')}")

            alts = det.get("alternate_limits", [])
            if alts:
                alt_strs = [f"{a['value_raw']} {a['unit']} (Sec. {a['section_ref']})" for a in alts]
                lines.append(f"  Other Limits:     {', '.join(alt_strs)} — different facility class")
                lines.append(f"  NOTE: The selected limit was auto-detected from your query context.")
                lines.append(f"  Mention that different limits apply for other facility types.")

            lines.append("")

        lines.append("Do NOT include evidence hashes in your narrative text — they")
        lines.append("are already shown in the appended Compliance Determination table.")
        lines.append("")

        return "\n".join(lines)

    def _build_compliance_badge(self, determinations: list[dict]) -> str:
        """Build the compliance determination badge appended in the outlet.

        Shows a structured summary with status, limits, and evidence hash.
        """
        if not determinations:
            return ""

        # Filter out NO_THRESHOLD_FOUND entries for the badge
        real_dets = [d for d in determinations if d.get("status") in ("BREACH", "BORDERLINE", "COMPLIANT")]
        if not real_dets:
            return ""

        lines = ["\n\n---\n**Compliance Determination**\n"]

        for det in real_dets:
            status = det["status"]
            if status == "BREACH":
                status_display = "BREACH"
                margin_note = f"exceeds limit by {abs(det['margin'])} {det['threshold_unit']}"
            elif status == "BORDERLINE":
                status_display = "BORDERLINE (Approaching Limit)"
                margin_note = f"within {det['margin']} {det['threshold_unit']} of limit"
            else:
                status_display = "COMPLIANT"
                margin_note = f"within limit by {det['margin']} {det['threshold_unit']}"

            direction_symbol = "≤" if det["threshold_direction"] == "max" else "≥" if det["threshold_direction"] == "min" else "="

            lines.append(f"| Field | Value |")
            lines.append(f"|---|---|")
            lines.append(f"| Parameter | {det['parameter']} |")
            lines.append(f"| Measured | {det['user_value']} {det.get('user_unit', det['threshold_unit'])} |")
            lines.append(f"| Limit | {direction_symbol} {det['threshold_value_raw']} {det['threshold_unit']} (Sec. {det['section_ref'].replace('_', '-')}) |")
            lines.append(f"| Status | **{status_display}** — {margin_note} ({det['pct_of_limit']}% of limit) |")
            lines.append(f"| Evidence Hash | `{det['evidence_hash'][:16]}...` |")

            # Show alternate (less strict) limits as a note
            alts = det.get("alternate_limits", [])
            if alts:
                alt_notes = ", ".join(
                    f"{a['value_raw']} {a['unit']} (Sec. {a['section_ref'].replace('_', '-')})"
                    for a in alts
                )
                lines.append(f"| Other Limits | {alt_notes} — applies to different facility class |")

            lines.append("")

        lines.append("*This determination was computed programmatically from Chapter 24 regulatory thresholds and recorded with a SHA-256 evidence hash for audit verification.*")

        return "\n".join(lines)

    # ── GUARDRAIL METHODS ──────────────────────────────────────

    def _check_out_of_scope(self, query: str) -> tuple[bool, str]:
        """Check if the query mentions topics clearly outside Chapter 24.

        Returns (triggered: bool, reason: str).
        Uses the configurable exclusion keywords list from Valves.
        """
        if not self.valves.guardrail_exclusion_keywords:
            return False, ""

        query_lower = query.lower()
        keywords = [k.strip().lower() for k in self.valves.guardrail_exclusion_keywords.split(",") if k.strip()]

        matched = []
        for kw in keywords:
            if kw in query_lower:
                matched.append(kw)

        if matched:
            return True, f"Query references topics outside Chapter 24 scope: {', '.join(matched)}"
        return False, ""

    def _check_zero_retrieval(self, entities: list, sections: list) -> tuple[bool, str]:
        """Check if both entity search and section search returned nothing.

        Returns (triggered: bool, reason: str).
        This indicates the query has no connection to any Chapter 24 content.
        """
        if len(entities) == 0 and len(sections) == 0:
            return True, "No regulatory entities or sections found — query has no connection to Chapter 24 content"
        return False, ""

    # Built-in location lists for jurisdiction mismatch detection.
    # These are checked against the query text (case-insensitive).
    _FOREIGN_COUNTRIES = [
        "saudi arabia", "canada", "mexico", "united kingdom", "uk", "china",
        "india", "germany", "france", "japan", "australia", "brazil", "italy",
        "south korea", "spain", "russia", "nigeria", "south africa", "egypt",
        "indonesia", "pakistan", "turkey", "argentina", "colombia", "uae",
        "dubai", "qatar", "kuwait", "bahrain", "oman", "iraq", "iran",
        "philippines", "vietnam", "thailand", "malaysia", "singapore",
        "new zealand", "ireland", "scotland", "wales", "netherlands",
        "belgium", "switzerland", "austria", "sweden", "norway", "denmark",
        "finland", "portugal", "greece", "poland", "czech republic",
        "hungary", "romania", "chile", "peru", "venezuela", "ecuador",
        "kenya", "ghana", "tanzania", "ethiopia", "morocco", "tunisia",
    ]

    _US_STATES_EXCEPT_FL = [
        "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
        "connecticut", "delaware", "georgia", "hawaii", "idaho", "illinois",
        "indiana", "iowa", "kansas", "kentucky", "louisiana", "maine",
        "maryland", "massachusetts", "michigan", "minnesota", "mississippi",
        "missouri", "montana", "nebraska", "nevada", "new hampshire",
        "new jersey", "new mexico", "new york", "north carolina",
        "north dakota", "ohio", "oklahoma", "oregon", "pennsylvania",
        "rhode island", "south carolina", "south dakota", "tennessee",
        "texas", "utah", "vermont", "virginia", "washington", "west virginia",
        "wisconsin", "wyoming",
    ]

    def _check_jurisdiction_mismatch(self, query: str) -> tuple[bool, str]:
        """Check if the query explicitly references a location outside Miami-Dade.

        Returns (triggered: bool, reason: str).

        Detection strategy:
        1. If query mentions an allowlisted term (miami, dade county, etc.),
           it's in-jurisdiction — return False immediately.
        2. If query mentions a foreign country, a US state other than Florida,
           or a custom blocklisted term — flag as jurisdiction mismatch.

        This is a text-based heuristic, not entity metadata inspection.
        It runs on the raw query BEFORE graph search.
        """
        if not self.valves.guardrail_jurisdiction_enabled:
            return False, ""

        query_lower = query.lower()

        # Step 1: Check allowlist — if Miami-Dade related terms are present, pass through
        allowlist = [
            t.strip().lower()
            for t in self.valves.guardrail_jurisdiction_allowlist.split(",")
            if t.strip()
        ]
        for term in allowlist:
            if term in query_lower:
                return False, ""

        # Step 2: Check foreign countries
        matched_locations = []
        for country in self._FOREIGN_COUNTRIES:
            if country in query_lower:
                matched_locations.append(country.title())

        # Step 3: Check US states (except Florida)
        for state in self._US_STATES_EXCEPT_FL:
            if state in query_lower:
                matched_locations.append(state.title())

        # Step 4: Check custom blocklist
        if self.valves.guardrail_jurisdiction_blocklist.strip():
            blocklist = [
                t.strip().lower()
                for t in self.valves.guardrail_jurisdiction_blocklist.split(",")
                if t.strip()
            ]
            for term in blocklist:
                if term in query_lower:
                    matched_locations.append(term.title())

        if matched_locations:
            locations_str = ", ".join(sorted(set(matched_locations)))
            return True, (
                f"Query references a jurisdiction outside Miami-Dade County: {locations_str}. "
                f"Chapter 24 applies only to Miami-Dade County, Florida."
            )

        return False, ""

    def _generate_guardrail_ref(self, user_id: str = "", chat_id: str = "") -> str:
        """Generate a guardrail reference ID.

        Format: GRD-YYYYMMDD-XXXX (same pattern as escalation case refs).
        """
        date_str = time.strftime("%Y%m%d", time.gmtime())
        hash_input = f"grd:{user_id}:{chat_id}:{time.time()}"
        short_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:4].upper()
        return f"GRD-{date_str}-{short_hash}"

    def _build_guardrail_notice(self) -> str:
        """Build a structured guardrail notice appended to the response.

        Replaces the confidence disclaimer when a guardrail triggers.
        Uses professional enterprise wording with customer service contact.
        """
        if self._guardrail_type == "out_of_scope":
            title = "Outside Regulatory Scope"
            body = (
                "RegOS identified this question as outside its current scope. "
                "RegOS is designed to support compliance with Miami-Dade County Chapter 24 "
                "(Environmental Quality Control Board) and does not cover the topic referenced "
                "in your query."
            )
            next_steps = (
                "If your question relates to Chapter 24, try rephrasing with specific "
                "regulatory terms (e.g., effluent limits, pretreatment, discharge permits). "
                "For topics outside Chapter 24, consult the relevant regulatory authority directly."
            )
        elif self._guardrail_type == "jurisdiction":
            title = "Outside Applicable Jurisdiction"
            body = (
                "RegOS identified this question as referencing a jurisdiction outside "
                "Miami-Dade County, Florida. Chapter 24 of the Miami-Dade County Code "
                "applies exclusively to facilities and operations within Miami-Dade County "
                "and cannot be used to determine compliance requirements for other locations."
            )
            next_steps = (
                "For regulatory requirements in the referenced jurisdiction, contact the "
                "appropriate local environmental or regulatory authority. If your question "
                "does involve a Miami-Dade County facility, try rephrasing without the "
                "external location reference."
            )
        elif self._guardrail_type == "zero_retrieval":
            title = "No Regulatory Context Found"
            body = (
                "RegOS could not locate any Chapter 24 sections relevant to this query. "
                "This typically means the topic falls outside the scope of Chapter 24, "
                "or the question may need more specific regulatory terminology."
            )
            next_steps = (
                "Try rephrasing your question with specific Chapter 24 section references "
                "or regulatory terms such as effluent limits, pretreatment requirements, "
                "or discharge permit conditions."
            )
        elif self._guardrail_type == "neo4j_unavailable":
            title = "System Temporarily Unavailable"
            body = (
                "RegOS is currently unable to reach the regulatory knowledge graph. "
                "This is a temporary connectivity issue — the system cannot retrieve "
                "Chapter 24 sections until the connection is restored."
            )
            next_steps = (
                "Please try again in a few minutes. If the issue persists, contact "
                "your system administrator. Your question has been logged and can "
                "be re-submitted once the service is restored."
            )
        else:
            title = "Query Could Not Be Processed"
            body = "RegOS was unable to process this query within its regulatory scope."
            next_steps = (
                "Try rephrasing your question to focus on Chapter 24 compliance requirements."
            )

        ref_line = ""
        if self._guardrail_ref:
            ref_line = f"  \nRef: {self._guardrail_ref}"

        # Build contact line — use configured contact or generic fallback
        contact = self.valves.guardrail_support_contact.strip()
        if contact:
            contact_line = (
                f"If you believe this determination is incorrect, please contact "
                f"our support team at {contact} for further assistance."
            )
        else:
            contact_line = (
                "If you believe this determination is incorrect, please contact "
                "our support team for further assistance."
            )

        return (
            f"\n\n---\n"
            f"**{title}**\n\n"
            f"{body}\n\n"
            f"**Next steps:** {next_steps}\n\n"
            f"{contact_line}"
            f"{ref_line}"
        )

    # ── ESCALATION METHODS ─────────────────────────────────────

    def _should_escalate(self) -> bool:
        """Determine whether the current query should be flagged for expert review.

        Triggers when:
          - Confidence score is below the escalation threshold
          - Zero sections were retrieved (no regulatory context at all)
          - Confidence band is LOW regardless of exact score
        """
        if not self.valves.escalation_enabled:
            return False
        if self._confidence_score is None:
            return False

        n_sections = len(self._citations) if self._citations else 0

        # Zero retrieval — always escalate
        if n_sections == 0:
            return True

        # Below configured threshold
        if self._confidence_score < self.valves.escalation_threshold:
            return True

        # LOW band (catches edge cases where threshold was raised above 0.5)
        if self._confidence_band == "LOW":
            return True

        return False

    def _escalation_reason(self) -> str:
        """Return a human-readable explanation of why escalation triggered."""
        n_sections = len(self._citations) if self._citations else 0
        pct = int(self._confidence_score * 100)

        if n_sections == 0:
            return "No regulatory sections retrieved for this query"

        # Check which signals were weakest
        if self._confidence_signals:
            signals = self._confidence_signals
            weak = []
            if signals.get("entity_count", 0) <= 2:
                weak.append("weak entity matching")
            if signals.get("final_section_count", 0) <= 1:
                weak.append("sparse section retrieval")
            max_overlap = 0
            counts = signals.get("section_entity_counts", [])
            if counts:
                max_overlap = max(counts)
            if max_overlap <= 1:
                weak.append("weak graph bridging")

            if weak:
                return f"Low retrieval confidence ({pct}%): {', '.join(weak)}"

        return f"Low overall retrieval confidence ({pct}%)"

    def _generate_case_ref(self, user_id: str = "", chat_id: str = "") -> str:
        """Generate a deterministic, human-readable case reference.

        Format: REG-YYYYMMDD-XXXX where XXXX is a 4-char hex derived from
        a hash of user_id + chat_id + epoch to avoid collisions.
        """
        date_str = time.strftime("%Y%m%d", time.gmtime())
        hash_input = f"{user_id}:{chat_id}:{time.time()}"
        short_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:4].upper()
        return f"REG-{date_str}-{short_hash}"

    def _build_escalation_notice(self, case_ref: str, user_email: str = "") -> str:
        """Build a structured escalation notice that replaces the disclaimer.

        Includes case reference, status, and contact email for follow-up.
        """
        contact_line = ""
        if user_email:
            contact_line = (
                f"\n**Contact:** We'll reach out to you at {user_email} once our review is complete."
                f"\n\n*If this isn't your preferred contact email, please update your Open WebUI profile.*"
            )

        return (
            f"\n\n---\n"
            f"**Expert Review Initiated**\n\n"
            f"This analysis has been flagged for compliance review due to limited regulatory context.\n\n"
            f"**Case:** {case_ref} | **Status:** Under review"
            f"{contact_line}"
        )

    def _build_case_packet(
        self,
        case_ref: str,
        reason: str,
        user_info: dict,
        query: str,
        response: str,
        messages: list[dict] = None,
        chat_id: str = "",
        message_id: str = "",
        model: str = "",
    ) -> dict:
        """Build the full case packet JSON for the n8n webhook.

        Includes complete context for the reviewer / AI summarizer:
        - Full conversation history (all messages in the chat session)
        - GraphRAG citations with full section text
        - KB sources (if present on the assistant message)
        - Entity matches from graph search
        - Assembled graph context that was injected into the LLM
        """
        # ── Conversation history (clean, no injected graph context) ──
        conversation_history = []
        if messages:
            for msg in messages:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                if isinstance(content, str):
                    # Strip injected graph context from user messages
                    marker = "\n\n---\n[GRAPH KNOWLEDGE CONTEXT"
                    idx = content.find(marker)
                    if idx != -1:
                        content = content[:idx].strip()
                elif isinstance(content, list):
                    content = " ".join(
                        p.get("text", "")
                        for p in content
                        if isinstance(p, dict) and p.get("type") == "text"
                    )
                if content and role in ("user", "assistant", "system"):
                    conversation_history.append({"role": role, "content": content})

        # ── KB sources (from the assistant message's sources list) ──
        kb_sources = []
        if messages:
            for msg in reversed(messages):
                if msg.get("role") == "assistant" and "sources" in msg:
                    for src in msg["sources"]:
                        # Skip GraphRAG sources (we have those in citations)
                        src_id = (src.get("source") or {}).get("id", "")
                        if src_id.startswith("graphrag_"):
                            continue
                        kb_sources.append({
                            "name": (src.get("source") or {}).get("name", "Unknown"),
                            "content": (src.get("document") or [""])[0][:2000],
                        })
                    break

        return {
            "case_ref": case_ref,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "user": {
                "id": user_info.get("id", ""),
                "email": user_info.get("email", ""),
                "name": user_info.get("name", ""),
                "role": user_info.get("role", ""),
            },
            "query": query,
            "response": response,
            "confidence": {
                "score": self._confidence_score,
                "band": self._confidence_band,
                "signals": self._confidence_signals,
            },
            "escalation": {
                "reason": reason,
                "target": self.valves.escalation_target,
                "threshold": self.valves.escalation_threshold,
            },
            "conversation_history": conversation_history,
            "retrieval_context": {
                "graphrag_citations": [
                    {
                        "index": c["index"],
                        "section": c["section"],
                        "content": c.get("content", ""),
                    }
                    for c in (self._citations or [])
                ],
                "kb_sources": kb_sources,
                "entity_matches": self._entity_matches or [],
                "graph_context_injected": self._graph_context or "",
            },
            "context": {
                "chat_id": chat_id,
                "message_id": message_id,
                "model": model,
            },
        }

    def _send_escalation_webhook(self, case_packet: dict) -> dict | None:
        """POST case packet to the configured n8n webhook.

        Returns the parsed JSON response or None on failure.
        Fire-and-forget — never blocks the chat if n8n is down.
        """
        if not self.valves.escalation_webhook_url:
            return None
        try:
            data = json.dumps(case_packet, default=str).encode("utf-8")
            req = urllib.request.Request(
                self.valves.escalation_webhook_url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read().decode())
        except Exception:
            return None

    def _extract_last_user_query(self, messages: list[dict]) -> str:
        """Extract the last user message text from the messages list."""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str):
                    # Strip the injected graph context if present
                    marker = "\n\n---\n[GRAPH KNOWLEDGE CONTEXT"
                    idx = content.find(marker)
                    return content[:idx].strip() if idx != -1 else content.strip()
                elif isinstance(content, list):
                    return " ".join(
                        p.get("text", "")
                        for p in content
                        if isinstance(p, dict) and p.get("type") == "text"
                    ).strip()
        return ""

    # ── SYSTEM PROMPT ─────────────────────────────────────────

    def _build_system_prompt(self, context: str, citations: list[dict], debug_info: dict = None, confidence: tuple = None) -> str:
        """Build the system prompt with regulatory context."""
        citation_refs = "\n".join(f"  [G{c['index']}] {c['section']}" for c in citations)

        match_names = []
        if debug_info and "doc_matches" in debug_info:
            match_names = debug_info["doc_matches"]
        elif debug_info and "entity_matches" in debug_info:
            match_names = debug_info["entity_matches"]

        conf_line = ""
        if confidence:
            conf_score, conf_band = confidence
            conf_line = f"\nRetrieval confidence: {conf_band} ({conf_score})"
            if conf_band == "LOW":
                conf_line += " — retrieval quality is low; hedge your answer and recommend the user verify with the original regulation text."

        prompt = f"""=== GRAPH-RETRIEVED REGULATORY CONTEXT (Neo4j Knowledge Graph) ===

The following regulatory sections were retrieved from the Neo4j knowledge graph
by matching your question against 141 Ch24Document sections, 455 Ch24Entity nodes,
and 97 Ch24Class ontology concepts in the Chapter 24 FEA knowledge graph.

Graph sections matched: {', '.join(match_names) if match_names else 'N/A'}{conf_line}

CITATION RULES:
1. Cite these sections using [G1], [G2], etc. (G = graph-retrieved).
2. Quote exact regulatory language for requirements, limits, or definitions.
3. If you also have Knowledge Base context, use BOTH sources and cite each appropriately.
{self._enterprise_format_instructions()}

GRAPH-RETRIEVED SECTIONS:
{context}

GRAPH REFERENCES:
{citation_refs}"""

        if self.valves.debug and debug_info:
            prompt += f"\n\n[GRAPHRAG DEBUG: doc_matches={debug_info.get('doc_matches','?')}, sections={debug_info.get('sections_found','?')}, time={debug_info.get('retrieval_ms','?')}ms]"

        return prompt

    async def inlet(
        self,
        body: dict,
        __user__: dict = None,
        __chat_id__: str = None,
        __message_id__: str = None,
        __session_id__: str = None,
        __metadata__: dict = None,
    ) -> dict:
        """
        Intercept the user's message, search Neo4j for relevant regulatory
        sections, and prepend a system message with the context.
        """
        if not self.valves.enabled:
            return body

        if not self.valves.neo4j_password:
            return body

        messages = body.get("messages", [])
        if not messages:
            return body

        # Extract user question
        last_msg = messages[-1]
        user_question = ""
        if isinstance(last_msg.get("content"), str):
            user_question = last_msg["content"]
        elif isinstance(last_msg.get("content"), list):
            user_question = " ".join(
                p.get("text", "")
                for p in last_msg["content"]
                if isinstance(p, dict) and p.get("type") == "text"
            )

        if not user_question.strip():
            return body

        # ── DOCUMENT ANALYSIS (before guardrails — runs if files present) ──
        self._doc_analysis = None


        if self.valves.doc_analysis_enabled:
            try:
                doc_text = self._analyze_uploaded_files(
                    body, user_question, __user__=__user__, __metadata__=__metadata__,
                )
                if doc_text:
                    self._doc_analysis = doc_text
            except Exception as e:
                _doc_logger.error(f"[DOC-ANALYZER] Analysis failed: {e}")

        # ── GUARDRAIL: Reset state ──────────────────────────────────
        self._guardrail_triggered = False
        self._guardrail_type = None
        self._guardrail_reason = None
        self._guardrail_ref = None

        # ── GUARDRAIL: Out-of-scope keyword check (before graph search) ──
        if self.valves.guardrail_enabled:
            oos_triggered, oos_reason = self._check_out_of_scope(user_question)
            if oos_triggered:
                user_id = (__user__ or {}).get("id", "")
                chat_id = __chat_id__ or ""
                self._guardrail_triggered = True
                self._guardrail_type = "out_of_scope"
                self._guardrail_reason = oos_reason
                self._guardrail_ref = self._generate_guardrail_ref(user_id, chat_id)
                # Don't skip the LLM — let the system prompt handle the refusal naturally.
                # But skip the GraphRAG pipeline (no point searching for out-of-scope content).
                self._last_trace = None
                self._confidence_score = None
                self._confidence_band = None
                self._confidence_signals = None
                self._citations = None
                self._entity_matches = None
                self._graph_context = None
                # Still inject document analysis if present (form may be in-scope)
                if self._doc_analysis:
                    self._inject_doc_analysis_into_message(messages)
                    body["messages"] = messages
                return body

        # ── GUARDRAIL: Jurisdiction mismatch check (before graph search) ──
        if self.valves.guardrail_enabled:
            jur_triggered, jur_reason = self._check_jurisdiction_mismatch(user_question)
            if jur_triggered:
                user_id = (__user__ or {}).get("id", "")
                chat_id = __chat_id__ or ""
                self._guardrail_triggered = True
                self._guardrail_type = "jurisdiction"
                self._guardrail_reason = jur_reason
                self._guardrail_ref = self._generate_guardrail_ref(user_id, chat_id)
                self._last_trace = None
                self._confidence_score = None
                self._confidence_band = None
                self._confidence_signals = None
                self._citations = None
                self._entity_matches = None
                self._graph_context = None
                if self._doc_analysis:
                    self._inject_doc_analysis_into_message(messages)
                    body["messages"] = messages
                return body

        # ── BUILD CONVERSATION CONTEXT ─────────────────────────────────
        # Combine all user messages into a single context string so that
        # threshold detection, disambiguation, and graph search can leverage
        # the full conversation history — not just the latest message.
        conversation_context = self._build_conversation_context(messages)

        # ── THRESHOLD DETECTION (before graph search) ─────────────────
        self._threshold_determinations = None
        if self.valves.threshold_check_enabled:
            try:
                # Try current message first for measurements
                detections = self._detect_threshold_query(user_question)

                # If no measurements in the current message, scan the full
                # conversation history — the user may have stated a value
                # earlier and is now providing follow-up context.
                if not detections and len(messages) > 2:
                    detections = self._detect_threshold_query(conversation_context)

                if detections:
                    user_id = (__user__ or {}).get("id", "")
                    chat_id = __chat_id__ or ""
                    # Use conversation_context for disambiguation so keywords
                    # from ANY message in the chat can resolve ambiguous limits
                    self._threshold_determinations = self._evaluate_thresholds(
                        detections,
                        user_id=user_id,
                        chat_id=chat_id,
                        query=conversation_context,
                    )
            except Exception:
                pass  # Non-fatal — graph retrieval continues regardless

        # ── RETRIEVAL ────────────────────────────────────────────────
        # Use conversation_context for graph search when the current message
        # is short / contextual (e.g. "We're discharging into the canal")
        # so that earlier mentions of BOD, TSS, etc. still drive retrieval.
        search_query = user_question
        if len(user_question.split()) < 8 and len(messages) > 2:
            search_query = conversation_context

        # Enhance the search query with terms extracted from document analysis.
        # When a user uploads a form and asks "is this compliant?", the bare
        # question yields poor graph retrieval. The document analysis knows the
        # form is an "EQCB Public Hearing Application for Notice of Violation"
        # — injecting those terms dramatically improves retrieval relevance.
        if self._doc_analysis:
            doc_terms = self._extract_search_terms_from_analysis(self._doc_analysis)
            if doc_terms:
                search_query = f"{search_query} {doc_terms}"

        try:
            t0 = time.time()

            # Step 1: Fulltext search on Ch24Document (title + text)
            doc_matches = self._search_documents(search_query)

            t1 = time.time()

            # Step 2a: Entity name search → traverse MENTIONS_ENTITY back to documents
            entity_matches = self._search_entities_by_name(search_query)
            entity_eids = [e["eid"] for e in entity_matches]
            entity_sections = self._get_sections_for_matched_entities(entity_eids)

            t2 = time.time()

            # Step 2b: Concept expansion — from top doc matches, find related via ontology
            top_section_ids = [d["id"] for d in doc_matches[:3] if d.get("id")]
            concept_sections = self._get_sections_via_concepts(top_section_ids)

            t3 = time.time()

            # Step 3: Direct fulltext search (separate path for merge)
            direct_sections = self._search_sections_direct(search_query)

            t4 = time.time()

            # Combine and assemble (doc_matches + entity traversal + concept expansion + direct)
            all_sections = doc_matches + entity_sections + concept_sections + direct_sections
            context, citations = self._assemble_context(all_sections)

            retrieval_ms = round((t4 - t0) * 1000)

            debug_info = {
                "doc_matches": [d.get("title", d.get("id", ""))[:60] for d in doc_matches[:5]],
                "entity_matches": [e["name"] for e in entity_matches[:5]],
                "sections_found": len(citations),
                "retrieval_ms": retrieval_ms,
            }

            # ── CONFIDENCE SCORING ──────────────────────────────────
            confidence_signals = {
                "entity_scores": [round(d.get("score", 0), 2) for d in doc_matches],
                "entity_count": len(doc_matches),
                "entity_names": [d.get("title", d.get("id", ""))[:40] for d in doc_matches[:5]],
                "concept_section_count": len(concept_sections),
                "graph_section_uuids": {s.get("id", "") for s in entity_sections + concept_sections},
                "direct_section_uuids": {s.get("id", "") for s in direct_sections},
                "direct_scores": [round(s.get("score", 0), 2) for s in direct_sections],
                "final_section_count": len(citations),
                "retrieval_ms": retrieval_ms,
            }

            conf_score, conf_band = self._calculate_confidence(confidence_signals)
            self._confidence_score = conf_score
            self._confidence_band = conf_band
            # Make JSON-serializable copy (sets → lists) for audit
            self._confidence_signals = {
                k: list(v) if isinstance(v, set) else v
                for k, v in confidence_signals.items()
            }
            self._confidence_signals["score"] = conf_score
            self._confidence_signals["band"] = conf_band

            # ── BUILD FULL TRACE (for show_trace mode) ──────────────
            if self.valves.show_trace:
                trace_lines = []
                trace_lines.append("# Neo4j GraphRAG Retrieval Trace")
                trace_lines.append(f"**Query:** {user_question}")
                trace_lines.append(f"**Total retrieval time:** {retrieval_ms}ms")
                trace_lines.append("")

                # Step 1 trace: Document fulltext search
                trace_lines.append("## Step 1: Document Fulltext Search (141 Ch24Document nodes)")
                trace_lines.append(f"*Time: {round((t1-t0)*1000)}ms*")
                trace_lines.append("")
                if doc_matches:
                    trace_lines.append("| # | Section | Title | Score |")
                    trace_lines.append("|---|---|---|---|")
                    for idx, d in enumerate(doc_matches, 1):
                        title = (d.get("title") or "")[:80]
                        trace_lines.append(f"| {idx} | **{d.get('id', '?')}** | {title} | {d.get('score', 0):.2f} |")
                else:
                    trace_lines.append("*No documents matched.*")
                trace_lines.append("")

                # Step 2a trace: Entity traversal
                trace_lines.append("## Step 2a: Entity Traversal (Ch24Entity → MENTIONS_ENTITY → Ch24Document)")
                trace_lines.append(f"*Time: {round((t2-t1)*1000)}ms — Matched {len(entity_matches)} entities*")
                trace_lines.append("")
                if entity_sections:
                    trace_lines.append("| # | Section | Matched Entities | Entity Count |")
                    trace_lines.append("|---|---|---|---|")
                    for idx, s in enumerate(entity_sections, 1):
                        title = s.get("title", s.get("id", "?"))[:60]
                        matched = ", ".join(s.get("matched_entities", [])[:4])
                        count = s.get("entity_count", 0)
                        trace_lines.append(f"| {idx} | {title} | {matched} | {count} |")
                else:
                    trace_lines.append("*No sections found via entity traversal.*")
                trace_lines.append("")

                # Step 2b trace: Concept expansion
                trace_lines.append("## Step 2b: Concept Expansion (Ch24Document → RELATES_TO_CONCEPT → Ch24Class)")
                trace_lines.append(f"*Time: {round((t3-t2)*1000)}ms — Expanded from {len(top_section_ids)} seed documents*")
                trace_lines.append("")
                if concept_sections:
                    trace_lines.append("| # | Section | Concept | Similarity |")
                    trace_lines.append("|---|---|---|---|")
                    for idx, s in enumerate(concept_sections, 1):
                        title = s.get("title", s.get("id", "?"))[:60]
                        concept = s.get("concept", "?")
                        score = s.get("score", 0)
                        trace_lines.append(f"| {idx} | {title} | {concept} | {score:.3f} |")
                else:
                    trace_lines.append("*No additional sections found via concept expansion.*")
                trace_lines.append("")

                # Step 3 trace: Direct search
                trace_lines.append("## Step 3: Direct Fulltext Search (141 Ch24Document nodes)")
                trace_lines.append(f"*Time: {round((t4-t3)*1000)}ms*")
                trace_lines.append("")
                if direct_sections:
                    trace_lines.append("| # | Section | Score | Content Preview |")
                    trace_lines.append("|---|---|---|---|")
                    for idx, s in enumerate(direct_sections, 1):
                        title = s.get("title", s.get("id", "?"))[:60]
                        score = s.get("score", 0)
                        preview = (s.get("content") or "")[:80].replace("\n", " ")
                        trace_lines.append(f"| {idx} | {title} | {score:.2f} | {preview}... |")
                else:
                    trace_lines.append("*No sections found via direct search.*")
                trace_lines.append("")

                # Step 4 trace: Final assembly
                trace_lines.append("## Step 4: Context Assembly (deduplicated)")
                trace_lines.append(f"*{len(citations)} unique sections assembled, ~{len(context)} chars total*")
                trace_lines.append("")
                if citations:
                    for c in citations:
                        trace_lines.append(f"- **[G{c['index']}]** {c['section']}")
                trace_lines.append("")

                # Confidence scoring breakdown
                pct = int(conf_score * 100)
                trace_lines.append(f"## Source Confidence: {pct}%")
                trace_lines.append("")
                trace_lines.append(f"The confidence score reflects how well the retrieval pipeline matched your query to regulatory content. Here's how the {pct}% was calculated:")
                trace_lines.append("")

                _es = confidence_signals["entity_scores"]
                _avg_e = round(sum(_es) / max(len(_es), 1), 2) if _es else 0
                _norm_e = min(_avg_e / 10, 1.0)
                _ds = confidence_signals["direct_scores"]
                _avg_d = round(sum(_ds) / max(len(_ds), 1), 2) if _ds else 0
                _norm_d = min(_avg_d / 10, 1.0)
                _concept_ct = confidence_signals.get("concept_section_count", 0)
                _norm_concept = min(_concept_ct / max(self.valves.max_sections, 1), 1.0)
                _norm_ec = min(len(doc_matches) / self.valves.entity_search_limit, 1.0)
                _norm_sc = min(len(citations) / max(self.valves.max_sections, 1), 1.0)
                _ge = 1 if (confidence_signals["graph_section_uuids"] - confidence_signals["direct_section_uuids"]) else 0

                trace_lines.append("| What we measured | Result | Contribution | Why it matters |")
                trace_lines.append("|---|---|---|---|")
                trace_lines.append(f"| **Document match quality** — how strongly your query matched regulatory sections | Avg score {_avg_e}/10 → {_norm_e:.0%} | ×0.30 = **{_norm_e*0.30:.2f}** | Higher means your question maps cleanly to specific regulatory sections |")
                trace_lines.append(f"| **Document count** — how many regulatory sections matched | {len(doc_matches)}/{self.valves.entity_search_limit} found → {_norm_ec:.0%} | ×0.15 = **{_norm_ec*0.15:.2f}** | More matches = broader coverage of your question |")
                trace_lines.append(f"| **Concept expansion** — ontology concepts linked related regulatory sections | {_concept_ct} sections via concepts → {_norm_concept:.0%} | ×0.25 = **{_norm_concept*0.25:.2f}** | Primary signal: the ontology hierarchy found related sections beyond keyword matches |")
                trace_lines.append(f"| **Sections retrieved** — how many unique regulatory sections were assembled | {len(citations)}/{self.valves.max_sections} → {_norm_sc:.0%} | ×0.12 = **{_norm_sc*0.12:.2f}** | Full coverage means the system found enough source material |")
                trace_lines.append(f"| **Graph added unique value** — did the knowledge graph find sections that text search missed? | {'Yes' if _ge else 'No'} → {_ge:.0%} | ×0.10 = **{_ge*0.10:.2f}** | This is the core advantage of GraphRAG over standard text search |")
                trace_lines.append(f"| **Direct text relevance** — how well your query matched regulatory text directly | Avg score {_avg_d}/10 → {_norm_d:.0%} | ×0.08 = **{_norm_d*0.08:.2f}** | Confirms your question has text-level relevance to the regulatory content |")
                trace_lines.append("")
                _total = _norm_e*0.30 + _norm_ec*0.15 + _norm_concept*0.25 + _norm_sc*0.12 + _ge*0.10 + _norm_d*0.08
                trace_lines.append(f"**Total: {_total:.2f} → {int(_total*100)}%**")
                trace_lines.append("")

                # How this differs from KB
                trace_lines.append("## How This Differs From Knowledge Base (ChromaDB)")
                trace_lines.append("- **Knowledge Base:** text similarity search — finds chunks containing similar words")
                trace_lines.append("- **GraphRAG:** relationship traversal — finds sections connected by entity relationships")
                trace_lines.append(f"- **Documents used as bridge:** {', '.join(d.get('title', d.get('id', ''))[:40] for d in doc_matches[:5])}")
                trace_lines.append("- These entities connected your question to sections that may not contain your exact words but are conceptually relevant via the knowledge graph")

                self._last_trace = "\n".join(trace_lines)
            else:
                self._last_trace = None

        except Exception as e:
            # Reset retrieval state on any failure
            self._last_trace = None
            self._confidence_score = None
            self._confidence_band = None
            self._confidence_signals = None
            self._citations = None
            self._entity_matches = None
            self._graph_context = None

            # Determine if this is a Neo4j connectivity failure
            err_name = type(e).__name__
            err_str = str(e).lower()
            is_neo4j_failure = (
                err_name in ("ServiceUnavailable", "SessionExpired", "DriverError",
                             "ConnectionRefusedError", "BoltHandshakeError")
                or "neo4j" in err_name.lower()
                or "connection" in err_str and ("refused" in err_str or "unavailable" in err_str
                    or "timeout" in err_str or "reset" in err_str or "closed" in err_str)
                or "failed to establish" in err_str
                or "dns resolution" in err_str
            )

            if is_neo4j_failure:
                # Neo4j is down — trigger dedicated guardrail, not zero-retrieval
                _doc_logger.error(f"[NEO4J-FAILOVER] Connection failure: {err_name}: {e}")
                # Invalidate cached driver so next request retries fresh
                self._driver = None

                if self.valves.neo4j_fallback_to_kb:
                    # Degraded mode: let the query pass through to KB-only retrieval
                    # with a notice injected so the user knows graph context is missing
                    self._guardrail_triggered = False
                    self._neo4j_degraded = True
                    if self._doc_analysis:
                        self._inject_doc_analysis_into_message(messages)
                    # Inject degraded-mode notice into the user message so the LLM
                    # knows it only has KB context (not graph context)
                    for i in range(len(messages) - 1, -1, -1):
                        if messages[i].get("role") == "user":
                            original = messages[i].get("content", "")
                            if isinstance(original, str):
                                messages[i]["content"] = (
                                    f"{original}\n\n"
                                    f"---\n"
                                    f"[SYSTEM NOTICE: The Neo4j knowledge graph is temporarily "
                                    f"unreachable. You only have Knowledge Base context for this "
                                    f"query. Answer using available context but note that graph-"
                                    f"retrieved regulatory sections are unavailable.]\n"
                                    f"---"
                                )
                            break
                    body["messages"] = messages
                else:
                    # Hard block: show guardrail notice, do not pass query to LLM
                    self._guardrail_triggered = True
                    self._guardrail_type = "neo4j_unavailable"
                    self._guardrail_reason = f"Neo4j connection failure: {err_name}"
                    user_id = (__user__ or {}).get("id", "")
                    chat_id = __chat_id__ or ""
                    self._guardrail_ref = self._generate_guardrail_ref(user_id, chat_id)
                    if self._doc_analysis:
                        self._inject_doc_analysis_into_message(messages)
                        body["messages"] = messages
            else:
                # Other retrieval error — log but don't block
                _doc_logger.error(f"[GRAPHRAG] Retrieval error: {err_name}: {e}")
                # Still inject document analysis if present
                if self._doc_analysis:
                    self._inject_doc_analysis_into_message(messages)
                    body["messages"] = messages

            if self.valves.debug:
                body["messages"] = [
                    {"role": "system", "content": f"[GraphRAG retrieval error: {str(e)}]"}
                ] + messages
            return body

        if not context:
            # No relevant sections found — check zero-retrieval guardrail
            if self.valves.guardrail_enabled:
                zr_triggered, zr_reason = self._check_zero_retrieval(doc_matches, all_sections)
                if zr_triggered:
                    user_id = (__user__ or {}).get("id", "")
                    chat_id = __chat_id__ or ""
                    self._guardrail_triggered = True
                    self._guardrail_type = "zero_retrieval"
                    self._guardrail_reason = zr_reason
                    self._guardrail_ref = self._generate_guardrail_ref(user_id, chat_id)
            # Pass through without modification — LLM responds naturally
            self._last_trace = None
            self._confidence_score = None
            self._confidence_band = None
            self._confidence_signals = None
            self._citations = None
            self._entity_matches = None
            self._graph_context = None
            # Still inject document analysis if present
            if self._doc_analysis:
                self._inject_doc_analysis_into_message(messages)
                body["messages"] = messages
            return body

        # Store citations for the outlet to inject into the Sources panel
        self._citations = citations

        # Store entity matches for escalation case packet (full context)
        self._entity_matches = [
            {"name": d.get("title", d.get("id", "")), "score": round(d.get("score", 0), 2), "summary": (d.get("content") or "")[:200]}
            for d in doc_matches
        ]

        # ── INJECT CONTEXT ───────────────────────────────────────────
        # We append the GraphRAG context directly to the user's message
        # rather than as a system message. This is because Open WebUI's
        # Knowledge Base RAG runs AFTER filters and can overwrite/replace
        # system messages. By embedding context in the user message, it
        # survives the RAG pipeline and reaches the LLM alongside the
        # KB chunks — giving the model BOTH sources of context.

        graph_context = self._build_system_prompt(
            context, citations,
            debug_info if self.valves.debug else None,
            confidence=(conf_score, conf_band),
        )

        # Store the assembled graph context for escalation case packet
        self._graph_context = graph_context

        # Build threshold context block (if any measurements were detected)
        threshold_context = ""
        if self._threshold_determinations:
            threshold_context = self._build_threshold_context(self._threshold_determinations)

        # Find the last user message and append all context blocks:
        # document analysis + graph context + threshold context
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "user":
                original_content = messages[i].get("content", "")
                if isinstance(original_content, str):
                    injected = f"{original_content}\n\n"

                    # Document analysis block (if files were uploaded)
                    if self._doc_analysis:
                        injected += (
                            f"---\n"
                            f"[UPLOADED DOCUMENT ANALYSIS — extracted by vision model]\n"
                            f"{self._doc_analysis}\n"
                            f"---\n\n"
                        )

                    # Graph knowledge context block
                    injected += (
                        f"---\n"
                        f"[GRAPH KNOWLEDGE CONTEXT — from Neo4j regulatory knowledge graph]\n"
                        f"{graph_context}\n"
                    )
                    if threshold_context:
                        injected += f"\n{threshold_context}\n"
                    injected += "---"
                    messages[i]["content"] = injected
                break

        body["messages"] = messages
        return body

    async def outlet(
        self,
        body: dict,
        __user__: dict = None,
        __chat_id__: str = None,
        __message_id__: str = None,
        __session_id__: str = None,
        __metadata__: dict = None,
    ) -> dict:
        """
        Outlet: append confidence badge and/or retrieval trace to the
        assistant's response. Also inject GraphRAG sources into the
        message's sources list so they appear in the Sources button
        alongside any KB sources.
        """
        has_confidence = self._confidence_score is not None
        has_trace = self.valves.show_trace and self._last_trace
        has_citations = self._citations is not None and len(self._citations) > 0
        has_guardrail = self._guardrail_triggered
        has_threshold = self._threshold_determinations is not None and len(self._threshold_determinations) > 0
        has_degraded = getattr(self, "_neo4j_degraded", False)

        if not has_confidence and not has_trace and not has_citations and not has_guardrail and not has_threshold and not has_degraded:
            return body

        messages = body.get("messages", [])
        if not messages:
            return body

        # ── INJECT GRAPHRAG SOURCES INTO SOURCES PANEL ──────────────
        # Find the last assistant message and append GraphRAG sources
        # to its existing sources list (KB sources are already there).
        if has_citations:
            for i in range(len(messages) - 1, -1, -1):
                if messages[i].get("role") == "assistant":
                    existing_sources = messages[i].get("sources", [])

                    for c in self._citations:
                        existing_sources.append({
                            "source": {
                                "id": f"graphrag_{c.get('id', c.get('uuid', str(c['index'])))}",
                                "name": f"[G{c['index']}] {c['section']}",
                            },
                            "document": [c.get("content", "")],
                            "metadata": [
                                {
                                    "source": c["section"],
                                    "name": f"[G{c['index']}] {c['section']}",
                                }
                            ],
                        })

                    messages[i]["sources"] = existing_sources
                    break

        # ── APPEND CONFIDENCE & TRACE TO RESPONSE TEXT ──────────────
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "assistant":
                content = messages[i].get("content", "")
                if not isinstance(content, str):
                    break

                appendix = ""

                # ── THRESHOLD COMPLIANCE BADGE (shown FIRST — most important for threshold queries) ──
                if has_threshold:
                    appendix += self._build_compliance_badge(self._threshold_determinations)
                    # Store threshold data on message dict for audit logger
                    messages[i]["graphrag_threshold"] = {
                        "determinations": [
                            {
                                "parameter": d.get("parameter"),
                                "value": d.get("user_value"),
                                "status": d.get("status"),
                                "threshold_value": d.get("threshold_value"),
                                "evidence_hash": d.get("evidence_hash"),
                                "section_ref": d.get("section_ref"),
                            }
                            for d in self._threshold_determinations
                            if d.get("status") in ("BREACH", "BORDERLINE", "COMPLIANT")
                        ],
                    }

                # ── GUARDRAIL / ESCALATION / DISCLAIMER (mutually exclusive) ──
                # NOTE: Confidence data is only stored when NO guardrail fires.
                # When a guardrail triggers, confidence is meaningless (the query
                # was out-of-scope or had zero retrieval) and should not appear
                # in the audit record or response.
                escalation_data = None

                if has_guardrail:
                    appendix += self._build_guardrail_notice()
                    # Store guardrail data on message dict for audit logger
                    messages[i]["graphrag_guardrail"] = {
                        "triggered": True,
                        "type": self._guardrail_type,
                        "reason": self._guardrail_reason,
                        "ref": self._guardrail_ref,
                    }

                # Neo4j degraded mode — KB-only fallback notice
                elif has_degraded:
                    appendix += (
                        "\n\n---\n"
                        "**Degraded Mode — Knowledge Base Only**\n\n"
                        "The Neo4j knowledge graph was temporarily unreachable for this query. "
                        "This response is based solely on the Knowledge Base (vector search) and "
                        "does not include graph-retrieved regulatory sections, confidence scoring, "
                        "or citation references.\n\n"
                        "**Please verify critical findings** against the full regulation text. "
                        "Graph retrieval will resume automatically when the connection is restored."
                    )
                    # Log degraded event for audit trail
                    messages[i]["graphrag_guardrail"] = {
                        "triggered": False,
                        "type": "neo4j_degraded",
                        "reason": "Neo4j unreachable — KB-only fallback active",
                        "ref": None,
                    }

                # Escalation check — flag low-confidence queries for expert review
                # When escalation triggers, the notice REPLACES the disclaimer (not stacked).
                # Guardrail takes priority over escalation — if guardrail triggered, skip escalation.
                elif has_confidence and self._should_escalate():
                    # Store confidence data (no guardrail, so confidence is meaningful)
                    messages[i]["graphrag_confidence"] = {
                        "score": self._confidence_score,
                        "band": self._confidence_band,
                        "signals": self._confidence_signals,
                    }
                    user_id = (__user__ or {}).get("id", "")
                    user_email = (__user__ or {}).get("email", "")
                    chat_id = __chat_id__ or ""
                    message_id = __message_id__ or ""
                    model = body.get("model", "")
                    case_ref = self._generate_case_ref(user_id, chat_id)
                    reason = self._escalation_reason()

                    escalation_data = {
                        "triggered": True,
                        "target": self.valves.escalation_target,
                        "case_ref": case_ref,
                        "reason": reason,
                        "confidence_score": self._confidence_score,
                        "confidence_band": self._confidence_band,
                    }

                    # Build and send case packet to n8n webhook
                    case_packet = self._build_case_packet(
                        case_ref=case_ref,
                        reason=reason,
                        user_info=__user__ or {},
                        query=self._extract_last_user_query(messages),
                        response=content,
                        messages=messages,
                        chat_id=chat_id,
                        message_id=message_id,
                        model=model,
                    )
                    self._send_escalation_webhook(case_packet)

                    # Escalation notice REPLACES the disclaimer
                    appendix += self._build_escalation_notice(case_ref, user_email)

                elif has_confidence:
                    # Store confidence data (no guardrail, so confidence is meaningful)
                    messages[i]["graphrag_confidence"] = {
                        "score": self._confidence_score,
                        "band": self._confidence_band,
                        "signals": self._confidence_signals,
                    }
                    # Color-coded confidence banner
                    if self.valves.show_confidence:
                        _doc_logger.info(f"[OUTLET] Appending confidence banner: score={self._confidence_score}, band={self._confidence_band}")
                        appendix += self._build_disclaimer()

                # Store escalation data on message dict for audit logger
                if escalation_data:
                    messages[i]["graphrag_escalation"] = escalation_data

                # Trace section (pure markdown, no HTML tags)
                if has_trace:
                    appendix += (
                        f"\n\n---\n\n"
                        f"**📊 Retrieval Trace**\n\n"
                        f"{self._last_trace}"
                    )

                messages[i]["content"] = content + appendix
                break

        # Clear state
        self._last_trace = None
        self._confidence_score = None
        self._confidence_band = None
        self._confidence_signals = None
        self._citations = None
        self._entity_matches = None
        self._graph_context = None
        self._guardrail_triggered = False
        self._guardrail_type = None
        self._guardrail_reason = None
        self._guardrail_ref = None
        self._neo4j_degraded = False
        self._threshold_determinations = None

        body["messages"] = messages
        return body
