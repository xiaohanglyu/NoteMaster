"""
TDD tests for AnkiConnect export feature.
Issues: #60 (sync readiness), #61 (push modal / buildNote), #62 (client + push flow)
        #63 (Admin export UI), #64 (Admin push wiring), #65 (English view cleanup)

Frontend logic is tested via HTML structure assertions and pure-function extraction.
Backend: POST /shadow generic endpoint.
"""
import pytest
from pathlib import Path
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

from notemaster.models import Entry, EntryData, EntryType

FRONTEND = Path(__file__).parent.parent.parent / "frontend" / "index.html"


def make_entry(id="e1", phonetics="/wɜːd/", translation="单词", examples=None, context_note=None, source_ref=None):
    return Entry(
        id=id, text="word",
        source_type=EntryType.MANUAL,
        source_ref=source_ref,
        data=EntryData(
            phonetics=phonetics,
            translation=translation,
            examples=examples or ["An example sentence."],
            context_note=context_note,
        ),
        weight=1.0,
        created_at=datetime(2026, 5, 1),
        updated_at=datetime(2026, 5, 1),
    )


def make_entry_bare(id="e-bare"):
    return Entry(
        id=id, text="bare",
        source_type=EntryType.MANUAL,
        weight=1.0,
        created_at=datetime(2026, 5, 1),
        updated_at=datetime(2026, 5, 1),
    )


# ---------------------------------------------------------------------------
# Issue #60 — Sync readiness indicator
# ---------------------------------------------------------------------------

class TestSyncReadiness:
    """isEntryReady(entry) — pure JS function; tested via HTML presence."""

    def test_ready_function_present_in_frontend(self):
        html = FRONTEND.read_text()
        assert "isEntryReady" in html

    def test_sync_badge_rendered_in_entry_card(self):
        html = FRONTEND.read_text()
        assert "anki-ready" in html or "sync-badge" in html

    def test_ready_condition_checks_phonetics_and_translation(self):
        # The JS condition must require both fields — verify both strings appear
        # together in the isEntryReady function body.
        html = FRONTEND.read_text()
        idx = html.index("isEntryReady")
        snippet = html[idx: idx + 300]
        assert "phonetics" in snippet
        assert "translation" in snippet


# ---------------------------------------------------------------------------
# Issue #61 — buildNote pure function + field mapping
# ---------------------------------------------------------------------------

class TestBuildNote:
    """buildNote(entry, deckName, modelName, fieldMap) — pure JS function."""

    def test_build_note_function_present_in_frontend(self):
        html = FRONTEND.read_text()
        assert "buildNote" in html

    def test_anki_push_modal_present_in_frontend(self):
        html = FRONTEND.read_text()
        assert "anki-push-modal" in html or "id=\"anki-modal\"" in html

    def test_deck_selector_present_in_modal(self):
        html = FRONTEND.read_text()
        assert "anki-deck" in html

    def test_model_selector_present_in_modal(self):
        html = FRONTEND.read_text()
        assert "anki-model" in html

    def test_field_mapping_section_present(self):
        html = FRONTEND.read_text()
        assert "anki-field-map" in html or "field-mapping" in html

    def test_push_to_anki_button_present(self):
        html = FRONTEND.read_text()
        assert "Push to Anki" in html


# ---------------------------------------------------------------------------
# Issue #62 — AnkiConnect client + push flow
# ---------------------------------------------------------------------------

class TestAnkiClient:
    """ankiConnect(action, params) — JS fetch wrapper."""

    def test_anki_connect_function_present(self):
        html = FRONTEND.read_text()
        assert "ankiConnect" in html

    def test_anki_connect_targets_port_8765(self):
        html = FRONTEND.read_text()
        assert "8765" in html

    def test_anki_connect_uses_version_6(self):
        html = FRONTEND.read_text()
        assert '"version": 6' in html or "'version': 6" in html or "version: 6" in html

    def test_anki_connect_throws_on_error_field(self):
        html = FRONTEND.read_text()
        idx = html.index("ankiConnect")
        snippet = html[idx: idx + 500]
        assert "data.error" in snippet or ".error" in snippet


class TestPushFlow:
    """Push flow UI elements and action bar."""

    def test_action_bar_present(self):
        # Anki export moved to Admin — verify Admin section exists instead
        html = FRONTEND.read_text()
        assert "admin-anki-export" in html

    def test_select_all_button_present(self):
        html = FRONTEND.read_text()
        assert "selectAllEntries" in html or "select-all" in html

    def test_push_result_banner_present(self):
        html = FRONTEND.read_text()
        assert "anki-result" in html or "push-result" in html

    def test_connectivity_check_on_open(self):
        html = FRONTEND.read_text()
        assert "ankiConnect" in html
        # setup instructions shown on failure
        assert "2055492159" in html  # addon code shown in help text


# ---------------------------------------------------------------------------
# Issue #65 — English view cleanup (Anki UI removed)
# ---------------------------------------------------------------------------

