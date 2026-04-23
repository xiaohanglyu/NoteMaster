import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from notemaster.models import (
    InterviewQuestion, QuestionType, QuestionSource, QuestionReviewRecord,
)


def make_question(id="q-1", q_type=QuestionType.BEHAVIORAL):
    return InterviewQuestion(
        id=id,
        question="Tell me about yourself",
        answer="Backend engineer, 5 years exp.",
        q_type=q_type,
        source=QuestionSource.MOCK,
        created_at=datetime(2026, 4, 1, 10, 0),
    )


def make_review_record(question_id="q-1"):
    now = datetime(2026, 4, 22, 10, 0)
    return QuestionReviewRecord(
        question_id=question_id,
        grade=3,
        reviewed_at=now,
        next_review_at=now + timedelta(days=3),
        interval=3,
        reps=1,
        ef=2.5,
    )


def make_db():
    db = MagicMock()
    db.get_questions.return_value = [make_question()]
    db.get_question.return_value = make_question()
    db.create_question.side_effect = lambda q: q
    db.update_question.return_value = make_question()
    db.get_next_due_question.return_value = make_question()
    db.record_question_review.return_value = make_review_record()
    db.bulk_import_questions.return_value = 2
    return db


@pytest.fixture
def client():
    from notemaster.main import app, get_db
    mock_db = make_db()
    app.dependency_overrides[get_db] = lambda: mock_db
    yield TestClient(app), mock_db
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# GET /questions
# ---------------------------------------------------------------------------

class TestListQuestions:
    def test_returns_list(self, client):
        tc, _ = client
        resp = tc.get("/questions")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_has_expected_fields(self, client):
        tc, _ = client
        data = tc.get("/questions").json()
        assert data[0]["question"] == "Tell me about yourself"
        assert "q_type" in data[0]
        assert "source" in data[0]

    def test_filter_by_type(self, client):
        tc, mock_db = client
        tc.get("/questions?q_type=behavioral")
        mock_db.get_questions.assert_called_with(
            q_type=QuestionType.BEHAVIORAL, source=None, application_id=None, due_only=False
        )

    def test_filter_due_only(self, client):
        tc, mock_db = client
        tc.get("/questions?due_only=true")
        mock_db.get_questions.assert_called_with(
            q_type=None, source=None, application_id=None, due_only=True
        )


# ---------------------------------------------------------------------------
# POST /questions
# ---------------------------------------------------------------------------

class TestCreateQuestion:
    def test_creates_and_returns_201(self, client):
        tc, mock_db = client
        payload = {
            "question": "Design a URL shortener",
            "q_type": "system_design",
            "source": "mock",
        }
        resp = tc.post("/questions", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert data["q_type"] == "system_design"

    def test_missing_question_returns_422(self, client):
        tc, _ = client
        resp = tc.post("/questions", json={"q_type": "coding"})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /questions/next
# ---------------------------------------------------------------------------

class TestGetNextQuestion:
    def test_returns_next_due(self, client):
        tc, _ = client
        resp = tc.get("/questions/next")
        assert resp.status_code == 200
        assert resp.json()["id"] == "q-1"

    def test_no_due_returns_404(self, client):
        tc, mock_db = client
        mock_db.get_next_due_question.return_value = None
        resp = tc.get("/questions/next")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /questions/{id}
# ---------------------------------------------------------------------------

class TestGetQuestion:
    def test_returns_question(self, client):
        tc, _ = client
        resp = tc.get("/questions/q-1")
        assert resp.status_code == 200
        assert resp.json()["id"] == "q-1"

    def test_not_found_returns_404(self, client):
        tc, mock_db = client
        mock_db.get_question.return_value = None
        resp = tc.get("/questions/ghost")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /questions/{id}
# ---------------------------------------------------------------------------

class TestUpdateQuestion:
    def test_updates_answer(self, client):
        tc, mock_db = client
        resp = tc.patch("/questions/q-1", json={"answer": "Updated answer"})
        assert resp.status_code == 200
        mock_db.update_question.assert_called_once()

    def test_not_found_returns_404(self, client):
        tc, mock_db = client
        mock_db.update_question.return_value = None
        resp = tc.patch("/questions/ghost", json={"answer": "x"})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /questions/{id}
# ---------------------------------------------------------------------------

class TestDeleteQuestion:
    def test_deletes_returns_204(self, client):
        tc, mock_db = client
        resp = tc.delete("/questions/q-1")
        assert resp.status_code == 204
        mock_db.delete_question.assert_called_once_with("q-1")

    def test_not_found_returns_404(self, client):
        tc, mock_db = client
        mock_db.get_question.return_value = None
        resp = tc.delete("/questions/ghost")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /questions/{id}/review
# ---------------------------------------------------------------------------

class TestReviewQuestion:
    def test_records_review(self, client):
        tc, mock_db = client
        resp = tc.post("/questions/q-1/review", json={"grade": 3})
        assert resp.status_code == 200
        data = resp.json()
        assert data["question_id"] == "q-1"
        assert "next_review_at" in data
        assert "interval" in data

    def test_invalid_grade_returns_422(self, client):
        tc, _ = client
        resp = tc.post("/questions/q-1/review", json={"grade": 5})
        assert resp.status_code == 422

    def test_not_found_returns_404(self, client):
        tc, mock_db = client
        mock_db.record_question_review.side_effect = ValueError("not found")
        resp = tc.post("/questions/q-1/review", json={"grade": 2})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /questions/import
# ---------------------------------------------------------------------------

class TestBulkImport:
    def test_imports_and_returns_count(self, client):
        tc, mock_db = client
        payload = [
            {"question": "Tell me about a challenge", "q_type": "behavioral", "source": "mock"},
            {"question": "Design a cache", "q_type": "system_design", "source": "mock"},
        ]
        resp = tc.post("/questions/import", json=payload)
        assert resp.status_code == 200
        assert resp.json()["imported"] == 2

    def test_empty_list_returns_zero(self, client):
        tc, mock_db = client
        mock_db.bulk_import_questions.return_value = 0
        resp = tc.post("/questions/import", json=[])
        assert resp.status_code == 200
        assert resp.json()["imported"] == 0
