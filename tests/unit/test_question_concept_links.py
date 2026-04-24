import pytest
from datetime import datetime
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from notemaster.db import Database
from notemaster.models import (
    Book, Concept, InterviewQuestion, QuestionType, QuestionSource,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db():
    return Database(":memory:")


@pytest.fixture
def book(db):
    b = Book(id="book-1", title="DDIA", asset_id="asset-1", synced_at=datetime.now())
    db.save_book(b)
    return b


@pytest.fixture
def concept(db, book):
    now = datetime.now()
    c = Concept(id="c-1", title="CAP Theorem", summary="...",
                book_id=book.id, highlight_ids=[], weight=1.5,
                created_at=now, updated_at=now)
    db.create_concept(c)
    return c


@pytest.fixture
def question(db):
    q = InterviewQuestion(
        id="q-1", question="Explain CAP theorem",
        q_type=QuestionType.SYSTEM_DESIGN, source=QuestionSource.REAL,
        created_at=datetime.now(),
    )
    db.create_question(q)
    return q


# ---------------------------------------------------------------------------
# DB: question_concept_links CRUD
# ---------------------------------------------------------------------------

class TestQuestionConceptLinksDb:
    def test_link_question_to_concept(self, db, question, concept):
        db.link_question_concept(question.id, concept.id)
        links = db.get_question_concepts(question.id)
        assert len(links) == 1
        assert links[0].id == concept.id

    def test_link_is_idempotent(self, db, question, concept):
        db.link_question_concept(question.id, concept.id)
        db.link_question_concept(question.id, concept.id)
        assert len(db.get_question_concepts(question.id)) == 1

    def test_unlink_question_concept(self, db, question, concept):
        db.link_question_concept(question.id, concept.id)
        db.unlink_question_concept(question.id, concept.id)
        assert db.get_question_concepts(question.id) == []

    def test_get_concepts_for_question(self, db, question, concept, book):
        now = datetime.now()
        c2 = Concept(id="c-2", title="Consistency", summary="...",
                     book_id=book.id, highlight_ids=[], weight=1.0,
                     created_at=now, updated_at=now)
        db.create_concept(c2)
        db.link_question_concept(question.id, "c-1")
        db.link_question_concept(question.id, "c-2")
        links = db.get_question_concepts(question.id)
        assert len(links) == 2

    def test_get_questions_for_concept(self, db, question, concept):
        db.link_question_concept(question.id, concept.id)
        questions = db.get_concept_questions(concept.id)
        assert len(questions) == 1
        assert questions[0].id == question.id

    def test_delete_question_cascades_links(self, db, question, concept):
        db.link_question_concept(question.id, concept.id)
        db.delete_question(question.id)
        assert db.get_question_concepts(question.id) == []

    def test_delete_concept_cascades_links(self, db, question, concept):
        db.link_question_concept(question.id, concept.id)
        db.conn.execute("DELETE FROM concepts WHERE id = ?", (concept.id,))
        db.conn.commit()
        assert db.get_question_concepts(question.id) == []


# ---------------------------------------------------------------------------
# API: /questions/{id}/concepts
# ---------------------------------------------------------------------------

def make_concept_obj(id="c-1"):
    now = datetime.now()
    return Concept(id=id, title="CAP Theorem", summary="Consistency, Availability, Partition tolerance",
                   book_id="book-1", highlight_ids=[], weight=1.5,
                   created_at=now, updated_at=now)


def make_question_obj(id="q-1"):
    return InterviewQuestion(
        id=id, question="Explain CAP theorem",
        q_type=QuestionType.SYSTEM_DESIGN, source=QuestionSource.REAL,
        created_at=datetime.now(),
    )


def make_db_mock():
    db = MagicMock()
    db.get_question.return_value = make_question_obj()
    db.get_concept.return_value = make_concept_obj()
    db.get_question_concepts.return_value = [make_concept_obj()]
    db.get_concept_questions.return_value = [make_question_obj()]
    return db


@pytest.fixture
def client():
    from notemaster.main import app, get_db
    mock_db = make_db_mock()
    app.dependency_overrides[get_db] = lambda: mock_db
    yield TestClient(app), mock_db
    app.dependency_overrides.clear()


class TestQuestionConceptLinksApi:
    def test_get_linked_concepts(self, client):
        tc, _ = client
        resp = tc.get("/questions/q-1/concepts")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
        assert resp.json()[0]["id"] == "c-1"

    def test_link_concept(self, client):
        tc, mock_db = client
        resp = tc.post("/questions/q-1/concepts", json={"concept_id": "c-1"})
        assert resp.status_code == 201
        mock_db.link_question_concept.assert_called_once_with("q-1", "c-1")

    def test_link_concept_question_not_found(self, client):
        tc, mock_db = client
        mock_db.get_question.return_value = None
        resp = tc.post("/questions/ghost/concepts", json={"concept_id": "c-1"})
        assert resp.status_code == 404

    def test_link_concept_concept_not_found(self, client):
        tc, mock_db = client
        mock_db.get_concept.return_value = None
        resp = tc.post("/questions/q-1/concepts", json={"concept_id": "ghost"})
        assert resp.status_code == 404

    def test_unlink_concept(self, client):
        tc, mock_db = client
        resp = tc.delete("/questions/q-1/concepts/c-1")
        assert resp.status_code == 204
        mock_db.unlink_question_concept.assert_called_once_with("q-1", "c-1")

    def test_get_questions_for_concept(self, client):
        tc, _ = client
        resp = tc.get("/concepts/c-1/questions")
        assert resp.status_code == 200
        assert resp.json()[0]["id"] == "q-1"
