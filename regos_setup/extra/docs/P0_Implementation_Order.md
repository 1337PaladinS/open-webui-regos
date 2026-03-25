# P0 Implementation Order

## The Order

1. Audit Logging Schema
2. GraphRAG Pipe (Entity Linker → Cypher Generator → Neo4j Traversal → ChromaDB Ranking → Answer Validation)
3. Confidence Scoring Engine
4. Enterprise Output Formatting
5. Escalation Workflow (Case Packets + Configurable Thresholds)
6. Regulatory Threshold Evaluation Engine
7. Dashboard
8. Refusal & Guardrails Improvements

## Why This Order

**1. Audit Logging Schema — first because it's cheap and everything else writes to it.**

The audit schema is just a data model — a table definition and a few API endpoints. It takes a couple of hours to design and wire up. But every single feature after this (the Pipe, confidence scoring, escalation, guardrails) needs to emit audit records. If you build the schema first, you instrument as you go. If you build it last, you have to go back and retrofit logging into every feature you already built. The blueprint says it explicitly: "instrument from day one — retroactively adding audit trails is not viable." This is the cheapest thing on the list and the most expensive to skip.

**2. GraphRAG Pipe — second because it's the biggest blocker and nothing works without it.**

The Pipe is the core product. The demo is: user asks a question, gets a cited compliance answer via graph-guided retrieval. Features 3 through 7 all depend on or enhance the Pipe's output. Confidence scoring scores the Pipe's retrieval. Enterprise formatting formats the Pipe's response. Escalation triggers on the Pipe's confidence. The dashboard displays the Pipe's answers. You can't build or meaningfully test any of those without the Pipe running end-to-end. It's also the hardest thing on the list — entity linking, Cypher generation, graph traversal, hybrid ranking, answer validation — so you want maximum time for iteration and debugging. Start it second (after audit schema is in place so you can log as you build).

**3. Confidence Scoring — third because escalation and formatting both need it.**

The escalation workflow triggers when confidence is below a threshold. The enterprise response template displays the confidence score. Both are downstream. The scoring engine itself is a function that takes retrieval signals (relevance scores, coverage completeness, graph dependency satisfaction, reranker scores) and outputs a number. It plugs into the Pipe as Step 8. You need it working before you can build escalation logic or display it in the formatted output. It's also medium difficulty — the hardest part is agreeing on what signals to use and how to weight them, not the code.

**4. Enterprise Output Formatting — fourth because it's the demo surface.**

At this point you have: a working GraphRAG Pipe that returns cited answers, a confidence score on each response, and audit records for everything. But the output still looks like raw text in a chat bubble. Enterprise formatting turns that into the structured template — determination header, citation block, confidence badge, escalation indicator. It's a presentation layer: backend formatting logic in the Pipe's outlet plus a Svelte component for the frontend. Medium difficulty, no blockers, and it makes everything you've already built look demo-ready.

**5. Escalation Workflow — fifth because it needs confidence scoring and formatting to exist.**

Escalation is: confidence score below threshold → generate case packet → send to n8n → show indicator in response. You need the confidence score (Feature 3) to trigger it. You need the enterprise template (Feature 4) to display the escalation indicator. You need the Pipe (Feature 2) to generate the case packet contents. All three are done by now. The work here is: bundle the case packet from data you already have, call the existing n8n webhook with a richer payload, and add a configurable threshold Valve. This is wiring, not invention.

**6. Regulatory Threshold Evaluation — sixth because it has a cross-team dependency.**

This needs normalized sensor data from the Pump Station Ontology team. You don't control that timeline. Building this earlier means you might be blocked waiting for data. Building it here means you've already shipped the entire chat/query experience (Features 1–5) and you're now adding the monitoring layer. The implementation itself is straightforward — a background service that compares readings against a curated threshold table and stores breach records with SHA-256 hashes. Register a Tool so the chat can query breaches. The hard part is curating the threshold table from Chapter 24, which is a data task someone can do in parallel while you build Features 1–5.

**7. Dashboard — seventh because it consumes everything above.**

The dashboard displays compliance status (from the threshold engine), breach alerts (from the threshold engine), and embeds the chat (the Pipe). It's a consumer of data, not a producer. Building it earlier means you'd have nothing to display. Building it here means every data source it needs is already live. It's a single Svelte page — a new route at `/dashboard` with some status indicators, a breach list, and an embedded chat component. The Open WebUI codebase already has an admin analytics page you can use as a reference. Medium difficulty, no unknowns.

**8. Refusal & Guardrails — last because it already works and the gap is small.**

The blueprint calls this "the lightest P0 workstream — the foundation is solid and the gaps are incremental." Refusal already works via system prompts. The system already recommends alternatives. What's left is: format refusals using the enterprise template (which exists by now), log guardrail triggers to the audit record (which exists by now), and run an adversarial test suite. These are polish tasks. The Pipe (Feature 2) can also add hard guardrails — short-circuiting when graph traversal returns nothing — which you'd naturally add while building the Pipe anyway. Doing this last means you're testing and hardening a system that's otherwise complete.
