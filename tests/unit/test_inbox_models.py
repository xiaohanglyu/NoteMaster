import pytest
from datetime import datetime


class TestInboxItem:
    def test_required_fields(self):
        from notemaster.models import InboxItem
        now = datetime(2026, 4, 24, 10, 0)
        item = InboxItem(id="i-1", content="granularity", created_at=now)
        assert item.content == "granularity"
        assert item.tags == []
        assert item.processed_at is None

    def test_tags_default_empty(self):
        from notemaster.models import InboxItem
        now = datetime(2026, 4, 24, 10, 0)
        item = InboxItem(id="i-1", content="x", created_at=now)
        assert item.tags == []

    def test_processed_at_nullable(self):
        from notemaster.models import InboxItem
        now = datetime(2026, 4, 24, 10, 0)
        item = InboxItem(id="i-1", content="x", created_at=now, processed_at=now)
        assert item.processed_at == now

    def test_is_pending_property(self):
        from notemaster.models import InboxItem
        now = datetime(2026, 4, 24, 10, 0)
        pending = InboxItem(id="i-1", content="x", created_at=now)
        done = InboxItem(id="i-2", content="x", created_at=now, processed_at=now)
        assert pending.is_pending is True
        assert done.is_pending is False


class TestInboxClassification:
    def test_english_classification(self):
        from notemaster.models import InboxClassification
        c = InboxClassification(
            item_type="english",
            reasoning="Looks like a vocabulary word",
            preview={"text": "granularity", "translation": "粒度"},
        )
        assert c.item_type == "english"
        assert c.preview["translation"] == "粒度"

    def test_concept_classification(self):
        from notemaster.models import InboxClassification
        c = InboxClassification(
            item_type="concept",
            reasoning="Technical explanation",
            preview={"title": "Consistent Hashing", "summary": "..."},
        )
        assert c.item_type == "concept"

    def test_question_classification(self):
        from notemaster.models import InboxClassification
        c = InboxClassification(
            item_type="question",
            reasoning="Looks like an interview question",
            preview={"question": "Explain CAP theorem", "q_type": "system_design"},
        )
        assert c.item_type == "question"

    def test_unknown_type_allowed(self):
        from notemaster.models import InboxClassification
        c = InboxClassification(item_type="unknown", reasoning="Not sure", preview={})
        assert c.item_type == "unknown"

    def test_valid_types_only(self):
        from pydantic import ValidationError
        from notemaster.models import InboxClassification
        with pytest.raises(ValidationError):
            InboxClassification(item_type="banana", reasoning="x", preview={})
