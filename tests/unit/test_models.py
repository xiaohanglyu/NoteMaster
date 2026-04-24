import pytest
from datetime import date, datetime
from notemaster.models import (
    Highlight,
    HighlightColor,
    FocusArea,
    CardSelection,
    SessionConfig,
    EvaluationResult,
    QuizQuestionType,
    QuizQuestion,
    ReviewRecord,
    StudySession,
)


# --- EntryData ---

class TestEntryData:
    def test_defaults_are_empty(self):
        from notemaster.models import EntryData
        d = EntryData()
        assert d.phonetics is None
        assert d.translation is None
        assert d.context_note is None
        assert d.examples == []
        assert d.tenses == []
        assert d.word_forms == []
        assert d.root is None
        assert d.synonyms == []
        assert d.derivatives == []

    def test_all_fields_roundtrip(self):
        from notemaster.models import EntryData
        d = EntryData(
            phonetics="/hɪt/",
            translation="迅速投入",
            context_note="idiom",
            examples=["She hit the ground running."],
            tenses=["hit", "hits", "had hit"],
            word_forms=["noun: a hit"],
            root="Old English: hyttan",
            synonyms=["dash", "sprint"],
            derivatives=["hitting", "hitter"],
        )
        assert d.phonetics == "/hɪt/"
        assert d.translation == "迅速投入"
        assert len(d.tenses) == 3
        assert d.root == "Old English: hyttan"
        assert len(d.synonyms) == 2
        assert len(d.derivatives) == 2

    def test_list_fields_default_to_empty_list(self):
        from notemaster.models import EntryData
        d = EntryData()
        for field in ("examples", "tenses", "word_forms", "synonyms", "derivatives"):
            assert getattr(d, field) == [], f"{field} should default to []"


# --- Entry with data field ---

class TestEntryWithData:
    def _make(self, **kwargs):
        from notemaster.models import Entry, EntryType
        now = datetime(2026, 4, 24, 10, 0)
        return Entry(
            id="e-1", text="hit the ground running",
            source_type=EntryType.MANUAL,
            weight=1.0, created_at=now, updated_at=now,
            **kwargs,
        )

    def test_data_defaults_to_empty_entry_data(self):
        from notemaster.models import EntryData
        e = self._make()
        assert isinstance(e.data, EntryData)
        assert e.data.phonetics is None

    def test_data_field_accepted(self):
        from notemaster.models import EntryData
        e = self._make(data=EntryData(phonetics="/hɪt/", translation="打"))
        assert e.data.phonetics == "/hɪt/"
        assert e.data.translation == "打"



# --- Highlight ---

class TestHighlight:
    def test_valid_highlight(self):
        h = Highlight(
            id="abc123",
            text="Replication lag occurs when...",
            color=HighlightColor.GREEN,
            book_id="book-1",
            book_title="Designing Data-Intensive Applications",
            chapter="Chapter 5",
        )
        assert h.text == "Replication lag occurs when..."
        assert h.color == HighlightColor.GREEN

    def test_invalid_color_raises(self):
        with pytest.raises(Exception):
            Highlight(
                id="abc123",
                text="some text",
                color="purple",
                book_id="book-1",
                book_title="DDIA",
                chapter="Chapter 1",
            )

    def test_chapter_is_optional(self):
        h = Highlight(
            id="abc123",
            text="some text",
            color=HighlightColor.YELLOW,
            book_id="book-1",
            book_title="DDIA",
        )
        assert h.chapter is None


# --- SessionConfig ---

class TestSessionConfig:
    def test_defaults(self):
        config = SessionConfig()
        assert config.duration_minutes == 10
        assert config.focus_area == FocusArea.MIXED
        assert config.card_selection == CardSelection.WEAK_FIRST

    def test_custom_config(self):
        config = SessionConfig(duration_minutes=20, focus_area=FocusArea.CONCEPT)
        assert config.duration_minutes == 20
        assert config.focus_area == FocusArea.CONCEPT

    def test_duration_must_be_positive(self):
        with pytest.raises(Exception):
            SessionConfig(duration_minutes=0)

    def test_duration_must_be_positive_negative(self):
        with pytest.raises(Exception):
            SessionConfig(duration_minutes=-5)


