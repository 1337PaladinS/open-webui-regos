# RegOS P0 Demo Script

**Duration:** ~10 minutes
**Presenter:** APAS Team
**System:** Better Hardeep.ai (Open WebUI + GraphRAG + Audit Logger)
**Comparison:** Hardeep.ai (Open WebUI, KB only)

---

## Opening (30 seconds)

> "RegOS is a regulatory compliance AI built on Open WebUI. Today I'll show you three features we've shipped: a knowledge graph retrieval pipeline that finds regulatory content pure text search misses, a confidence scoring system that tells users how reliable each answer is, and a full audit trail that captures every interaction for compliance review."

---

## Act 1: The Problem with Pure RAG (2 minutes)

**Open Hardeep.ai** (the baseline system with Knowledge Base only).

**Ask this exact query:**

> What treatment standards apply to facilities near the Everglades?

**What happens:** The system returns Sec. 24-15.3 — a section about *how to design* sewage works (engineering reference manuals). It cites the WPCF manual and the Florida State Board of Health sewerage guide.

**What to say:**

> "This looks authoritative — it cites specific code sections and federal regulations. But it's answering the wrong question. Sec. 24-15.3 is about *plan preparation standards* — which engineering manuals to follow when designing a facility. A compliance officer asking 'what limits must I meet?' gets told to read the WPCF manual. No actual discharge limits appear anywhere in this answer."

**Why it failed:** ChromaDB matched the words "treatment" and "standards" to Sec. 24-15.3 (titled "Standards for preparation of plans"). The section with actual treatment limits — Sec. 24-42.1 "Tertiary treatment requirements" — was never retrieved because the words "Everglades," "facilities," and "standards" don't appear prominently in it.

> "This is the core problem with pure text-based retrieval: it matches words, not concepts. And the failure is invisible — the model sounds confident even though it's answering from the wrong source."

---

## Act 2: GraphRAG Finds What Text Search Misses (3 minutes)

**Switch to Better Hardeep.ai** (GraphRAG + KB system).

**Ask the same exact query:**

> What treatment standards apply to facilities near the Everglades?

**What happens:** The system returns actual numeric discharge limits from Sec. 24-42.1, plus Everglades-specific provisions from Sec. 24-48.21 (Bird Drive Basin Plan).

**Point out these specifics:**

- BOD effluent not exceeding 15.0 mg/l with 95% removal
- TSS not exceeding 15.0 mg/l with 95% removal
- Phosphorous not exceeding 1.0 mg/l
- MBAS not exceeding 3.0 mg/l
- Bird Drive Everglades Wetland Basin consistency requirements
- Stormwater management requirements for the North Trail Basin

**What to say:**

> "Same question, dramatically different answer. The system found Sec. 24-42.1 — the actual tertiary treatment limits — even though the words in the query don't match the section title. It did this through concept expansion: the knowledge graph uses a 3-layer architecture where ontology concepts (Ch24Class nodes) connect to regulatory documents (Ch24Document nodes) which mention specific entities (Ch24Entity nodes). By traversing concept relationships in the ontology, the graph found related sections that pure word matching would have missed."

> "It also found the Everglades-specific Bird Drive Basin Plan requirements from Sec. 24-48.21, which pure text search missed entirely."

**If someone asks 'is this answer perfect?':**

> "No — the model presents county-wide tertiary treatment limits as if they're Everglades-specific. That's a reasoning error, not a retrieval error. The right sections were found; the model drew an imprecise conclusion about scope. Retrieval errors are systemic and invisible. Reasoning errors are correctable — through better prompting, confidence scoring, or human review — because the source material is present."

---

## Act 3: Confidence Scoring — Trust but Verify (3 minutes)

**Stay on Better Hardeep.ai.** Turn on trace mode in valves for the fullest view (`show_trace: true`, `show_confidence: true`).

### Demo 3a: Strong Query

**Ask:**

> What are the BOD limits for industrial discharge?

**Expected result:** Confidence badge shows **HIGH (0.73)**.

**What to say:**

