import json
import sqlite3
import pytest
from pathlib import Path


def _make_old_db(tmp_path: Path) -> Path:
    """Create a DB with the old flat-column schema for testing migration."""
    db_path = tmp_path / "old.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE entries (
            id           TEXT PRIMARY KEY,
            text         TEXT NOT NULL,
            source_type  TEXT NOT NULL DEFAULT 'manual',
            source_ref   TEXT,
            phonetics    TEXT,
            translation  TEXT,
            examples     TEXT NOT NULL DEFAULT '[]',
            context_note TEXT,
            weight       REAL NOT NULL DEFAULT 1.0,
            created_at   TEXT NOT NULL,
            updated_at   TEXT NOT NULL
        );
        INSERT INTO entries VALUES (
            'e-1', 'hit the ground running', 'manual', NULL,
            '/hɪt/', '迅速投入', '["She hit the ground running."]',
            'idiom', 1.0, '2026-04-01T10:00:00', '2026-04-01T10:00:00'
        );
        INSERT INTO entries VALUES (
            'e-2', 'bootstrap', 'highlight', 'DDIA',
            NULL, NULL, '[]',
            NULL, 1.0, '2026-04-02T10:00:00', '2026-04-02T10:00:00'
        );
    """)
    conn.commit()
    conn.close()
    return db_path


class TestMigrateEntriesData:
    def test_migrates_flat_columns_to_data_json(self, tmp_path):
        from scripts.migrate_entries_data import run
        db_path = _make_old_db(tmp_path)
        run(db_path, dry_run=False)

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT data FROM entries WHERE id = 'e-1'").fetchone()
        d = json.loads(row["data"])
        assert d["phonetics"] == "/hɪt/"
        assert d["translation"] == "迅速投入"
        assert d["context_note"] == "idiom"
        assert d["examples"] == ["She hit the ground running."]
        conn.close()

    def test_null_fields_become_none_in_data(self, tmp_path):
        from scripts.migrate_entries_data import run
        db_path = _make_old_db(tmp_path)
        run(db_path, dry_run=False)

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT data FROM entries WHERE id = 'e-2'").fetchone()
        d = json.loads(row["data"])
        assert d["phonetics"] is None
        assert d["translation"] is None
        assert d["examples"] == []
        conn.close()

    def test_old_columns_removed_after_migration(self, tmp_path):
        from scripts.migrate_entries_data import run
        db_path = _make_old_db(tmp_path)
        run(db_path, dry_run=False)

        conn = sqlite3.connect(str(db_path))
        cols = {row[1] for row in conn.execute("PRAGMA table_info(entries)")}
        conn.close()
        for old_col in ("phonetics", "translation", "examples", "context_note"):
            assert old_col not in cols

    def test_data_column_present_after_migration(self, tmp_path):
        from scripts.migrate_entries_data import run
        db_path = _make_old_db(tmp_path)
        run(db_path, dry_run=False)

        conn = sqlite3.connect(str(db_path))
        cols = {row[1] for row in conn.execute("PRAGMA table_info(entries)")}
        conn.close()
        assert "data" in cols

    def test_idempotent(self, tmp_path):
        from scripts.migrate_entries_data import run
        db_path = _make_old_db(tmp_path)
        run(db_path, dry_run=False)
        run(db_path, dry_run=False)  # second run is a no-op

        conn = sqlite3.connect(str(db_path))
        count = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
        conn.close()
        assert count == 2

    def test_dry_run_does_not_modify(self, tmp_path):
        from scripts.migrate_entries_data import run
        db_path = _make_old_db(tmp_path)
        run(db_path, dry_run=True)

        conn = sqlite3.connect(str(db_path))
        cols = {row[1] for row in conn.execute("PRAGMA table_info(entries)")}
        conn.close()
        assert "phonetics" in cols  # old schema still present
