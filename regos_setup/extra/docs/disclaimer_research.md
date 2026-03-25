# RegOS Disclaimer Strategy — Research & Recommendations

## The Problem

The current RegOS disclaimer reads:

> *This is an AI-generated draft analysis based on Miami-Dade County Chapter 24, not a final compliance determination. Source confidence: X%. Verify all requirements against the original regulation text and consult qualified professionals before acting on this guidance.*

This undermines RegOS's credibility because APAS **is** the qualified professional. Telling your own users to "consult qualified professionals" when they're environmental consultants using a tool built by environmental consultants is counterproductive. It signals weakness, not transparency.

---

## What the Research Found

### 1. The Trust Paradox — Disclaimers Actually Erode Professional Trust

A 2025 peer-reviewed study across 13 experiments with 5,000+ participants found that **disclosing AI usage makes professionals appear less trustworthy, not more** [1]. This effect is robust — framing, timing, and making disclosure voluntary vs. mandatory doesn't fix it.

Professional users interpret "consult a qualified professional" disclaimers as liability-shifting and a signal that the vendor doesn't understand the user's actual role [2]. For domain experts using AI tools, generic disclaimers feel patronizing.

### 2. How the Big Players Handle It

None of the leading legal/compliance AI tools use "consult a professional" language. Instead:

**Harvey AI** (legal): Frames output as "a research tool" with output that "may contain errors" — but never says "consult a lawyer." The professional relationship is assumed [3].

**CoCounsel (Thomson Reuters)**: Uses conditional confidence — "As long as the user stays within the skills for which CoCounsel is trained, they should be able to have confidence in the results." Their Terms require "human review" but frame it as standard professional practice, not a lack of confidence [4].

**Westlaw AI**: Calls output "a starting point" and says "always verify results with additional research" — framing verification as normal professional workflow, not a warning [5].

**Pattern**: Professional tools frame verification as **standard practice**, not as a **deficiency warning**. They never tell professionals to "consult a professional."

### 3. What Professional Users Actually Want (Instead of Disclaimers)

Research from Harvard Business Review [6] and enterprise adoption studies shows professionals prefer:

- **Explainability** — Show HOW the answer was derived (RegOS already does this with traces)
- **Source verification** — Show WHERE the information came from (RegOS already does this with citations)
- **Confidence indicators** — Quantify certainty (RegOS already does this with scoring)
- **Scope clarity** — State what the analysis covers and doesn't cover (the Gaps & Limitations section)

RegOS already has all four. The disclaimer is the weakest link.

### 4. Why You Still Need SOMETHING (The Risk Side)

You can't remove disclaimers entirely. Here's why:

**Legal liability**: Courts hold that even professional tools must set verification expectations. In the Workday discrimination case (2025), the court held an AI vendor directly liable for tool outputs. RegOS would face the same exposure [7].

**Insurance**: E&O insurers are implementing AI-specific exclusions. If AI use is undisclosed or verification expectations aren't documented, insurers can deny coverage [8].

**Regulatory trajectory**: The FTC mandated AI disclosure (October 2024). The EU AI Act requires transparency by August 2026. Colorado's AI law takes effect February 2026. The trend is toward mandatory disclosure, not away from it [9].

**The bottom line**: You need a disclaimer, but it should be a **professional confidence statement**, not a **credibility-undermining warning**.

---

## Recommended Approach: Conditional, Confident Disclaimers

Based on the research, the best approach for a professional AI tool is **conditional disclaimers** — the language changes based on what the system actually knows and doesn't know.

### Option A: Confidence-Based Conditional Disclaimer

The disclaimer adapts based on the confidence score and what was retrieved:

**When confidence is HIGH (80%+) and sections are complete:**
> *RegOS analysis based on Miami-Dade County Chapter 24, Sections [G1]–[G5]. Source confidence: 85%. Review the cited sections for your specific facility context.*

**When confidence is MEDIUM (50–79%):**
> *RegOS analysis based on Miami-Dade County Chapter 24. Source confidence: 67% — some applicable sections may not have been retrieved. Cross-check critical requirements against the full regulation text.*

**When confidence is LOW (<50%):**
> *Limited regulatory context was retrieved for this query. Source confidence: 32%. This analysis should be verified against the full Chapter 24 text before use in any compliance determination.*

**When gaps are detected (missing context):**
> *This analysis covers [retrieved scope]. The following context was not available: [specific gaps]. Provide [missing info] for a more complete analysis.*

### Option B: Professional Workflow Framing

Frame verification as standard professional practice, not a product deficiency:

> *RegOS regulatory analysis — Miami-Dade Chapter 24. Source confidence: X%. Recommended workflow: (1) Review cited sections for your facility context, (2) Verify critical thresholds against current DERM guidance, (3) Apply site-specific engineering judgment where noted in Gaps & Limitations.*

### Option C: Scope-Only Disclaimer (Minimal)

State only what the analysis covers, not what it can't do:

> *Analysis scope: Miami-Dade County Chapter 24, Sections [G1]–[G5]. Source confidence: X%. See Gaps & Limitations for areas requiring additional context.*

