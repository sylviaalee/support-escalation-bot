"""
kb/build_kb.py
Reads data/faqs/*.md and data/past_tickets.json, embeds everything,
and saves to kb/kb_cache.json so the pipeline can load it instantly.

Run once (or whenever your data changes):
    python kb/build_kb.py
"""

from __future__ import annotations
import json
import math
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

EMBED_MODEL = "text-embedding-3-small"
DATA_DIR = Path(__file__).parent / "data"
FAQS_DIR = DATA_DIR / "faqs"
TICKETS_FILE = DATA_DIR / "past_tickets.json"
CACHE_FILE = Path(__file__).parent / "kb_cache.json"


# ---------------------------------------------------------------------------
# Cosine similarity + VectorStore (self-contained so pipeline can import it)
# ---------------------------------------------------------------------------

def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class VectorStore:
    def __init__(self, client: OpenAI):
        self._client = client
        self._records: list[dict] = []

    def add_batch(self, items: list[tuple[str, dict]]) -> None:
        """Embed and store a list of (text, metadata) pairs in one API call."""
        texts = [t for t, _ in items]
        resp = self._client.embeddings.create(input=texts, model=EMBED_MODEL)
        for (text, metadata), data in zip(items, resp.data):
            self._records.append({
                "text": text,
                "embedding": data.embedding,
                "metadata": metadata,
            })

    def query(self, query_text: str, top_k: int = 3) -> list[dict]:
        """Return top_k most similar records by cosine similarity."""
        if not self._records:
            return []
        q_emb = self._client.embeddings.create(
            input=query_text, model=EMBED_MODEL
        ).data[0].embedding
        scored = [
            {
                "text": r["text"],
                "metadata": r["metadata"],
                "score": cosine_similarity(q_emb, r["embedding"]),
            }
            for r in self._records
        ]
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    def save(self, path: Path) -> None:
        with open(path, "w") as f:
            json.dump(self._records, f)
        print(f"  Saved {len(self._records)} records → {path}")

    def load(self, path: Path) -> None:
        with open(path) as f:
            self._records = json.load(f)

    def __len__(self) -> int:
        return len(self._records)


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_faqs() -> list[tuple[str, dict]]:
    """Read every .md file in data/faqs/ and return (text, metadata) pairs."""
    items = []
    md_files = sorted(FAQS_DIR.glob("*.md"))
    if not md_files:
        print(f"  WARNING: No .md files found in {FAQS_DIR}")
        return items
    for path in md_files:
        text = path.read_text(encoding="utf-8").strip()
        items.append((
            text,
            {
                "source_id": f"faq-{path.stem}",
                "type": "faq",
                "source": path.name,
                # Derive a readable title from the filename
                "title": path.stem.replace("_", " ").title(),
            },
        ))
    return items


def load_past_tickets() -> list[tuple[str, dict]]:
    """
    Read data/past_tickets.json.
    Each ticket has: id, question, resolution, category
    We embed question + resolution together so retrieval matches on both.
    """
    with open(TICKETS_FILE, encoding="utf-8") as f:
        tickets = json.load(f)

    items = []
    for t in tickets:
        # Skip stale/outdated resolutions — flag them in metadata but still embed
        # so the pipeline knows they exist (the research step will see the text)
        text = (
            f"Customer question: {t['question']}\n"
            f"Resolution: {t['resolution']}"
        )
        items.append((
            text,
            {
                "source_id": f"ticket-{t['id']}",
                "type": "past_ticket",
                "id": t["id"],
                "category": t["category"],
                "status": "resolved",
                # Flag tickets that explicitly say they're stale
                "stale": "STALE" in t.get("resolution", "").upper()
                         or "NO LONGER VALID" in t.get("resolution", "").upper(),
            },
        ))
    return items


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def build(force: bool = False) -> VectorStore:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    store = VectorStore(client)

    if CACHE_FILE.exists() and not force:
        print(f"Cache found at {CACHE_FILE} — loading (pass --force to rebuild).")
        store.load(CACHE_FILE)
        print(f"Loaded {len(store)} records.\n")
        return store

    print("Building knowledge base from scratch...\n")

    faq_items = load_faqs()
    print(f"  Found {len(faq_items)} FAQ files in {FAQS_DIR}")
    if faq_items:
        store.add_batch(faq_items)

    ticket_items = load_past_tickets()
    print(f"  Found {len(ticket_items)} past tickets in {TICKETS_FILE}")
    stale = sum(1 for _, m in ticket_items if m.get("stale"))
    if stale:
        print(f"  ⚠  {stale} ticket(s) flagged as stale — still indexed but marked in metadata")
    if ticket_items:
        store.add_batch(ticket_items)

    print(f"\nTotal records embedded: {len(store)}")
    store.save(CACHE_FILE)
    return store


if __name__ == "__main__":
    force = "--force" in sys.argv
    build(force=force)
    print("\nDone. Run 'python cli.py' to process tickets.")