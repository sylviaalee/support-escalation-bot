"""
pipeline/orchestrator.py
Wires triage → research → drafter into a single pipeline call.

Handles:
- Spam short-circuit after triage
- Research retry loop (up to MAX_RETRIES) when has_enough_info=False
"""

from __future__ import annotations
import sys
from pathlib import Path

import anthropic
from openai import OpenAI

sys.path.insert(0, str(Path(__file__).parent.parent / "kb"))
from build_kb import VectorStore  # noqa: E402

from triage import triage
from research import research
from drafter import drafter

MAX_RETRIES = 2  # max research retries before drafting anyway


def run_pipeline(
    ticket: dict,
    store: VectorStore,
    claude_client: anthropic.Anthropic,
    oai_client: OpenAI,
    verbose: bool = True,
) -> dict:
    """
    Process one ticket through the full pipeline.

    Returns:
        {
            "ticket":   dict,
            "triage":   dict,   # {category, priority, reasoning}
            "research": dict,   # {matches, search_terms_used, ...}
            "draft":    dict | None,  # {response_text, sources_used}
            "skipped":  bool,
            "retries":  int,
        }
    """
    def log(msg: str) -> None:
        if verbose:
            print(msg)

    result: dict = {
        "ticket": ticket,
        "triage": None,
        "research": None,
        "draft": None,
        "skipped": False,
        "retries": 0,
    }

    # ── Step 1: Triage ────────────────────────────────────────────────────
    log(f"\n{'─'*55}")
    log(f"  Ticket {ticket.get('id', '?')} | {ticket.get('subject', '')[:50]}")
    log(f"{'─'*55}")
    log("  [1/3] Triage...")

    triage_result = triage(ticket, claude_client)
    result["triage"] = triage_result

    log(f"       category={triage_result['category']} | "
        f"priority={triage_result['priority']} | "
        f"spam={triage_result['is_spam']}")
    log(f"       reasoning: {triage_result['reasoning']}")

    if triage_result["is_spam"]:
        log("  ⛔  Spam detected — skipping research and drafting.\n")
        result["skipped"] = True
        return result

    # ── Step 2: Research (with retry) ────────────────────────────────────
    log("  [2/3] Research...")

    search_query: str | None = None
    research_result: dict = {}

    for attempt in range(MAX_RETRIES + 1):
        if attempt > 0:
            terms = research_result.get("suggested_search_terms", [])
            search_query = " ".join(terms) if terms else None
            log(f'       ↺ Retry {attempt}/{MAX_RETRIES} | query: "{search_query}"')

        research_result = research(
            ticket=ticket,
            store=store,
            client=oai_client,
            search_query=search_query,
        )

        n = len(research_result.get("matches", []))
        enough = research_result.get("has_enough_info", False)
        stale_ids = research_result.get("stale_ids", [])
        log(f"       attempt {attempt + 1}: {n} match(es) | enough={enough}"
            + (f" | ⚠ stale: {stale_ids}" if stale_ids else ""))

        if enough:
            break
        if attempt == MAX_RETRIES:
            log("       Max retries reached — drafting with available context.")

    result["research"] = research_result
    result["retries"] = attempt

    # ── Step 3: Drafter ──────────────────────────────────────────────────
    log("  [3/3] Drafting reply...")

    draft_result = drafter(
        ticket=ticket,
        triage_result=triage_result,
        research_result=research_result,
        client=oai_client,
    )
    result["draft"] = draft_result

    log("       sources_used=" + str(draft_result.get("sources_used", []))
        + (" | ⚠ stale sources used" if draft_result.get("stale_warning") else ""))

    return result