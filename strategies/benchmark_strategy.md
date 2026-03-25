# PDF Extraction Benchmark Strategy
## Docling vs GPT-4o Vision — Opa-Locka Code of Ordinances

**Document:** Opa-locka, FL Code of Ordinances (948 pages, 5.4MB)
**Goal:** Determine the best extraction approach for RegOS GraphRAG pipeline — comparing IBM Docling (local, free) vs GPT-4o Vision via OpenRouter (cloud API, paid).

---

## 1. Test Pages (10 pages across 5 content types)

| Pages | Content Type | Why It Matters |
|-------|-------------|----------------|
| 1–2 | Table of Contents / Instruction sheet | Tests structure detection, page layout parsing |
| 100–101 | Dense legal text with nested subsections (a)(b)(c)(d) | Core use case — most of the document is this |
| 200–201 | Fee schedules with indented pricing ($ amounts, numbered items) | Tests numeric extraction + indentation preservation |
| 500–501 | Rate tables with columns (meter sizes, dates, dollar amounts) | Tests table extraction — critical differentiator |
| 750–751 | Land Development Code with lettered subsections (A)(B)(I)(II) | Tests different numbering scheme + cross-references |

**Total: 10 pages** — enough for statistical validity, small enough to run quickly.

---

## 2. Evaluation Metrics (3 dimensions)

### Dimension 1: Content Recovery (order-independent)
Measures *what percentage of the source content was captured*, regardless of text order.

```python
# Bag-of-words overlap (unigrams)
def content_recovery(baseline_text, extracted_text):
    baseline_words = set(baseline_text.lower().split())
    extracted_words = set(extracted_text.lower().split())
    if not baseline_words:
        return 0.0
    return len(baseline_words & extracted_words) / len(baseline_words)
```

This fixes the main problem from the first benchmark — Docling reorders multi-column text but still captures 95%+ of the content. This metric won't penalise reordering.

Also compute **bigram overlap** (pairs of consecutive words) to catch cases where words are present but context is garbled.

### Dimension 2: Structural Fidelity
Measures *how well the extraction preserves the document's legal structure*.

Score these with regex patterns against both outputs:

| Element | Pattern | Points |
|---------|---------|--------|
| Section numbers | `Sec. 21-66`, `§ 22-118` | 2 per correct detection |
| Article/Division headers | `DIVISION 3.`, `ARTICLE II` | 3 per correct detection |
| Subsection nesting | `(a)`, `(b)(i)`, `(1)(a)` | 1 per correct detection |
| Cross-references | `pursuant to section X` | 1 per preserved reference |
| Ordinance citations | `Ord. No. 16-06, § 2` | 1 per correct citation |
| Table structure | Correctly parsed rows/columns | 5 per table |

Count what pdftotext finds as the expected count, then score each tool on what percentage they detect.

### Dimension 3: GraphRAG Chunk Quality
The ultimate test — *does the extraction produce good chunks for Neo4j ingestion?*

After extraction, run both outputs through the same chunking logic (split on section boundaries). Then evaluate:

- **Chunk count** — closer to the actual number of sections = better
- **Average chunk size** — ideal 500–2000 chars for embedding
- **Section boundary alignment** — does each chunk start with a section number?
- **Cross-reference preservation** — are `pursuant to section X` references intact within chunks?

---

## 3. Pipeline Architecture

### Pipeline A: Docling

```
PDF → Docling (--to md + --to json) → Parse JSON for structure labels → Chunk by section_header labels → Evaluate
```

**Key:** Run Docling with both markdown AND JSON output. The JSON gives you element-level labels (`section_header`, `list_item`, `text`, `table`, `page_header`, `page_footer`) which are directly useful for intelligent chunking. The markdown is for human-readable comparison.

