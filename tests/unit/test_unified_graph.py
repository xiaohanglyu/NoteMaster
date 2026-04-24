import pytest
from datetime import datetime
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from notemaster.models import (
    Book, Concept, ConceptEdge, RelationType,
    InterviewQuestion, QuestionType, QuestionSource,
)


def make_concept(id="c-1", book_id="book-1"):
    now = datetime(2026, 4, 22)
    return Concept(id=id, title=f"Concept {id}", summary="...",
                   book_id=book_id, highlight_ids=[], weight=1.0,
                   created_at=now, updated_at=now)


def make_question(id="q-1"):
    return InterviewQuestion(
        id=id, question="Explain CAP theorem",
        q_type=QuestionType.SYSTEM_DESIGN, source=QuestionSource.REAL,
        created_at=datetime(2026, 4, 22),
    )


def make_edge(from_id="c-1", to_id="c-2"):
    return ConceptEdge(from_concept_id=from_id, to_concept_id=to_id,
                       relation=RelationType.DEPENDS_ON)


def make_db():
    db = MagicMock()
    db.get_books.return_value = [
        Book(id="book-1", title="DDIA", asset_id="a1", synced_at=datetime(2026,4,22)),
        Book(id="book-2", title="SICP", asset_id="a2", synced_at=datetime(2026,4,22)),
    ]
    db.get_concepts.return_value = [make_concept("c-1", "book-1"), make_concept("c-2", "book-2")]
    db.get_edges.return_value = [make_edge()]
    db.get_questions.return_value = [make_question()]
    db.get_question_concepts.return_value = [make_concept()]
    db.get_concept_questions.return_value = [make_question()]
    return db


@pytest.fixture
def client():
    from notemaster.main import app, get_db
    mock_db = make_db()
    app.dependency_overrides[get_db] = lambda: mock_db
    yield TestClient(app), mock_db
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# GET /graph — existing behavior unchanged
# ---------------------------------------------------------------------------

class TestGraphBackcompat:
    def test_no_book_id_returns_all_concepts(self, client):
        tc, _ = client
        resp = tc.get("/graph")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["nodes"]) == 2

    def test_book_id_filters_concepts(self, client):
        tc, mock_db = client
        mock_db.get_concepts.return_value = [make_concept("c-1", "book-1")]
        resp = tc.get("/graph?book_id=book-1")
        assert resp.status_code == 200
        mock_db.get_concepts.assert_called_with(book_id="book-1")

    def test_nodes_have_expected_fields(self, client):
        tc, _ = client
        data = tc.get("/graph").json()
        node = data["nodes"][0]
        assert "id" in node
        assert "title" in node
        assert "book_id" in node
        assert node.get("node_type") == "concept"

    def test_edges_filtered_to_visible_concepts(self, client):
        tc, mock_db = client
        mock_db.get_concepts.return_value = [make_concept("c-1", "book-1")]
        mock_db.get_edges.return_value = [make_edge("c-1", "c-2")]
        resp = tc.get("/graph?book_id=book-1")
        data = resp.json()
        assert data["edges"] == []


# ---------------------------------------------------------------------------
# GET /graph?include_questions=true
# ---------------------------------------------------------------------------

class TestGraphWithQuestions:
    def test_includes_question_nodes(self, client):
        tc, mock_db = client
        mock_db.get_questions.return_value = [make_question()]
        mock_db.get_question_concepts.return_value = [make_concept()]
        resp = tc.get("/graph?include_questions=true")
        data = resp.json()
        node_types = {n["node_type"] for n in data["nodes"]}
        assert "question" in node_types

    def test_question_nodes_have_expected_fields(self, client):
        tc, mock_db = client
        mock_db.get_questions.return_value = [make_question()]
        mock_db.get_question_concepts.return_value = []
        resp = tc.get("/graph?include_questions=true")
        q_nodes = [n for n in resp.json()["nodes"] if n["node_type"] == "question"]
        assert len(q_nodes) == 1
        assert q_nodes[0]["id"] == "q-1"
        assert "q_type" in q_nodes[0]

    def test_tested_by_edges_added(self, client):
        tc, mock_db = client
        mock_db.get_questions.return_value = [make_question("q-1")]
        mock_db.get_question_concepts.return_value = [make_concept("c-1")]
        resp = tc.get("/graph?include_questions=true")
        edges = resp.json()["edges"]
        tested_by = [e for e in edges if e.get("relation") == "tested_by"]
        assert len(tested_by) == 1
        assert tested_by[0]["from"] == "c-1"
        assert tested_by[0]["to"] == "q-1"

    def test_without_include_questions_no_question_nodes(self, client):
        tc, mock_db = client
        resp = tc.get("/graph")
        node_types = {n.get("node_type") for n in resp.json()["nodes"]}
        assert "question" not in node_types
        mock_db.get_questions.assert_not_called()


# ---------------------------------------------------------------------------
# GET /graph/books — list books for selector
# ---------------------------------------------------------------------------

class TestGraphBooks:
    def test_returns_book_list(self, client):
        tc, _ = client
        resp = tc.get("/graph/books")
        assert resp.status_code == 200
        books = resp.json()
        assert len(books) == 2
        assert books[0]["id"] == "book-1"
