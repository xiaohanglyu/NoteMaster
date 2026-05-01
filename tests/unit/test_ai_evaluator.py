"""Tests for AI Evaluator — answer coverage + expression feedback (#53)."""
import pytest
from unittest.mock import MagicMock
from datetime import datetime

from notemaster.models import InterviewQuestion, QuestionType, QuestionSource


def make_question(**kwargs):
    defaults = dict(
        id="q-1",
        question="Tell me about a time you resolved a conflict",
        answer="I used the STAR method. I identified the root cause, spoke directly with my colleague, and we agreed on a shared solution. The team shipped on time.",
        key_points=[
            {"text": "Situation described clearly"},
            {"text": "Specific action taken"},
            {"text": "Quantified outcome"},
        ],
        q_type=QuestionType.BEHAVIORAL,
        source=QuestionSource.MOCK,
        created_at=datetime(2026, 4, 30),
    )
    return InterviewQuestion(**{**defaults, **kwargs})


def make_mock_client(content: str):
    client = MagicMock()
    client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=content))]
    )
    return client


# ---------------------------------------------------------------------------
# AI function: evaluate_answer
# ---------------------------------------------------------------------------

_SAMPLE_RESPONSE = """{
  "coverage": [
    {"point": "Situation described clearly", "hit": true, "note": "Good context given"},
    {"point": "Specific action taken", "hit": true, "note": "Direct conversation mentioned"},
    {"point": "Quantified outcome", "hit": false, "note": "No numbers or metrics"}
  ],
  "expression_feedback": [
    {"original": "we agreed on a shared solution", "suggestion": "we reached a mutual agreement on the approach", "issue": "slightly informal"}
  ],
  "score": 0.67
}"""


class TestEvaluateAnswer:
    def test_returns_coverage_list(self):
        from notemaster.ai import evaluate_answer
        q = make_question()
        result = evaluate_answer(q, "I talked to my colleague and we fixed it.", client=make_mock_client(_SAMPLE_RESPONSE))
        assert "coverage" in result
        assert len(result["coverage"]) == 3

    def test_coverage_hit_values(self):
        from notemaster.ai import evaluate_answer
        q = make_question()
        result = evaluate_answer(q, "I talked to my colleague.", client=make_mock_client(_SAMPLE_RESPONSE))
        hits = {c["point"]: c["hit"] for c in result["coverage"]}
        assert hits["Situation described clearly"] is True
        assert hits["Quantified outcome"] is False

    def test_returns_score(self):
        from notemaster.ai import evaluate_answer
        q = make_question()
        result = evaluate_answer(q, "response", client=make_mock_client(_SAMPLE_RESPONSE))
        assert abs(result["score"] - 0.67) < 0.01

    def test_returns_expression_feedback(self):
        from notemaster.ai import evaluate_answer
        q = make_question()
        result = evaluate_answer(q, "response", client=make_mock_client(_SAMPLE_RESPONSE))
        assert "expression_feedback" in result
        assert len(result["expression_feedback"]) == 1
        assert "suggestion" in result["expression_feedback"][0]

    def test_empty_key_points_still_works(self):
        from notemaster.ai import evaluate_answer
        q = make_question(key_points=[])
        resp = '{"coverage": [], "expression_feedback": [], "score": 0.5}'
        result = evaluate_answer(q, "response", client=make_mock_client(resp))
        assert result["coverage"] == []
        assert result["score"] == 0.5

    def test_strips_markdown_fences(self):
        from notemaster.ai import evaluate_answer
        q = make_question()
        fenced = f"```json\n{_SAMPLE_RESPONSE}\n```"
        result = evaluate_answer(q, "response", client=make_mock_client(fenced))
        assert "coverage" in result

    def test_raises_on_invalid_json(self):
        from notemaster.ai import evaluate_answer
        q = make_question()
        with pytest.raises((ValueError, Exception)):
            evaluate_answer(q, "response", client=make_mock_client("not json"))


# ---------------------------------------------------------------------------
# API: POST /questions/{id}/evaluate
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    from notemaster.main import app, get_db
    mock_db = MagicMock()
    mock_db.get_question.return_value = make_question()
    mock_db.create_attempt.side_effect = lambda a: a
    app.dependency_overrides[get_db] = lambda: mock_db
    from fastapi.testclient import TestClient
    yield TestClient(app), mock_db
    app.dependency_overrides.clear()


_EVAL_RESULT = {
    "coverage": [
        {"point": "Situation described clearly", "hit": True, "note": "Good"},
        {"point": "Quantified outcome", "hit": False, "note": "Missing"},
    ],
    "expression_feedback": [{"original": "we fixed it", "suggestion": "we resolved the issue", "issue": "informal"}],
    "score": 0.5,
}


class TestEvaluateApi:
    def test_evaluate_returns_result(self, client):
        from unittest.mock import patch
        tc, _ = client
        with patch("notemaster.main.ai.evaluate_answer", return_value=_EVAL_RESULT):
            resp = tc.post("/questions/q-1/evaluate", json={"response_text": "I talked to my colleague."})
        assert resp.status_code == 200
        data = resp.json()
        assert "coverage" in data
        assert "expression_feedback" in data
        assert "score" in data

    def test_evaluate_saves_attempt(self, client):
        from unittest.mock import patch
        tc, mock_db = client
        with patch("notemaster.main.ai.evaluate_answer", return_value=_EVAL_RESULT):
            tc.post("/questions/q-1/evaluate", json={"response_text": "My answer."})
        mock_db.create_attempt.assert_called_once()
        attempt = mock_db.create_attempt.call_args[0][0]
        assert attempt.question_id == "q-1"
        assert abs(attempt.score - 0.5) < 0.01

    def test_evaluate_question_not_found(self, client):
        tc, mock_db = client
        mock_db.get_question.return_value = None
        resp = tc.post("/questions/ghost/evaluate", json={"response_text": "x"})
        assert resp.status_code == 404

    def test_evaluate_empty_response(self, client):
        tc, _ = client
        resp = tc.post("/questions/q-1/evaluate", json={"response_text": ""})
        assert resp.status_code == 422
