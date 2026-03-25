"""
title: RegOS GraphRAG Pipe
description: Graph-enhanced RAG pipeline for Chapter 24 regulatory queries. Searches Neo4j knowledge graph for relevant entities and regulatory sections, assembles cited context, and routes to a backend LLM for answer generation.
author: APAS AI
version: 0.1.0
required_open_webui_version: 0.4.0
"""

from pydantic import BaseModel, Field
from typing import Optional, Generator
import json
import time
import requests


class Pipe:
    """
    GraphRAG Pipe for regulatory compliance queries.

    This Pipe appears as a selectable "model" in the Open WebUI chat interface.
    When a user sends a message to this Pipe, it:

    1. Extracts the user's question from the conversation
    2. Searches the Neo4j knowledge graph for relevant Entity nodes (concepts)
    3. Traverses MENTIONS relationships to find Episodic nodes (regulatory text sections)
    4. Also does direct fulltext search on Episodic content for broad coverage
    5. Deduplicates and ranks the retrieved regulatory sections
    6. Assembles a system prompt with the retrieved context + citation metadata
    7. Calls a backend LLM model (configured via Valves) with the augmented prompt
    8. Returns the LLM's response (streamed)

    The Neo4j graph schema:
    - Episodic nodes: regulatory text sections with `content`, `source_description`, `uuid`
    - Entity nodes: regulatory concepts with `name`, `summary`, `uuid`
    - MENTIONS: Episodic → Entity (a section mentions a concept)
    - RELATES_TO: Entity → Entity (concepts are related)
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

        # Backend LLM
        backend_model: str = Field(
            default="",
            description="Model ID to use for answer generation (e.g. 'gemini-2.5-pro' or 'nvidia_nim/nvidia/llama-3.3-nemotron-super-49b-v1'). Must be a model already configured in Open WebUI.",
        )
        openwebui_base_url: str = Field(
            default="http://localhost:8080",
            description="Internal Open WebUI API base URL (inside the container).",
        )

        # Retrieval settings
        max_sections: int = Field(
            default=8,
            description="Maximum number of regulatory sections to include in context.",
        )
        entity_search_limit: int = Field(
            default=10,
            description="Maximum entities to retrieve from fulltext search.",
        )
        min_relevance_score: float = Field(
            default=0.5,
            description="Minimum fulltext search score to consider a result relevant.",
        )

        # Feature flags
        enabled: bool = Field(
            default=True,
            description="Enable or disable the GraphRAG pipeline.",
        )
        debug: bool = Field(
            default=False,
            description="Include retrieval debug info in the response.",
        )

    def __init__(self):
        self.valves = self.Valves()
        self._driver = None

    def _get_driver(self):
        """Lazy-initialize Neo4j driver."""
        if self._driver is None:
            try:
                from neo4j import GraphDatabase

                self._driver = GraphDatabase.driver(
                    self.valves.neo4j_uri,
                    auth=(self.valves.neo4j_username, self.valves.neo4j_password),
                )
            except Exception as e:
                raise RuntimeError(f"Neo4j connection failed: {e}")
        return self._driver

    def _search_entities(self, query: str) -> list[dict]:
        """
        Step 1: Fulltext search on Entity nodes.
        Returns entities matching the user's query terms.
        """
        driver = self._get_driver()
        with driver.session(database=self.valves.neo4j_database) as session:
            # Escape special Lucene characters for safety
            safe_query = query.replace("\\", "\\\\")
            for ch in ["+", "-", "&&", "||", "!", "(", ")", "{", "}", "[", "]", "^", '"', "~", "*", "?", ":", "/"]:
                safe_query = safe_query.replace(ch, f"\\{ch}")

            result = session.run(
                """
                CALL db.index.fulltext.queryNodes('entity_search', $search_term)
                YIELD node, score
                WHERE score >= $min_score
                RETURN node.uuid AS uuid, node.name AS name, node.summary AS summary, score
                ORDER BY score DESC
                LIMIT $limit
                """,
                search_term=safe_query,
                min_score=self.valves.min_relevance_score,
                limit=self.valves.entity_search_limit,
            )
            return [dict(r) for r in result]

    def _get_sections_for_entities(self, entity_uuids: list[str]) -> list[dict]:
        """
        Step 2: Traverse MENTIONS relationships from matched entities
        back to their source Episodic (regulatory text) nodes.
        """
        if not entity_uuids:
            return []

        driver = self._get_driver()
        with driver.session(database=self.valves.neo4j_database) as session:
            result = session.run(
                """
                MATCH (ep:Episodic)-[:MENTIONS]->(ent:Entity)
                WHERE ent.uuid IN $uuids
                WITH ep, collect(DISTINCT ent.name) AS matched_entities, count(DISTINCT ent) AS entity_count
                RETURN ep.uuid AS uuid,
                       ep.content AS content,
                       ep.source_description AS source,
                       matched_entities,
                       entity_count
                ORDER BY entity_count DESC
                """,
                uuids=entity_uuids,
            )
            return [dict(r) for r in result]

    def _search_sections_direct(self, query: str) -> list[dict]:
        """
        Step 3: Direct fulltext search on Episodic content.
        This catches sections that mention the user's terms even if
        the entity linker missed them.
        """
        driver = self._get_driver()
        with driver.session(database=self.valves.neo4j_database) as session:
            safe_query = query.replace("\\", "\\\\")
            for ch in ["+", "-", "&&", "||", "!", "(", ")", "{", "}", "[", "]", "^", '"', "~", "*", "?", ":", "/"]:
                safe_query = safe_query.replace(ch, f"\\{ch}")

            result = session.run(
                """
                CALL db.index.fulltext.queryNodes('episodic_search', $search_term)
                YIELD node, score
                WHERE score >= $min_score
                RETURN node.uuid AS uuid,
                       node.content AS content,
                       node.source_description AS source,
                       score
                ORDER BY score DESC
                LIMIT $limit
                """,
                search_term=safe_query,
                min_score=self.valves.min_relevance_score,
                limit=self.valves.max_sections,
            )
            return [dict(r) for r in result]

    def _get_related_entities(self, entity_uuids: list[str]) -> list[dict]:
        """
        Step 2b: Expand matched entities via RELATES_TO for richer context.
        Returns related entities one hop away.
        """
        if not entity_uuids:
            return []

        driver = self._get_driver()
        with driver.session(database=self.valves.neo4j_database) as session:
            result = session.run(
                """
                MATCH (e1:Entity)-[:RELATES_TO]-(e2:Entity)
                WHERE e1.uuid IN $uuids AND NOT e2.uuid IN $uuids
                RETURN DISTINCT e2.uuid AS uuid, e2.name AS name, e2.summary AS summary
                LIMIT 10
                """,
                uuids=entity_uuids,
            )
            return [dict(r) for r in result]

    def _assemble_context(self, sections: list[dict]) -> tuple[str, list[dict]]:
        """
        Step 4: Assemble numbered context blocks from retrieved sections.
        Returns (context_string, citation_list).
        """
        seen_uuids = set()
        unique_sections = []
        for s in sections:
            uid = s["uuid"]
            if uid not in seen_uuids:
                seen_uuids.add(uid)
                unique_sections.append(s)

        # Limit to max_sections
        unique_sections = unique_sections[: self.valves.max_sections]

        if not unique_sections:
            return "", []

        context_parts = []
        citations = []

        for i, s in enumerate(unique_sections, 1):
            source = s.get("source", "Unknown source")
            content = s.get("content", "")

            # Extract section reference from source_description
            # Format: "Chapter 24 | vv2026-01-05 | Miami-Dade County | File: Sec._24_42.4..."
            section_ref = source.split("File: ")[-1].replace(".docx", "").replace("_", " ") if "File: " in source else source

            context_parts.append(f"[{i}] {section_ref}\n{content}")
            citations.append(
                {
                    "index": i,
                    "section": section_ref,
                    "source": source,
                    "uuid": s["uuid"],
                    "matched_entities": s.get("matched_entities", []),
                }
            )

        context_text = "\n\n---\n\n".join(context_parts)
        return context_text, citations

    def _build_system_prompt(self, context: str, citations: list[dict]) -> str:
        """
        Step 5: Build the system prompt with regulatory context.
        """
        citation_refs = "\n".join(
            f"  [{c['index']}] {c['section']}" for c in citations
        )

        return f"""You are a regulatory compliance assistant for Miami-Dade County Chapter 24 (Environmental Protection). You answer questions based ONLY on the regulatory text provided below.

