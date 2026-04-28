"""Tests for Source model."""
import pytest
from datetime import datetime
from notemaster.models import Source, SourceType


def make_source(**kwargs):
    defaults = dict(
        id="s-1",
        title="Apache Flink Guide",
        source_type=SourceType.URL,
        source_ref="https://flink.apache.org/docs",
        content_cache=None,
        tags=[],
        created_at=datetime(2026, 4, 24),
    )
    return Source(**{**defaults, **kwargs})


class TestSourceModel:
    def test_create_url_source(self):
        s = make_source()
        assert s.id == "s-1"
        assert s.source_type == SourceType.URL
        assert s.source_ref == "https://flink.apache.org/docs"

    def test_create_file_source(self):
        s = make_source(source_type=SourceType.FILE, source_ref="/tmp/notes.md")
        assert s.source_type == SourceType.FILE

    def test_create_text_source(self):
        s = make_source(source_type=SourceType.TEXT, source_ref=None)
        assert s.source_ref is None

    def test_content_cache_optional(self):
        s = make_source(content_cache="some cached text")
        assert s.content_cache == "some cached text"

    def test_tags_default_empty(self):
        s = make_source()
        assert s.tags == []

    def test_tags_list(self):
        s = make_source(tags=["flink", "streaming"])
        assert "flink" in s.tags


class TestInterviewQuestionSourceId:
    def test_source_id_defaults_none(self):
        from notemaster.models import InterviewQuestion, QuestionCategory
        q = InterviewQuestion(
            id="q-1", question="What is Flink?",
            category=QuestionCategory.STUDY,
            created_at=datetime(2026, 4, 24),
        )
        assert q.source_id is None

    def test_source_id_can_be_set(self):
        from notemaster.models import InterviewQuestion, QuestionCategory
        q = InterviewQuestion(
            id="q-1", question="What is Flink?",
            category=QuestionCategory.STUDY,
            source_id="s-1",
            created_at=datetime(2026, 4, 24),
        )
        assert q.source_id == "s-1"
