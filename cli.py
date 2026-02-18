"""
cli.py
Entry point. Loads the KB, reads data/test_tickets.json, and runs each
ticket through the pipeline. Prints a formatted summary to stdout.

Usage:
    python3 cli.py                    # run all test tickets
    python3 cli.py --id TEST007       # run a single ticket by ID
    python3 cli.py --limit 3          # run first N tickets
    python3 cli.py --build            # force-rebuild the KB cache first
"""

from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
import anthropic
from openai import OpenAI

# ── Path setup ───────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "kb"))
sys.path.insert(0, str(ROOT))

from build_kb import VectorStore, build          # noqa: E402
from orchestrator import run_pipeline      # noqa: E402

load_dotenv()

DATA_DIR = ROOT / "data"
TEST_TICKETS_FILE = DATA_DIR / "test_tickets.json"


# ── Formatting helpers ───────────────────────────────────────────────────────

PRIORITY_BADGE = {
    "urgent": "🔴 URGENT",
    "high":   "🟠 HIGH",
    "medium": "🟡 MEDIUM",
    "low":    "🟢 LOW",
}


def print_result(result: dict) -> None:
    ticket = result["ticket"]
    triage = result["triage"]
    draft = result.get("draft")

    print(f"\n{'═'*60}")
    print(f"  {ticket['id']} | {ticket.get('subject', '')}")
    print(f"{'═'*60}")

    # Triage summary
    badge = PRIORITY_BADGE.get(triage.get("priority", "medium"), "⚪")
    print(f"  TRIAGE   {badge} | {triage.get('category','?')} | {triage.get('reasoning','')}")

    if result["skipped"]:
        print("  RESULT   ⛔ Spam — no reply drafted.\n")
        return

    # Research summary
    matches = result.get("research", {}).get("matches", [])
    stale_ids = result.get("research", {}).get("stale_ids", [])
    search_terms = result.get("research", {}).get("search_terms_used", [])
    print(f"  RESEARCH {len(matches)} match(es) | terms: {search_terms}"
          + (f" | ⚠  stale: {stale_ids}" if stale_ids else "")
          + (f" | {result['retries']} retry(s)" if result["retries"] else ""))

    # Draft
    if draft:
        stale_warn = " | ⚠  STALE SOURCES — review before sending" if draft.get("stale_warning") else ""
        sources = draft.get("sources_used", [])
        print(f"  DRAFT    sources={sources}{stale_warn}")
        print()
        for line in draft.get("response_text", "").split("\n"):
            print(f"  {line}")
    print()


def print_summary(results: list[dict]) -> None:
    total = len(results)
    spam = sum(1 for r in results if r["skipped"])
    retried = sum(1 for r in results if r.get("retries", 0) > 0)
    stale_warnings = sum(
        1 for r in results
        if r.get("draft") and r["draft"].get("stale_warning")
    )

    print(f"\n{'═'*60}")
    print(f"  SUMMARY: {total} tickets processed")
    print(f"{'═'*60}")
    print(f"  ⛔ Spam / skipped        : {spam}")
    print(f"  ↺  Research retries used : {retried}")
    print(f"  ⚠  Stale source warnings : {stale_warnings}")
    print()


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Run the support ticket pipeline.")
    parser.add_argument("--id",    help="Run a single ticket by ID (e.g. TEST007)")
    parser.add_argument("--limit", type=int, help="Only process first N tickets")
    parser.add_argument("--build", action="store_true", help="Force-rebuild KB cache")
    args = parser.parse_args()

    # ── Clients ──────────────────────────────────────────────────────────
    claude_client = anthropic.Anthropic(api_key=os.getenv("CLAUDE_API_KEY"))
    oai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    # ── Knowledge base ───────────────────────────────────────────────────
    print("Loading knowledge base...")
    store: VectorStore = build(force=args.build)

    # ── Load test tickets ─────────────────────────────────────────────────
    with open(TEST_TICKETS_FILE, encoding="utf-8") as f:
        all_tickets: list[dict] = json.load(f)

    if args.id:
        tickets = [t for t in all_tickets if t["id"] == args.id]
        if not tickets:
            print(f"No ticket found with id={args.id}")
            sys.exit(1)
    elif args.limit:
        tickets = all_tickets[: args.limit]
    else:
        tickets = all_tickets

    print(f"Running {len(tickets)} ticket(s) through the pipeline...\n")

    # ── Run pipeline ──────────────────────────────────────────────────────
    results = []
    for ticket in tickets:
        result = run_pipeline(
            ticket=ticket,
            store=store,
            claude_client=claude_client,
            oai_client=oai_client,
            verbose=True,
        )
        print_result(result)
        results.append(result)

    if len(results) > 1:
        print_summary(results)


if __name__ == "__main__":
    main()