import pytest
from datetime import datetime
from notemaster.db import Database
from notemaster.models import Entry, EntryData, Concept


@pytest.fixture
def db():
    return Database(":memory:")


def make_entry(id="e-1", text="granularity"):
    return Entry(id=id, text=text, data=EntryData(),
                 created_at=datetime(2026, 4, 24), updated_at=datetime(2026, 4, 24))


def make_concept(id="c-1", title="Data Sharding"):
    return Concept(id=id, title=title, summary="Splitting data across nodes",
                   book_id="b-1", highlight_ids=[], weight=1.0,
                   created_at=datetime(2026, 4, 24), updated_at=datetime(2026, 4, 24))


class TestEmbeddingsSchema:
    def test_table_exists(self, db):
        tables = {r[0] for r in db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "embeddings" in tables

    def test_columns(self, db):
        cols = {r[1] for r in db.conn.execute("PRAGMA table_info(embeddings)")}
        for col in ("note_type", "note_id", "vector", "updated_at"):
            assert col in cols


class TestSaveEmbedding:
    def test_save_and_retrieve(self, db):
        db.save_embedding("entry", "e-1", [0.1, 0.2, 0.3])
        row = db.conn.execute(
            "SELECT vector FROM embeddings WHERE note_type='entry' AND note_id='e-1'"
        ).fetchone()
        assert row is not None

    def test_upsert_overwrites(self, db):
        db.save_embedding("entry", "e-1", [0.1, 0.2])
        db.save_embedding("entry", "e-1", [0.9, 0.8])
        rows = db.conn.execute("SELECT COUNT(*) FROM embeddings WHERE note_id='e-1'").fetchone()
        assert rows[0] == 1

    def test_different_types_same_id(self, db):
        db.save_embedding("entry", "x-1", [0.1, 0.2])
        db.save_embedding("concept", "x-1", [0.3, 0.4])
        rows = db.conn.execute("SELECT COUNT(*) FROM embeddings WHERE note_id='x-1'").fetchone()
        assert rows[0] == 2


class TestGetRelated:
    def test_returns_similar_notes(self, db):
        db.save_embedding("entry", "e-1", [1.0, 0.0])
        db.save_embedding("entry", "e-2", [0.9, 0.1])   # similar
        db.save_embedding("concept", "c-1", [-1.0, 0.0]) # dissimilar
        results = db.get_related("entry", "e-1", limit=5)
        ids = [r["note_id"] for r in results]
        assert "e-1" not in ids  # excludes self
        assert ids[0] == "e-2"   # most similar first

    def test_excludes_self(self, db):
        db.save_embedding("entry", "e-1", [1.0, 0.0])
        db.save_embedding("entry", "e-2", [0.8, 0.2])
        results = db.get_related("entry", "e-1")
        assert all(r["note_id"] != "e-1" for r in results)

    def test_respects_limit(self, db):
        for i in range(10):
            db.save_embedding("entry", f"e-{i}", [float(i), 0.0])
        results = db.get_related("entry", "e-0", limit=3)
        assert len(results) <= 3

    def test_returns_empty_when_no_others(self, db):
        db.save_embedding("entry", "e-1", [1.0, 0.0])
        assert db.get_related("entry", "e-1") == []

    def test_result_has_expected_keys(self, db):
        db.save_embedding("entry", "e-1", [1.0, 0.0])
        db.save_embedding("concept", "c-1", [0.9, 0.1])
        results = db.get_related("entry", "e-1")
        assert len(results) == 1
        r = results[0]
        assert "note_type" in r
        assert "note_id" in r
        assert "score" in r

    def test_cross_type_results(self, db):
        db.save_embedding("entry", "e-1", [1.0, 0.0])
        db.save_embedding("concept", "c-1", [0.95, 0.05])
        db.save_embedding("question", "q-1", [0.85, 0.15])
        results = db.get_related("entry", "e-1")
        types = {r["note_type"] for r in results}
        assert "concept" in types
        assert "question" in types
