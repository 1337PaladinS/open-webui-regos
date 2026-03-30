# graphrag_pipe.py — GraphRAG Pipe

## Status: OBSOLETE (Abandoned v0.1.0)

This was the original v0.1.0 implementation of the GraphRAG pipeline as an Open WebUI **Pipe** (appears as a selectable model in the chat interface, replaces the LLM endpoint). It was abandoned because the Pipe approach caused a deadlock — the Pipe called a backend LLM for answer generation, creating a request-within-a-request loop.

**Replaced by:** `graphrag_filter.py` (v0.3.0+), which uses the **Filter** pattern (inlet/outlet) to work WITH any model rather than replacing the LLM. See `REGOS_CHANGELOG.md`, Session 1, Feature 2 for the full evolution story.

## Why It Remains

Retained as a reference for the original Pipe API surface and as a reminder of why the Filter approach was chosen. May be useful if a Pipe-based architecture is ever reconsidered.
