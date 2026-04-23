import pytest
from pathlib import Path
from notemaster.models import HighlightColor
from notemaster.books import get_highlights, find_annotation_db

FIXTURE_DB = Path(__file__).parent.parent / "fixtures" / "test_books.sqlite"


class TestGetHighlights:
    def test_returns_non_deleted_highlights(self):
        highlights = get_highlights(
            asset_id="asset-ddia", book_id="book-1", book_title="DDIA", db_path=FIXTURE_DB
        )
        ids = [h.id for h in highlights]
        assert "uuid-4" not in ids  # deleted

    def test_filters_by_asset_id(self):
        highlights = get_highlights(
            asset_id="asset-ddia", book_id="book-1", book_title="DDIA", db_path=FIXTURE_DB
        )
        assert all(h.book_title == "DDIA" for h in highlights)
        assert len(highlights) == 3

    def test_excludes_other_books(self):
        highlights = get_highlights(
            asset_id="asset-ddia", book_id="book-1", book_title="DDIA", db_path=FIXTURE_DB
        )
        ids = [h.id for h in highlights]
        assert "uuid-5" not in ids

    def test_yellow_color_mapping(self):
        highlights = get_highlights(
            asset_id="asset-ddia", book_id="book-1", book_title="DDIA", db_path=FIXTURE_DB
        )
        yellow = next(h for h in highlights if h.id == "uuid-1")
        assert yellow.color == HighlightColor.YELLOW

    def test_green_color_mapping(self):
        highlights = get_highlights(
            asset_id="asset-ddia", book_id="book-1", book_title="DDIA", db_path=FIXTURE_DB
        )
        green = next(h for h in highlights if h.id == "uuid-2")
        assert green.color == HighlightColor.GREEN

    def test_blue_color_mapping(self):
        highlights = get_highlights(
            asset_id="asset-ddia", book_id="book-1", book_title="DDIA", db_path=FIXTURE_DB
        )
        blue = next(h for h in highlights if h.id == "uuid-3")
        assert blue.color == HighlightColor.BLUE

    def test_book_id_is_set(self):
        highlights = get_highlights(
            asset_id="asset-ddia", book_id="book-1", book_title="DDIA", db_path=FIXTURE_DB
        )
        assert all(h.book_id == "book-1" for h in highlights)

    def test_highlight_text_is_preserved(self):
        highlights = get_highlights(
            asset_id="asset-ddia", book_id="book-1", book_title="DDIA", db_path=FIXTURE_DB
        )
        yellow = next(h for h in highlights if h.id == "uuid-1")
        assert "reliability" in yellow.text

    def test_empty_result_for_unknown_asset(self):
        highlights = get_highlights(
            asset_id="asset-unknown", book_id="book-1", book_title="DDIA", db_path=FIXTURE_DB
        )
        assert highlights == []


class TestFindAnnotationDb:
    def test_returns_path(self):
        path = find_annotation_db()
        assert path is None or path.exists()

    def test_returns_sqlite_file(self):
        path = find_annotation_db()
        if path is not None:
            assert path.suffix == ".sqlite"
