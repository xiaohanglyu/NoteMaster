import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from notemaster.models import (
    Concept, ConceptWithPriority,
    Entry, EntryType, EntryWithPriority,
    InterviewQuestion, QuestionType, QuestionSource,
)


def make_concept(id="c-1"):
    now = datetime(2026, 4, 22, 10, 0)
    return Concept(
        id=id, title="Fault vs Failure", summary="A fault is...",
        book_id="book-1", highlight_ids=[], weight=1.5,
        created_at=now, updated_at=now,
    )


def make_concept_priority(id="c-1", priority=2.0, days_overdue=1.0):
    return ConceptWithPriority(
        concept=make_concept(id), priority=priority,
        days_overdue=days_overdue, last_mastery=None,
    )


def make_entry(id="e-1"):
    now = datetime(2026, 4, 22, 10, 0)
    return Entry(
        id=id, text="ubiquitous", source_type=EntryType.MANUAL,
        weight=1.0, created_at=now, updated_at=now,
    )


def make_entry_priority(id="e-1", priority=1.5, days_overdue=0.5):
    return EntryWithPriority(
        entry=make_entry(id), priority=priority,
        days_overdue=days_overdue, last_mastery=None,
    )


def make_question(id="q-1"):
    return InterviewQuestion(
        id=id, question="Tell me about a challenge",
        q_type=QuestionType.BEHAVIORAL, source=QuestionSource.MOCK,
        created_at=datetime(2026, 4, 1, 10, 0),
    )


def make_db():
    db = MagicMock()
    db.get_due_concepts.return_value = [make_concept_priority()]
    db.get_due_entries.return_value = [make_entry_priority()]
    db.get_questions.return_value = [make_question()]
    db.get_streak.return_value = 3
    db.get_heatmap.return_value = {"2026-04-22": 2}
    db.get_study_sessions.return_value = []
    return db


@pytest.fixture
def client():
    from notemaster.main import app, get_db
    mock_db = make_db()
    app.dependency_overrides[get_db] = lambda: mock_db
    yield TestClient(app), mock_db
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# GET /session/queue — backward compatibility
# ---------------------------------------------------------------------------

class TestSessionQueueBackcompat:
    def test_returns_list_without_include_questions(self, client):
        tc, mock_db = client
        resp = tc.get("/session/queue")
        assert resp.status_code == 200
        items = resp.json()
        assert isinstance(items, list)

    def test_default_does_not_call_get_questions(self, client):
        tc, mock_db = client
        tc.get("/session/queue")
        mock_db.get_questions.assert_not_called()


# ---------------------------------------------------------------------------
# GET /session/queue?include_questions=true
# ---------------------------------------------------------------------------

class TestUnifiedQueue:
    def test_includes_note_type_field(self, client):
        tc, mock_db = client
        resp = tc.get("/session/queue?include_questions=true")
        assert resp.status_code == 200
        items = resp.json()
        for item in items:
            assert "note_type" in item
            assert item["note_type"] in ("concept", "entry", "question")

    def test_includes_all_three_types(self, client):
        tc, mock_db = client
        resp = tc.get("/session/queue?include_questions=true")
        items = resp.json()
        types = {i["note_type"] for i in items}
        assert "concept" in types
        assert "entry" in types
        assert "question" in types

    def test_sorted_by_priority_descending(self, client):
        tc, mock_db = client
        mock_db.get_due_concepts.return_value = [
            make_concept_priority("c-1", priority=5.0, days_overdue=3.0),
        ]
        mock_db.get_due_entries.return_value = [
            make_entry_priority("e-1", priority=1.0, days_overdue=0.1),
        ]
        mock_db.get_questions.return_value = [make_question("q-1")]
        resp = tc.get("/session/queue?include_questions=true")
        items = resp.json()
        priorities = [i["priority"] for i in items]
        assert priorities == sorted(priorities, reverse=True)

    def test_each_item_has_priority_and_item(self, client):
        tc, mock_db = client
        resp = tc.get("/session/queue?include_questions=true")
        for item in resp.json():
            assert "priority" in item
            assert "item" in item

    def test_question_item_has_question_field(self, client):
        tc, mock_db = client
        mock_db.get_due_concepts.return_value = []
        mock_db.get_due_entries.return_value = []
        resp = tc.get("/session/queue?include_questions=true")
        items = resp.json()
        assert len(items) == 1
        assert items[0]["note_type"] == "question"
        assert items[0]["item"]["question"] == "Tell me about a challenge"

    def test_calls_get_questions_due_only(self, client):
        tc, mock_db = client
        tc.get("/session/queue?include_questions=true")
        mock_db.get_questions.assert_called_once_with(due_only=True)


# ---------------------------------------------------------------------------
# GET /session/next?include_questions=true
# ---------------------------------------------------------------------------

class TestSessionNextWithQuestions:
    def test_returns_highest_priority_item(self, client):
        tc, mock_db = client
        mock_db.get_due_concepts.return_value = [
            make_concept_priority("c-1", priority=10.0)
        ]
        mock_db.get_due_entries.return_value = []
        mock_db.get_questions.return_value = []
        resp = tc.get("/session/next?include_questions=true")
        assert resp.status_code == 200
        data = resp.json()
        assert data["note_type"] == "concept"

    def test_question_wins_when_highest_priority(self, client):
        tc, mock_db = client
        mock_db.get_due_concepts.return_value = []
        mock_db.get_due_entries.return_value = []
        q = make_question()
        mock_db.get_questions.return_value = [q]
        resp = tc.get("/session/next?include_questions=true")
        assert resp.status_code == 200
        assert resp.json()["note_type"] == "question"

    def test_404_when_nothing_due(self, client):
        tc, mock_db = client
        mock_db.get_due_concepts.return_value = []
        mock_db.get_due_entries.return_value = []
        mock_db.get_questions.return_value = []
        resp = tc.get("/session/next?include_questions=true")
        assert resp.status_code == 404
