import pytest
from unittest.mock import MagicMock, patch


def make_db():
    db = MagicMock()
    db.get_related.return_value = [
        {"note_type": "concept", "note_id": "c-1", "score": 0.95},
        {"note_type": "question", "note_id": "q-1", "score": 0.82},
    ]
    return db


@pytest.fixture
def client():
    from notemaster.main import app, get_db
    mock_db = make_db()
    app.dependency_overrides[get_db] = lambda: mock_db
    from fastapi.testclient import TestClient
    yield TestClient(app), mock_db
    app.dependency_overrides.clear()


class TestRelatedEndpoint:
    def test_returns_list(self, client):
        tc, _ = client
        resp = tc.get("/notes/entry/e-1/related")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_calls_db_with_correct_args(self, client):
        tc, mock_db = client
        tc.get("/notes/entry/e-1/related")
        mock_db.get_related.assert_called_once_with("entry", "e-1", limit=5)

    def test_custom_limit(self, client):
        tc, mock_db = client
        tc.get("/notes/concept/c-1/related?limit=3")
        mock_db.get_related.assert_called_once_with("concept", "c-1", limit=3)

    def test_result_shape(self, client):
        tc, _ = client
        resp = tc.get("/notes/entry/e-1/related")
        item = resp.json()[0]
        assert "note_type" in item
        assert "note_id" in item
        assert "score" in item

    def test_empty_when_no_related(self, client):
        tc, mock_db = client
        mock_db.get_related.return_value = []
        resp = tc.get("/notes/entry/e-1/related")
        assert resp.status_code == 200
        assert resp.json() == []


class TestBgEmbed:
    def test_entry_creation_triggers_embed(self, client):
        tc, mock_db = client
        from datetime import datetime
        from notemaster.models import Entry, EntryData
        mock_db.create_entry.return_value = Entry(
            id="e-new", text="granularity", data=EntryData(),
            created_at=datetime(2026, 4, 24), updated_at=datetime(2026, 4, 24),
        )
        with patch("notemaster.main.embeddings.embed", return_value=[0.1] * 384):
            resp = tc.post("/entries", json={"text": "granularity"})
        assert resp.status_code == 200
