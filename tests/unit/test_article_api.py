import json
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
from notemaster.models import InterviewQuestion, QuestionType, QuestionSource


def make_question(qid="q-1", question="What is rate limiting?"):
    return InterviewQuestion(
        id=qid,
        question=question,
        answer="Controls request rate...",
        q_type=QuestionType.SYSTEM_DESIGN,
        source=QuestionSource.MOCK,
        tags=["article", "study"],
        created_at=datetime(2026, 4, 24),
    )


STUDY_AI_RESULT = [
    {"question": "What is rate limiting?", "answer": "Controls...", "q_type": "system_design", "follow_ups": []},
    {"question": "Leaky vs token bucket?", "answer": "Token allows bursts...", "q_type": "system_design", "follow_ups": []},
    {"question": "When to use REST?", "answer": "REST is simpler...", "q_type": "other", "follow_ups": []},
    {"question": "What is idempotency?", "answer": "Same result...", "q_type": "system_design", "follow_ups": []},
    {"question": "API versioning strategies?", "answer": "URL, header...", "q_type": "system_design", "follow_ups": []},
]

INTERVIEW_AI_RESULT = [
    {
        "question": "You are designing a public API. How do you handle versioning?",
        "answer": "I would use URL versioning...",
        "q_type": "system_design",
        "follow_ups": ["Why not header versioning?", "What breaks if two teams own the endpoint?"],
    },
    {
        "question": "Your API sees 10x traffic. How do you rate limit?",
        "answer": "Token bucket at the gateway...",
        "q_type": "system_design",
        "follow_ups": ["How do you handle distributed rate limiting?"],
    },
    {
        "question": "Design a paginated feed for 1M items.",
        "answer": "Cursor-based pagination...",
        "q_type": "system_design",
        "follow_ups": ["Why not offset?"],
    },
    {
        "question": "API breaks backward compat. How do you notify clients?",
        "answer": "Deprecation headers...",
        "q_type": "system_design",
        "follow_ups": ["Deprecation window?"],
    },
    {
        "question": "Explain idempotency and when POST should be idempotent.",
        "answer": "Same result on repeat calls...",
        "q_type": "system_design",
        "follow_ups": ["How do you implement idempotency keys?"],
    },
]


@pytest.fixture
def client():
    from notemaster.main import app, get_db
    mock_db = MagicMock()
    mock_db.create_question.side_effect = [
        make_question(f"q-{i}", r["question"]) for i, r in enumerate(STUDY_AI_RESULT + INTERVIEW_AI_RESULT)
    ]
    app.dependency_overrides[get_db] = lambda: mock_db
    from fastapi.testclient import TestClient
    yield TestClient(app), mock_db
    app.dependency_overrides.clear()


class TestGenerateQuestionsEndpoint:
    def test_text_input_study_mode(self, client):
        tc, mock_db = client
        with patch("notemaster.main.ai.generate_questions_from_article", return_value=STUDY_AI_RESULT):
            resp = tc.post("/articles/generate-questions", json={"content": "# API Design\n...", "mode": "study"})
        assert resp.status_code == 200

    def test_returns_question_ids(self, client):
        tc, mock_db = client
        with patch("notemaster.main.ai.generate_questions_from_article", return_value=STUDY_AI_RESULT):
            resp = tc.post("/articles/generate-questions", json={"content": "some content", "mode": "study"})
        body = resp.json()
        assert "question_ids" in body
        assert len(body["question_ids"]) == 5

    def test_returns_questions_created_count(self, client):
        tc, mock_db = client
        with patch("notemaster.main.ai.generate_questions_from_article", return_value=STUDY_AI_RESULT):
            resp = tc.post("/articles/generate-questions", json={"content": "some content", "mode": "study"})
        assert resp.json()["questions_created"] == 5

    def test_saves_each_question_to_db(self, client):
        tc, mock_db = client
        with patch("notemaster.main.ai.generate_questions_from_article", return_value=STUDY_AI_RESULT):
            tc.post("/articles/generate-questions", json={"content": "some content", "mode": "study"})
        assert mock_db.create_question.call_count == 5

    def test_study_mode_tags(self, client):
        tc, mock_db = client
        with patch("notemaster.main.ai.generate_questions_from_article", return_value=STUDY_AI_RESULT):
            tc.post("/articles/generate-questions", json={"content": "content", "mode": "study"})
        call_args = mock_db.create_question.call_args_list[0]
        question_arg = call_args.args[0]
        assert "article" in question_arg.tags
        assert "study" in question_arg.tags

    def test_interview_mode_tags(self, client):
        tc, mock_db = client
        with patch("notemaster.main.ai.generate_questions_from_article", return_value=INTERVIEW_AI_RESULT):
            tc.post("/articles/generate-questions", json={"content": "content", "mode": "interview"})
        call_args = mock_db.create_question.call_args_list[0]
        question_arg = call_args.args[0]
        assert "article" in question_arg.tags
        assert "interview" in question_arg.tags

    def test_interview_mode_follow_ups_in_notes(self, client):
        tc, mock_db = client
        with patch("notemaster.main.ai.generate_questions_from_article", return_value=INTERVIEW_AI_RESULT):
            tc.post("/articles/generate-questions", json={"content": "content", "mode": "interview"})
        call_args = mock_db.create_question.call_args_list[0]
        question_arg = call_args.args[0]
        notes_data = json.loads(question_arg.notes)
        assert isinstance(notes_data, list)
        assert len(notes_data) >= 1

    def test_requires_content_or_url(self, client):
        tc, _ = client
        resp = tc.post("/articles/generate-questions", json={"mode": "study"})
        assert resp.status_code == 422

    def test_url_input_fetches_content(self, client):
        tc, mock_db = client
        mock_response = MagicMock()
        mock_response.text = "<html><body><p>API Design article content.</p></body></html>"
        mock_response.raise_for_status = MagicMock()
        with patch("notemaster.main.ai.generate_questions_from_article", return_value=STUDY_AI_RESULT) as mock_gen:
            with patch("httpx.get", return_value=mock_response):
                resp = tc.post("/articles/generate-questions", json={
                    "url": "https://example.com/api-design",
                    "mode": "study",
                })
        assert resp.status_code == 200
        called_content = mock_gen.call_args.args[0]
        assert "API Design article content" in called_content

    def test_default_mode_is_study(self, client):
        tc, mock_db = client
        with patch("notemaster.main.ai.generate_questions_from_article", return_value=STUDY_AI_RESULT) as mock_gen:
            tc.post("/articles/generate-questions", json={"content": "content"})
        assert mock_gen.call_args.kwargs.get("mode", mock_gen.call_args.args[1] if len(mock_gen.call_args.args) > 1 else "study") in ("study", None, "")
