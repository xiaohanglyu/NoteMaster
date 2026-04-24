from unittest.mock import MagicMock
import pytest
from notemaster.models import InboxItem, InboxClassification
from datetime import datetime


def make_item(content="granularity"):
    return InboxItem(id="i-1", content=content, created_at=datetime(2026, 4, 24, 10, 0))


def make_mock_client(content: str):
    client = MagicMock()
    choice = MagicMock()
    choice.message.content = content
    client.chat.completions.create.return_value = MagicMock(choices=[choice])
    return client


class TestClassifyInboxItem:
    def test_returns_classification(self):
        from notemaster.ai import classify_inbox_item
        resp = '{"item_type":"english","reasoning":"vocab word","preview":{"text":"granularity"}}'
        result = classify_inbox_item(make_item(), client=make_mock_client(resp))
        assert isinstance(result, InboxClassification)
        assert result.item_type == "english"

    def test_concept_type(self):
        from notemaster.ai import classify_inbox_item
        resp = '{"item_type":"concept","reasoning":"tech concept","preview":{"title":"CAP Theorem","summary":"..."}}'
        result = classify_inbox_item(make_item("CAP Theorem"), client=make_mock_client(resp))
        assert result.item_type == "concept"

    def test_question_type(self):
        from notemaster.ai import classify_inbox_item
        resp = '{"item_type":"question","reasoning":"interview q","preview":{"question":"Explain CAP","q_type":"system_design"}}'
        result = classify_inbox_item(make_item("Explain CAP theorem"), client=make_mock_client(resp))
        assert result.item_type == "question"

    def test_unknown_type(self):
        from notemaster.ai import classify_inbox_item
        resp = '{"item_type":"unknown","reasoning":"unclear","preview":{}}'
        result = classify_inbox_item(make_item("random stuff"), client=make_mock_client(resp))
        assert result.item_type == "unknown"

    def test_strips_markdown_fences(self):
        from notemaster.ai import classify_inbox_item
        resp = '```json\n{"item_type":"english","reasoning":"vocab","preview":{}}\n```'
        result = classify_inbox_item(make_item(), client=make_mock_client(resp))
        assert result.item_type == "english"

    def test_raises_on_invalid_json(self):
        from notemaster.ai import classify_inbox_item
        with pytest.raises(Exception):
            classify_inbox_item(make_item(), client=make_mock_client("not json"))
