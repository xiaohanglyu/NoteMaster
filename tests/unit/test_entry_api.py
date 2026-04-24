import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from notemaster.models import Entry, EntryData, EntryType, EntryReviewRecord, EntryWithPriority, PronunciationResult


def make_entry(id="entry-1"):
    now = datetime(2026, 4, 23, 10, 0)
    return Entry(
        id=id,
        text="hit the ground running",
        source_type=EntryType.MANUAL,
        source_ref=None,
        data=EntryData(
            phonetics="/hɪt ðə ɡraʊnd ˈrʌnɪŋ/",
            translation="迅速投入工作",
            examples=["She hit the ground running on her first day."],
            context_note="idiom — start productively",
        ),
        weight=1.0,
        created_at=now,
        updated_at=now,
    )


def make_entry_unenriched(id="entry-u"):
    now = datetime(2026, 4, 23, 10, 0)
    return Entry(
        id=id, text="bootstrap", source_type=EntryType.MANUAL,
        weight=1.0, created_at=now, updated_at=now,
    )


def make_entry_with_priority(id="entry-1"):
    return EntryWithPriority(
        entry=make_entry(id),
        priority=1.0,
        days_overdue=0.0,
        last_mastery=None,
    )


def make_review_record():
    now = datetime(2026, 4, 23, 10, 0)
    return EntryReviewRecord(
        entry_id="entry-1",
        mastery_score=4,
        reviewed_at=now,
        next_review_at=now + timedelta(days=14),
    )


def make_db():
    db = MagicMock()
    db.create_entry.return_value = make_entry()
    db.get_entry.return_value = make_entry()
    db.get_entries.return_value = [make_entry()]
    db.update_entry.return_value = make_entry()
    db.get_due_entries.return_value = [make_entry_with_priority()]
    db.record_entry_review.return_value = make_review_record()
    return db


@pytest.fixture
def client():
    from notemaster.main import app, get_db
    mock_db = make_db()
    app.dependency_overrides[get_db] = lambda: mock_db
    yield TestClient(app), mock_db
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# POST /entries
# ---------------------------------------------------------------------------

