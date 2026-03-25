"""
LLM-based contextual prefix generation for chunks.
Uses OpenRouter (or any OpenAI-compatible endpoint).
"""
import os
from openai import OpenAI


def get_client() -> OpenAI:
    return OpenAI(
        api_key=os.environ.get("OPENROUTER_API_KEY", ""),
        base_url=os.environ.get("LLM_BASE_URL", "https://openrouter.ai/api/v1"),
    )


def generate_context_prefix(
    chunk_text: str,
    breadcrumb: str,
    document_name: str,
    content_type: str,
) -> str:
    """
    Generate a 1-2 sentence context prefix for a chunk.
    This implements Summary-Augmented Chunking (SAC) from arXiv:2510.06999.
    """
    model = os.environ.get("LLM_MODEL", "openai/gpt-4o-mini")
    client = get_client()

    prompt = f"""You are a legal document analyst. Generate a 1-2 sentence context prefix for this regulatory text chunk. The prefix should:
1. State what document and section this is from
2. Summarize what this section covers
3. Note any key relationships to other sections if apparent

Document: {document_name}
Location: {breadcrumb}
Content type: {content_type}

Text:
{chunk_text[:2000]}

Write ONLY the context prefix (1-2 sentences), nothing else. Start with "[Context: ..." and end with "]"."""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.3,
        )
        prefix = response.choices[0].message.content.strip()
        if not prefix.startswith("[Context:"):
            prefix = f"[Context: {prefix}]"
        if not prefix.endswith("]"):
            prefix = prefix + "]"
        return prefix
    except Exception as e:
        return f"[Context: {breadcrumb} in {document_name}. Content type: {content_type}.]"


def enrich_chunks(chunks: list[dict], progress_callback=None) -> list[dict]:
    """
    Add contextual prefixes to all chunks.
    Returns enriched chunks with context_prefix and enriched_text fields.
    """
    total = len(chunks)
    for i, chunk in enumerate(chunks):
        meta = chunk["metadata"]
        prefix = generate_context_prefix(
            chunk_text=chunk["text"],
            breadcrumb=meta["breadcrumb"],
            document_name=meta["document"],
            content_type=meta["content_type"],
        )
        chunk["context_prefix"] = prefix
        chunk["enriched_text"] = f"{prefix}\n\n{chunk['text']}"

        if progress_callback:
            progress_callback(i + 1, total)

    return chunks
