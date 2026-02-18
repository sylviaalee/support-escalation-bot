"""
kb/build_kb.py
Reads data/faqs/*.md and data/past_tickets.json, embeds everything via
OpenAI, and persists to a ChromaDB collection at kb/chroma/.

Run once (or whenever your data changes):
    python3 kb/build_kb.py
    python3 kb/build_kb.py --force   # wipe and rebuild
"""

from __future__ import annotations
import os
import sys
import json
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
import chromadb
from chromadb.config import Settings

load_dotenv()

EMBED_MODEL  = "text-embedding-3-small"
DATA_DIR     = Path(__file__).parent / "data"
FAQS_DIR     = DATA_DIR / "faqs"
TICKETS_FILE = DATA_DIR / "past_tickets.json"
CHROMA_DIR   = Path(__file__).parent / "chroma"
COLLECTION   = "support_kb"


# ---------------------------------------------------------------------------
# VectorStore — wraps ChromaDB with the same .add_batch() / .query() API
# the rest of the pipeline already expects
# ---------------------------------------------------------------------------

class VectorStore:
    def __init__(self, openai_client: OpenAI):
        self._oai    = openai_client
        self._client = chromadb.PersistentClient(
            path=str(CHROMA_DIR),
            settings=Settings(anonymized_telemetry=False),
        )
        self._col = self._client.get_or_create_collection(
            name=COLLECTION,
            metadata={"hnsw:space": "cosine"},   # cosine distance
        )

    # ── write ────────────────────────────────────────────────────────────

    def add_batch(self, items: list[tuple[str, dict]]) -> None:
        """Embed and upsert a list of (text, metadata) pairs."""
        texts     = [t for t, _ in items]
        metadatas = [m for _, m in items]

        resp = self._oai.embeddings.create(input=texts, model=EMBED_MODEL)
        embeddings = [d.embedding for d in resp.data]

        # Chroma requires string IDs — use source_id from metadata
        ids = [m["source_id"] for m in metadatas]

        # Chroma metadata values must be str / int / float / bool — cast stale
        safe_metas = [
            {k: (str(v) if isinstance(v, bool) else v) for k, v in m.items()}
            for m in metadatas
        ]

        self._col.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=safe_metas,
        )

    def wipe(self) -> None:
        """Delete and recreate the collection."""
        self._client.delete_collection(COLLECTION)
        self._col = self._client.get_or_create_collection(
            name=COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )

    # ── read ─────────────────────────────────────────────────────────────

    def query(self, query_text: str, top_k: int = 3) -> list[dict]:
        """
        Return top_k results as dicts with keys:
            text, metadata, score   (score = 1 - chroma_distance, so higher = better)
        """
        if len(self) == 0:
            return []

        q_emb = self._oai.embeddings.create(
            input=query_text, model=EMBED_MODEL
        ).data[0].embedding

        results = self._col.query(
            query_embeddings=[q_emb],
            n_results=min(top_k, len(self)),
            include=["documents", "metadatas", "distances"],
        )

        out = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            # Chroma cosine distance is 1 - similarity; convert back
            score = 1.0 - dist
            # Re-cast stale back to bool
            meta = {**meta, "stale": meta.get("stale") == "True"}
            out.append({"text": doc, "metadata": meta, "score": score})

        return out

    def __len__(self) -> int:
        return self._col.count()


# ---------------------------------------------------------------------------
# Loaders (unchanged from original)
# ---------------------------------------------------------------------------

def load_faqs() -> list[tuple[str, dict]]:
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
                "type":      "faq",
                "source":    path.name,
                "title":     path.stem.replace("_", " ").title(),
            },
        ))
    return items


def load_past_tickets() -> list[tuple[str, dict]]:
    with open(TICKETS_FILE, encoding="utf-8") as f:
        tickets = json.load(f)

    items = []
    for t in tickets:
        text = (
            f"Customer question: {t['question']}\n"
            f"Resolution: {t['resolution']}"
        )
        is_stale = (
            "STALE" in t.get("resolution", "").upper()
            or "NO LONGER VALID" in t.get("resolution", "").upper()
        )
        items.append((
            text,
            {
                "source_id": f"ticket-{t['id']}",
                "type":      "past_ticket",
                "id":        t["id"],
                "category":  t["category"],
                "status":    "resolved",
                "stale":     is_stale,   # stored as bool, cast to str on upsert
            },
        ))
    return items


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def build(force: bool = False) -> VectorStore:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    store  = VectorStore(client)

    if len(store) > 0 and not force:
        print(f"Chroma collection '{COLLECTION}' already has {len(store)} records.")
        print("Pass --force to wipe and rebuild.\n")
        return store

    if force and len(store) > 0:
        print(f"--force: wiping existing {len(store)} records...")
        store.wipe()

    print("Building knowledge base from scratch...\n")

    faq_items = load_faqs()
    print(f"  Found {len(faq_items)} FAQ files in {FAQS_DIR}")
    if faq_items:
        store.add_batch(faq_items)

    ticket_items = load_past_tickets()
    print(f"  Found {len(ticket_items)} past tickets in {TICKETS_FILE}")
    stale = sum(1 for _, m in ticket_items if m.get("stale"))
    if stale:
        print(f"  ⚠  {stale} ticket(s) flagged as stale — indexed but marked")
    if ticket_items:
        store.add_batch(ticket_items)

    print(f"\nTotal records in Chroma: {len(store)}")
    print(f"Persisted at: {CHROMA_DIR}\n")
    return store


if __name__ == "__main__":
    force = "--force" in sys.argv
    build(force=force)
    print("Done. Run 'python3 cli.py' to process tickets.")