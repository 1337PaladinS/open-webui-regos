"""Pydantic models for chunks, jobs, and stats."""
from pydantic import BaseModel
from typing import Optional
from enum import Enum


class JobStatus(str, Enum):
    PENDING = "pending"
    EXTRACTING = "extracting"
    CHUNKING = "chunking"
    ENRICHING = "enriching"
    DONE = "done"
    ERROR = "error"
    PUSHING = "pushing"


class ChunkMetadata(BaseModel):
    chunk_id: str
    document: str
    jurisdiction: str
    breadcrumb: str
    content_type: str  # definition, prose, table, list, reserved, technical
    hierarchy: dict  # {chapter, article, division, section, section_title, subsection}
    cross_references: list[str] = []
    defined_term: Optional[str] = None
    ordinance_citations: list[str] = []
    effective_dates: list[str] = []
    dollar_amounts_present: bool = False
    page_range: Optional[str] = None
    token_count: int = 0


class Chunk(BaseModel):
    metadata: ChunkMetadata
    text: str
    context_prefix: Optional[str] = None
    enriched_text: Optional[str] = None


class DocumentStats(BaseModel):
    total_pages: int = 0
    total_sections: int = 0
    total_subsections: int = 0
    total_definitions: int = 0
    total_tables: int = 0
    total_cross_references: int = 0
    total_chunks: int = 0
    avg_chunk_tokens: float = 0
    min_chunk_tokens: int = 0
    max_chunk_tokens: int = 0
    content_type_breakdown: dict = {}  # {prose: N, definition: N, ...}
    hierarchy_tree: dict = {}  # nested tree structure


class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    filename: str
    message: str = ""
    stats: Optional[DocumentStats] = None
    progress: float = 0.0


class Neo4jStatus(BaseModel):
    connected: bool = False
    mode: str = "external"
    uri: str = ""
    total_nodes: int = 0
    total_relationships: int = 0
    last_push: Optional[str] = None


class LogEntry(BaseModel):
    id: int
    filename: str
    upload_time: str
    page_count: int
    chunk_count: int
    pushed_to_neo4j: bool
    push_time: Optional[str] = None
    processing_duration_s: float
    status: str
    enrichment_enabled: bool = False
    error_message: Optional[str] = None
