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


# --- Highlight ---

class TestHighlight:
    def test_valid_highlight(self):
        h = Highlight(
            id="abc123",
            text="Replication lag occurs when...",
            color=HighlightColor.GREEN,
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
                book_title="DDIA",
                chapter="Chapter 1",
            )

    def test_chapter_is_optional(self):
        h = Highlight(
            id="abc123",
            text="some text",
            color=HighlightColor.YELLOW,
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
