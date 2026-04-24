import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from notemaster.db import Database
from notemaster.models import Book


# ---------------------------------------------------------------------------
# DB: sync_log CRUD
# ---------------------------------------------------------------------------

@pytest.fixture
def db():
    return Database(":memory:")


@pytest.fixture
def book(db):
    b = Book(id="book-1", title="DDIA", asset_id="ASSET1", synced_at=datetime.now())
    db.save_book(b)
    return b


class TestSyncLogDb:
    def test_record_sync_creates_entry(self, db, book):
        db.record_sync(book.id, highlights_synced=20, sections=None)
        history = db.get_sync_history(book.id)
        assert len(history) == 1
        assert history[0]["book_id"] == "book-1"
        assert history[0]["highlights_synced"] == 20
        assert history[0]["sections"] is None

    def test_record_sync_with_sections(self, db, book):
        db.record_sync(book.id, highlights_synced=10, sections=["reliability", "introduction"])
        history = db.get_sync_history(book.id)
        assert history[0]["sections"] == ["reliability", "introduction"]

    def test_multiple_syncs_ordered_newest_first(self, db, book):
        db.record_sync(book.id, highlights_synced=10, sections=None)
        db.record_sync(book.id, highlights_synced=5, sections=["reliability"])
        history = db.get_sync_history(book.id)
        assert len(history) == 2
        assert history[0]["highlights_synced"] == 5  # newest first

    def test_get_all_sync_history_no_filter(self, db):
        b1 = Book(id="b1", title="DDIA", asset_id="A1", synced_at=datetime.now())
        b2 = Book(id="b2", title="SICP", asset_id="A2", synced_at=datetime.now())
        db.save_book(b1)
        db.save_book(b2)
        db.record_sync("b1", highlights_synced=10, sections=None)
        db.record_sync("b2", highlights_synced=5, sections=None)
        history = db.get_sync_history()
        assert len(history) == 2


# ---------------------------------------------------------------------------
# books.py: get_highlight_sections + section-filtered get_highlights
# ---------------------------------------------------------------------------

class TestGetHighlightSections:
    def test_returns_sections_with_counts(self):
        from notemaster import books as bks
        fake_locs = [
            ("epubcfi(/6/16[ch-1]!/4/2[sec_introduction]/2,/1:0,/2:5)",),
            ("epubcfi(/6/16[ch-1]!/4/2[sec_introduction]/4,/1:0,/2:5)",),
            ("epubcfi(/6/16[ch-1]!/4/2[sec_reliability]/2,/1:0,/2:5)",),
        ]
        with patch("sqlite3.connect") as mock_conn:
            mock_conn.return_value.execute.return_value.fetchall.return_value = fake_locs
            sections = bks.get_highlight_sections("ASSET1", db_path="/fake.sqlite")
        assert len(sections) == 2
        labels = {s["label"]: s["count"] for s in sections}
        assert labels["introduction"] == 2
        assert labels["reliability"] == 1

    def test_returns_empty_when_no_db(self):
        from notemaster import books as bks
        result = bks.get_highlight_sections("ASSET1", db_path=None)
        assert result == []

    def test_get_highlights_filtered_by_section(self):
        from notemaster import books as bks
        intro_loc = "epubcfi(/6/16[ch-1]!/4/2[sec_introduction]/2,/1:0,/2:5)"
        rel_loc = "epubcfi(/6/16[ch-1]!/4/2[sec_reliability]/2,/1:0,/2:5)"
        fake_rows = [
            ("uuid-1", "intro text", 1, intro_loc),
            ("uuid-2", "reliability text", 2, rel_loc),
        ]
        with patch("sqlite3.connect") as mock_conn:
            mock_conn.return_value.execute.return_value.fetchall.return_value = fake_rows
            result = bks.get_highlights(
                asset_id="ASSET1", book_id="b1", book_title="DDIA",
                db_path="/fake.sqlite", sections=["introduction"]
            )
        assert len(result) == 1
        assert result[0].text == "intro text"


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def make_db_mock():
    db = MagicMock()
    db.get_sync_history.return_value = [
        {"id": 1, "book_id": "book-1", "book_title": "DDIA",
         "highlights_synced": 20, "sections": None, "synced_at": "2026-04-23T10:00:00"},
    ]
    db.get_book_by_asset_id.return_value = None
    db.save_book.return_value = None
    db.get_highlights.return_value = []
    db.get_entries.return_value = []
    return db


@pytest.fixture
def client():
    from notemaster.main import app, get_db
    mock_db = make_db_mock()
    app.dependency_overrides[get_db] = lambda: mock_db
    yield TestClient(app), mock_db
    app.dependency_overrides.clear()


class TestSyncHistoryApi:
    def test_get_sync_history_for_book(self, client):
        tc, _ = client
        resp = tc.get("/sync/history?book_id=book-1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["highlights_synced"] == 20

    def test_get_sections_endpoint(self, client):
        tc, _ = client
        with patch("notemaster.books.get_highlight_sections", return_value=[
            {"section_id": "sec_introduction", "label": "introduction", "count": 22},
            {"section_id": "sec_reliability", "label": "reliability", "count": 62},
        ]):
            resp = tc.get("/apple-books/ASSET1/sections")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["label"] == "introduction"

    def test_sync_records_history(self, client):
        tc, mock_db = client
        with patch("notemaster.books.get_highlights", return_value=[]):
            resp = tc.post("/sync", json={"asset_id": "ASSET1", "book_title": "DDIA"})
        assert resp.status_code == 200
        mock_db.record_sync.assert_called_once()

    def test_sync_with_section_filter(self, client):
        tc, mock_db = client
        with patch("notemaster.books.get_highlights", return_value=[]) as mock_gh:
            resp = tc.post("/sync", json={
                "asset_id": "ASSET1",
                "book_title": "DDIA",
                "sections": ["reliability"],
            })
        assert resp.status_code == 200