RULES:
1. Base your answer ONLY on the provided regulatory sections. Do not use outside knowledge.
2. Cite specific sections using [1], [2], etc. matching the reference numbers below.
3. If the provided sections do not contain enough information to answer the question, say so clearly. Do not guess or fabricate.
4. Quote the exact regulatory language when citing specific requirements, limits, or definitions.
5. If multiple sections are relevant, synthesize them and cite all applicable references.
6. Structure your answer clearly: start with a direct answer, then provide supporting detail with citations.

AVAILABLE REGULATORY SECTIONS:
{context}

CITATION REFERENCES:
{citation_refs}

Answer the user's question based on these regulatory sections."""

    def _call_backend_llm(
        self, messages: list[dict], api_key: str
    ) -> Generator[str, None, None]:
        """
        Step 6: Call the backend LLM via Open WebUI's internal API.
        Streams the response.
        """
        url = f"{self.valves.openwebui_base_url}/api/chat/completions"

        payload = {
            "model": self.valves.backend_model,
            "messages": messages,
            "stream": True,
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        try:
            response = requests.post(
                url, json=payload, headers=headers, stream=True, timeout=120
            )
            response.raise_for_status()

            for line in response.iter_lines():
                if not line:
                    continue
                line_str = line.decode("utf-8")
                if line_str.startswith("data: "):
                    data_str = line_str[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        delta = (
                            data.get("choices", [{}])[0]
                            .get("delta", {})
                            .get("content", "")
                        )
                        if delta:
                            yield delta
                    except json.JSONDecodeError:
                        continue

        except requests.exceptions.RequestException as e:
            yield f"\n\n**Error calling backend model:** {str(e)}"

    def pipes(self) -> list[dict]:
        """
        Register this Pipe as a selectable model in Open WebUI.
        """
        return [
            {
                "id": "graphrag-chapter24",
                "name": "RegOS Chapter 24 (GraphRAG)",
            }
        ]

    def pipe(
        self,
        body: dict,
        __user__: dict = None,
        __metadata__: dict = None,
    ) -> Generator[str, None, None]:
        """
        Main pipeline entry point. Called when user sends a message
        to the 'RegOS Chapter 24 (GraphRAG)' model.
        """
        if not self.valves.enabled:
            yield "GraphRAG pipeline is currently disabled."
            return

        if not self.valves.neo4j_password:
            yield "**Configuration error:** Neo4j password is not set. Go to Admin > Functions > GraphRAG Pipe > Settings and enter the Neo4j password."
            return

        if not self.valves.backend_model:
            yield "**Configuration error:** Backend model is not set. Go to Admin > Functions > GraphRAG Pipe > Settings and set the backend model ID."
            return

        # Extract user question
        messages = body.get("messages", [])
        if not messages:
            yield "No message received."
            return

        user_question = ""
        if messages:
            last_msg = messages[-1]
            if isinstance(last_msg.get("content"), str):
                user_question = last_msg["content"]
            elif isinstance(last_msg.get("content"), list):
                user_question = " ".join(
                    p.get("text", "")
                    for p in last_msg["content"]
                    if isinstance(p, dict) and p.get("type") == "text"
                )

        if not user_question.strip():
            yield "Please enter a question about Chapter 24 regulations."
            return

        # Get API key from user metadata for calling backend
        api_key = ""
        if __metadata__:
            api_key = __metadata__.get("token", "")
        if not api_key and __user__:
            api_key = __user__.get("api_key", "")

        # ── RETRIEVAL PIPELINE ──────────────────────────────────────

        retrieval_start = time.time()
        all_sections = []
        matched_entities = []
        related_entities = []
        debug_info = {}

        try:
            # Step 1: Entity search
            entities = self._search_entities(user_question)
            matched_entities = entities
            entity_uuids = [e["uuid"] for e in entities]

            # Step 2: Get sections via entity traversal
            entity_sections = self._get_sections_for_entities(entity_uuids)
            all_sections.extend(entity_sections)

            # Step 2b: Get related entities for richer understanding
            related_entities = self._get_related_entities(entity_uuids)

            # Step 3: Direct episodic search (catches what entity linking missed)
            direct_sections = self._search_sections_direct(user_question)
            all_sections.extend(direct_sections)

            retrieval_time = time.time() - retrieval_start

            if self.valves.debug:
                debug_info = {
                    "matched_entities": [
                        {"name": e["name"], "score": round(e["score"], 3)}
                        for e in matched_entities
                    ],
                    "related_entities": [e["name"] for e in related_entities],
                    "entity_sections": len(entity_sections),
                    "direct_sections": len(direct_sections),
                    "retrieval_time_ms": round(retrieval_time * 1000),
                }

        except Exception as e:
            yield f"**Retrieval error:** {str(e)}\n\nPlease check Neo4j connection settings."
            return

        # Step 4: Assemble context
        context_text, citations = self._assemble_context(all_sections)

        if not context_text:
            yield (
                "I couldn't find any relevant regulatory sections in Chapter 24 for your question. "
                "This could mean:\n"
                "- The topic isn't covered by Chapter 24 (Environmental Protection)\n"
                "- Try rephrasing with specific regulatory terms (e.g., 'BOD limits', 'discharge permit', 'stormwater standards')\n"
            )
            if self.valves.debug and debug_info:
                yield f"\n\n**Debug:** {json.dumps(debug_info, indent=2)}"
            return

        # Step 5: Build augmented prompt
        system_prompt = self._build_system_prompt(context_text, citations)

        # Build messages for backend LLM
        llm_messages = [{"role": "system", "content": system_prompt}]

        # Include conversation history (last few messages) for context
        for msg in messages[-6:]:
            if msg.get("role") in ("user", "assistant"):
                llm_messages.append(
                    {"role": msg["role"], "content": msg.get("content", "")}
                )

        # Step 6: Call backend LLM (streaming)
        for chunk in self._call_backend_llm(llm_messages, api_key):
            yield chunk

        # Append citation footer
        if citations:
            yield "\n\n---\n**Sources:**\n"
            for c in citations:
                yield f"- [{c['index']}] {c['section']}\n"

        # Debug info
        if self.valves.debug and debug_info:
            yield f"\n\n<details><summary>Retrieval Debug</summary>\n\n```json\n{json.dumps(debug_info, indent=2)}\n```\n</details>"
