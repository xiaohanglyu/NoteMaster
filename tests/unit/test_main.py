import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from notemaster.models import (
    Book, Concept, ConceptWithPriority, EvaluationResult, StudySession,
)
from datetime import date


# --- Helpers ---

def make_concept(id="concept-1"):
    now = datetime(2026, 4, 22)
    return Concept(
        id=id,
        title="Fault vs Failure",
        summary="A fault is a component deviation; a failure is service unavailability.",
        book_id="book-1",
        highlight_ids=["h-1"],
        weight=1.5,
        created_at=now,
        updated_at=now,
    )


def make_concept_with_priority(id="concept-1"):
    return ConceptWithPriority(
        concept=make_concept(id),
        priority=1.5,
        days_overdue=0.0,
        last_mastery=None,
    )


def make_book():
    return Book(
        id="book-1",
        title="DDIA",
        asset_id="asset-ddia",
        synced_at=datetime(2026, 4, 22),
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


def make_db():
    db = MagicMock()
    db.get_book_by_asset_id.return_value = make_book()
    db.get_books.return_value = [make_book()]
    db.get_due_concepts.return_value = [make_concept_with_priority()]
    db.get_concept.return_value = make_concept()
    db.get_streak.return_value = 3
    db.get_heatmap.return_value = {"2026-04-22": 1}
    db.get_study_sessions.return_value = []
    return db


@pytest.fixture
def client():
    from notemaster.main import app, get_db
    mock_db = make_db()
    app.dependency_overrides[get_db] = lambda: mock_db
    yield TestClient(app), mock_db
    app.dependency_overrides.clear()


# --- GET /books ---

class TestGetBooks:
    def test_returns_list(self, client):
        tc, _ = client
        resp = tc.get("/books")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_book_has_expected_fields(self, client):
        tc, _ = client
        data = tc.get("/books").json()
        assert "id" in data[0]
        assert "title" in data[0]


# --- POST /sync ---

class TestSync:
    def test_returns_synced_count_and_book_id(self, client):
        tc, mock_db = client
        with patch("notemaster.main.books.get_highlights", return_value=[]):
            resp = tc.post("/sync", json={"asset_id": "asset-ddia", "book_title": "DDIA"})
        assert resp.status_code == 200
        assert "synced" in resp.json()
        assert "book_id" in resp.json()

    def test_saves_each_highlight(self, client):
        tc, mock_db = client
        from notemaster.models import Highlight, HighlightColor
        hl = Highlight(id="h-1", text="text", color=HighlightColor.GREEN,
                       book_id="book-1", book_title="DDIA")
        with patch("notemaster.main.books.get_highlights", return_value=[hl, hl]):
            tc.post("/sync", json={"asset_id": "asset-ddia", "book_title": "DDIA"})
        assert mock_db.save_highlight.call_count == 2

    def test_missing_asset_id_returns_422(self, client):
        tc, _ = client
        resp = tc.post("/sync", json={"book_title": "DDIA"})
        assert resp.status_code == 422


class TestSyncColorRouting:
    """Yellow highlights → entries only (not knowledge graph). Green/Blue → highlights table."""

    def _make_highlight(self, color, id="h-1"):
        from notemaster.models import Highlight, HighlightColor
        return Highlight(id=id, text="some text", color=color,
                         book_id="book-1", book_title="DDIA")

    def test_yellow_not_saved_to_highlights_table(self, client):
        tc, mock_db = client
        from notemaster.models import HighlightColor
        yellow = self._make_highlight(HighlightColor.YELLOW)
        with patch("notemaster.main.books.get_highlights", return_value=[yellow]):
            tc.post("/sync", json={"asset_id": "asset-ddia", "book_title": "DDIA"})
        mock_db.save_highlight.assert_not_called()

    def test_yellow_saved_as_entry(self, client):
        tc, mock_db = client
        from notemaster.models import HighlightColor
        yellow = self._make_highlight(HighlightColor.YELLOW)
        with patch("notemaster.main.books.get_highlights", return_value=[yellow]):
            tc.post("/sync", json={"asset_id": "asset-ddia", "book_title": "DDIA"})
        mock_db.create_entry.assert_called_once()
        entry_arg = mock_db.create_entry.call_args[0][0]
        assert entry_arg.text == "some text"

    def test_green_saved_to_highlights_table_not_entry(self, client):
        tc, mock_db = client
        from notemaster.models import HighlightColor
        green = self._make_highlight(HighlightColor.GREEN)
        with patch("notemaster.main.books.get_highlights", return_value=[green]):
            tc.post("/sync", json={"asset_id": "asset-ddia", "book_title": "DDIA"})
        mock_db.save_highlight.assert_called_once()
        mock_db.create_entry.assert_not_called()

    def test_blue_saved_to_highlights_table(self, client):
        tc, mock_db = client
        from notemaster.models import HighlightColor
        blue = self._make_highlight(HighlightColor.BLUE)
        with patch("notemaster.main.books.get_highlights", return_value=[blue]):
            tc.post("/sync", json={"asset_id": "asset-ddia", "book_title": "DDIA"})
        mock_db.save_highlight.assert_called_once()

    def test_entries_synced_count_reflects_yellow_only(self, client):
        tc, mock_db = client
        from notemaster.models import HighlightColor
        highlights = [
            self._make_highlight(HighlightColor.YELLOW, "h-1"),
            self._make_highlight(HighlightColor.GREEN, "h-2"),
            self._make_highlight(HighlightColor.BLUE, "h-3"),
        ]
        with patch("notemaster.main.books.get_highlights", return_value=highlights):
            resp = tc.post("/sync", json={"asset_id": "asset-ddia", "book_title": "DDIA"})
        assert resp.json()["entries_synced"] == 1
        assert mock_db.save_highlight.call_count == 2  # green + blue only


# --- GET /session/next ---

class TestSessionNext:
    def test_returns_concept(self, client):
        tc, _ = client
        resp = tc.get("/session/next")
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert "title" in data
        assert "summary" in data

    def test_returns_404_when_nothing_due(self, client):
        tc, mock_db = client
        mock_db.get_due_concepts.return_value = []
        resp = tc.get("/session/next")
        assert resp.status_code == 404


# --- POST /answer/text ---

class TestAnswerText:
    def test_returns_evaluation_result(self, client):
        tc, _ = client
        with patch("notemaster.main.ai.evaluate", return_value=make_eval_result()):
            resp = tc.post("/answer/text", json={
                "concept_id": "concept-1",
                "answer": "A fault is when one part breaks its contract",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert "concept_score" in data
        assert "english_score" in data

    def test_does_not_auto_record_review(self, client):
        # review is recorded explicitly via POST /concepts/{id}/review (mastery button)
        tc, mock_db = client
        with patch("notemaster.main.ai.evaluate", return_value=make_eval_result()):
            tc.post("/answer/text", json={"concept_id": "concept-1", "answer": "answer"})
        mock_db.record_review.assert_not_called()

    def test_returns_404_for_unknown_concept(self, client):
        tc, mock_db = client
        mock_db.get_concept.return_value = None
        with patch("notemaster.main.ai.evaluate", return_value=make_eval_result()):
            resp = tc.post("/answer/text", json={"concept_id": "bad-id", "answer": "answer"})
        assert resp.status_code == 404

    def test_missing_answer_returns_422(self, client):
        tc, _ = client
        resp = tc.post("/answer/text", json={"concept_id": "concept-1"})
        assert resp.status_code == 422


# --- POST /answer/voice ---

class TestAnswerVoice:
    def test_transcribes_and_evaluates(self, client):
        tc, _ = client
        with patch("notemaster.main.stt.transcribe", return_value="transcribed answer"), \
             patch("notemaster.main.ai.evaluate", return_value=make_eval_result()):
            resp = tc.post(
                "/answer/voice",
                data={"concept_id": "concept-1"},
                files={"audio": ("test.webm", b"\x00\x01\x02", "audio/webm")},
            )
        assert resp.status_code == 200
        assert "concept_score" in resp.json()


# --- GET /graph ---

class TestGraph:
    def test_returns_nodes_and_edges(self, client):
        tc, mock_db = client
        mock_db.get_concepts.return_value = [make_concept()]
        mock_db.get_edges.return_value = []
        resp = tc.get("/graph")
        assert resp.status_code == 200
        data = resp.json()
        assert "nodes" in data
        assert "edges" in data

    def test_node_has_expected_fields(self, client):
        tc, mock_db = client
        mock_db.get_concepts.return_value = [make_concept()]
        mock_db.get_edges.return_value = []
        data = tc.get("/graph").json()
        node = data["nodes"][0]
        assert "id" in node
        assert "title" in node
        assert "weight" in node


# --- GET /stats ---

class TestStats:
    def test_returns_streak_heatmap_sessions(self, client):
        tc, _ = client
        resp = tc.get("/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["streak"] == 3
        assert "heatmap" in data
        assert "sessions" in data
