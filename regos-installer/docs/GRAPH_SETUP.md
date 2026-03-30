# Graph Data Setup

The Neo4j knowledge graph export (`chaptor_24_graph.json`, ~226 MB) is too large for git and must be added manually.

## Option 1: Copy into the installer repo

Place the file in the `data/` directory:

```bash
cp /path/to/chaptor_24_graph.json data/
```

The installer will automatically detect and copy it into the container during Step 03.

## Option 2: Copy directly into the container

```bash
docker cp chaptor_24_graph.json open-webui:/app/backend/data/
```

## Option 3: Import into Neo4j Aura directly

If using Neo4j Aura (cloud), import the graph JSON via the Neo4j import tools rather than storing it in the container filesystem.

## What this file contains

The graph export contains the full Chapter 24 knowledge graph with:

- **141 Ch24Document nodes** — regulatory text sections with titles, section IDs, and full text
- **455 Ch24Entity nodes** — extracted entities (parameters, limits, facilities, zones, etc.)
- **15 Ch24Class nodes** — ontology concepts (SEWER_DISCHARGE_LIMITS, WELLFIELD_PROTECTION, etc.)
- **Relationships**: MENTIONS_ENTITY, RELATES_TO_CONCEPT, SUBCLASS_OF, CH24_RELATIONSHIP

The `graphrag_filter` function queries this graph via the Neo4j connection configured in its Valves.
