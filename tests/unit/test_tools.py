import pytest
from datetime import datetime
from notemaster.db import Database
from notemaster.models import Book, Highlight, HighlightColor, Concept, RelationType
from notemaster.tools import SYNTHESIS_TOOLS, REVIEW_TOOLS, ToolHandler


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db():
    return Database(":memory:")


@pytest.fixture
def populated_db(db):
    book = Book(id="book-1", title="DDIA", asset_id="asset-1",
                synced_at=datetime(2026, 4, 22))
    db.save_book(book)
    db.save_highlight(Highlight(id="h-green", text="A fault is a component deviation",
                                color=HighlightColor.GREEN, book_id="book-1", book_title="DDIA"))
    db.save_highlight(Highlight(id="h-yellow", text="reliability means continuing to work",
                                color=HighlightColor.YELLOW, book_id="book-1", book_title="DDIA"))
    return db


@pytest.fixture
def handler(populated_db):
    return ToolHandler(populated_db)


# ---------------------------------------------------------------------------
# Tool schema sanity checks
# ---------------------------------------------------------------------------

class TestToolSchemas:
    def test_synthesis_tools_are_valid(self):
        names = {t["function"]["name"] for t in SYNTHESIS_TOOLS}
        assert names == {"list_highlights", "list_concepts", "create_concept",
                         "update_concept", "link_concepts"}

    def test_review_tools_are_valid(self):
        names = {t["function"]["name"] for t in REVIEW_TOOLS}
        assert names == {"get_due_concepts", "get_concept", "record_review"}

    def test_each_tool_has_description(self):
        for tool in SYNTHESIS_TOOLS + REVIEW_TOOLS:
            assert tool["function"]["description"]

    def test_required_params_defined(self):
        create = next(t for t in SYNTHESIS_TOOLS if t["function"]["name"] == "create_concept")
        required = create["function"]["parameters"]["required"]
        assert set(required) == {"title", "summary", "highlight_ids", "book_id"}


# ---------------------------------------------------------------------------
# ToolHandler — synthesis tools
# ---------------------------------------------------------------------------

class TestListHighlights:
    def test_returns_all_highlights(self, handler):
        results = handler.dispatch("list_highlights", {"book_id": "book-1"})
        assert len(results) == 2

    def test_unprocessed_only(self, handler, populated_db):
        now = datetime(2026, 4, 22)
        concept = Concept(id="c-1", title="Fault", summary="...", book_id="book-1",
                          highlight_ids=["h-green"], weight=1.5, created_at=now, updated_at=now)
        populated_db.create_concept(concept)
        results = handler.dispatch("list_highlights",
                                   {"book_id": "book-1", "unprocessed_only": True})
        ids = {r["id"] for r in results}
        assert "h-green" not in ids
        assert "h-yellow" in ids


class TestCreateConcept:
    def test_creates_concept_with_correct_weight(self, handler):
        result = handler.dispatch("create_concept", {
            "title": "Fault",
            "summary": "A fault is a component deviation from its spec.",
            "highlight_ids": ["h-green"],
            "book_id": "book-1",
        })
        assert result["title"] == "Fault"
        # GREEN highlight → weight 1.5
        assert result["weight"] == pytest.approx(1.5)

    def test_multi_highlight_weight_sums(self, handler):
        result = handler.dispatch("create_concept", {
            "title": "Reliability",
            "summary": "Both concept and English dimension.",
            "highlight_ids": ["h-green", "h-yellow"],
            "book_id": "book-1",
        })
        # GREEN(1.5) + YELLOW(1.0)
        assert result["weight"] == pytest.approx(2.5)

    def test_concept_stored_in_db(self, handler, populated_db):
        handler.dispatch("create_concept", {
            "title": "Fault",
            "summary": "...",
            "highlight_ids": ["h-green"],
            "book_id": "book-1",
        })
        concepts = populated_db.get_concepts(book_id="book-1")
        assert len(concepts) == 1


class TestUpdateConcept:
    def _create(self, handler):
        return handler.dispatch("create_concept", {
            "title": "Fault",
            "summary": "Initial summary.",
            "highlight_ids": ["h-green"],
            "book_id": "book-1",
        })

    def test_update_summary(self, handler):
        created = self._create(handler)
        updated = handler.dispatch("update_concept", {
            "concept_id": created["id"],
            "summary": "Updated summary with more detail.",
        })
        assert updated["summary"] == "Updated summary with more detail."

    def test_add_highlight_recalculates_weight(self, handler):
        created = self._create(handler)
        updated = handler.dispatch("update_concept", {
            "concept_id": created["id"],
            "add_highlight_ids": ["h-yellow"],
        })
        # GREEN(1.5) + YELLOW(1.0) = 2.5
        assert updated["weight"] == pytest.approx(2.5)


