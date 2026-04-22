import pytest
from datetime import datetime, date, timedelta
from notemaster.db import Database
from notemaster.models import Highlight, HighlightColor, StudySession


@pytest.fixture
def db():
    """In-memory database, fresh for each test."""
    return Database(":memory:")


@pytest.fixture
def sample_highlight():
    return Highlight(
        id="uuid-1",
        text="A fault is defined as one component deviating from its spec",
        color=HighlightColor.GREEN,
        book_title="Designing Data-Intensive Applications",
    )


@pytest.fixture
def another_highlight():
    return Highlight(
        id="uuid-2",
        text="reliability means the system should continue to work correctly",
        color=HighlightColor.YELLOW,
        book_title="Designing Data-Intensive Applications",
    )


# --- Schema ---

class TestSchema:
    def test_tables_created_on_init(self, db):
        tables = {
            row[0]
            for row in db.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert {"highlights", "review_records", "study_sessions"}.issubset(tables)


# --- Highlights ---

class TestHighlights:
    def test_save_and_retrieve(self, db, sample_highlight):
        db.save_highlight(sample_highlight)
        results = db.get_highlights()
        assert len(results) == 1
        assert results[0].id == "uuid-1"

    def test_save_is_idempotent(self, db, sample_highlight):
        db.save_highlight(sample_highlight)
        db.save_highlight(sample_highlight)
        assert len(db.get_highlights()) == 1

    def test_get_highlights_by_color(self, db, sample_highlight, another_highlight):
        db.save_highlight(sample_highlight)
        db.save_highlight(another_highlight)
        green = db.get_highlights(color=HighlightColor.GREEN)
        assert len(green) == 1
        assert green[0].id == "uuid-1"

    def test_get_all_highlights_no_filter(self, db, sample_highlight, another_highlight):
        db.save_highlight(sample_highlight)
        db.save_highlight(another_highlight)
        assert len(db.get_highlights()) == 2


# --- Review Records ---

class TestReviewRecords:
    def test_save_and_retrieve(self, db, sample_highlight):
        db.save_highlight(sample_highlight)
        db.save_review_record(highlight_id="uuid-1", mastery_score=3)
        record = db.get_review_record("uuid-1")
        assert record is not None
        assert record.mastery_score == 3

    def test_update_mastery_score(self, db, sample_highlight):
        db.save_highlight(sample_highlight)
        db.save_review_record(highlight_id="uuid-1", mastery_score=2)
        db.save_review_record(highlight_id="uuid-1", mastery_score=4)
        record = db.get_review_record("uuid-1")
        assert record.mastery_score == 4

    def test_returns_none_for_unreviewed(self, db, sample_highlight):
        db.save_highlight(sample_highlight)
        assert db.get_review_record("uuid-1") is None

    def test_get_due_highlights_includes_never_reviewed(self, db, sample_highlight, another_highlight):
        db.save_highlight(sample_highlight)
        db.save_highlight(another_highlight)
        due = db.get_due_highlights()
        assert len(due) == 2

    def test_get_due_highlights_excludes_future(self, db, sample_highlight):
        db.save_highlight(sample_highlight)
        future = datetime.now() + timedelta(days=7)
        db.save_review_record(highlight_id="uuid-1", mastery_score=4, next_review_at=future)
        due = db.get_due_highlights()
        assert len(due) == 0

    def test_get_due_highlights_includes_past(self, db, sample_highlight):
        db.save_highlight(sample_highlight)
        past = datetime.now() - timedelta(days=1)
        db.save_review_record(highlight_id="uuid-1", mastery_score=2, next_review_at=past)
        due = db.get_due_highlights()
        assert len(due) == 1


# --- Study Sessions ---

class TestStudySessions:
    def test_save_session(self, db):
        db.save_study_session(StudySession(
            date=date.today(),
            duration_minutes=10,
            items_reviewed=5,
            quiz_score=0.8,
        ))
        sessions = db.get_study_sessions()
        assert len(sessions) == 1

    def test_streak_single_day(self, db):
        db.save_study_session(StudySession(
            date=date.today(),
            duration_minutes=10,
            items_reviewed=5,
            quiz_score=0.8,
        ))
        assert db.get_streak() == 1

    def test_streak_consecutive_days(self, db):
        for days_ago in range(3):
            db.save_study_session(StudySession(
                date=date.today() - timedelta(days=days_ago),
                duration_minutes=10,
                items_reviewed=5,
                quiz_score=0.8,
            ))
        assert db.get_streak() == 3

    def test_streak_broken(self, db):
        db.save_study_session(StudySession(
            date=date.today(),
            duration_minutes=10,
            items_reviewed=5,
            quiz_score=0.8,
        ))
        db.save_study_session(StudySession(
            date=date.today() - timedelta(days=2),
            duration_minutes=10,
            items_reviewed=5,
            quiz_score=0.8,
        ))
        assert db.get_streak() == 1

    def test_streak_zero_when_no_sessions(self, db):
        assert db.get_streak() == 0

    def test_heatmap_returns_last_365_days(self, db):
        db.save_study_session(StudySession(
            date=date.today(),
            duration_minutes=10,
            items_reviewed=5,
            quiz_score=0.8,
        ))
        heatmap = db.get_heatmap()
        assert date.today().isoformat() in heatmap
        assert heatmap[date.today().isoformat()] == 1