```bash
# Install
pip install docling

# Run both outputs
docling --from pdf --to md --no-ocr "Opa-locka, FL Code of Ordinances.pdf" --output docling_md/
docling --from pdf --to json --no-ocr "Opa-locka, FL Code of Ordinances.pdf" --output docling_json/
```

**Docling JSON structure** (from our test run):
```json
{
  "texts": [
    {"label": "section_header", "text": "Sec. 24-9. Contempt powers."},
    {"label": "text", "text": "Environmental Quality Control Board..."},
    {"label": "list_item", "text": "(a) The storage of factory..."},
    {"label": "page_header", "text": "§ 24-8"},
    {"label": "page_footer", "text": "CD24:42"}
  ]
}
```

The `section_header` labels are gold for chunking — you split on those boundaries. GPT-4o doesn't natively produce this metadata.

### Pipeline B: GPT-4o Vision via OpenRouter

```
PDF → pdf2image (render pages at 200 DPI) → base64 encode → OpenRouter API (GPT-4o) → Parse markdown → Chunk by heading levels → Evaluate
```

```python
import openai

client = openai.OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key="YOUR_OPENROUTER_KEY",
)

response = client.chat.completions.create(
    model="openai/gpt-4o",
    messages=[{
        "role": "user",
        "content": [
            {"type": "text", "text": EXTRACTION_PROMPT},
            {"type": "image_url", "image_url": {
                "url": f"data:image/png;base64,{page_image_b64}",
                "detail": "high"
            }}
        ]
    }],
    max_tokens=4096,
    temperature=0.0,
)
```

**Extraction prompt** (tuned for municipal code):
```
Extract ALL text from this municipal code page verbatim. Output as structured markdown.

Rules:
1. Use ## for Article/Division headers, ### for Section headers (e.g., ### Sec. 21-66)
2. Preserve ALL section numbers exactly (§ 22-118, Sec. 21-66)
3. Preserve ALL subsection labels exactly: (a), (b), (1), (i), (ii)
4. Render tables as markdown tables with | delimiters
5. Preserve ALL dollar amounts, dates, and numeric values exactly
6. Preserve ALL ordinance citations (Ord. No. XX-XX, § X, date)
7. Preserve ALL cross-references ("pursuant to section X")
8. Do NOT summarise, paraphrase, or skip any text
9. Mark page headers (§ XX-XX) and footers (CD21:42) with <!-- header --> and <!-- footer --> comments
```

### Pipeline C: Baseline (pdftotext)

```bash
pdftotext -f START -l END "Opa-locka, FL Code of Ordinances.pdf" baseline.txt
```

This is the reference — not perfect, but deterministic and consistent.

---

## 4. CPU Normalisation

Since Docling runs locally and GPT-4o runs on OpenAI servers, raw timing isn't comparable.

**Approach:** Run a single-threaded arithmetic benchmark on your Mac to establish a normalisation factor. Then report both raw and normalised times.

```python
import time

def cpu_benchmark():
    start = time.perf_counter()
    total = 0
    for i in range(2_000_000):
        total += i * i % 997
    return time.perf_counter() - start

# Run 3 times, take median
times = sorted([cpu_benchmark() for _ in range(3)])
your_cpu_score = times[1]

# Reference: M2 Pro = ~0.30s, M1 = ~0.40s, Intel i7 = ~0.35s
REFERENCE_SEC = 0.30  # M2 Pro baseline
normalisation_factor = your_cpu_score / REFERENCE_SEC
```

**Report both:**
- Raw time/page (what actually happened)
- Normalised time/page (what it would be on reference hardware)
- Projected full-document time (normalised × 948 pages)

---

## 5. Cost Calculation

### Docling
- Software: $0.00 (MIT license)
- Compute: Your existing hardware (electricity only)
- **Total: $0.00**

### GPT-4o via OpenRouter