class TestLinkConcepts:
    def _create_two(self, handler):
        c1 = handler.dispatch("create_concept", {
            "title": "Fault", "summary": "...",
            "highlight_ids": ["h-green"], "book_id": "book-1",
        })
        c2 = handler.dispatch("create_concept", {
            "title": "Failure", "summary": "...",
            "highlight_ids": ["h-yellow"], "book_id": "book-1",
        })
        return c1, c2

    def test_creates_edge(self, handler, populated_db):
        c1, c2 = self._create_two(handler)
        handler.dispatch("link_concepts", {
            "from_concept_id": c1["id"],
            "to_concept_id": c2["id"],
            "relation": "depends_on",
        })
        edges = populated_db.get_edges()
        assert len(edges) == 1
        assert edges[0].relation == RelationType.DEPENDS_ON

    def test_invalid_relation_raises(self, handler):
        c1, c2 = self._create_two(handler)
        with pytest.raises(Exception):
            handler.dispatch("link_concepts", {
                "from_concept_id": c1["id"],
                "to_concept_id": c2["id"],
                "relation": "invented_relation",
            })


# ---------------------------------------------------------------------------
# ToolHandler — review tools
# ---------------------------------------------------------------------------

class TestGetDueConcepts:
    def test_returns_unreviewed_concepts(self, handler):
        handler.dispatch("create_concept", {
            "title": "Fault", "summary": "...",
            "highlight_ids": ["h-green"], "book_id": "book-1",
        })
        results = handler.dispatch("get_due_concepts", {})
        assert len(results) == 1
        assert results[0]["last_mastery"] is None

    def test_higher_weight_comes_first(self, handler):
        handler.dispatch("create_concept", {
            "title": "Light", "summary": "...",
            "highlight_ids": ["h-yellow"], "book_id": "book-1",
        })
        handler.dispatch("create_concept", {
            "title": "Heavy", "summary": "...",
            "highlight_ids": ["h-green"], "book_id": "book-1",
        })
        results = handler.dispatch("get_due_concepts", {})
        # GREEN weight(1.5) > YELLOW weight(1.0)
        assert results[0]["concept"]["title"] == "Heavy"


class TestGetConcept:
    def test_returns_full_concept_with_highlights(self, handler):
        created = handler.dispatch("create_concept", {
            "title": "Fault", "summary": "...",
            "highlight_ids": ["h-green"], "book_id": "book-1",
        })
        result = handler.dispatch("get_concept", {"concept_id": created["id"]})
        assert result["title"] == "Fault"
        assert len(result["highlights"]) == 1
        assert result["highlights"][0]["id"] == "h-green"

    def test_returns_none_for_unknown(self, handler):
        result = handler.dispatch("get_concept", {"concept_id": "nonexistent"})
        assert result is None


class TestRecordReview:
    def test_updates_weight_on_high_mastery(self, handler):
        created = handler.dispatch("create_concept", {
            "title": "Fault", "summary": "...",
            "highlight_ids": ["h-green"], "book_id": "book-1",
        })
        original_weight = created["weight"]
        result = handler.dispatch("record_review", {
            "concept_id": created["id"],
            "mastery_score": 5,
        })
        assert result["new_weight"] < original_weight

    def test_updates_weight_on_low_mastery(self, handler):
        created = handler.dispatch("create_concept", {
            "title": "Fault", "summary": "...",
            "highlight_ids": ["h-green"], "book_id": "book-1",
        })
        original_weight = created["weight"]
        result = handler.dispatch("record_review", {
            "concept_id": created["id"],
            "mastery_score": 1,
        })
        assert result["new_weight"] > original_weight

    def test_returns_next_review_time(self, handler):
        created = handler.dispatch("create_concept", {
            "title": "Fault", "summary": "...",
            "highlight_ids": ["h-green"], "book_id": "book-1",
        })
        result = handler.dispatch("record_review", {
            "concept_id": created["id"],
            "mastery_score": 3,
        })
        assert "next_review_at" in result

    def test_unknown_tool_raises(self, handler):
        with pytest.raises(ValueError, match="Unknown tool"):
            handler.dispatch("nonexistent_tool", {})
