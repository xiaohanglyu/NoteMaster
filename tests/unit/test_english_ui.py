"""
Smoke tests for the English tab UI.
Verifies HTML structure and end-to-end entry flow via TestClient.
"""
import pytest
from pathlib import Path
from fastapi.testclient import TestClient


FRONTEND = Path(__file__).parent.parent.parent / "frontend" / "index.html"


class TestFrontendStructure:
    def test_english_view_exists(self):
        html = FRONTEND.read_text()
        assert 'id="view-english"' in html

    def test_entry_input_exists(self):
        html = FRONTEND.read_text()
        assert 'id="entry-input"' in html

    def test_entry_list_exists(self):
        html = FRONTEND.read_text()
        assert 'id="entry-list"' in html

    def test_tts_speak_function_exists(self):
        html = FRONTEND.read_text()
        assert "speakText" in html

    def test_submit_entry_function_exists(self):
        html = FRONTEND.read_text()
        assert "submitEntry" in html

    def test_english_nav_button_exists(self):
        html = FRONTEND.read_text()
        assert "openEnglish" in html


class TestEnglishEntryFlow:
    """End-to-end: create → list → review via API."""

    @pytest.fixture
    def client(self):
        from notemaster.main import app, get_db
        from notemaster.db import Database
        db = Database(":memory:")
        app.dependency_overrides[get_db] = lambda: db
        yield TestClient(app)
        app.dependency_overrides.clear()

    def test_create_then_list(self, client):
        client.post("/entries", json={"text": "hit the ground running"})
        resp = client.get("/entries")
        assert len(resp.json()) == 1
        assert resp.json()[0]["text"] == "hit the ground running"

    def test_create_then_next(self, client):
        client.post("/entries", json={"text": "at the expense of"})
        resp = client.get("/entries/next")
        assert resp.status_code == 200
        assert resp.json()["text"] == "at the expense of"

    def test_create_then_review_then_not_due(self, client):
        client.post("/entries", json={"text": "call it a day"})
        entry_id = client.get("/entries").json()[0]["id"]
        client.post(f"/entries/{entry_id}/review", json={"mastery_score": 5})
        resp = client.get("/entries/next")
        assert resp.status_code == 404