# --- EvaluationResult ---

class TestEvaluationResult:
    def test_valid_result(self):
        result = EvaluationResult(
            concept_feedback="Good explanation of replication lag.",
            english_feedback="Grammar is correct. Consider saying 'occurs' instead of 'happen'.",
            concept_score=4,
            english_score=3,
            concept_suggestions=["Mention read-your-writes consistency"],
            english_suggestions=["Use 'occurs' instead of 'happen'"],
        )
        assert result.concept_score == 4
        assert result.english_score == 3

    def test_score_out_of_range(self):
        with pytest.raises(Exception):
            EvaluationResult(
                concept_feedback="ok",
                english_feedback="ok",
                concept_score=6,
                english_score=3,
                concept_suggestions=[],
                english_suggestions=[],
            )

    def test_score_minimum(self):
        with pytest.raises(Exception):
            EvaluationResult(
                concept_feedback="ok",
                english_feedback="ok",
                concept_score=0,
                english_score=3,
                concept_suggestions=[],
                english_suggestions=[],
            )


# --- QuizQuestion ---

class TestQuizQuestion:
    def test_valid_question(self):
        q = QuizQuestion(
            type=QuizQuestionType.DEFINE,
            prompt="Explain replication lag and its impact on consistency.",
            time_limit_seconds=60,
        )
        assert q.time_limit_seconds == 60
        assert q.type == QuizQuestionType.DEFINE

    def test_default_time_limit(self):
        q = QuizQuestion(
            type=QuizQuestionType.SCENARIO,
            prompt="Your write throughput dropped suddenly. Why?",
        )
        assert q.time_limit_seconds == 60


# --- ReviewRecord ---

class TestReviewRecord:
    def test_valid_record(self):
        r = ReviewRecord(
            highlight_id="abc123",
            mastery_score=3,
            last_reviewed_at=datetime(2026, 4, 22, 10, 0),
            next_review_at=datetime(2026, 4, 29, 10, 0),
        )
        assert r.mastery_score == 3

    def test_mastery_score_out_of_range_high(self):
        with pytest.raises(Exception):
            ReviewRecord(
                highlight_id="abc123",
                mastery_score=6,
                last_reviewed_at=datetime(2026, 4, 22),
                next_review_at=datetime(2026, 4, 29),
            )

    def test_mastery_score_out_of_range_low(self):
        with pytest.raises(Exception):
            ReviewRecord(
                highlight_id="abc123",
                mastery_score=0,
                last_reviewed_at=datetime(2026, 4, 22),
                next_review_at=datetime(2026, 4, 29),
            )


class TestConceptReviewRecord:
    def test_valid_record(self):
        from notemaster.models import ConceptReviewRecord
        r = ConceptReviewRecord(
            concept_id="concept-1",
            mastery_score=4,
            reviewed_at=datetime(2026, 4, 22, 10, 0),
            next_review_at=datetime(2026, 5, 6, 10, 0),
        )
        assert r.concept_id == "concept-1"
        assert r.mastery_score == 4

    def test_mastery_score_out_of_range(self):
        from notemaster.models import ConceptReviewRecord
        with pytest.raises(Exception):
            ConceptReviewRecord(
                concept_id="concept-1",
                mastery_score=6,
                reviewed_at=datetime(2026, 4, 22),
                next_review_at=datetime(2026, 5, 6),
            )


# --- StudySession ---

class TestStudySession:
    def test_valid_session(self):
        s = StudySession(
            date=date(2026, 4, 22),
            duration_minutes=10,
            items_reviewed=8,
            quiz_score=0.75,
        )
        assert s.quiz_score == 0.75

    def test_quiz_score_out_of_range(self):
        with pytest.raises(Exception):
            StudySession(
                date=date(2026, 4, 22),
                duration_minutes=10,
                items_reviewed=8,
                quiz_score=1.5,
            )
