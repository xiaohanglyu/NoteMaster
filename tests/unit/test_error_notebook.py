"""Tests for Error Notebook — pronunciation + expression mistakes → Entry (#54)."""
import pytest
from datetime import datetime
from unittest.mock import MagicMock

from notemaster.models import Entry, EntryData, EntryType


def make_entry(**kwargs):
    defaults = dict(
        id="e-1", text="granularity",
        created_at=datetime(2026, 4, 30),
        updated_at=datetime(2026, 4, 30),
    )
    return Entry(**{**defaults, **kwargs})


# ---------------------------------------------------------------------------
# DB: get_entries tag filter
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    from notemaster.db import Database
    return Database(tmp_path / "test.db")


class TestEntryTagFilter:
    def test_filter_by_single_tag(self, db):
        e1 = make_entry(id="e-1", text="granularity", data=EntryData(), source_type=EntryType.MANUAL)
        e2 = make_entry(id="e-2", text="albeit", data=EntryData(), source_type=EntryType.MANUAL)
        # manually set tags via create then update
        db.create_entry(e1)
        db.create_entry(e2)
        db.update_entry("e-1", tags=["pronunciation"])
        db.update_entry("e-2", tags=["expression"])
        results = db.get_entries(tag="pronunciation")
        assert len(results) == 1
        assert results[0].text == "granularity"

    def test_filter_by_expression_tag(self, db):
        db.create_entry(make_entry(id="e-1", text="w1"))
        db.create_entry(make_entry(id="e-2", text="w2"))
        db.update_entry("e-1", tags=["expression", "interview"])
        db.update_entry("e-2", tags=["pronunciation"])
        results = db.get_entries(tag="expression")
        assert len(results) == 1
        assert results[0].id == "e-1"

    def test_no_tag_returns_all(self, db):
        db.create_entry(make_entry(id="e-1", text="w1"))
        db.create_entry(make_entry(id="e-2", text="w2"))
        db.update_entry("e-1", tags=["pronunciation"])
        assert len(db.get_entries()) == 2

    def test_unknown_tag_returns_empty(self, db):
        db.create_entry(make_entry(id="e-1", text="w1"))
        assert db.get_entries(tag="nonexistent") == []

    def test_source_ref_roundtrips(self, db):
        e = make_entry(source_ref="q-abc-123")
        db.create_entry(e)
        loaded = db.get_entry("e-1")
        assert loaded.source_ref == "q-abc-123"


# ---------------------------------------------------------------------------
# API: GET /entries?tag=pronunciation
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    from notemaster.main import app, get_db
    mock_db = MagicMock()
    mock_db.get_entries.return_value = [
        make_entry(id="e-1", text="granularity", source_type=EntryType.MANUAL,
                   data=EntryData(context_note="Mispronounced")),
    ]
    app.dependency_overrides[get_db] = lambda: mock_db
    from fastapi.testclient import TestClient
    yield TestClient(app), mock_db
    app.dependency_overrides.clear()


class TestEntryTagApi:
    def test_filter_by_tag(self, client):
        tc, mock_db = client
        resp = tc.get("/entries?tag=pronunciation")
        assert resp.status_code == 200
        mock_db.get_entries.assert_called_once_with(source_type=None, tag="pronunciation")

    def test_no_tag_calls_without_tag(self, client):
        tc, mock_db = client
        tc.get("/entries")
        mock_db.get_entries.assert_called_once_with(source_type=None, tag=None)

    def test_create_entry_with_system_tags(self, client):
        tc, mock_db = client
        e = make_entry(source_type=EntryType.MANUAL, data=EntryData())
        mock_db.create_entry.return_value = e
        resp = tc.post("/entries", json={
            "text": "albeit",
            "tags": ["pronunciation", "interview"],
            "source_ref": "q-123",
        })
        assert resp.status_code == 200

    def test_create_entry_with_context_note(self, client):
        tc, mock_db = client
        e = make_entry(source_type=EntryType.MANUAL, data=EntryData())
        mock_db.create_entry.return_value = e
        resp = tc.post("/entries", json={
            "text": "albeit",
            "data": {"context_note": "Mispronounced in shadow reading"},
            "tags": ["pronunciation"],
        })
        assert resp.status_code == 200
