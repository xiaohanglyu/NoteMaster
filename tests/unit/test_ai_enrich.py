import pytest
from unittest.mock import MagicMock, patch
from notemaster.models import Entry, EntryData, EntryType, PronunciationResult
from datetime import datetime


def make_entry(id="entry-1"):
    now = datetime(2026, 4, 23, 10, 0)
    return Entry(
        id=id,
        text="hit the ground running",
        source_type=EntryType.MANUAL,
        weight=1.0,
        created_at=now,
        updated_at=now,
    )


def make_mock_client(content: str):
    client = MagicMock()
    choice = MagicMock()
    choice.message.content = content
    client.chat.completions.create.return_value = MagicMock(choices=[choice])
    return client


VALID_RESPONSE = '''{
  "phonetics": "/hɪt ðə ɡraʊnd ˈrʌnɪŋ/",
  "translation": "迅速投入工作；一开始就全力以赴",
  "examples": [
    "She hit the ground running on her first day at the new job.",
    "The team hit the ground running after the product launch.",
    "He hit the ground running with his research from day one."
  ],
  "context_note": "idiom — to start a new activity with great energy and enthusiasm"
}'''


class TestEnrichEntry:
    def test_returns_phonetics(self):
        from notemaster.ai import enrich_entry
        client = make_mock_client(VALID_RESPONSE)
        result = enrich_entry(make_entry(), client=client)
        assert result["phonetics"] == "/hɪt ðə ɡraʊnd ˈrʌnɪŋ/"

    def test_returns_three_examples(self):
        from notemaster.ai import enrich_entry
        client = make_mock_client(VALID_RESPONSE)
        result = enrich_entry(make_entry(), client=client)
        assert len(result["examples"]) == 3

    def test_returns_context_note(self):
        from notemaster.ai import enrich_entry
        client = make_mock_client(VALID_RESPONSE)
        result = enrich_entry(make_entry(), client=client)
        assert "idiom" in result["context_note"]

    def test_returns_chinese_translation(self):
        from notemaster.ai import enrich_entry
        client = make_mock_client(VALID_RESPONSE)
        result = enrich_entry(make_entry(), client=client)
        assert result["translation"] == "迅速投入工作；一开始就全力以赴"

    def test_strips_markdown_fences(self):
        from notemaster.ai import enrich_entry
        fenced = f"```json\n{VALID_RESPONSE}\n```"
        client = make_mock_client(fenced)
        result = enrich_entry(make_entry(), client=client)
        assert result["phonetics"] is not None

    def test_raises_on_invalid_json(self):
        from notemaster.ai import enrich_entry
        client = make_mock_client("not json at all")
        with pytest.raises(ValueError):
            enrich_entry(make_entry(), client=client)

    def test_uses_entry_text_in_prompt(self):
        from notemaster.ai import enrich_entry
        client = make_mock_client(VALID_RESPONSE)
        enrich_entry(make_entry(), client=client)
        call_args = client.chat.completions.create.call_args
        messages = call_args.kwargs.get("messages") or call_args.args[0] if call_args.args else call_args.kwargs["messages"]
        assert "hit the ground running" in str(messages)

    def test_temperature_is_low(self):
        from notemaster.ai import enrich_entry
        client = make_mock_client(VALID_RESPONSE)
        enrich_entry(make_entry(), client=client)
        call_kwargs = client.chat.completions.create.call_args.kwargs
        assert call_kwargs.get("temperature", 1.0) <= 0.3