class TestEnglishViewCleanup:
    def test_sync_badge_not_in_entry_card_template(self):
        html = FRONTEND.read_text()
        # syncBadge must NOT appear inside entryCardHTML
        idx = html.index("function entryCardHTML")
        # find the closing brace of entryCardHTML (next top-level function)
        next_fn = html.index("\nfunction ", idx + 1)
        snippet = html[idx:next_fn]
        assert "sync-badge" not in snippet

    def test_push_to_anki_not_in_bulk_toolbar(self):
        html = FRONTEND.read_text()
        idx = html.index('id="bulk-toolbar"')
        end = html.index("</div>", idx)
        snippet = html[idx:end]
        assert "Push to Anki" not in snippet

    def test_hover_checkbox_css_removed(self):
        html = FRONTEND.read_text()
        assert "entry-card:hover .entry-select-cb" not in html

    def test_bulk_ready_count_not_in_toolbar(self):
        html = FRONTEND.read_text()
        idx = html.index('id="bulk-toolbar"')
        end = html.index("</div>", idx)
        snippet = html[idx:end]
        assert "bulk-ready-count" not in snippet


# ---------------------------------------------------------------------------
# Issue #63 — Admin Anki Export UI
# ---------------------------------------------------------------------------

class TestAdminAnkiExport:
    def test_admin_anki_export_section_present(self):
        html = FRONTEND.read_text()
        assert "admin-anki-export" in html

    def test_tag_filter_present_in_export(self):
        html = FRONTEND.read_text()
        idx = html.index("admin-anki-export")
        snippet = html[idx: idx + 2000]
        assert "anki-export-tag" in snippet

    def test_readiness_filter_present_in_export(self):
        html = FRONTEND.read_text()
        idx = html.index("admin-anki-export")
        snippet = html[idx: idx + 2000]
        assert "anki-export-readiness" in snippet

    def test_search_input_present_in_export(self):
        html = FRONTEND.read_text()
        idx = html.index("admin-anki-export")
        snippet = html[idx: idx + 2000]
        assert "anki-export-search" in snippet

    def test_select_all_function_present(self):
        html = FRONTEND.read_text()
        assert "selectAllAnkiEntries" in html

    def test_entry_list_container_present(self):
        html = FRONTEND.read_text()
        assert "anki-export-list" in html

    def test_push_button_in_export_section(self):
        html = FRONTEND.read_text()
        idx = html.index("admin-anki-export")
        snippet = html[idx: idx + 3000]
        assert "Push to Anki" in snippet

    def test_summary_bar_present(self):
        html = FRONTEND.read_text()
        assert "anki-export-summary" in html


# ---------------------------------------------------------------------------
# Issue #64 — Admin push wiring
# ---------------------------------------------------------------------------

class TestAdminAnkiPush:
    def test_admin_push_calls_open_anki_modal(self):
        html = FRONTEND.read_text()
        assert "openAnkiModal" in html

    def test_anki_export_selected_ids_separate_from_english_selected(self):
        # Admin export must use its own selection set, not _selectedEntryIds
        html = FRONTEND.read_text()
        assert "_ankiExportIds" in html

    def test_push_to_anki_uses_anki_export_ids(self):
        # pushToAnki uses _ankiModalIds which is set to _ankiExportIds when called from Admin
        html = FRONTEND.read_text()
        idx = html.index("function pushToAnki")
        snippet = html[idx: idx + 1500]
        assert "_ankiModalIds" in snippet


# ---------------------------------------------------------------------------
# Backend: POST /shadow generic endpoint (already implemented, needs coverage)
# ---------------------------------------------------------------------------

class TestShadowGenericEndpoint:
    @pytest.fixture
    def client(self):
        from notemaster.main import app
        return TestClient(app)

    def test_shadow_endpoint_exists(self, client):
        # POST without audio should return 422 (validation), not 404
        resp = client.post("/shadow", data={"reference": "hello world"})
        assert resp.status_code != 404

    def test_shadow_endpoint_rejects_missing_reference(self, client):
        import io
        audio = io.BytesIO(b"fake-audio")
        resp = client.post("/shadow", files={"audio": ("rec.webm", audio, "audio/webm")})
        assert resp.status_code == 422

    def test_shadow_endpoint_rejects_missing_audio(self, client):
        resp = client.post("/shadow", data={"reference": "hello world"})
        assert resp.status_code == 422

    def test_shadow_endpoint_returns_shadow_fields(self, client):
        import io
        fake_audio = io.BytesIO(b"\x00" * 100)

        with patch("notemaster.stt.transcribe", return_value="hello world"), \
             patch("notemaster.pronunciation.assess_shadow") as mock_assess:
            mock_result = MagicMock()
            mock_result.overall_score = 0.95
            mock_result.words = []
            mock_result.feedback = "Great job"
            mock_assess.return_value = mock_result

            resp = client.post(
                "/shadow",
                data={"reference": "hello world"},
                files={"audio": ("rec.webm", fake_audio, "audio/webm")},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "overall_score" in data
        assert "transcript" in data
        assert "reference" in data
        assert "words" in data
        assert data["reference"] == "hello world"
