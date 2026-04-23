import pytest
from datetime import datetime, timedelta, date
from notemaster.db import Database
from notemaster.models import Entry, EntryType, EntryReviewRecord


@pytest.fixture
def db():
    return Database(":memory:")


def make_entry(id="entry-1", text="hit the ground running", weight=1.0):
    now = datetime(2026, 4, 23, 10, 0)
    return Entry(
        id=id,
        text=text,
        source_type=EntryType.MANUAL,
        source_ref=None,
        phonetics=None,
        examples=[],
        context_note=None,
        weight=weight,
        created_at=now,
        updated_at=now,
    )


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

class TestEntrySchema:
    def test_entries_table_exists(self, db):
        tables = {
            row[0]
            for row in db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "entries" in tables

    def test_entry_review_records_table_exists(self, db):
        tables = {
            row[0]
            for row in db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "entry_review_records" in tables


# ---------------------------------------------------------------------------
# Create / Get
# ---------------------------------------------------------------------------

class TestCreateEntry:
    def test_create_and_retrieve(self, db):
        entry = make_entry()
        db.create_entry(entry)
        found = db.get_entry("entry-1")
        assert found is not None
        assert found.text == "hit the ground running"
        assert found.source_type == EntryType.MANUAL

    def test_returns_none_for_unknown(self, db):
        assert db.get_entry("nonexistent") is None

    def test_create_with_source_ref(self, db):
        entry = make_entry()
        entry = entry.model_copy(update={"source_ref": "DDIA", "source_type": EntryType.HIGHLIGHT})
        db.create_entry(entry)
        found = db.get_entry("entry-1")
        assert found.source_ref == "DDIA"
        assert found.source_type == EntryType.HIGHLIGHT

    def test_create_with_phonetics_and_examples(self, db):
        entry = make_entry()
        entry = entry.model_copy(update={
            "phonetics": "/hɪt ðə ɡraʊnd ˈrʌnɪŋ/",
            "examples": ["She hit the ground running on her first day."],
        })
        db.create_entry(entry)
        found = db.get_entry("entry-1")
        assert found.phonetics == "/hɪt ðə ɡraʊnd ˈrʌnɪŋ/"
        assert len(found.examples) == 1


# ---------------------------------------------------------------------------
# Get entries (list)
# ---------------------------------------------------------------------------

class TestGetEntries:
    def test_returns_all_entries(self, db):
        db.create_entry(make_entry("e-1", "phrase one"))
        db.create_entry(make_entry("e-2", "phrase two"))
        assert len(db.get_entries()) == 2

    def test_filter_by_source_type(self, db):
        manual = make_entry("e-1", "manual phrase")
        highlight = make_entry("e-2", "highlight phrase")
        highlight = highlight.model_copy(update={"source_type": EntryType.HIGHLIGHT})
        db.create_entry(manual)
        db.create_entry(highlight)
        results = db.get_entries(source_type=EntryType.MANUAL)
        assert len(results) == 1
        assert results[0].id == "e-1"

    def test_returns_empty_list_when_none(self, db):
        assert db.get_entries() == []


# ---------------------------------------------------------------------------
# Update entry
# ---------------------------------------------------------------------------

class TestUpdateEntry:
    def test_update_phonetics(self, db):
        db.create_entry(make_entry())
        updated = db.update_entry("entry-1", phonetics="/hɪt/")
        assert updated.phonetics == "/hɪt/"

    def test_update_examples(self, db):
        db.create_entry(make_entry())
        updated = db.update_entry("entry-1", examples=["Example one.", "Example two."])
        assert len(updated.examples) == 2

    def test_update_context_note(self, db):
        db.create_entry(make_entry())
        updated = db.update_entry("entry-1", context_note="idiom — start productively")
        assert updated.context_note == "idiom — start productively"

    def test_update_text(self, db):
        db.create_entry(make_entry())
        updated = db.update_entry("entry-1", text="get off to a flying start")
        assert updated.text == "get off to a flying start"

    def test_returns_none_for_unknown(self, db):
        assert db.update_entry("nonexistent", text="x") is None

    def test_updated_at_changes(self, db):
        db.create_entry(make_entry())
        original = db.get_entry("entry-1")
        updated = db.update_entry("entry-1", text="new text")
        assert updated.updated_at >= original.updated_at


# ---------------------------------------------------------------------------
# Entry reviews (SM-2)
# ---------------------------------------------------------------------------

class TestEntryReviews:
    def test_record_review_returns_record(self, db):
        db.create_entry(make_entry())
        record = db.record_entry_review("entry-1", mastery_score=3)
        assert isinstance(record, EntryReviewRecord)
        assert record.entry_id == "entry-1"
        assert record.mastery_score == 3
        assert record.next_review_at > record.reviewed_at

    def test_low_mastery_increases_weight(self, db):
        db.create_entry(make_entry(weight=1.0))
        db.record_entry_review("entry-1", mastery_score=1)
        entry = db.get_entry("entry-1")
        assert entry.weight > 1.0

    def test_high_mastery_decreases_weight(self, db):
        db.create_entry(make_entry(weight=1.0))
        db.record_entry_review("entry-1", mastery_score=5)
        entry = db.get_entry("entry-1")
        assert entry.weight < 1.0

    def test_mastery_3_keeps_weight(self, db):
        db.create_entry(make_entry(weight=1.0))
        db.record_entry_review("entry-1", mastery_score=3)
        entry = db.get_entry("entry-1")
        assert entry.weight == pytest.approx(1.0)

    def test_due_entries_includes_never_reviewed(self, db):
        db.create_entry(make_entry())
        due = db.get_due_entries()
        assert len(due) == 1
        assert due[0].last_mastery is None

    def test_due_entries_excludes_future_reviews(self, db):
        db.create_entry(make_entry())
        db.record_entry_review("entry-1", mastery_score=5)
        due = db.get_due_entries()
        assert len(due) == 0

    def test_due_entries_sorted_by_priority(self, db):
        now = datetime(2026, 4, 23, 10, 0)
        heavy = make_entry("e-heavy", "hard phrase", weight=3.0)
        light = make_entry("e-light", "easy phrase", weight=0.5)
        db.create_entry(heavy)
        db.create_entry(light)
        due = db.get_due_entries()
        assert due[0].entry.id == "e-heavy"

    def test_record_review_raises_for_unknown_entry(self, db):
        with pytest.raises(ValueError):
            db.record_entry_review("nonexistent", mastery_score=3)
