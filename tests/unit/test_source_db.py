"""Tests for Source CRUD in Database."""
import pytest
from datetime import datetime
from notemaster.models import Source, SourceType


@pytest.fixture
def db(tmp_path):
    from notemaster.db import Database
    return Database(tmp_path / "test.db")


def make_source(**kwargs):
    defaults = dict(
        id="s-1",
        title="Flink Guide",
        source_type=SourceType.URL,
        source_ref="https://flink.apache.org",
        content_cache=None,
        tags=[],
        created_at=datetime(2026, 4, 24),
    )
    return Source(**{**defaults, **kwargs})


class TestCreateSource:
    def test_create_returns_source(self, db):
        s = db.create_source(make_source())
        assert s.id == "s-1"
        assert s.title == "Flink Guide"

    def test_create_stores_tags(self, db):
        s = db.create_source(make_source(tags=["flink", "streaming"]))
        fetched = db.get_source("s-1")
        assert "flink" in fetched.tags

    def test_create_stores_content_cache(self, db):
        s = db.create_source(make_source(content_cache="cached content"))
        fetched = db.get_source("s-1")
        assert fetched.content_cache == "cached content"


class TestGetSource:
    def test_get_existing(self, db):
        db.create_source(make_source())
        s = db.get_source("s-1")
        assert s is not None
        assert s.title == "Flink Guide"

    def test_get_missing_returns_none(self, db):
        assert db.get_source("nonexistent") is None


class TestListSources:
    def test_empty_list(self, db):
        assert db.list_sources() == []

    def test_returns_all(self, db):
        db.create_source(make_source(id="s-1", title="A"))
        db.create_source(make_source(id="s-2", title="B"))
        assert len(db.list_sources()) == 2

    def test_ordered_newest_first(self, db):
        db.create_source(make_source(id="s-1", title="Old", created_at=datetime(2026, 1, 1)))
        db.create_source(make_source(id="s-2", title="New", created_at=datetime(2026, 4, 24)))
        sources = db.list_sources()
        assert sources[0].title == "New"


class TestDeleteSource:
    def test_delete_removes_source(self, db):
        db.create_source(make_source())
        db.delete_source("s-1")
        assert db.get_source("s-1") is None

    def test_delete_nonexistent_noop(self, db):
        db.delete_source("nonexistent")  # should not raise


class TestSourceQuestionLink:
    def test_questions_linked_to_source(self, db):
        from notemaster.models import InterviewQuestion, QuestionCategory
        db.create_source(make_source())
        q = InterviewQuestion(
            id="q-1", question="What is Flink?",
            category=QuestionCategory.STUDY,
            source_id="s-1",
            created_at=datetime(2026, 4, 24),
        )
        db.create_question(q)
        qs = db.get_questions_by_source("s-1")
        assert len(qs) == 1
        assert qs[0].id == "q-1"

    def test_get_questions_by_source_empty(self, db):
        db.create_source(make_source())
        assert db.get_questions_by_source("s-1") == []