class TestEnrichExtra:
    def _make_extra_client(self, content: str):
        return make_mock_client(content)

    def test_returns_requested_fields(self):
        from notemaster.ai import enrich_entry_extra
        resp = '{"tenses": ["run", "ran", "has run"], "root": "Old English: rinnan"}'
        client = self._make_extra_client(resp)
        result = enrich_entry_extra(make_entry(), fields=["tenses", "root"], client=client)
        assert result["tenses"] == ["run", "ran", "has run"]
        assert result["root"] == "Old English: rinnan"

    def test_prompt_contains_requested_fields(self):
        from notemaster.ai import enrich_entry_extra
        resp = '{"synonyms": ["dash", "sprint"]}'
        client = self._make_extra_client(resp)
        enrich_entry_extra(make_entry(), fields=["synonyms"], client=client)
        call_args = client.chat.completions.create.call_args
        messages = str(call_args.kwargs.get("messages", ""))
        assert "synonyms" in messages

    def test_prompt_contains_entry_text(self):
        from notemaster.ai import enrich_entry_extra
        resp = '{"derivatives": ["runner"]}'
        client = self._make_extra_client(resp)
        enrich_entry_extra(make_entry(), fields=["derivatives"], client=client)
        call_args = client.chat.completions.create.call_args
        messages = str(call_args.kwargs.get("messages", ""))
        assert "hit the ground running" in messages

    def test_raises_on_empty_fields(self):
        from notemaster.ai import enrich_entry_extra
        with pytest.raises(ValueError):
            enrich_entry_extra(make_entry(), fields=[], client=make_mock_client("{}"))

    def test_raises_on_invalid_json(self):
        from notemaster.ai import enrich_entry_extra
        client = make_mock_client("not json")
        with pytest.raises(ValueError):
            enrich_entry_extra(make_entry(), fields=["tenses"], client=client)

    def test_strips_markdown_fences(self):
        from notemaster.ai import enrich_entry_extra
        resp = '```json\n{"tenses": ["runs"]}\n```'
        client = self._make_extra_client(resp)
        result = enrich_entry_extra(make_entry(), fields=["tenses"], client=client)
        assert result["tenses"] == ["runs"]


class TestEnrichEndpoint:
    @pytest.fixture
    def client(self):
        from notemaster.main import app, get_db
        mock_db = MagicMock()
        mock_db.get_entry.return_value = make_entry()
        mock_db.update_entry.return_value = make_entry()
        app.dependency_overrides[get_db] = lambda: mock_db
        from fastapi.testclient import TestClient
        yield TestClient(app), mock_db
        app.dependency_overrides.clear()

    def test_enrich_returns_updated_entry(self, client):
        tc, mock_db = client
        with patch("notemaster.main.ai.enrich_entry", return_value={
            "phonetics": "/hɪt/",
            "translation": "迅速",
            "examples": ["Example one."],
            "context_note": "idiom",
        }):
            resp = tc.post("/entries/entry-1/enrich")
        assert resp.status_code == 200

    def test_enrich_saves_to_db(self, client):
        tc, mock_db = client
        enriched = {
            "phonetics": "/hɪt/",
            "translation": "迅速",
            "examples": ["Ex."],
            "context_note": "note",
        }
        with patch("notemaster.main.ai.enrich_entry", return_value=enriched):
            tc.post("/entries/entry-1/enrich")
        mock_db.update_entry.assert_called_once()
        call_kwargs = mock_db.update_entry.call_args.kwargs
        assert call_kwargs["data"].phonetics == "/hɪt/"
        assert call_kwargs["data"].translation == "迅速"

    def test_enrich_returns_404_for_unknown(self, client):
        tc, mock_db = client
        mock_db.get_entry.return_value = None
        resp = tc.post("/entries/bad-id/enrich")
        assert resp.status_code == 404


