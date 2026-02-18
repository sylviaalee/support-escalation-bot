"""
pipeline/research.py
Step 2 — Query the knowledge base and assess match quality using GPT.

Returns a dict matching the spec:
{
    "matches": [
        {
            "source_id":        str,   # e.g. "faq-12" or "ticket-287"
            "content_snippet":  str,   # short excerpt
            "similarity_score": float, # 0–1 cosine score
            "source_type":      str    # "faq" | "past_ticket"
        }
    ],
    "search_terms_used": list[str],

    # Internal-use fields (not in public spec, used by orchestrator/drafter):
    "has_enough_info":        bool,
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


SYSTEM_PROMPT = """You are a knowledge-base research agent for a SaaS customer support team.

You are given a support ticket and candidate matches retrieved from the KB.
Your job is to decide which matches are genuinely helpful for answering this ticket.

IMPORTANT: Some past ticket resolutions are marked stale=true. If a match is stale,
still include it in matches but mark it so the drafter can avoid it.

Set has_enough_info=false if:
- No matches are relevant, OR
- All relevant matches are stale, OR
- The top match similarity_score is below 0.55

Reply with ONLY a JSON object — no prose, no markdown fences:
{
  "matches": [
    {
      "source_id": "<e.g. faq-01 or ticket-012>",
      "content_snippet": "<50-80 word excerpt most relevant to the ticket>",
      "similarity_score": <float 0-1>,
      "source_type": "<faq|past_ticket>",
      "stale": <true|false>
    }
  ],
  "search_terms_used": ["<term>"],
  "has_enough_info": <true|false>,
  "suggested_search_terms": ["<term1>", "<term2>"]
}

Only populate suggested_search_terms when has_enough_info=false."""


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
    Query the vector store with the ticket text (or a refined search_query),
    then ask GPT to assess which matches are useful.

    ticket must have 'subject' and 'body' keys.
    """
    base_query = f"{ticket.get('subject', '')} {ticket.get('body', '')}".strip()
    query = search_query or base_query
    search_terms_used = query.split()[:6]  # rough approximation for logging

    raw_matches = store.query(query, top_k=top_k)

    # Format matches for the prompt
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
    result.setdefault("search_terms_used", search_terms_used)
    result.setdefault("has_enough_info", False)
    result.setdefault("suggested_search_terms", [])

    # Build stale_ids for drafter convenience
    result["stale_ids"] = [
        m["source_id"] for m in result["matches"] if m.get("stale")
    ]

    return result