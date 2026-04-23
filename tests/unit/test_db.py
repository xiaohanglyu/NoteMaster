import pytest
from datetime import datetime, date, timedelta
from notemaster.db import Database, _initial_weight, _update_weight, _sm2_interval
from notemaster.models import (
    Book, Highlight, HighlightColor, Concept, ConceptEdge, RelationType, StudySession,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db():
    return Database(":memory:")


@pytest.fixture
def book():
    return Book(
        id="book-1",
        title="Designing Data-Intensive Applications",
        asset_id="asset-abc",
        synced_at=datetime(2026, 4, 22, 10, 0),
    )


@pytest.fixture
def green_highlight(book):
    return Highlight(
        id="h-green",
        text="A fault is one component deviating from its spec",
        color=HighlightColor.GREEN,
        book_id=book.id,
        book_title=book.title,
    )


@pytest.fixture
def yellow_highlight(book):
    return Highlight(
        id="h-yellow",
        text="reliability means the system continues to work",
        color=HighlightColor.YELLOW,
        book_id=book.id,
        book_title=book.title,
    )


def make_concept(book_id: str, highlight_ids: list[str], weight: float = 1.5) -> Concept:
    now = datetime(2026, 4, 22, 10, 0)
    return Concept(
        id="concept-1",
        title="Fault vs Failure",
        summary="A fault is a component deviation; a failure is when the system stops providing service.",
        book_id=book_id,
        highlight_ids=highlight_ids,
        weight=weight,
        created_at=now,
        updated_at=now,
    )


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

class TestSchema:
    def test_all_tables_created(self, db):
        tables = {
            row[0]
            for row in db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert {"books", "highlights", "concepts", "concept_highlights",
                "concept_edges", "review_records", "study_sessions"}.issubset(tables)


# ---------------------------------------------------------------------------
# Books
# ---------------------------------------------------------------------------

class TestBooks:
    def test_save_and_retrieve_by_asset_id(self, db, book):
        db.save_book(book)
        found = db.get_book_by_asset_id("asset-abc")
        assert found is not None
        assert found.id == "book-1"
        assert found.title == "Designing Data-Intensive Applications"

    def test_returns_none_for_unknown_asset_id(self, db):
        assert db.get_book_by_asset_id("nonexistent") is None

    def test_save_is_idempotent(self, db, book):
        db.save_book(book)
        db.save_book(book)
        assert len(db.get_books()) == 1

    def test_get_books_lists_all(self, db, book):
        db.save_book(book)
        books = db.get_books()
        assert len(books) == 1
        assert books[0].asset_id == "asset-abc"


# ---------------------------------------------------------------------------
# Highlights
# ---------------------------------------------------------------------------

class TestHighlights:
    def test_save_and_retrieve(self, db, book, green_highlight):
        db.save_book(book)
        db.save_highlight(green_highlight)
        results = db.get_highlights(book_id="book-1")
        assert len(results) == 1
        assert results[0].id == "h-green"

    def test_save_is_idempotent(self, db, book, green_highlight):
        db.save_book(book)
        db.save_highlight(green_highlight)
        db.save_highlight(green_highlight)
        assert len(db.get_highlights(book_id="book-1")) == 1

    def test_unprocessed_only_excludes_assigned(self, db, book, green_highlight, yellow_highlight):
        db.save_book(book)
        db.save_highlight(green_highlight)
        db.save_highlight(yellow_highlight)
        concept = make_concept("book-1", ["h-green"])
        db.create_concept(concept)
        unprocessed = db.get_highlights(book_id="book-1", unprocessed_only=True)
        ids = {h.id for h in unprocessed}
        assert "h-green" not in ids
        assert "h-yellow" in ids

    def test_unprocessed_only_includes_all_when_none_assigned(self, db, book, green_highlight):
        db.save_book(book)
        db.save_highlight(green_highlight)
        assert len(db.get_highlights(book_id="book-1", unprocessed_only=True)) == 1


# ---------------------------------------------------------------------------
# Weight helpers
# ---------------------------------------------------------------------------

class TestWeightHelpers:
    def test_initial_weight_sums_color_factors(self):
        assert _initial_weight(["green", "yellow"]) == pytest.approx(1.5 + 1.0)

    def test_initial_weight_all_green(self):
        assert _initial_weight(["green", "green"]) == pytest.approx(3.0)

    def test_initial_weight_floor(self):
        assert _initial_weight([]) == pytest.approx(0.1)

    def test_update_weight_low_mastery_increases(self):
        assert _update_weight(1.0, 1) > 1.0

    def test_update_weight_high_mastery_decreases(self):
        assert _update_weight(1.0, 5) < 1.0

    def test_update_weight_mastery_3_unchanged(self):
        assert _update_weight(1.5, 3) == pytest.approx(1.5)

    def test_update_weight_floor_respected(self):
        assert _update_weight(0.1, 5) == pytest.approx(0.1)

    def test_sm2_interval_high_weight_shorter(self):
        interval_low = _sm2_interval(3, 0.5)
        interval_high = _sm2_interval(3, 2.0)
        assert interval_high < interval_low


# ---------------------------------------------------------------------------
# Concepts
# ---------------------------------------------------------------------------

class TestConcepts:
    def test_create_and_retrieve(self, db, book, green_highlight):
        db.save_book(book)
        db.save_highlight(green_highlight)
        concept = make_concept("book-1", ["h-green"])
        db.create_concept(concept)
        found = db.get_concept("concept-1")
        assert found is not None
        assert found.title == "Fault vs Failure"
        assert "h-green" in found.highlight_ids

    def test_get_concepts_by_book(self, db, book, green_highlight):
        db.save_book(book)
        db.save_highlight(green_highlight)
        db.create_concept(make_concept("book-1", ["h-green"]))
        concepts = db.get_concepts(book_id="book-1")
        assert len(concepts) == 1

    def test_update_concept_title(self, db, book, green_highlight):
        db.save_book(book)
        db.save_highlight(green_highlight)
        db.create_concept(make_concept("book-1", ["h-green"]))
        updated = db.update_concept("concept-1", title="Faults and Failures")
        assert updated.title == "Faults and Failures"

    def test_update_concept_adds_highlight_and_recalculates_weight(
        self, db, book, green_highlight, yellow_highlight
    ):
        db.save_book(book)
        db.save_highlight(green_highlight)
        db.save_highlight(yellow_highlight)
        concept = make_concept("book-1", ["h-green"], weight=1.5)
        db.create_concept(concept)
        updated = db.update_concept("concept-1", add_highlight_ids=["h-yellow"])
        assert "h-yellow" in updated.highlight_ids
        # GREEN(1.5) + YELLOW(1.0) = 2.5
        assert updated.weight == pytest.approx(2.5)

    def test_returns_none_for_unknown_concept(self, db):
        assert db.get_concept("nonexistent") is None


# ---------------------------------------------------------------------------
# Edges
# ---------------------------------------------------------------------------

class TestEdges:
    def _setup(self, db, book, green_highlight, yellow_highlight):
        db.save_book(book)
        db.save_highlight(green_highlight)
        db.save_highlight(yellow_highlight)
        now = datetime(2026, 4, 22)
        c1 = Concept(id="c1", title="Fault", summary="...", book_id="book-1",
                     highlight_ids=["h-green"], weight=1.5, created_at=now, updated_at=now)
        c2 = Concept(id="c2", title="Failure", summary="...", book_id="book-1",
                     highlight_ids=["h-yellow"], weight=1.0, created_at=now, updated_at=now)
        db.create_concept(c1)
        db.create_concept(c2)
        return c1, c2

    def test_create_and_retrieve_edge(self, db, book, green_highlight, yellow_highlight):
        c1, c2 = self._setup(db, book, green_highlight, yellow_highlight)
        edge = ConceptEdge(from_concept_id="c1", to_concept_id="c2",
                           relation=RelationType.DEPENDS_ON)
        db.create_edge(edge)
        edges = db.get_edges()
        assert len(edges) == 1
        assert edges[0].relation == RelationType.DEPENDS_ON

    def test_get_edges_for_specific_concept(self, db, book, green_highlight, yellow_highlight):
        c1, c2 = self._setup(db, book, green_highlight, yellow_highlight)
        db.create_edge(ConceptEdge(from_concept_id="c1", to_concept_id="c2",
                                   relation=RelationType.PART_OF))
        edges = db.get_edges(concept_id="c1")
        assert len(edges) == 1

    def test_upsert_edge_updates_relation(self, db, book, green_highlight, yellow_highlight):
        self._setup(db, book, green_highlight, yellow_highlight)
        db.create_edge(ConceptEdge(from_concept_id="c1", to_concept_id="c2",
                                   relation=RelationType.DEPENDS_ON))
        db.create_edge(ConceptEdge(from_concept_id="c1", to_concept_id="c2",
                                   relation=RelationType.CONTRASTS_WITH))
        edges = db.get_edges()
        assert len(edges) == 1
        assert edges[0].relation == RelationType.CONTRASTS_WITH


# ---------------------------------------------------------------------------
# Concept reviews
# ---------------------------------------------------------------------------

class TestConceptReviews:
    def _create_concept(self, db, book, green_highlight, weight=1.5):
        db.save_book(book)
        db.save_highlight(green_highlight)
        db.create_concept(make_concept("book-1", ["h-green"], weight=weight))

    def test_record_review_returns_record(self, db, book, green_highlight):
        self._create_concept(db, book, green_highlight)
        record = db.record_review("concept-1", mastery_score=3)
        assert record.concept_id == "concept-1"
        assert record.mastery_score == 3
        assert record.next_review_at > record.reviewed_at

    def test_low_mastery_increases_weight(self, db, book, green_highlight):
        self._create_concept(db, book, green_highlight, weight=1.0)
        db.record_review("concept-1", mastery_score=1)
        concept = db.get_concept("concept-1")
        assert concept.weight > 1.0

    def test_high_mastery_decreases_weight(self, db, book, green_highlight):
        self._create_concept(db, book, green_highlight, weight=1.5)
        db.record_review("concept-1", mastery_score=5)
        concept = db.get_concept("concept-1")
        assert concept.weight < 1.5

    def test_due_concepts_includes_never_reviewed(self, db, book, green_highlight):
        self._create_concept(db, book, green_highlight)
        due = db.get_due_concepts()
        assert len(due) == 1
        assert due[0].last_mastery is None

    def test_due_concepts_sorted_by_priority(self, db, book, green_highlight, yellow_highlight):
        db.save_book(book)
        db.save_highlight(green_highlight)
        db.save_highlight(yellow_highlight)
        now = datetime(2026, 4, 22)
        heavy = Concept(id="c-heavy", title="Heavy", summary="...", book_id="book-1",
                        highlight_ids=["h-green"], weight=3.0, created_at=now, updated_at=now)
        light = Concept(id="c-light", title="Light", summary="...", book_id="book-1",
                        highlight_ids=["h-yellow"], weight=0.5, created_at=now, updated_at=now)
        db.create_concept(heavy)
        db.create_concept(light)
        due = db.get_due_concepts()
        assert due[0].concept.id == "c-heavy"


# ---------------------------------------------------------------------------
# Study sessions
# ---------------------------------------------------------------------------

class TestStudySessions:
    def test_save_and_retrieve(self, db):
        db.save_study_session(StudySession(
            date=date.today(), duration_minutes=10, items_reviewed=5, quiz_score=0.8,
        ))
        assert len(db.get_study_sessions()) == 1

    def test_streak_single_day(self, db):
        db.save_study_session(StudySession(
            date=date.today(), duration_minutes=10, items_reviewed=5, quiz_score=0.8,
        ))
        assert db.get_streak() == 1

    def test_streak_consecutive_days(self, db):
        for days_ago in range(3):
            db.save_study_session(StudySession(
                date=date.today() - timedelta(days=days_ago),
                duration_minutes=10, items_reviewed=5, quiz_score=0.8,
            ))
        assert db.get_streak() == 3

    def test_streak_broken(self, db):
        db.save_study_session(StudySession(
            date=date.today(), duration_minutes=10, items_reviewed=5, quiz_score=0.8,
        ))
        db.save_study_session(StudySession(
            date=date.today() - timedelta(days=2),
            duration_minutes=10, items_reviewed=5, quiz_score=0.8,
        ))
        assert db.get_streak() == 1

    def test_streak_zero_when_no_sessions(self, db):
        assert db.get_streak() == 0

    def test_heatmap_includes_today(self, db):
        db.save_study_session(StudySession(
            date=date.today(), duration_minutes=10, items_reviewed=5, quiz_score=0.8,
        ))
        heatmap = db.get_heatmap()
        assert date.today().isoformat() in heatmap