class TestEnrichExtraEndpoint:
    @pytest.fixture
    def client(self):
        from notemaster.main import app, get_db
        mock_db = MagicMock()
        mock_db.get_entry.return_value = make_entry()
        mock_db.update_entry.return_value = make_entry()
        app.dependency_overrides[get_db] = lambda: mock_db
        from fastapi.testclient import TestClient
        yield TestClient(app), mock_db
        app.dependency_overrides.clear()

    def test_enrich_extra_returns_updated_entry(self, client):
        tc, mock_db = client
        with patch("notemaster.main.ai.enrich_entry_extra", return_value={
            "tenses": ["ran", "has run"],
        }):
            resp = tc.post("/entries/entry-1/enrich/extra", json={"fields": ["tenses"]})
        assert resp.status_code == 200

    def test_enrich_extra_merges_into_data(self, client):
        tc, mock_db = client
        with patch("notemaster.main.ai.enrich_entry_extra", return_value={"root": "hyttan"}):
            tc.post("/entries/entry-1/enrich/extra", json={"fields": ["root"]})
        call_kwargs = mock_db.update_entry.call_args.kwargs
        assert call_kwargs["data"].root == "hyttan"

    def test_enrich_extra_returns_404_for_unknown(self, client):
        tc, mock_db = client
        mock_db.get_entry.return_value = None
        resp = tc.post("/entries/bad-id/enrich/extra", json={"fields": ["tenses"]})
        assert resp.status_code == 404

    def test_enrich_extra_empty_fields_returns_422(self, client):
        tc, _ = client
        resp = tc.post("/entries/entry-1/enrich/extra", json={"fields": []})
        assert resp.status_code == 422


class TestBatchEnrichEndpoint:
    @pytest.fixture
    def client(self):
        from notemaster.main import app, get_db
        mock_db = MagicMock()
        mock_db.get_entry.side_effect = lambda eid: make_entry(id=eid)
        app.dependency_overrides[get_db] = lambda: mock_db
        from fastapi.testclient import TestClient
        yield TestClient(app), mock_db
        app.dependency_overrides.clear()

    def test_batch_enrich_queues_all_ids(self, client):
        tc, _ = client
        resp = tc.post("/entries/batch-enrich", json={"entry_ids": ["e1", "e2"], "fields": ["tenses"]})
        assert resp.status_code == 200
        assert resp.json()["queued"] == 2

    def test_batch_enrich_skips_unknown_ids(self, client):
        tc, mock_db = client
        mock_db.get_entry.side_effect = lambda eid: make_entry(id=eid) if eid == "e1" else None
        resp = tc.post("/entries/batch-enrich", json={"entry_ids": ["e1", "bad"], "fields": ["tenses"]})
        assert resp.json()["queued"] == 1

    def test_batch_enrich_empty_ids_returns_400(self, client):
        tc, _ = client
        resp = tc.post("/entries/batch-enrich", json={"entry_ids": [], "fields": ["tenses"]})
        assert resp.status_code == 400

    def test_batch_enrich_empty_fields_returns_400(self, client):
        tc, _ = client
        resp = tc.post("/entries/batch-enrich", json={"entry_ids": ["e1"], "fields": []})
        assert resp.status_code == 400


class TestCheckPronunciation:
    def test_exact_match_returns_match_true(self):
        from notemaster.ai import check_pronunciation
        result = check_pronunciation(make_entry(), "hit the ground running")
        assert result.match is True
        assert result.score >= 0.8

    def test_mismatch_returns_match_false(self):
        from notemaster.ai import check_pronunciation
        result = check_pronunciation(make_entry(), "completely different words here today")
        assert result.match is False

    def test_case_insensitive(self):
        from notemaster.ai import check_pronunciation
        result = check_pronunciation(make_entry(), "HIT THE GROUND RUNNING")
        assert result.match is True

    def test_returns_original_heard_text(self):
        from notemaster.ai import check_pronunciation
        result = check_pronunciation(make_entry(), "  hit the ground running  ")
        assert result.heard == "hit the ground running"

    def test_close_match_passes_threshold(self):
        from notemaster.ai import check_pronunciation
        result = check_pronunciation(make_entry(), "hit the ground runnin")
        assert result.match is True

    def test_score_is_float_between_0_and_1(self):
        from notemaster.ai import check_pronunciation
        result = check_pronunciation(make_entry(), "something unrelated")
        assert 0.0 <= result.score <= 1.0

    def test_returns_pronunciation_result_type(self):
        from notemaster.ai import check_pronunciation
        result = check_pronunciation(make_entry(), "hit the ground running")
        assert isinstance(result, PronunciationResult)
