import pytest
from unittest.mock import MagicMock, patch
from notemaster.models import Entry, EntryType, PronunciationResult
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
        prompt_text = str(messages)
        assert "hit the ground running" in prompt_text

    def test_temperature_is_low(self):
        from notemaster.ai import enrich_entry
        client = make_mock_client(VALID_RESPONSE)
        enrich_entry(make_entry(), client=client)
        call_kwargs = client.chat.completions.create.call_args.kwargs
        assert call_kwargs.get("temperature", 1.0) <= 0.3


class TestEnrichEndpoint:
    @pytest.fixture
    def client(self):
        from notemaster.main import app, get_db
        from unittest.mock import MagicMock
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
            "examples": ["Example one."],
            "context_note": "idiom",
        }):
            resp = tc.post("/entries/entry-1/enrich")
        assert resp.status_code == 200

    def test_enrich_saves_to_db(self, client):
        tc, mock_db = client
        enriched = {"phonetics": "/hɪt/", "examples": ["Ex."], "context_note": "note"}
        with patch("notemaster.main.ai.enrich_entry", return_value=enriched):
            tc.post("/entries/entry-1/enrich")
        mock_db.update_entry.assert_called_once_with(
            "entry-1",
            phonetics="/hɪt/",
            examples=["Ex."],
            context_note="note",
        )

    def test_enrich_returns_404_for_unknown(self, client):
        tc, mock_db = client
        mock_db.get_entry.return_value = None
        resp = tc.post("/entries/bad-id/enrich")
        assert resp.status_code == 404


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
        # Whisper occasionally drops a final letter — still close enough
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
