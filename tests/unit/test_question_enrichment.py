"""Tests for key_points + sub_questions on InterviewQuestion (#51)."""
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from notemaster.models import InterviewQuestion, QuestionType, QuestionSource, QuestionCategory


def make_question(**kwargs):
    defaults = dict(
        id="q-1", question="Tell me about a time you resolved a conflict",
        q_type=QuestionType.BEHAVIORAL, source=QuestionSource.MOCK,
        category=QuestionCategory.STUDY, created_at=datetime(2026, 4, 30),
    )
    return InterviewQuestion(**{**defaults, **kwargs})


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

class TestKeyPointsModel:
    def test_key_points_defaults_empty(self):
        q = make_question()
        assert q.key_points == []

    def test_sub_questions_defaults_empty(self):
        q = make_question()
        assert q.sub_questions == []

    def test_set_key_points(self):
        q = make_question(key_points=[{"text": "Situation clarity"}, {"text": "Impact stated"}])
        assert len(q.key_points) == 2
        assert q.key_points[0]["text"] == "Situation clarity"

    def test_set_sub_questions(self):
        q = make_question(sub_questions=[
            {"text": "What was the outcome?", "answer": "We shipped on time", "self_score": 2}
        ])
        assert q.sub_questions[0]["self_score"] == 2


# ---------------------------------------------------------------------------
# DB
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    from notemaster.db import Database
    return Database(tmp_path / "test.db")


class TestKeyPointsDb:
    def test_key_points_roundtrip(self, db):
        q = make_question(key_points=[{"text": "Used STAR"}, {"text": "Quantified impact"}])
        db.create_question(q)
        loaded = db.get_question("q-1")
        assert len(loaded.key_points) == 2
        assert loaded.key_points[1]["text"] == "Quantified impact"

    def test_sub_questions_roundtrip(self, db):
        q = make_question(sub_questions=[
            {"text": "Follow-up?", "answer": "Yes", "self_score": 1}
        ])
        db.create_question(q)
        loaded = db.get_question("q-1")
        assert loaded.sub_questions[0]["self_score"] == 1

    def test_empty_defaults_roundtrip(self, db):
        q = make_question()
        db.create_question(q)
        loaded = db.get_question("q-1")
        assert loaded.key_points == []
        assert loaded.sub_questions == []

    def test_update_key_points(self, db):
        q = make_question()
        db.create_question(q)
        db.update_question("q-1", key_points=[{"text": "New point"}])
        loaded = db.get_question("q-1")
        assert loaded.key_points[0]["text"] == "New point"

    def test_update_sub_questions(self, db):
        q = make_question()
        db.create_question(q)
        db.update_question("q-1", sub_questions=[{"text": "Sub?", "answer": "A", "self_score": 3}])
        loaded = db.get_question("q-1")
        assert loaded.sub_questions[0]["self_score"] == 3


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    from notemaster.main import app, get_db
    mock_db = MagicMock()
    q = make_question(
        key_points=[{"text": "STAR structure"}],
        sub_questions=[{"text": "What did you learn?", "answer": "...", "self_score": 2}],
    )
    mock_db.get_question.return_value = q
    mock_db.update_question.return_value = q
    app.dependency_overrides[get_db] = lambda: mock_db
    from fastapi.testclient import TestClient
    yield TestClient(app), mock_db
    app.dependency_overrides.clear()


class TestKeyPointsApi:
    def test_get_question_includes_key_points(self, client):
        tc, _ = client
        resp = tc.get("/questions/q-1")
        assert resp.status_code == 200
        data = resp.json()
        assert "key_points" in data
        assert data["key_points"][0]["text"] == "STAR structure"

    def test_patch_key_points(self, client):
        tc, mock_db = client
        resp = tc.patch("/questions/q-1", json={"key_points": [{"text": "Updated point"}]})
        assert resp.status_code == 200
        call_kwargs = mock_db.update_question.call_args
        assert "key_points" in call_kwargs.kwargs or "key_points" in str(call_kwargs)

    def test_patch_sub_questions(self, client):
        tc, mock_db = client
        resp = tc.patch("/questions/q-1", json={
            "sub_questions": [{"text": "What was the impact?", "answer": "Saved 2 weeks", "self_score": 3}]
        })
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# AI: extract_key_points
# ---------------------------------------------------------------------------

class TestExtractKeyPoints:
    def test_returns_list_of_points(self):
        from notemaster.ai import extract_key_points
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content='["STAR structure","Quantified impact","Lessons learned"]'))]
        )
        result = extract_key_points("Tell me about a conflict", "I resolved it by...", client=mock_client)
        assert isinstance(result, list)
        assert len(result) == 3
        assert result[0] == "STAR structure"

    def test_strips_markdown_fences(self):
        from notemaster.ai import extract_key_points
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content='```json\n["Point A"]\n```'))]
        )
        result = extract_key_points("Q", "A", client=mock_client)
        assert result == ["Point A"]

    def test_raises_on_invalid_json(self):
        from notemaster.ai import extract_key_points
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content='not json'))]
        )
        with pytest.raises((ValueError, Exception)):
            extract_key_points("Q", "A", client=mock_client)
