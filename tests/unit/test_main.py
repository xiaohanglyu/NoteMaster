import json
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from notemaster.models import (
    Highlight, HighlightColor, EvaluationResult, StudySession
)
from datetime import date


# --- Helpers ---

def make_highlight(id="uuid-1"):
    return Highlight(
        id=id,
        text="A fault is one component deviating from its spec",
        color=HighlightColor.GREEN,
        book_title="DDIA",
    )


def make_eval_result():
    return EvaluationResult(
        concept_feedback="Good.",
        english_feedback="Clear.",
        concept_score=4,
        english_score=3,
        concept_suggestions=[],
        english_suggestions=[],
    )


def make_db(highlights=None, streak=3, heatmap=None):
    db = MagicMock()
    db.get_highlights.return_value = highlights or [make_highlight()]
    db.get_due_highlights.return_value = highlights or [make_highlight()]
    db.get_streak.return_value = streak
    db.get_heatmap.return_value = heatmap or {"2026-04-22": 1}
    db.get_study_sessions.return_value = []
    db.get_review_record.return_value = None
    return db


@pytest.fixture
def client():
    from notemaster.main import app, get_db
    mock_db = make_db()
    app.dependency_overrides[get_db] = lambda: mock_db
    yield TestClient(app), mock_db
    app.dependency_overrides.clear()


# --- POST /sync ---

class TestSync:
    def test_returns_synced_count(self, client):
        tc, mock_db = client
        with patch("notemaster.main.books.get_highlights", return_value=[make_highlight(), make_highlight()]):
            resp = tc.post("/sync", json={"asset_id": "asset-ddia", "book_title": "DDIA"})
        assert resp.status_code == 200
        assert resp.json()["synced"] == 2

    def test_saves_each_highlight(self, client):
        tc, mock_db = client
        highlights = [make_highlight("a"), make_highlight("b")]
        with patch("notemaster.main.books.get_highlights", return_value=highlights):
            tc.post("/sync", json={"asset_id": "asset-ddia", "book_title": "DDIA"})
        assert mock_db.save_highlight.call_count == 2

    def test_missing_asset_id_returns_422(self, client):
        tc, _ = client
        resp = tc.post("/sync", json={"book_title": "DDIA"})
        assert resp.status_code == 422


# --- GET /session/next ---

class TestSessionNext:
    def test_returns_highlight(self, client):
        tc, _ = client
        resp = tc.get("/session/next")
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert "text" in data

    def test_returns_404_when_nothing_due(self, client):
        tc, mock_db = client
        mock_db.get_due_highlights.return_value = []
        mock_db.get_highlights.return_value = []
        resp = tc.get("/session/next")
        assert resp.status_code == 404

    def test_focus_area_query_param(self, client):
        tc, _ = client
        resp = tc.get("/session/next?focus_area=concept")
        assert resp.status_code == 200


# --- POST /answer/text ---

class TestAnswerText:
    def test_returns_evaluation_result(self, client):
        tc, mock_db = client
        with patch("notemaster.main.ai.evaluate", return_value=make_eval_result()):
            resp = tc.post("/answer/text", json={
                "highlight_id": "uuid-1",
                "answer": "A fault is when one part breaks its contract",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert "concept_score" in data
        assert "english_score" in data

    def test_saves_review_record(self, client):
        tc, mock_db = client
        with patch("notemaster.main.ai.evaluate", return_value=make_eval_result()):
            tc.post("/answer/text", json={
                "highlight_id": "uuid-1",
                "answer": "some answer",
            })
        mock_db.save_review_record.assert_called_once()

    def test_missing_answer_returns_422(self, client):
        tc, _ = client
        resp = tc.post("/answer/text", json={"highlight_id": "uuid-1"})
        assert resp.status_code == 422


# --- POST /answer/voice ---

class TestAnswerVoice:
    def test_transcribes_and_evaluates(self, client):
        tc, mock_db = client
        with patch("notemaster.main.stt.transcribe", return_value="transcribed answer"), \
             patch("notemaster.main.ai.evaluate", return_value=make_eval_result()):
            resp = tc.post("/answer/voice", data={"highlight_id": "uuid-1"},
                           files={"audio": ("test.webm", b"\x00\x01\x02", "audio/webm")})
        assert resp.status_code == 200
        assert "concept_score" in resp.json()


# --- GET /stats ---

class TestStats:
    def test_returns_streak_and_heatmap(self, client):
        tc, _ = client
        resp = tc.get("/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["streak"] == 3
        assert "heatmap" in data
        assert "sessions" in data
