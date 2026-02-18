"""
pipeline/research.py
Step 2 — Query the knowledge base and assess match quality using GPT.

Returns a dict matching the spec:
{
    "matches": [
        {
            "source_id":        str,   # e.g. "faq-12" or "ticket-287"
            "content_snippet":  str,   # short excerpt
            "similarity_score": float, # 0-1 cosine score
            "source_type":      str    # "faq" | "past_ticket"
        }
    ],
    "search_terms_used": list[str],

    # Internal-use fields (not in public spec, used by orchestrator/drafter):
    "has_enough_info":        bool,   # True when >= 2 non-stale matches score >= 0.7
    "suggested_search_terms": list[str],
    "stale_ids":              list[str]   # source_ids of stale matches
}
"""

from __future__ import annotations
import json
import re
import sys
from pathlib import Path

from openai import OpenAI

sys.path.insert(0, str(Path(__file__).parent.parent / "kb"))
from build_kb import VectorStore  # noqa: E402

# Retry loop parameters — must match orchestrator expectations
SIMILARITY_THRESHOLD = 0.5   # minimum cosine score to count as a strong match
MIN_STRONG_MATCHES   = 2     # need at least this many strong matches to skip retry


SYSTEM_PROMPT = """You are a knowledge-base research agent for a SaaS customer support team.

You are given a support ticket and candidate matches retrieved from a vector KB.
Your job is to summarise each match into a useful content_snippet for the support drafter.

IMPORTANT: Some past ticket resolutions are marked stale=true. Include them in your output
but preserve the stale flag so the drafter knows to avoid them.

Reply with ONLY a JSON object — no prose, no markdown fences:
{
  "matches": [
    {
      "source_id": "<copy exactly from the match header>",
      "content_snippet": "<50-80 word excerpt most relevant to the ticket>",
      "similarity_score": <copy the score float from the match header>,
      "source_type": "<faq|past_ticket>",
      "stale": <true|false>
    }
  ],
  "suggested_search_terms": ["<term1>", "<term2>"]
}

Populate suggested_search_terms with 2-3 alternative search terms that might find
better KB matches for this ticket. Always include them — the orchestrator uses them
if a retry is needed."""


def _extract_json(text: str) -> dict:
    text = re.sub(r"```(?:json)?", "", text).strip().rstrip("```").strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON found in research response:\n{text}")
    return json.loads(match.group())


def research(
    ticket: dict,
    store: VectorStore,
    client: OpenAI,
    search_query: str | None = None,
    top_k: int = 3,
) -> dict:
    """
    Query the vector store, ask GPT to summarise matches, then set has_enough_info
    based on whether >= MIN_STRONG_MATCHES non-stale results score >= SIMILARITY_THRESHOLD.

    ticket must have 'subject' and 'body' keys.
    """
    base_query = f"{ticket.get('subject', '')} {ticket.get('body', '')}".strip()
    query = search_query or base_query
    search_terms_used = query.split()[:6]

    raw_matches = store.query(query, top_k=top_k)

    # Format matches for the prompt — pass scores so GPT can copy them faithfully
    matches_text = "\n\n".join(
        f"[Match {i + 1} | source_id={m['metadata'].get('source_id', f'item-{i}')} | "
        f"score={m['score']:.3f} | "
        f"type={m['metadata'].get('type', '?')} | "
        f"category={m['metadata'].get('category', '?')} | "
        f"stale={m['metadata'].get('stale', False)}]\n{m['text']}"
        for i, m in enumerate(raw_matches)
    )

    user_message = (
        f"SUPPORT TICKET\n"
        f"Subject: {ticket.get('subject', '')}\n"
        f"Body: {ticket.get('body', '')}\n\n"
        f"RETRIEVED KB MATCHES:\n{matches_text}"
    )

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
    )

    result = _extract_json(response.choices[0].message.content)
    result.setdefault("matches", [])
    result.setdefault("suggested_search_terms", [])
    result["search_terms_used"] = search_terms_used

    # ── Retry decision: driven by cosine scores, not GPT's opinion ──────────
    # Count non-stale matches whose similarity_score meets the threshold.
    # GPT copies scores from the prompt header, so these are the real values.
    strong = sum(
        1 for m in result["matches"]
        if not m.get("stale") and m.get("similarity_score", 0) >= SIMILARITY_THRESHOLD
    )
    result["has_enough_info"] = strong >= MIN_STRONG_MATCHES

    # Convenience list for orchestrator logging
    result["stale_ids"] = [
        m["source_id"] for m in result["matches"] if m.get("stale")
    ]

    return result