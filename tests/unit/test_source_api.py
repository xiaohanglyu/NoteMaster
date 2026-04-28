"""Tests for /sources REST endpoints."""
import pytest
from datetime import datetime
from unittest.mock import MagicMock
from notemaster.models import Source, SourceType, InterviewQuestion, QuestionCategory


def make_source(sid="s-1"):
    return Source(
        id=sid, title="Flink Guide", source_type=SourceType.URL,
        source_ref="https://flink.apache.org", content_cache=None,
        tags=["flink"], created_at=datetime(2026, 4, 24),
    )


def make_question(qid="q-1", source_id="s-1"):
    return InterviewQuestion(
        id=qid, question="What is Flink?",
        category=QuestionCategory.STUDY,
        source_id=source_id,
        created_at=datetime(2026, 4, 24),
    )


@pytest.fixture
def client():
    from notemaster.main import app, get_db
    mock_db = MagicMock()
    mock_db.list_sources.return_value = [make_source()]
    mock_db.get_source.return_value = make_source()
    mock_db.create_source.side_effect = lambda s: s
    mock_db.delete_source.return_value = None
    mock_db.get_questions_by_source.return_value = [make_question()]
    app.dependency_overrides[get_db] = lambda: mock_db
    from fastapi.testclient import TestClient
    yield TestClient(app), mock_db
    app.dependency_overrides.clear()


class TestListSources:
    def test_returns_200(self, client):
        tc, _ = client
        assert tc.get("/sources").status_code == 200

    def test_returns_list(self, client):
        tc, _ = client
        assert isinstance(tc.get("/sources").json(), list)


class TestCreateSource:
    def test_create_url(self, client):
        tc, mock_db = client
        resp = tc.post("/sources", json={
            "title": "Flink Docs",
            "source_type": "url",
            "source_ref": "https://flink.apache.org",
        })
        assert resp.status_code == 201
        mock_db.create_source.assert_called_once()

    def test_create_text(self, client):
        tc, mock_db = client
        resp = tc.post("/sources", json={
            "title": "Pasted notes",
            "source_type": "text",
            "content": "Some long article text…",
        })
        assert resp.status_code == 201

    def test_requires_title(self, client):
        tc, _ = client
        resp = tc.post("/sources", json={"source_type": "url"})
        assert resp.status_code == 422

    def test_requires_source_type(self, client):
        tc, _ = client
        resp = tc.post("/sources", json={"title": "Test"})
        assert resp.status_code == 422


class TestDeleteSource:
    def test_delete_returns_204(self, client):
        tc, mock_db = client
        resp = tc.delete("/sources/s-1")
        assert resp.status_code == 204
        mock_db.delete_source.assert_called_once_with("s-1")

    def test_delete_missing_returns_404(self, client):
        tc, mock_db = client
        mock_db.get_source.return_value = None
        resp = tc.delete("/sources/missing")
        assert resp.status_code == 404


class TestGetSourceQuestions:
    def test_returns_questions(self, client):
        tc, _ = client
        resp = tc.get("/sources/s-1/questions")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_missing_source_returns_404(self, client):
        tc, mock_db = client
        mock_db.get_source.return_value = None
        resp = tc.get("/sources/missing/questions")
        assert resp.status_code == 404


class TestGenerateQuestionsCreatesSource:
    def test_generate_stores_source_id_on_questions(self, client):
        tc, mock_db = client
        from unittest.mock import patch
        with patch("notemaster.main.ai.generate_questions_from_article") as mock_gen:
            mock_gen.return_value = [{"question": "Q?", "answer": "A", "q_type": "other", "follow_ups": []}]
            mock_db.create_question.side_effect = lambda q: q
            resp = tc.post("/articles/generate-questions", json={
                "title": "Flink Intro",
                "content": "Flink is a stream processor.",
                "mode": "study",
                "count": 1,
            })
        assert resp.status_code == 200
        # source should have been created
        mock_db.create_source.assert_called_once()
        # question should have source_id
        saved_q = mock_db.create_question.call_args[0][0]
        assert saved_q.source_id is not None
