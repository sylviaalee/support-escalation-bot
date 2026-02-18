"""
pipeline/triage.py
Step 1 — Classify the ticket using Claude (Anthropic Messages API).

Returns a dict matching the spec:
{
    "category":  str,   # billing | technical | account | feature_request | spam | general
    "priority":  str,   # low | medium | high | urgent
    "reasoning": str    # one-sentence explanation
}

is_spam is derived from category == "spam".
"""

from __future__ import annotations
import json
import re
import anthropic


SYSTEM_PROMPT = """You are a customer-support triage agent for a SaaS platform.

Classify the incoming support ticket and set a priority level.

Priority rules:
- urgent: production down, data loss, locked out with imminent deadline
- high:   major feature broken, billing error > $500, significant user impact
- medium: feature degraded but workaround exists, billing questions, general account issues
- low:    how-to questions, feature requests, minor cosmetic issues, vague or unclear requests

Category options: billing, technical, account, feature_request, spam, general

Use category=spam for: advertisements, phishing attempts, job offers, gibberish,
executable attachments, or anything not a real support request.

Use priority=low when the ticket is vague, asks a question only tangentially related to
the product, or has no immediate impact on the customer's ability to use the product.

Reply with ONLY a JSON object — no prose, no markdown fences:
{
  "category": "<category>",
  "priority": "<low|medium|high|urgent>",
  "reasoning": "<one sentence explaining the classification>"
}"""


def _extract_json(text: str) -> dict:
    text = re.sub(r"```(?:json)?", "", text).strip().rstrip("```").strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON found in triage response:\n{text}")
    return json.loads(match.group())


def triage(ticket: dict, client: anthropic.Anthropic) -> dict:
    """
    Classify a ticket dict (must have 'subject' and 'body' keys).
    Returns triage result dict with keys: category, priority, reasoning, is_spam.
    """
    user_message = f"Subject: {ticket.get('subject', '')}\n\n{ticket.get('body', '')}"

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=256,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    result = _extract_json(response.content[0].text)
    result.setdefault("category", "general")
    result.setdefault("priority", "medium")
    result.setdefault("reasoning", "")
    # Derive is_spam from category for internal orchestrator use
    result["is_spam"] = result["category"] == "spam"
    return result