### Option D: Engagement-Level Disclaimer (Not Per-Response)

Move the full disclaimer to the service agreement / onboarding, and use only a minimal per-response footer:

**In service agreement (one-time):**
> "RegOS analyses are AI-assisted regulatory reviews. All outputs are professional-grade starting points intended for use within a professional compliance workflow. Users are expected to apply domain expertise, site-specific context, and current regulatory interpretations as part of their standard review process."

**Per-response footer:**
> *Source confidence: X% · [N] sections cited · See Gaps & Limitations*

---

## What Changes in the Code

The current disclaimer is hardcoded in `graphrag_filter.py` outlet (line ~660). Whatever approach you choose, I'll implement it as a conditional system that adapts based on:

1. `self._confidence_score` — the retrieval confidence
2. `self._confidence_band` — HIGH / MEDIUM / LOW
3. `len(self._citations)` — how many sections were retrieved
4. The Gaps & Limitations section presence (from the LLM response)

---

## My Recommendation

**Option A (Confidence-Based Conditional)** is the strongest choice. Here's why:

1. **It's honest without being self-deprecating** — when confidence is high, the disclaimer is minimal. When confidence is low, it says so clearly. This is what professionals expect.
2. **It's specific** — instead of a generic "verify everything," it tells the user exactly what to verify and why.
3. **It protects you legally** — courts and insurers see conditional, specific disclaimers as more responsible than blanket ones.
4. **It differentiates RegOS** — no other compliance AI tool does this. Most use blanket disclaimers. A confidence-adaptive disclaimer is a product feature, not a liability.

You could also combine A with D — conditional per-response footer plus a one-time service agreement disclaimer for full legal coverage.

---

## Decision (Implemented in v0.8.1)

**Chosen approach:** Amalgam of Options A + B + D.

The team selected a 3-state conditional disclaimer system that combines confidence-based adaptation (Option A), professional workflow framing (Option B), and a minimal per-response footer philosophy (Option D). The implementation:

**State 1 — HIGH confidence (≥80%, full retrieval):** Minimal footer. Names the cited sections, states the confidence percentage, and says "Review cited sections for your specific facility context." No warnings. Assumes the user is a professional.

**State 2 — MEDIUM confidence (50–79%, partial retrieval):** Acknowledges potential gaps. "Some applicable sections may not have been retrieved. Cross-check critical requirements against the full regulation text for completeness." Uses professional workflow language, not deficiency language.

**State 3 — LOW confidence (<50%, ≤1 section retrieved):** Honest about limitations. "Limited regulatory context was retrieved for this query." Tells the user how to get a better answer: "Provide more specific details about your compliance question for a stronger analysis."

**What was eliminated:**
- "consult qualified professionals" — removed entirely
- "not a final compliance determination" — removed entirely
- Any language that positions RegOS as uncertain about its own capabilities

**Implementation:** `_build_disclaimer()` method in `graphrag_filter.py` (v0.8.1). The one-time engagement-level disclaimer (Option D) is documented in the service agreement language above and is recommended for inclusion in the RegOS onboarding flow, but is not implemented in code — it belongs in the service agreement, not in per-response output.

---

## Sources

1. [The transparency dilemma: How AI disclosure erodes trust — ScienceDirect (2025)](https://www.sciencedirect.com/science/article/pii/S0749597825000172)
2. [AI Disclosure is literally meaningless in a professional context — Medium](https://dirksonguer.medium.com/ai-disclosure-is-literally-meaningless-in-a-professional-context-5d138c48929d)
3. [Harvey AI Legal Terms](https://www.harvey.ai/legal)
4. [Casetext CoCounsel Overview](https://topaitools.com/tools/casetext)
5. [Thomson Reuters Launches CoCounsel Legal — LawNext](https://www.lawnext.com/2025/08/thomson-reuters-launches-cocounsel-legal-with-agentic-ai-and-deep-research-capabilities-along-with-a-new-and-final-version-of-westlaw.html)
6. [How to Get Your Customers to Trust AI — Harvard Business Review](https://hbr.org/2026/01/how-to-get-your-customers-to-trust-ai)
7. [AI Vendor Liability Squeeze — Jones Walker LLP](https://www.joneswalker.com/en/insights/blogs/ai-law-blog/ai-vendor-liability-squeeze-courts-expand-accountability-while-contracts-shift-risk.html)
8. [AI-Related Insurance Policy Exclusions — Zelle Law](https://www.zellelaw.com/AI_Update_The_Growing_Trend_of_AI-Related_Insurance_Policy_Exclusions)
9. [EU AI Act Article 50 — Transparency Obligations](https://artificialintelligenceact.eu/article/50/)
10. [ABA Formal Opinion 512 — Ethics Guidance on AI Tools](https://www.americanbar.org/content/dam/aba/administrative/professional_responsibility/ethics-opinions/aba-formal-opinion-512.pdf)
11. [Open WebUI Community — Discussion #16099](https://github.com/open-webui/open-webui/discussions/16099)
