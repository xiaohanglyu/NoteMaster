"""Tests for Problem ↔ InterviewQuestion sections link (#SD strengthening)."""
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from notemaster.models import (
    InterviewQuestion, QuestionType, QuestionSource, QuestionCategory,
    Problem, ProblemType, ProblemDifficulty,
)


def make_problem(**kwargs):
    defaults = dict(
        id="p-1", title="Design URL Shortener", problem_type=ProblemType.SD,
        difficulty=ProblemDifficulty.MEDIUM, created_at=datetime(2026, 4, 28),
    )
    return Problem(**{**defaults, **kwargs})


def make_question(**kwargs):
    defaults = dict(
        id="q-1", question="What are the functional requirements?",
        q_type=QuestionType.SYSTEM_DESIGN, source=QuestionSource.MOCK,
        category=QuestionCategory.STUDY, created_at=datetime(2026, 4, 28),
    )
    return InterviewQuestion(**{**defaults, **kwargs})


# ---------------------------------------------------------------------------
# Model: problem_id field on InterviewQuestion
# ---------------------------------------------------------------------------

class TestProblemIdOnQuestion:
    def test_defaults_none(self):
        q = make_question()
        assert q.problem_id is None

    def test_can_set_problem_id(self):
        q = make_question(problem_id="p-1")
        assert q.problem_id == "p-1"

    def test_round_field_for_section_type(self):
        q = make_question(problem_id="p-1", round="requirements")
        assert q.round == "requirements"


# ---------------------------------------------------------------------------
# DB: problem_id column + get_questions_by_problem
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    from notemaster.db import Database
    return Database(tmp_path / "test.db")


@pytest.fixture
def problem(db):
    p = make_problem()
    db.create_problem(p)
    return p


class TestProblemSectionsDb:
    def test_create_question_with_problem_id(self, db, problem):
        q = make_question(problem_id=problem.id)
        db.create_question(q)
        loaded = db.get_question(q.id)
        assert loaded.problem_id == problem.id

    def test_problem_id_none_roundtrips(self, db):
        q = make_question()
        db.create_question(q)
        loaded = db.get_question(q.id)
        assert loaded.problem_id is None

    def test_get_questions_by_problem(self, db, problem):
        q1 = make_question(id="q-1", problem_id=problem.id, round="requirements")
        q2 = make_question(id="q-2", problem_id=problem.id, round="hld")
        q3 = make_question(id="q-3")  # unrelated
        for q in [q1, q2, q3]:
            db.create_question(q)
        sections = db.get_questions_by_problem(problem.id)
        assert len(sections) == 2
        ids = {q.id for q in sections}
        assert "q-1" in ids and "q-2" in ids
        assert "q-3" not in ids

    def test_get_questions_by_problem_empty(self, db, problem):
        assert db.get_questions_by_problem(problem.id) == []

    def test_delete_problem_does_not_cascade_questions(self, db, problem):
        q = make_question(problem_id=problem.id)
        db.create_question(q)
        db.delete_problem(problem.id)
        # Question survives but problem_id becomes null / question still loadable
        loaded = db.get_question(q.id)
        assert loaded is not None


# ---------------------------------------------------------------------------
# API: GET /problems/{id}/questions and POST /problems/{id}/generate-sections
# ---------------------------------------------------------------------------

def make_db_mock():
    db = MagicMock()
    db.get_problem.return_value = make_problem()
    db.get_questions_by_problem.return_value = [
        make_question(id="q-1", problem_id="p-1", round="requirements"),
        make_question(id="q-2", problem_id="p-1", round="hld"),
    ]
    db.create_question.side_effect = lambda q: q
    return db


@pytest.fixture
def client():
    from notemaster.main import app, get_db
    mock_db = make_db_mock()
    app.dependency_overrides[get_db] = lambda: mock_db
    from fastapi.testclient import TestClient
    yield TestClient(app), mock_db
    app.dependency_overrides.clear()


class TestProblemSectionsApi:
    def test_get_problem_questions(self, client):
        tc, _ = client
        resp = tc.get("/problems/p-1/questions")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 2

    def test_get_problem_questions_not_found(self, client):
        tc, mock_db = client
        mock_db.get_problem.return_value = None
        resp = tc.get("/problems/ghost/questions")
        assert resp.status_code == 404

    def test_generate_sections_returns_questions(self, client):
        tc, mock_db = client
        sections = [
            {"round": "requirements", "question": "What are the functional requirements?", "answer": "Shorten URLs"},
            {"round": "hld", "question": "Draw the high-level design", "answer": "Load balancer → App → DB"},
        ]
        with patch("notemaster.main.ai.generate_sd_sections") as mock_gen:
            mock_gen.return_value = sections
            resp = tc.post("/problems/p-1/generate-sections")
        assert resp.status_code == 200
        data = resp.json()
        assert "created" in data
        assert data["created"] == 2

    def test_generate_sections_problem_not_found(self, client):
        tc, mock_db = client
        mock_db.get_problem.return_value = None
        resp = tc.post("/problems/ghost/generate-sections")
        assert resp.status_code == 404
