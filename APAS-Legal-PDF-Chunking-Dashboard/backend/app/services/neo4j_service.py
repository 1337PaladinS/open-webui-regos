"""
Neo4j service for pushing chunks as a knowledge graph.
Follows the existing FEA (Fixed Entity Architecture) schema:
  - Section nodes with hierarchy
  - Threshold, Penalty, Role, Standard, Obligation entities
  - Cross-reference edges
  - Hierarchy (PART_OF) edges
"""
import os
import re
from typing import Optional
from neo4j import GraphDatabase


def get_driver():
    uri = os.environ.get("NEO4J_URI", "bolt://host.docker.internal:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "neo4j")
    return GraphDatabase.driver(uri, auth=(user, password))


def check_connection() -> dict:
    """Check Neo4j connectivity and return stats."""
    try:
        driver = get_driver()
        with driver.session() as session:
            # Basic connectivity
            result = session.run("RETURN 1 AS ok")
            result.single()

            # Node count
            node_result = session.run("MATCH (n) RETURN count(n) AS count")
            node_count = node_result.single()["count"]

            # Relationship count
            rel_result = session.run("MATCH ()-[r]->() RETURN count(r) AS count")
            rel_count = rel_result.single()["count"]

            # Last push timestamp (from Document node if exists)
            last_push = None
            try:
                ts_result = session.run(
                    "MATCH (d:Document) RETURN d.pushed_at AS ts ORDER BY d.pushed_at DESC LIMIT 1"
                )
                rec = ts_result.single()
                if rec:
                    last_push = rec["ts"]
            except Exception:
                pass

        driver.close()
        return {
            "connected": True,
            "mode": os.environ.get("NEO4J_MODE", "external"),
            "uri": os.environ.get("NEO4J_URI", ""),
            "total_nodes": node_count,
            "total_relationships": rel_count,
            "last_push": last_push,
        }
    except Exception as e:
        return {
            "connected": False,
            "mode": os.environ.get("NEO4J_MODE", "external"),
            "uri": os.environ.get("NEO4J_URI", ""),
            "total_nodes": 0,
            "total_relationships": 0,
            "last_push": None,
            "error": str(e),
        }


def create_schema(session):
    """Create constraints and indexes following FEA schema."""
    schema_queries = [
        "CREATE CONSTRAINT IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (s:Section) REQUIRE s.id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Chunk) REQUIRE c.chunk_id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (r:Role) REQUIRE r.name IS UNIQUE",
        "CREATE INDEX IF NOT EXISTS FOR (c:Chunk) ON (c.content_type)",
        "CREATE INDEX IF NOT EXISTS FOR (c:Chunk) ON (c.document)",
        "CREATE INDEX IF NOT EXISTS FOR (s:Section) ON (s.number)",
    ]
    # Fulltext indexes - create separately with try/except
    for q in schema_queries:
        try:
            session.run(q)
        except Exception:
            pass

    # Fulltext index
    try:
        session.run(
            "CREATE FULLTEXT INDEX chunk_search IF NOT EXISTS "
            "FOR (c:Chunk) ON EACH [c.text, c.breadcrumb]"
        )
    except Exception:
        pass


def push_chunks_to_neo4j(
    chunks: list[dict],
    document_name: str,
    jurisdiction: str,
    job_id: str,
    progress_callback=None,
) -> dict:
    """
    Push all chunks + FEA entities + cross-reference edges to Neo4j.
    Returns summary stats.
    """
    from datetime import datetime, timezone

    driver = get_driver()
    stats = {
        "chunks_created": 0,
        "sections_created": 0,
        "cross_ref_edges": 0,
        "hierarchy_edges": 0,
        "threshold_nodes": 0,
        "penalty_nodes": 0,
        "role_nodes": 0,
        "standard_nodes": 0,
        "obligation_nodes": 0,
    }

    now = datetime.now(timezone.utc).isoformat()
    total = len(chunks)

    with driver.session() as session:
        # 1. Create schema
        create_schema(session)

        # 2. Create Document node
        session.run(
            """
            MERGE (d:Document {id: $doc_id})
            SET d.name = $name,
                d.jurisdiction = $jurisdiction,
                d.job_id = $job_id,
                d.pushed_at = $now,
                d.chunk_count = $chunk_count
            """,
            doc_id=f"{jurisdiction}_{document_name}".replace(" ", "_"),
            name=document_name,
            jurisdiction=jurisdiction,
            job_id=job_id,
            now=now,
            chunk_count=total,
        )

        # 3. Create Section nodes from chunk hierarchies
        sections_seen = set()
        for chunk in chunks:
            h = chunk["metadata"]["hierarchy"]
            sec = h.get("section", "")
            if sec and sec not in sections_seen:
                sections_seen.add(sec)
                sec_num = sec.replace("§ ", "")
                session.run(
                    """
                    MERGE (s:Section {id: $sec_id})
                    SET s.number = $number,
                        s.title = $title,
                        s.chapter = $chapter,
                        s.article = $article,
                        s.division = $division,
                        s.document = $document
                    """,
                    sec_id=f"{jurisdiction}_{sec_num}",
                    number=sec_num,
                    title=h.get("section_title", ""),
                    chapter=h.get("chapter", ""),
                    article=h.get("article", ""),
                    division=h.get("division", ""),
                    document=document_name,
                )
                stats["sections_created"] += 1

        # 4. Create Chunk nodes with all metadata
        for i, chunk in enumerate(chunks):
            meta = chunk["metadata"]
            text = chunk.get("enriched_text") or chunk["text"]

            session.run(
                """
                MERGE (c:Chunk {chunk_id: $chunk_id})
                SET c.document = $document,
                    c.jurisdiction = $jurisdiction,
                    c.breadcrumb = $breadcrumb,
                    c.content_type = $content_type,
                    c.text = $text,
                    c.token_count = $token_count,
                    c.page_range = $page_range,
                    c.cross_references = $cross_refs,
                    c.ordinance_citations = $ord_citations,
                    c.dollar_amounts_present = $dollars,
                    c.section_number = $section_number,
                    c.section_title = $section_title
                """,
                chunk_id=meta["chunk_id"],
                document=document_name,
                jurisdiction=jurisdiction,
                breadcrumb=meta["breadcrumb"],
                content_type=meta["content_type"],
                text=text,
                token_count=meta["token_count"],
                page_range=meta.get("page_range", ""),
                cross_refs=meta.get("cross_references", []),
                ord_citations=meta.get("ordinance_citations", []),
                dollars=meta.get("dollar_amounts_present", False),
                section_number=meta["hierarchy"].get("section", "").replace("§ ", ""),
                section_title=meta["hierarchy"].get("section_title", ""),
            )
            stats["chunks_created"] += 1

            # Link chunk to document
            session.run(
                """
                MATCH (d:Document {job_id: $job_id})
                MATCH (c:Chunk {chunk_id: $chunk_id})
                MERGE (c)-[:BELONGS_TO]->(d)
                """,
                job_id=job_id,
                chunk_id=meta["chunk_id"],
            )

            # Link chunk to section
            sec = meta["hierarchy"].get("section", "")
            if sec:
                sec_num = sec.replace("§ ", "")
                session.run(
                    """
                    MATCH (s:Section {id: $sec_id})
                    MATCH (c:Chunk {chunk_id: $chunk_id})
                    MERGE (c)-[:PART_OF]->(s)
                    """,
                    sec_id=f"{jurisdiction}_{sec_num}",
                    chunk_id=meta["chunk_id"],
                )

            # 5. Create FEA Layer 3 entities
            fea = meta.get("fea_entities", {})

            for t in fea.get("thresholds", []):
                session.run(
                    """
                    MATCH (c:Chunk {chunk_id: $chunk_id})
                    CREATE (th:Threshold {value: $value, unit: $unit, context: $context})
                    CREATE (c)-[:HAS_THRESHOLD]->(th)
                    """,
                    chunk_id=meta["chunk_id"],
                    value=t["value"],
                    unit=t["unit"],
                    context=t.get("context", "")[:200],
                )
                stats["threshold_nodes"] += 1

            for p in fea.get("penalties", []):
                session.run(
                    """
                    MATCH (c:Chunk {chunk_id: $chunk_id})
                    CREATE (pe:Penalty {amount: $amount, context: $context})
                    CREATE (c)-[:HAS_PENALTY]->(pe)
                    """,
                    chunk_id=meta["chunk_id"],
                    amount=p["amount"],
                    context=p.get("context", "")[:200],
                )
                stats["penalty_nodes"] += 1

            for role_name in fea.get("roles", []):
                session.run(
                    """
                    MERGE (r:Role {name: $name})
                    WITH r
                    MATCH (c:Chunk {chunk_id: $chunk_id})
                    MERGE (c)-[:MENTIONS_ROLE]->(r)
                    """,
                    name=role_name,
                    chunk_id=meta["chunk_id"],
                )
                stats["role_nodes"] += 1

            for std in fea.get("standards", []):
                session.run(
                    """
                    MERGE (st:Standard {name: $name})
                    WITH st
                    MATCH (c:Chunk {chunk_id: $chunk_id})
                    MERGE (c)-[:CITES_STANDARD]->(st)
                    """,
                    name=std,
                    chunk_id=meta["chunk_id"],
                )
                stats["standard_nodes"] += 1

            for obl in fea.get("obligations", []):
                session.run(
                    """
                    MATCH (c:Chunk {chunk_id: $chunk_id})
                    CREATE (ob:Obligation {text: $text, type: $type})
                    CREATE (c)-[:CONTAINS_OBLIGATION]->(ob)
                    """,
                    chunk_id=meta["chunk_id"],
                    text=obl["text"][:500],
                    type=obl["type"],
                )
                stats["obligation_nodes"] += 1

            if progress_callback:
                progress_callback(i + 1, total)

        # 6. Create cross-reference edges between chunks
        for chunk in chunks:
            meta = chunk["metadata"]
            for ref in meta.get("cross_references", []):
                # Find chunks that belong to the referenced section
                session.run(
                    """
                    MATCH (src:Chunk {chunk_id: $src_id})
                    MATCH (tgt:Chunk)
                    WHERE tgt.section_number = $ref_num AND tgt.chunk_id <> $src_id
                    MERGE (src)-[:REFERENCES]->(tgt)
                    """,
                    src_id=meta["chunk_id"],
                    ref_num=ref,
                )
                stats["cross_ref_edges"] += 1

        # 7. Create section hierarchy (PART_OF between sections)
        for sec in sections_seen:
            sec_num = sec.replace("§ ", "")
            # Check if subsection (e.g., 24-42.6 -> parent 24-42)
            if "." in sec_num:
                parent_num = sec_num.rsplit(".", 1)[0]
                parent_id = f"{jurisdiction}_{parent_num}"
                session.run(
                    """
                    MATCH (child:Section {id: $child_id})
                    MATCH (parent:Section {id: $parent_id})
                    MERGE (child)-[:PART_OF]->(parent)
                    """,
                    child_id=f"{jurisdiction}_{sec_num}",
                    parent_id=parent_id,
                )
                stats["hierarchy_edges"] += 1

    driver.close()
    return stats


def clear_document(job_id: str):
    """Remove all nodes associated with a specific job."""
    driver = get_driver()
    with driver.session() as session:
        session.run(
            """
            MATCH (d:Document {job_id: $job_id})<-[:BELONGS_TO]-(c:Chunk)
            OPTIONAL MATCH (c)-[r]->()
            DELETE r
            WITH c, d
            DETACH DELETE c, d
            """,
            job_id=job_id,
        )
    driver.close()


def run_cypher(query: str) -> list[dict]:
    """Execute arbitrary Cypher query (for the dashboard query box)."""
    driver = get_driver()
    with driver.session() as session:
        result = session.run(query)
        records = [dict(r) for r in result]
    driver.close()
    return records
