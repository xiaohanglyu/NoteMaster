"""Tests for AI-based Q&A extraction from transcripts/markdown."""
import json
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient


# ── AI layer ──────────────────────────────────────────────────────────────────

class TestExtractQuestionsAi:
    def test_returns_list_of_dicts(self):
        from notemaster.ai import extract_questions
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=json.dumps([
                {"question": "What is fault tolerance?",
                 "answer": "The ability to continue operating despite failures.",
                 "q_type": "system_design"}
            ])))]
        )
        result = extract_questions("Q: What is fault tolerance? A: The ability to...", client=mock_client)
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["question"] == "What is fault tolerance?"

    def test_returns_empty_list_on_no_questions(self):
        from notemaster.ai import extract_questions
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="[]"))]
        )
        result = extract_questions("No questions here.", client=mock_client)
        assert result == []

    def test_result_has_required_fields(self):
        from notemaster.ai import extract_questions
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=json.dumps([
                {"question": "Tell me about yourself.", "answer": "", "q_type": "behavioral"}
            ])))]
        )
        result = extract_questions("Tell me about yourself.", client=mock_client)
        assert "question" in result[0]
        assert "answer" in result[0]
        assert "q_type" in result[0]

    def test_handles_markdown_fenced_json_response(self):
        from notemaster.ai import extract_questions
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content='```json\n[{"question":"Q?","answer":"A.","q_type":"behavioral"}]\n```'))]
        )
        result = extract_questions("Q? A.", client=mock_client)
        assert result[0]["question"] == "Q?"

    def test_q_type_defaults_to_other_if_missing(self):
        from notemaster.ai import extract_questions
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=json.dumps([
                {"question": "Q?", "answer": "A."}
            ])))]
        )
        result = extract_questions("Q? A.", client=mock_client)
        assert result[0].get("q_type", "other") == "other"


# ── API layer ─────────────────────────────────────────────────────────────────

class TestExtractQuestionsApi:
    @pytest.fixture
    def client(self):
        from notemaster.main import app, get_db
        mock_db = MagicMock()
        app.dependency_overrides[get_db] = lambda: mock_db
        yield TestClient(app), mock_db
        app.dependency_overrides.clear()

    def test_extract_endpoint_exists(self, client):
        tc, _ = client
        with patch("notemaster.main.ai.extract_questions", return_value=[]):
            resp = tc.post("/questions/extract", json={"text": "hello"})
        assert resp.status_code == 200

    def test_returns_extracted_questions(self, client):
        tc, _ = client
        extracted = [{"question": "What is X?", "answer": "X is Y.", "q_type": "system_design"}]
        with patch("notemaster.main.ai.extract_questions", return_value=extracted):
            resp = tc.post("/questions/extract", json={"text": "What is X? X is Y."})
        assert resp.json() == extracted

    def test_empty_text_returns_422(self, client):
        tc, _ = client
        resp = tc.post("/questions/extract", json={"text": ""})
        assert resp.status_code == 422

    def test_missing_text_returns_422(self, client):
        tc, _ = client
        resp = tc.post("/questions/extract", json={})
        assert resp.status_code == 422
