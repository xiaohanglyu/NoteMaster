"""
One-time backfill: generate embeddings for all existing entries, concepts, and questions.

Usage:
    python -m scripts.backfill_embeddings          # live run
    python -m scripts.backfill_embeddings --dry-run
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from notemaster.db import Database
from notemaster.embeddings import embed

DRY_RUN = "--dry-run" in sys.argv


def backfill():
    db = Database()
    total = 0

    entries = db.get_entries()
    print(f"Entries: {len(entries)}")
    for e in entries:
        text = e.text
        if e.data.context_note:
            text += " " + e.data.context_note
        if not DRY_RUN:
            db.save_embedding("entry", e.id, embed(text))
        total += 1

    concepts = db.get_concepts()
    print(f"Concepts: {len(concepts)}")
    for c in concepts:
        text = c.title + ". " + c.summary
        if not DRY_RUN:
            db.save_embedding("concept", c.id, embed(text))
        total += 1

    questions = db.get_questions()
    print(f"Questions: {len(questions)}")
    for q in questions:
        text = q.question
        if q.answer:
            text += " " + q.answer
        if not DRY_RUN:
            db.save_embedding("question", q.id, embed(text))
        total += 1

    label = "Would embed" if DRY_RUN else "Embedded"
    print(f"\n{label} {total} notes.")


if __name__ == "__main__":
    backfill()