> "Every response now carries a confidence score. This one scored 0.73 — HIGH. The score is computed from 6 signals: average document fulltext match quality (0.30), the number of documents matched (0.15), concept expansion through ontology traversal finding related sections (0.25), the final number of assembled sections (0.12), whether the graph found unique sections text missed (0.10), and direct text relevance (0.08). It's a weighted composite that tells us how well the retrieval pipeline performed — not whether the LLM's answer is correct."

### Demo 3b: Vague Query

**Ask:**

> tell me about regulations

**Expected result:** Confidence badge shows **MEDIUM (0.48)** — noticeably lower.

**What to say:**

> "Same system, vague query. Score dropped to 0.48. The document fulltext match quality fell from 0.30 to 0.12 — the system matched sections like 'stream regulation', 'Bud' and 'zoning' instead of precise regulatory concepts. The score correctly tells us: the retrieval found *something*, but the matches are weak and may not be relevant."

### Demo 3c: Off-Topic Query

**Ask:**

> hello

**Expected result:** Confidence badge shows **LOW (0.00)**.

**What to say:**

> "Zero. No entities found, no sections retrieved, no context for the LLM. The system knows it has nothing to work with. When confidence is LOW, the LLM is automatically instructed to hedge its answer and recommend verifying with the original regulation text. In future versions, LOW confidence will trigger an escalation workflow — flagging the interaction for human review."

### Score Ranking Summary

> "The scoring correctly ranks: specific regulatory queries (0.67–0.73, HIGH) above vague queries (0.48, MEDIUM) above off-topic (0.00, LOW). This gives compliance teams a reliable signal for which answers to trust and which to review."

---

## Act 4: Audit Trail — Everything is Recorded (2 minutes)

**Open a terminal or DB viewer. Run this SQL against `/app/backend/data/audit.db`:**

```sql
SELECT
    query_text,
    confidence_score,
    confidence_signals,
    user_email,
    timestamp,
    substr(response_text, 1, 80) AS response_preview
FROM audit_records
ORDER BY epoch DESC
LIMIT 5;
```

**What to say:**

> "Every single interaction is captured in a structured audit database. You can see the three queries we just ran — 'hello' with confidence 0.00, 'tell me about regulations' at 0.58, and the BOD query at 0.73. Each record includes the full query text, the complete LLM response, the confidence score and all 6 underlying signals as JSON, the user identity, and timestamps."

**Point out specific fields:**

- `confidence_score` — the numeric score
- `confidence_signals` — full JSON with all 6 raw signals (entity scores, counts, overlap, etc.)
- `user_email`, `user_role` — who asked
- `chat_id`, `session_id` — traceable to specific conversations
- `record_hash` — tamper-evident SHA-256 hash

> "This audit trail is the foundation for everything else we're building: escalation workflows that trigger on low confidence, threshold evaluation for quality monitoring, and a compliance dashboard. Every feature writes to and reads from this same table."

---

## Closing (30 seconds)

> "Three features, one pipeline: the knowledge graph finds what text search misses, confidence scoring tells you how much to trust each answer, and the audit trail captures everything for review. Next up: enterprise output formatting, automated escalation on low-confidence answers, and the compliance dashboard."

---

## Quick Reference: Queries to Use

| Query | Expected Score | Band | Key Demo Point |
|---|---|---|---|
| What treatment standards apply to facilities near the Everglades? | 0.67 | MEDIUM | GraphRAG vs pure RAG comparison |
| What are the BOD limits for industrial discharge? | 0.73 | HIGH | Strong concept expansion, multiple related sections |
| What local rules implement federal pretreatment? | 0.72 | HIGH | Cross-referencing federal/local provisions |
| tell me about regulations | 0.48 | MEDIUM | Weak document matches, score correctly drops |
| hello | 0.00 | LOW | Zero retrieval, hedging triggered |

## Valve Settings for Demo

| Valve | Setting | Why |
|---|---|---|
| `show_confidence` | `true` | Badge visible on every response |
| `show_trace` | `true` for Act 3, `false` for Acts 1–2 | Trace shows signal breakdown (useful in Act 3), but clutters the comparison in Acts 1–2 |
| `debug` | `false` | Not needed for demo |

## Fallback: If Neo4j is Slow

If the Neo4j Aura instance has gone to sleep (free tier), the first query may take 5–8 seconds. Ask a warm-up query ("What is BOD?") before starting the demo to wake the connection.