class TestCreateEntry:
    def test_returns_created_entry(self, client):
        tc, _ = client
        resp = tc.post("/entries", json={"text": "hit the ground running"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["text"] == "hit the ground running"

    def test_entry_has_data_field(self, client):
        tc, _ = client
        data = tc.post("/entries", json={"text": "test phrase"}).json()
        assert "data" in data
        for field in ("id", "text", "source_type", "weight", "created_at"):
            assert field in data

    def test_missing_text_returns_422(self, client):
        tc, _ = client
        resp = tc.post("/entries", json={})
        assert resp.status_code == 422

    def test_optional_fields_accepted(self, client):
        tc, _ = client
        resp = tc.post("/entries", json={
            "text": "at the expense of",
            "source_type": "highlight",
            "source_ref": "DDIA",
        })
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /entries
# ---------------------------------------------------------------------------

class TestGetEntries:
    def test_returns_list(self, client):
        tc, _ = client
        resp = tc.get("/entries")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_filter_by_source_type(self, client):
        tc, mock_db = client
        tc.get("/entries?source_type=manual")
        mock_db.get_entries.assert_called_with(source_type=EntryType.MANUAL)

    def test_no_filter_returns_all(self, client):
        tc, mock_db = client
        tc.get("/entries")
        mock_db.get_entries.assert_called_with(source_type=None)


# ---------------------------------------------------------------------------
# GET /entries/{id}
# ---------------------------------------------------------------------------

class TestGetEntry:
    def test_returns_entry(self, client):
        tc, _ = client
        resp = tc.get("/entries/entry-1")
        assert resp.status_code == 200
        assert resp.json()["id"] == "entry-1"

    def test_returns_404_for_unknown(self, client):
        tc, mock_db = client
        mock_db.get_entry.return_value = None
        resp = tc.get("/entries/bad-id")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /entries/{id}
# ---------------------------------------------------------------------------

class TestUpdateEntry:
    def test_returns_updated_entry(self, client):
        tc, _ = client
        resp = tc.patch("/entries/entry-1", json={"data": {"phonetics": "/hɪt/"}})
        assert resp.status_code == 200
        assert "id" in resp.json()

    def test_returns_404_for_unknown(self, client):
        tc, mock_db = client
        mock_db.update_entry.return_value = None
        resp = tc.patch("/entries/bad-id", json={"text": "x"})
        assert resp.status_code == 404

    def test_update_text_accepted(self, client):
        tc, _ = client
        resp = tc.patch("/entries/entry-1", json={"text": "bootstrap"})
        assert resp.status_code == 200

    def test_update_data_with_extended_fields(self, client):
        tc, mock_db = client
        resp = tc.patch("/entries/entry-1", json={"data": {"tenses": ["run", "ran"], "root": "Old English"}})
        assert resp.status_code == 200
        call_kwargs = mock_db.update_entry.call_args.kwargs
        assert call_kwargs["data"].tenses == ["run", "ran"]
        assert call_kwargs["data"].root == "Old English"


# ---------------------------------------------------------------------------
# POST /entries/{id}/review
# ---------------------------------------------------------------------------

class TestRecordEntryReview:
    def test_returns_review_result(self, client):
        tc, _ = client
        resp = tc.post("/entries/entry-1/review", json={"mastery_score": 4})
        assert resp.status_code == 200
        data = resp.json()
        assert "entry_id" in data
        assert "next_review_at" in data
        assert "new_weight" in data

    def test_returns_404_for_unknown_entry(self, client):
        tc, mock_db = client
        mock_db.get_entry.return_value = None
        mock_db.record_entry_review.side_effect = ValueError("not found")
        resp = tc.post("/entries/bad-id/review", json={"mastery_score": 3})
        assert resp.status_code == 404

    def test_invalid_score_returns_422(self, client):
        tc, _ = client
        resp = tc.post("/entries/entry-1/review", json={"mastery_score": 6})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /entries/next
# ---------------------------------------------------------------------------

class TestNextEntry:
    def test_returns_next_due_entry(self, client):
        tc, _ = client
        resp = tc.get("/entries/next")
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert "text" in data

    def test_returns_404_when_nothing_due(self, client):
        tc, mock_db = client
        mock_db.get_due_entries.return_value = []
        resp = tc.get("/entries/next")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /entries/{id}/answer/voice
# ---------------------------------------------------------------------------

_FAKE_RESULT = PronunciationResult(heard="hit the ground running", match=True, score=1.0)


class TestEntryVoiceAnswer:
    def test_returns_pronunciation_result(self, client):
        tc, _ = client
        with patch("notemaster.main.stt.transcribe", return_value="hit the ground running"), \
             patch("notemaster.main.ai.check_pronunciation", return_value=_FAKE_RESULT):
            resp = tc.post("/entries/entry-1/answer/voice",
                           files={"audio": ("rec.webm", b"fake audio", "audio/webm")})
        assert resp.status_code == 200
        data = resp.json()
        assert "heard" in data
        assert "match" in data
        assert "score" in data

    def test_returns_404_for_unknown_entry(self, client):
        tc, mock_db = client
        mock_db.get_entry.return_value = None
        resp = tc.post("/entries/bad-id/answer/voice",
                       files={"audio": ("rec.webm", b"fake audio", "audio/webm")})
        assert resp.status_code == 404

    def test_match_true_propagated(self, client):
        tc, _ = client
        with patch("notemaster.main.stt.transcribe", return_value="hit the ground running"), \
             patch("notemaster.main.ai.check_pronunciation", return_value=_FAKE_RESULT):
            resp = tc.post("/entries/entry-1/answer/voice",
                           files={"audio": ("rec.webm", b"audio", "audio/webm")})
        assert resp.json()["match"] is True

    def test_transcribe_called_with_audio_bytes(self, client):
        tc, _ = client
        with patch("notemaster.main.stt.transcribe", return_value="test") as mock_stt, \
             patch("notemaster.main.ai.check_pronunciation", return_value=_FAKE_RESULT):
            tc.post("/entries/entry-1/answer/voice",
                    files={"audio": ("rec.webm", b"audio data", "audio/webm")})
        mock_stt.assert_called_once()

    def test_check_pronunciation_called_with_entry(self, client):
        tc, mock_db = client
        entry = make_entry()
        mock_db.get_entry.return_value = entry
        with patch("notemaster.main.stt.transcribe", return_value="hit the ground running"), \
             patch("notemaster.main.ai.check_pronunciation", return_value=_FAKE_RESULT) as mock_check:
            tc.post("/entries/entry-1/answer/voice",
                    files={"audio": ("rec.webm", b"audio", "audio/webm")})
        mock_check.assert_called_once_with(entry, "hit the ground running")


# ---------------------------------------------------------------------------
# POST /entries/enrich-all
# ---------------------------------------------------------------------------

class TestEnrichAll:
    def test_returns_queued_count(self, client):
        tc, mock_db = client
        unenriched = [make_entry_unenriched(f"e-{i}") for i in range(3)]
        mock_db.get_entries.return_value = unenriched
        resp = tc.post("/entries/enrich-all")
        assert resp.status_code == 200
        assert resp.json()["queued"] == 3

    def test_already_enriched_entries_skipped(self, client):
        tc, mock_db = client
        enriched = make_entry()  # has phonetics in data
        mock_db.get_entries.return_value = [enriched]
        resp = tc.post("/entries/enrich-all")
        assert resp.json()["queued"] == 0

    def test_returns_zero_when_all_enriched(self, client):
        tc, mock_db = client
        mock_db.get_entries.return_value = [make_entry(), make_entry("e-2")]
        resp = tc.post("/entries/enrich-all")
        assert resp.status_code == 200
        assert resp.json()["queued"] == 0
