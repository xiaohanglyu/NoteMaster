"""Tests for per-concept generated review questions."""
import json
import uuid
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from notemaster.models import Concept, HighlightColor, Highlight, Book
from notemaster.db import Database


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_db(tmp_path):
    return Database(tmp_path / "test.db")


def _make_concept(db, questions=None):
    book = Book(id="b-1", title="DDIA", asset_id="a-1", synced_at=datetime.now())
    db.save_book(book)
    h = Highlight(id="h-1", text="Some text", color=HighlightColor.GREEN,
                  book_id="b-1", book_title="DDIA")
    db.save_highlight(h)
    c = Concept(
        id=str(uuid.uuid4()),
        title="Fault Tolerance",
        summary="Faults are component deviations; failures are service unavailability.",
        book_id="b-1",
        highlight_ids=["h-1"],
        weight=1.0,
        questions=questions or [],
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    db.create_concept(c)
    return c


# ── DB layer ──────────────────────────────────────────────────────────────────

class TestConceptQuestionsDb:
    def test_create_concept_stores_questions(self, tmp_path):
        db = _make_db(tmp_path)
        qs = ["What is fault tolerance?", "Explain faults vs failures.", "Give an example."]
        c = _make_concept(db, questions=qs)
        fetched = db.get_concept(c.id)
        assert fetched.questions == qs

    def test_default_questions_is_empty_list(self, tmp_path):
        db = _make_db(tmp_path)
        c = _make_concept(db, questions=[])
        fetched = db.get_concept(c.id)
        assert fetched.questions == []

    def test_get_concepts_returns_questions(self, tmp_path):
        db = _make_db(tmp_path)
        qs = ["Q1", "Q2"]
        c = _make_concept(db, questions=qs)
        concepts = db.get_concepts()
        assert concepts[0].questions == qs

    def test_update_concept_can_set_questions(self, tmp_path):
        db = _make_db(tmp_path)
        c = _make_concept(db, questions=[])
        new_qs = ["What problem does this solve?", "Trade-offs?"]
        db.update_concept(c.id, questions=new_qs)
        fetched = db.get_concept(c.id)
        assert fetched.questions == new_qs


# ── Tool layer ────────────────────────────────────────────────────────────────

class TestCreateConceptToolQuestions:
    def test_tool_schema_includes_questions_field(self):
        from notemaster.tools import SYNTHESIS_TOOLS
        schema = next(
            t for t in SYNTHESIS_TOOLS if t["function"]["name"] == "create_concept"
        )
        assert "questions" in schema["function"]["parameters"]["properties"]

    def test_handle_create_concept_saves_questions(self, tmp_path):
        from notemaster.tools import ToolHandler
        db = _make_db(tmp_path)
        book = Book(id="b-1", title="DDIA", asset_id="a-1", synced_at=datetime.now())
        db.save_book(book)
        h = Highlight(id="h-1", text="text", color=HighlightColor.GREEN,
                      book_id="b-1", book_title="DDIA")
        db.save_highlight(h)

        handler = ToolHandler(db)
        qs = ["Explain fault tolerance.", "What's the difference between fault and failure?"]
        handler.dispatch("create_concept", {
            "title": "Fault Tolerance",
            "summary": "A summary.",
            "highlight_ids": ["h-1"],
            "book_id": "b-1",
            "questions": qs,
        })

        concepts = db.get_concepts()
        assert len(concepts) == 1
        assert concepts[0].questions == qs

    def test_handle_create_concept_without_questions_defaults_empty(self, tmp_path):
        from notemaster.tools import ToolHandler
        db = _make_db(tmp_path)
        book = Book(id="b-1", title="DDIA", asset_id="a-1", synced_at=datetime.now())
        db.save_book(book)
        h = Highlight(id="h-1", text="text", color=HighlightColor.GREEN,
                      book_id="b-1", book_title="DDIA")
        db.save_highlight(h)

        handler = ToolHandler(db)
        handler.dispatch("create_concept", {
            "title": "Fault Tolerance",
            "summary": "A summary.",
            "highlight_ids": ["h-1"],
            "book_id": "b-1",
        })

        concepts = db.get_concepts()
        assert concepts[0].questions == []


# ── API layer ─────────────────────────────────────────────────────────────────

class TestSessionNextReturnsQuestions:
    def test_session_next_includes_questions(self):
        from notemaster.main import app, get_db
        mock_db = MagicMock()
        now = datetime.now()
        concept = Concept(
            id="c-1", title="Fault Tolerance",
            summary="A summary.", book_id="b-1",
            highlight_ids=["h-1"], weight=1.0,
            questions=["What is fault tolerance?", "Explain faults vs failures."],
            created_at=now, updated_at=now,
        )
        from notemaster.models import ConceptWithPriority
        mock_db.get_due_concepts.return_value = [
            ConceptWithPriority(concept=concept, priority=1.0, days_overdue=0, last_mastery=None)
        ]
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            tc = TestClient(app)
            resp = tc.get("/session/next")
            assert resp.status_code == 200
            data = resp.json()
            assert "questions" in data
            assert data["questions"] == ["What is fault tolerance?", "Explain faults vs failures."]
        finally:
            app.dependency_overrides.clear()


# ── AI prompt smoke test ──────────────────────────────────────────────────────

class TestAiPhase1PromptIncludesQuestions:
    def test_phase1_system_prompt_asks_for_questions(self):
        from notemaster.ai import _PHASE1_SYSTEM
        assert "question" in _PHASE1_SYSTEM.lower()
