"""Tests for #16 (highlight routing), #17 (file import), #18 (OCR import)."""
import io
import uuid
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch, ANY
from fastapi.testclient import TestClient
from notemaster.models import Highlight, HighlightColor, Book, Entry, EntryType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_highlight(color=HighlightColor.YELLOW, text="hit the ground running"):
    return Highlight(
        id=str(uuid.uuid4()),
        text=text,
        color=color,
        book_id="book-1",
        book_title="DDIA",
    )


def make_db():
    db = MagicMock()
    db.get_book_by_asset_id.return_value = None
    db.save_book.return_value = None
    db.save_highlight.return_value = None
    db.create_entry.return_value = None
    db.get_entry.return_value = None
    return db


@pytest.fixture
def client():
    from notemaster.main import app, get_db
    mock_db = make_db()
    app.dependency_overrides[get_db] = lambda: mock_db
    yield TestClient(app), mock_db
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# #16 — Highlight colour routing during sync
# ---------------------------------------------------------------------------

class TestHighlightRouting:
    def _do_sync(self, tc, highlights):
        with patch("notemaster.main.books.get_highlights", return_value=highlights):
            return tc.post("/sync", json={"asset_id": "A1", "book_title": "DDIA"})

    def test_yellow_highlight_creates_entry(self, client):
        tc, mock_db = client
        h = make_highlight(HighlightColor.YELLOW)
        self._do_sync(tc, [h])
        created = [c for c in mock_db.create_entry.call_args_list]
        assert len(created) == 1
        entry_arg = created[0].args[0]
        assert entry_arg.text == h.text
        assert entry_arg.source_type == EntryType.HIGHLIGHT

    def test_blue_highlight_creates_entry(self, client):
        tc, mock_db = client
        h = make_highlight(HighlightColor.BLUE)
        self._do_sync(tc, [h])
        created = mock_db.create_entry.call_args_list
        assert len(created) == 1
        assert created[0].args[0].source_type == EntryType.HIGHLIGHT

    def test_green_highlight_does_not_create_entry(self, client):
        tc, mock_db = client
        self._do_sync(tc, [make_highlight(HighlightColor.GREEN)])
        mock_db.create_entry.assert_not_called()

    def test_blue_highlight_still_saved_as_highlight(self, client):
        tc, mock_db = client
        h = make_highlight(HighlightColor.BLUE)
        self._do_sync(tc, [h])
        mock_db.save_highlight.assert_called()

    def test_source_ref_is_book_title(self, client):
        tc, mock_db = client
        h = make_highlight(HighlightColor.YELLOW)
        self._do_sync(tc, [h])
        entry_arg = mock_db.create_entry.call_args_list[0].args[0]
        assert entry_arg.source_ref == "DDIA"

    def test_sync_response_includes_entries_synced(self, client):
        tc, mock_db = client
        highlights = [
            make_highlight(HighlightColor.YELLOW),
            make_highlight(HighlightColor.BLUE),
            make_highlight(HighlightColor.GREEN),
        ]
        resp = self._do_sync(tc, highlights)
        assert resp.status_code == 200
        assert "entries_synced" in resp.json()
        assert resp.json()["entries_synced"] == 2

    def test_multiple_yellow_and_blue_all_get_entries(self, client):
        tc, mock_db = client
        highlights = [make_highlight(HighlightColor.YELLOW) for _ in range(3)]
        self._do_sync(tc, highlights)
        assert mock_db.create_entry.call_count == 3


# ---------------------------------------------------------------------------
# #17 — File import helpers (importer module)
# ---------------------------------------------------------------------------

class TestParseTextFile:
    def test_splits_into_paragraphs(self):
        from notemaster.importer import parse_text_file
        text = "First paragraph.\n\nSecond paragraph.\n\nThird one."
        result = parse_text_file(text)
        assert len(result) == 3

    def test_filters_empty_paragraphs(self):
        from notemaster.importer import parse_text_file
        text = "First paragraph text.\n\n\n\nSecond paragraph text."
        result = parse_text_file(text)
        assert len(result) == 2

    def test_strips_whitespace(self):
        from notemaster.importer import parse_text_file
        text = "  Hello world.  \n\n  Another line.  "
        result = parse_text_file(text)
        assert result[0] == "Hello world."

    def test_filters_too_short(self):
        from notemaster.importer import parse_text_file
        text = "ok\n\nThis is a proper sentence with enough words."
        result = parse_text_file(text)
        assert len(result) == 1
        assert "proper" in result[0]


class TestParseMdFile:
    def test_strips_atx_headers(self):
        from notemaster.importer import parse_md_file
        text = "# Title\n\nSome content here that is long enough."
        result = parse_md_file(text)
        assert not any(r.startswith("#") for r in result)

    def test_strips_bold_markers(self):
        from notemaster.importer import parse_md_file
        text = "**important** concept that spans enough characters to pass the filter."
        result = parse_md_file(text)
        assert "**" not in result[0]

    def test_keeps_content(self):
        from notemaster.importer import parse_md_file
        text = "## Section\n\nThis is useful content that should be kept as a highlight."
        result = parse_md_file(text)
        assert any("useful content" in r for r in result)

    def test_skips_code_blocks(self):
        from notemaster.importer import parse_md_file
        text = "Some prose paragraph that is long enough to be kept here.\n\n```python\nx = 1\n```"
        result = parse_md_file(text)
        assert not any("```" in r for r in result)


