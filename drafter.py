"""
pipeline/drafter.py
Step 3 — Write the support reply using GPT, based on research context.

Returns a dict matching the spec:
{
    "response_text": str,        # full reply body
    "sources_used":  list[str]   # source_ids referenced (e.g. ["faq-12", "ticket-287"])
}

Internal fields also returned for orchestrator/display:
    "stale_warning": bool   # True if any stale source was in context
"""

from __future__ import annotations
import json
import re
from openai import OpenAI


SYSTEM_PROMPT = """You are a friendly, professional customer-support agent for a SaaS platform.

Write a helpful reply to the support ticket using ONLY the provided knowledge-base context.
Do not invent facts not present in the context.

STALE CONTEXT WARNING: If any context item is marked stale=true, do NOT use it to answer the
ticket. Stale resolutions describe old processes that no longer exist. Instead, acknowledge you
need to look into it and ask the customer to confirm details, or escalate.

Tone guidelines:
- Empathetic and concise
- Step-by-step instructions where applicable
- For high/urgent priority tickets: acknowledge urgency in the opening line
- If context is insufficient: say so honestly and offer next steps (escalate, ask clarifying Q)

Reply with ONLY a JSON object — no prose, no markdown fences:
{
  "response_text": "<full reply — use \\n for line breaks>",
  "sources_used": ["<source_id of each KB item that informed the reply>"],
  "stale_warning": <true|false>
}"""


def _extract_json(text: str) -> dict:
    text = re.sub(r"```(?:json)?", "", text).strip().rstrip("```").strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON found in drafter response:\n{text}")
    return json.loads(match.group())


def drafter(
    ticket: dict,
    triage_result: dict,
    research_result: dict,
    client: OpenAI,
) -> dict:
    """
    Draft a reply given the ticket, triage classification, and research matches.
    ticket must have 'subject' and 'body' keys.
    """
    matches = research_result.get("matches", [])

    if matches:
        context_text = "\n\n".join(
            f"[{m.get('source_type', 'source').upper()} | "
            f"source_id={m.get('source_id', '?')} | "
            f"relevance_score={m.get('similarity_score', '?')} | "
            f"stale={m.get('stale', False)}]\n{m['content_snippet']}"
            for m in matches
        )
    else:
        context_text = "No relevant context found in the knowledge base."

    user_message = (
        f"TICKET METADATA\n"
        f"Category: {triage_result.get('category', 'general')}\n"
        f"Priority: {triage_result.get('priority', 'medium')}\n\n"
        f"TICKET\n"
        f"Subject: {ticket.get('subject', '')}\n"
        f"Body: {ticket.get('body', '')}\n\n"
        f"KNOWLEDGE BASE CONTEXT\n{context_text}"
    )

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.3,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
    )

    result = _extract_json(response.choices[0].message.content)
    result.setdefault("response_text", "")
    result.setdefault("sources_used", [])
    result.setdefault("stale_warning", False)
    return result