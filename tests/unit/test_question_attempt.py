"""Tests for QuestionAttempt — answer history (#52)."""
import pytest
from datetime import datetime
from unittest.mock import MagicMock

from notemaster.models import QuestionAttempt, InterviewQuestion, QuestionType, QuestionSource


def make_attempt(**kwargs):
    defaults = dict(
        id="a-1",
        question_id="q-1",
        response_text="I resolved it by talking directly to the team member.",
        coverage=[{"point": "Situation clarity", "hit": True}, {"point": "Quantified impact", "hit": False}],
        ai_feedback="Good STAR structure. Missing quantified outcome.",
        score=0.6,
        attempted_at=datetime(2026, 4, 30, 10, 0),
    )
    return QuestionAttempt(**{**defaults, **kwargs})


def make_question():
    return InterviewQuestion(
        id="q-1", question="Tell me about a conflict",
        q_type=QuestionType.BEHAVIORAL, source=QuestionSource.MOCK,
        created_at=datetime(2026, 4, 30),
    )


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

class TestQuestionAttemptModel:
    def test_fields(self):
        a = make_attempt()
        assert a.question_id == "q-1"
        assert a.score == 0.6
        assert len(a.coverage) == 2

    def test_coverage_hit_false(self):
        a = make_attempt()
        missed = [c for c in a.coverage if not c["hit"]]
        assert missed[0]["point"] == "Quantified impact"

    def test_empty_coverage(self):
        a = make_attempt(coverage=[])
        assert a.coverage == []

    def test_optional_feedback(self):
        a = make_attempt(ai_feedback=None)
        assert a.ai_feedback is None


# ---------------------------------------------------------------------------
# DB
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    from notemaster.db import Database
    return Database(tmp_path / "test.db")


@pytest.fixture
def question(db):
    q = make_question()
    db.create_question(q)
    return q


class TestQuestionAttemptDb:
    def test_create_and_list(self, db, question):
        a = make_attempt()
        db.create_attempt(a)
        attempts = db.list_attempts("q-1")
        assert len(attempts) == 1
        assert attempts[0].response_text == a.response_text

    def test_coverage_roundtrips(self, db, question):
        a = make_attempt()
        db.create_attempt(a)
        loaded = db.list_attempts("q-1")[0]
        assert loaded.coverage[0]["hit"] is True
        assert loaded.coverage[1]["hit"] is False

    def test_score_roundtrips(self, db, question):
        a = make_attempt(score=0.85)
        db.create_attempt(a)
        loaded = db.list_attempts("q-1")[0]
        assert abs(loaded.score - 0.85) < 0.001

    def test_list_ordered_newest_first(self, db, question):
        db.create_attempt(make_attempt(id="a-1", attempted_at=datetime(2026, 4, 29)))
        db.create_attempt(make_attempt(id="a-2", attempted_at=datetime(2026, 4, 30)))
        attempts = db.list_attempts("q-1")
        assert attempts[0].id == "a-2"

    def test_delete_attempt(self, db, question):
        db.create_attempt(make_attempt())
        db.delete_attempt("a-1")
        assert db.list_attempts("q-1") == []

    def test_empty_list_for_new_question(self, db, question):
        assert db.list_attempts("q-1") == []

    def test_multiple_questions_isolated(self, db):
        db.create_question(InterviewQuestion(
            id="q-2", question="Q2", q_type=QuestionType.BEHAVIORAL,
            source=QuestionSource.MOCK, created_at=datetime(2026, 4, 30),
        ))
        db.create_question(make_question())
        db.create_attempt(make_attempt(question_id="q-1"))
        assert db.list_attempts("q-2") == []


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def make_db_mock():
    db = MagicMock()
    db.get_question.return_value = make_question()
    db.list_attempts.return_value = [make_attempt()]
    db.create_attempt.side_effect = lambda a: a
    db.delete_attempt.return_value = True
    return db


@pytest.fixture
def client():
    from notemaster.main import app, get_db
    mock_db = make_db_mock()
    app.dependency_overrides[get_db] = lambda: mock_db
    from fastapi.testclient import TestClient
    yield TestClient(app), mock_db
    app.dependency_overrides.clear()


class TestQuestionAttemptApi:
    def test_list_attempts(self, client):
        tc, _ = client
        resp = tc.get("/questions/q-1/attempts")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["score"] == 0.6

    def test_list_attempts_question_not_found(self, client):
        tc, mock_db = client
        mock_db.get_question.return_value = None
        resp = tc.get("/questions/ghost/attempts")
        assert resp.status_code == 404

    def test_create_attempt(self, client):
        tc, mock_db = client
        payload = {
            "response_text": "I handled it by...",
            "coverage": [{"point": "STAR", "hit": True}],
            "ai_feedback": "Good.",
            "score": 0.8,
        }
        resp = tc.post("/questions/q-1/attempts", json=payload)
        assert resp.status_code == 200
        mock_db.create_attempt.assert_called_once()

    def test_create_attempt_question_not_found(self, client):
        tc, mock_db = client
        mock_db.get_question.return_value = None
        resp = tc.post("/questions/ghost/attempts", json={"response_text": "x", "score": 0.5})
        assert resp.status_code == 404

    def test_delete_attempt(self, client):
        tc, mock_db = client
        resp = tc.delete("/attempts/a-1")
        assert resp.status_code == 204
        mock_db.delete_attempt.assert_called_once_with("a-1")

    def test_delete_attempt_not_found(self, client):
        tc, mock_db = client
        mock_db.delete_attempt.return_value = False
        resp = tc.delete("/attempts/ghost")
        assert resp.status_code == 404