Check current OpenRouter pricing at runtime:
```python
# OpenRouter pricing (as of March 2026, verify at openrouter.ai/models)
# GPT-4o: ~$2.50/1M input tokens, ~$10.00/1M output tokens
# Each page image at "high" detail: ~1,100 input tokens
# Extraction prompt: ~200 input tokens
# Expected output: ~600-1000 tokens per page

input_cost_per_page = (1300 * 2.50) / 1_000_000   # ~$0.00325
output_cost_per_page = (800 * 10.00) / 1_000_000   # ~$0.008
total_cost_per_page = input_cost_per_page + output_cost_per_page  # ~$0.011

cost_full_doc = total_cost_per_page * 948  # ~$10.43
```

---

## 6. Execution Steps

### Step 1: Setup (5 min)
```bash
pip install docling openai pdf2image Pillow
# Ensure poppler-utils installed (for pdftotext, pdfseparate, pdf2image)
brew install poppler  # macOS
```

### Step 2: Extract test pages (2 min)
```bash
# Create 5 separate PDFs for each page range
for range in "1-2" "100-101" "200-201" "500-501" "750-751"; do
    FIRST=$(echo $range | cut -d- -f1)
    LAST=$(echo $range | cut -d- -f2)
    pdfseparate -f $FIRST -l $LAST "Opa-locka, FL Code of Ordinances.pdf" "pages/p%d.pdf"
    pdfunite pages/p*.pdf "samples/sample_${range}.pdf"
    rm pages/p*.pdf
done
```

### Step 3: Run Docling on each sample (~10 min total)
```bash
for sample in samples/sample_*.pdf; do
    name=$(basename "$sample" .pdf)
    docling --from pdf --to md --no-ocr "$sample" --output "results/docling_md/$name/"
    docling --from pdf --to json --no-ocr "$sample" --output "results/docling_json/$name/"
done
```

### Step 4: Run GPT-4o Vision on each sample (~2 min total)
```python
# benchmark_gpt4o.py — processes each page individually
# Uses OpenRouter API
# Saves raw responses + timing + token counts
```

### Step 5: Run pdftotext baseline
```bash
for range in "1-2" "100-101" "200-201" "500-501" "750-751"; do
    FIRST=$(echo $range | cut -d- -f1)
    LAST=$(echo $range | cut -d- -f2)
    pdftotext -f $FIRST -l $LAST "Opa-locka, FL Code of Ordinances.pdf" "results/baseline/baseline_${range}.txt"
done
```

### Step 6: Score and generate report
```python
# score_benchmark.py — computes all metrics and generates the .docx report
```

---

## 7. Report Structure

The final .docx report will contain:

1. **Executive Summary** — verdict table, recommended approach
2. **Methodology** — what was tested, how, why
3. **Results by Content Type** — per-range comparison tables
4. **Aggregate Results** — overall winner per dimension
5. **Cost Analysis** — per-page and projected full-document
6. **GraphRAG Readiness** — which produces better chunks
7. **Docling Structural Metadata** — showcase the JSON element labels
8. **Recommendation** — final verdict with rationale
9. **Appendix** — raw extraction samples side-by-side

---

## 8. What "Fair" Means

To ensure neither tool is advantaged:

- **Same input:** Both process identical page images / PDFs
- **Best configuration:** Docling runs with `--no-ocr` (text-based PDF) + `--to json` (richest output). GPT-4o runs with the optimised municipal code prompt above.
- **Content recovery metric:** Order-independent, so Docling's text reordering doesn't get penalised
- **Structure metric:** Both scored on the same checklist of expected elements
- **Docling gets credit for JSON labels:** The element-level metadata (`section_header`, `list_item`, etc.) is scored as a structural advantage since it directly enables GraphRAG chunking
- **GPT-4o gets credit for semantic understanding:** Ability to resolve ambiguous layouts and extract entities in one pass
- **Speed normalised:** Docling times adjusted for CPU; GPT-4o times include network latency
- **Cost reported honestly:** Docling = $0, GPT-4o = actual OpenRouter charges
