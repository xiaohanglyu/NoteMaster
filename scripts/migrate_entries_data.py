"""
Standalone migration: collapse flat entry columns into a single data JSON column.

The same migration runs automatically on app startup via db._migrate().
Use this script to verify or force-run it independently.

Usage:
    python -m scripts.migrate_entries_data          # run migration
    python -m scripts.migrate_entries_data --dry-run
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

_DEFAULT_DB = Path(__file__).parent.parent / "data" / "notemaster.db"


def _needs_migration(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='entries'"
    ).fetchone()
    return row is not None and "phonetics" in row[0]


def run(db_path: Path, dry_run: bool = False) -> None:
    if not db_path.exists():
        print(f"Database not found: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    if not _needs_migration(conn):
        print("Already migrated — entries table has no flat columns.")
        conn.close()
        return

    rows = conn.execute(
        "SELECT id, phonetics, translation, examples, context_note FROM entries"
    ).fetchall()

    print(f"Migrating {len(rows)} entries{' (dry run)' if dry_run else ''}...")

    if dry_run:
        for r in rows[:5]:
            packed = {
                "phonetics": r["phonetics"],
                "translation": r["translation"],
                "examples": json.loads(r["examples"] or "[]"),
                "context_note": r["context_note"],
            }
            print(f"  [{r['id']}] → {json.dumps(packed, ensure_ascii=False)[:80]}")
        if len(rows) > 5:
            print(f"  ... and {len(rows) - 5} more")
        conn.close()
        return

    # Add data column
    conn.execute("ALTER TABLE entries ADD COLUMN data TEXT NOT NULL DEFAULT '{}'")

    # Pack flat columns into data JSON
    for r in rows:
        packed = json.dumps({
            "phonetics": r["phonetics"],
            "translation": r["translation"],
            "examples": json.loads(r["examples"] or "[]"),
            "context_note": r["context_note"],
        })
        conn.execute("UPDATE entries SET data = ? WHERE id = ?", (packed, r["id"]))

    # Rebuild table without old columns
    conn.executescript("""
        CREATE TABLE entries_new (
            id          TEXT PRIMARY KEY,
            text        TEXT NOT NULL,
            source_type TEXT NOT NULL DEFAULT 'manual',
            source_ref  TEXT,
            data        TEXT NOT NULL DEFAULT '{}',
            weight      REAL NOT NULL DEFAULT 1.0,
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        );
        INSERT INTO entries_new
            SELECT id, text, source_type, source_ref, data, weight, created_at, updated_at
            FROM entries;
        DROP TABLE entries;
        ALTER TABLE entries_new RENAME TO entries;
    """)
    conn.commit()
    conn.close()
    print(f"Done. Migrated {len(rows)} entries.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate entry flat columns to data JSON")
    parser.add_argument("--db", type=Path, default=_DEFAULT_DB)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(args.db, dry_run=args.dry_run)