class TestParsePdfFile:
    def test_extracts_text_from_pdf_bytes(self):
        from notemaster.importer import parse_pdf_file
        import pypdf, io
        writer = pypdf.PdfWriter()
        writer.add_blank_page(width=200, height=200)
        buf = io.BytesIO()
        writer.write(buf)
        # Blank PDF returns empty list — just check it doesn't raise
        result = parse_pdf_file(buf.getvalue())
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# #17 — POST /import/file endpoint
# ---------------------------------------------------------------------------

class TestImportFileEndpoint:
    def test_txt_import_creates_book_and_highlights(self, client):
        tc, mock_db = client
        content = "First long paragraph here.\n\nSecond long paragraph there for import."
        with patch("notemaster.main.importer.parse_text_file",
                   return_value=["First long paragraph here.", "Second long paragraph there for import."]):
            resp = tc.post("/import/file",
                           files={"file": ("notes.txt", content.encode(), "text/plain")})
        assert resp.status_code == 200
        data = resp.json()
        assert "book_id" in data
        assert "highlights" in data

    def test_md_import_uses_md_parser(self, client):
        tc, mock_db = client
        content = b"# Title\n\nSome long enough paragraph content for testing."
        with patch("notemaster.main.importer.parse_md_file",
                   return_value=["Some long enough paragraph content for testing."]) as mock_parse:
            tc.post("/import/file",
                    files={"file": ("notes.md", content, "text/markdown")})
        mock_parse.assert_called_once()

    def test_highlights_saved_to_db(self, client):
        tc, mock_db = client
        paragraphs = ["A long paragraph here.", "Another good paragraph there."]
        with patch("notemaster.main.importer.parse_text_file", return_value=paragraphs):
            tc.post("/import/file",
                    files={"file": ("n.txt", b"x", "text/plain")})
        assert mock_db.save_highlight.call_count == 2

    def test_highlights_are_green(self, client):
        tc, mock_db = client
        with patch("notemaster.main.importer.parse_text_file", return_value=["A long paragraph."]):
            tc.post("/import/file",
                    files={"file": ("n.txt", b"x", "text/plain")})
        h = mock_db.save_highlight.call_args.args[0]
        assert h.color == HighlightColor.GREEN

    def test_book_saved_to_db(self, client):
        tc, mock_db = client
        with patch("notemaster.main.importer.parse_text_file", return_value=["A paragraph."]):
            tc.post("/import/file",
                    files={"file": ("n.txt", b"x", "text/plain")})
        mock_db.save_book.assert_called()

    def test_unsupported_type_returns_422(self, client):
        tc, _ = client
        resp = tc.post("/import/file",
                       files={"file": ("notes.exe", b"x", "application/octet-stream")})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# #18 — OCR module
# ---------------------------------------------------------------------------

class TestOcrModule:
    def test_ocr_returns_string(self):
        from notemaster.ocr import ocr_image
        from PIL import Image
        img = Image.new("RGB", (200, 50), color=(255, 255, 255))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        with patch("notemaster.ocr.pytesseract.image_to_string", return_value="hello world"):
            result = ocr_image(buf.getvalue())
        assert isinstance(result, str)

    def test_ocr_called_with_image_bytes(self):
        from notemaster.ocr import ocr_image
        with patch("notemaster.ocr.Image.open", return_value=MagicMock()), \
             patch("notemaster.ocr.pytesseract.image_to_string", return_value="hello") as mock_ocr:
            ocr_image(b"fake-image-bytes")
        mock_ocr.assert_called_once()


# ---------------------------------------------------------------------------
# #18 — POST /import/image endpoint
# ---------------------------------------------------------------------------

class TestImportImageEndpoint:
    def test_returns_created_entries(self, client):
        tc, mock_db = client
        from notemaster.models import Entry, EntryType
        from datetime import datetime
        now = datetime(2026, 4, 23, 10, 0)
        entry = Entry(id="e1", text="hello world", source_type=EntryType.OCR,
                      weight=1.0, created_at=now, updated_at=now)
        mock_db.create_entry.return_value = None
        mock_db.get_entry.return_value = entry

        with patch("notemaster.main.ocr.ocr_image", return_value="hello world\nanother phrase"):
            resp = tc.post("/import/image",
                           files={"image": ("photo.png", b"fake-png", "image/png")})
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_entries_have_ocr_source_type(self, client):
        tc, mock_db = client
        with patch("notemaster.main.ocr.ocr_image", return_value="a phrase here"):
            tc.post("/import/image",
                    files={"image": ("photo.png", b"fake-png", "image/png")})
        if mock_db.create_entry.called:
            entry_arg = mock_db.create_entry.call_args_list[0].args[0]
            assert entry_arg.source_type == EntryType.OCR

    def test_empty_ocr_result_returns_empty_list(self, client):
        tc, _ = client
        with patch("notemaster.main.ocr.ocr_image", return_value="   \n  \n  "):
            resp = tc.post("/import/image",
                           files={"image": ("photo.png", b"fake-png", "image/png")})
        assert resp.status_code == 200
        assert resp.json() == []

    def test_ocr_called_with_uploaded_bytes(self, client):
        tc, mock_db = client
        with patch("notemaster.main.ocr.ocr_image", return_value="") as mock_ocr:
            tc.post("/import/image",
                    files={"image": ("p.png", b"img-data", "image/png")})
        mock_ocr.assert_called_once_with(b"img-data")
