"""Tests for question category split (study vs interview)."""
import pytest
from datetime import datetime
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from notemaster.models import InterviewQuestion, QuestionType, QuestionSource


def make_question(qid="q-1", category="interview"):
    return InterviewQuestion(
        id=qid,
        question="Tell me about yourself",
        answer="Backend engineer.",
        q_type=QuestionType.BEHAVIORAL,
        source=QuestionSource.MOCK,
        category=category,
        created_at=datetime(2026, 4, 24),
    )


@pytest.fixture
def client():
    from notemaster.main import app, get_db
    mock_db = MagicMock()
    mock_db.get_questions.return_value = [
        make_question("q-1", "interview"),
        make_question("q-2", "study"),
    ]
    mock_db.create_question.side_effect = lambda q: q
    app.dependency_overrides[get_db] = lambda: mock_db
    yield TestClient(app), mock_db
    app.dependency_overrides.clear()


class TestQuestionCategoryModel:
    def test_default_category_is_interview(self):
        from notemaster.models import InterviewQuestion
        q = InterviewQuestion(
            id="q-1", question="Q?", created_at=datetime(2026, 4, 24)
        )
        assert q.category == "interview"

    def test_study_category(self):
        q = make_question(category="study")
        assert q.category == "study"

    def test_interview_category(self):
        q = make_question(category="interview")
        assert q.category == "interview"

    def test_invalid_category_raises(self):
        with pytest.raises(Exception):
            make_question(category="unknown")


class TestQuestionCategoryFilter:
    def test_filter_interview_returns_only_interview(self, client):
        tc, mock_db = client
        mock_db.get_questions.return_value = [make_question("q-1", "interview")]
        resp = tc.get("/questions?category=interview")
        assert resp.status_code == 200
        mock_db.get_questions.assert_called_once()
        call_kwargs = mock_db.get_questions.call_args.kwargs
        assert call_kwargs.get("category") == "interview"

    def test_filter_study_returns_only_study(self, client):
        tc, mock_db = client
        mock_db.get_questions.return_value = [make_question("q-2", "study")]
        resp = tc.get("/questions?category=study")
        assert resp.status_code == 200
        call_kwargs = mock_db.get_questions.call_args.kwargs
        assert call_kwargs.get("category") == "study"

    def test_no_filter_returns_all(self, client):
        tc, mock_db = client
        resp = tc.get("/questions")
        assert resp.status_code == 200
        call_kwargs = mock_db.get_questions.call_args.kwargs
        assert call_kwargs.get("category") is None

    def test_create_question_defaults_to_interview(self, client):
        tc, mock_db = client
        resp = tc.post("/questions", json={"question": "Explain CAP theorem"}, headers={"Content-Type": "application/json"})
        assert resp.status_code == 201
        saved = mock_db.create_question.call_args.args[0]
        assert saved.category == "interview"

    def test_create_question_accepts_study_category(self, client):
        tc, mock_db = client
        resp = tc.post("/questions", json={"question": "Explain CAP theorem", "category": "study"}, headers={"Content-Type": "application/json"})
        assert resp.status_code == 201
        saved = mock_db.create_question.call_args.args[0]
        assert saved.category == "study"


class TestArticleGenerationCategory:
    def test_article_generated_questions_are_study(self, client):
        tc, mock_db = client
        from unittest.mock import patch
        study_result = [
            {"question": "What is rate limiting?", "answer": "Controls...", "q_type": "system_design", "follow_ups": []},
        ]
        mock_db.create_question.side_effect = lambda q: q
        with patch("notemaster.main.ai.generate_questions_from_article", return_value=study_result):
            resp = tc.post("/articles/generate-questions", json={"content": "article text", "mode": "study", "count": 1})
        assert resp.status_code == 200
        saved = mock_db.create_question.call_args.args[0]
        assert saved.category == "study"

    def test_interview_mode_article_questions_are_still_study(self, client):
        tc, mock_db = client
        from unittest.mock import patch
        interview_result = [
            {"question": "You are designing...", "answer": "I would...", "q_type": "system_design", "follow_ups": ["Why not X?"]},
        ]
        mock_db.create_question.side_effect = lambda q: q
        with patch("notemaster.main.ai.generate_questions_from_article", return_value=interview_result):
            resp = tc.post("/articles/generate-questions", json={"content": "article text", "mode": "interview", "count": 1})
        assert resp.status_code == 200
        saved = mock_db.create_question.call_args.args[0]
        assert saved.category == "study"
