import pytest
from datetime import datetime
from notemaster.db import Database
from notemaster.models import InboxItem


@pytest.fixture
def db():
    return Database(":memory:")


def make_item(id="i-1", content="granularity", tags=None):
    now = datetime(2026, 4, 24, 10, 0)
    return InboxItem(id=id, content=content, tags=tags or [], created_at=now)


class TestInboxSchema:
    def test_table_exists(self, db):
        tables = {r[0] for r in db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "inbox_items" in tables

    def test_columns(self, db):
        cols = {r[1] for r in db.conn.execute("PRAGMA table_info(inbox_items)")}
        for col in ("id", "content", "tags", "created_at", "processed_at"):
            assert col in cols


class TestCreateInboxItem:
    def test_create_and_retrieve(self, db):
        db.create_inbox_item(make_item())
        found = db.get_inbox_item("i-1")
        assert found is not None
        assert found.content == "granularity"
        assert found.tags == []
        assert found.processed_at is None

    def test_create_with_tags(self, db):
        db.create_inbox_item(make_item(tags=["english", "work"]))
        found = db.get_inbox_item("i-1")
        assert found.tags == ["english", "work"]

    def test_returns_none_for_unknown(self, db):
        assert db.get_inbox_item("nope") is None


class TestListInboxItems:
    def test_list_all(self, db):
        db.create_inbox_item(make_item("i-1"))
        db.create_inbox_item(make_item("i-2", "bootstrap"))
        assert len(db.get_inbox_items()) == 2

    def test_list_pending_only(self, db):
        db.create_inbox_item(make_item("i-1"))
        db.create_inbox_item(make_item("i-2", "bootstrap"))
        db.mark_inbox_processed("i-1")
        pending = db.get_inbox_items(pending_only=True)
        assert len(pending) == 1
        assert pending[0].id == "i-2"

    def test_empty_returns_empty_list(self, db):
        assert db.get_inbox_items() == []

    def test_ordered_newest_first(self, db):
        from datetime import timedelta
        now = datetime(2026, 4, 24, 10, 0)
        early = InboxItem(id="i-1", content="first", created_at=now)
        late = InboxItem(id="i-2", content="second", created_at=now + timedelta(hours=1))
        db.create_inbox_item(early)
        db.create_inbox_item(late)
        items = db.get_inbox_items()
        assert items[0].id == "i-2"


class TestUpdateInboxItem:
    def test_update_tags(self, db):
        db.create_inbox_item(make_item())
        updated = db.update_inbox_item("i-1", tags=["english"])
        assert updated.tags == ["english"]

    def test_update_content(self, db):
        db.create_inbox_item(make_item())
        updated = db.update_inbox_item("i-1", content="new content")
        assert updated.content == "new content"

    def test_returns_none_for_unknown(self, db):
        assert db.update_inbox_item("nope", tags=[]) is None


class TestMarkProcessed:
    def test_mark_processed_sets_timestamp(self, db):
        db.create_inbox_item(make_item())
        db.mark_inbox_processed("i-1")
        found = db.get_inbox_item("i-1")
        assert found.processed_at is not None
        assert found.is_pending is False

    def test_mark_processed_unknown_is_noop(self, db):
        db.mark_inbox_processed("nope")  # should not raise


class TestDeleteInboxItem:
    def test_delete_removes_item(self, db):
        db.create_inbox_item(make_item())
        db.delete_inbox_item("i-1")
        assert db.get_inbox_item("i-1") is None

    def test_delete_returns_true_on_success(self, db):
        db.create_inbox_item(make_item())
        assert db.delete_inbox_item("i-1") is True

    def test_delete_returns_false_for_unknown(self, db):
        assert db.delete_inbox_item("nope") is False


class TestPendingCount:
    def test_returns_count(self, db):
        db.create_inbox_item(make_item("i-1"))
        db.create_inbox_item(make_item("i-2", "b"))
        db.mark_inbox_processed("i-1")
        assert db.get_inbox_pending_count() == 1

    def test_zero_when_empty(self, db):
        assert db.get_inbox_pending_count() == 0
