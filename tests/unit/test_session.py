import pytest
from datetime import datetime, timedelta
from notemaster.models import (
    Highlight,
    HighlightColor,
    ReviewRecord,
    SessionConfig,
    FocusArea,
    CardSelection,
    QuizQuestionType,
)
from notemaster.session import select_highlights, generate_quiz_questions


# --- Fixtures ---

def make_highlight(id: str, color: HighlightColor, text: str = "some text") -> Highlight:
    return Highlight(
        id=id,
        text=text,
        color=color,
        book_id="book-1",
        book_title="DDIA",
    )


def make_record(highlight_id: str, mastery_score: int, days_until_due: int = -1) -> ReviewRecord:
    now = datetime.now()
    return ReviewRecord(
        highlight_id=highlight_id,
        mastery_score=mastery_score,
        last_reviewed_at=now - timedelta(days=7),
        next_review_at=now + timedelta(days=days_until_due),
    )


YELLOW = make_highlight("y1", HighlightColor.YELLOW, "reliability means the system continues to work")
GREEN = make_highlight("g1", HighlightColor.GREEN, "A fault is one component deviating from its spec")
BLUE = make_highlight("b1", HighlightColor.BLUE, "Scalability is the ability to cope with increased load")
ALL_HIGHLIGHTS = [YELLOW, GREEN, BLUE]


# --- Focus area filtering ---

class TestSelectHighlightsFocusArea:
    def test_concept_returns_green_and_blue(self):
        config = SessionConfig(focus_area=FocusArea.CONCEPT)
        result = select_highlights(ALL_HIGHLIGHTS, {}, config)
        ids = {h.id for h in result}
        assert "g1" in ids
        assert "b1" in ids
        assert "y1" not in ids

    def test_english_returns_yellow_and_blue(self):
        config = SessionConfig(focus_area=FocusArea.ENGLISH)
        result = select_highlights(ALL_HIGHLIGHTS, {}, config)
        ids = {h.id for h in result}
        assert "y1" in ids
        assert "b1" in ids
        assert "g1" not in ids

    def test_mixed_returns_all(self):
        config = SessionConfig(focus_area=FocusArea.MIXED)
        result = select_highlights(ALL_HIGHLIGHTS, {}, config)
        assert len(result) == 3

    def test_interview_returns_green_and_blue(self):
        config = SessionConfig(focus_area=FocusArea.INTERVIEW)
        result = select_highlights(ALL_HIGHLIGHTS, {}, config)
        ids = {h.id for h in result}
        assert "g1" in ids
        assert "b1" in ids
        assert "y1" not in ids


# --- Card selection ---

class TestSelectHighlightsCardSelection:
    def test_new_only_excludes_reviewed(self):
        records = {"g1": make_record("g1", mastery_score=3, days_until_due=7)}
        config = SessionConfig(focus_area=FocusArea.MIXED, card_selection=CardSelection.NEW_ONLY)
        result = select_highlights(ALL_HIGHLIGHTS, records, config)
        ids = {h.id for h in result}
        assert "g1" not in ids

    def test_new_only_includes_never_reviewed(self):
        records = {"g1": make_record("g1", mastery_score=3, days_until_due=7)}
        config = SessionConfig(focus_area=FocusArea.MIXED, card_selection=CardSelection.NEW_ONLY)
        result = select_highlights(ALL_HIGHLIGHTS, records, config)
        ids = {h.id for h in result}
        assert "y1" in ids
        assert "b1" in ids

    def test_weak_first_sorts_by_mastery_ascending(self):
        records = {
            "g1": make_record("g1", mastery_score=4, days_until_due=-1),
            "y1": make_record("y1", mastery_score=2, days_until_due=-1),
        }
        config = SessionConfig(focus_area=FocusArea.MIXED, card_selection=CardSelection.WEAK_FIRST)
        result = select_highlights(ALL_HIGHLIGHTS, records, config)
        # y1 (score=2) should come before g1 (score=4)
        ids = [h.id for h in result]
        assert ids.index("y1") < ids.index("g1")

    def test_all_includes_not_yet_due(self):
        records = {"g1": make_record("g1", mastery_score=5, days_until_due=14)}
        config = SessionConfig(focus_area=FocusArea.MIXED, card_selection=CardSelection.ALL)
        result = select_highlights(ALL_HIGHLIGHTS, records, config)
        ids = {h.id for h in result}
        assert "g1" in ids

    def test_weak_first_excludes_not_yet_due(self):
        records = {"g1": make_record("g1", mastery_score=5, days_until_due=14)}
        config = SessionConfig(focus_area=FocusArea.MIXED, card_selection=CardSelection.WEAK_FIRST)
        result = select_highlights(ALL_HIGHLIGHTS, records, config)
        ids = {h.id for h in result}
        assert "g1" not in ids


# --- Quiz generation ---

class TestGenerateQuizQuestions:
    def test_returns_requested_count(self):
        questions = generate_quiz_questions(ALL_HIGHLIGHTS, count=3)
        assert len(questions) == 3

    def test_count_capped_at_available_highlights(self):
        questions = generate_quiz_questions([GREEN], count=5)
        assert len(questions) == 1

    def test_define_type_from_concept_highlights(self):
        questions = generate_quiz_questions([GREEN], count=1)
        assert questions[0].type == QuizQuestionType.DEFINE

    def test_error_correction_from_english_highlights(self):
        questions = generate_quiz_questions([YELLOW], count=1)
        assert questions[0].type == QuizQuestionType.ERROR_CORRECTION

    def test_prompt_contains_highlight_text(self):
        questions = generate_quiz_questions([GREEN], count=1)
        assert "fault" in questions[0].prompt.lower() or "spec" in questions[0].prompt.lower()

    def test_default_time_limit_is_60(self):
        questions = generate_quiz_questions([GREEN], count=1)
        assert questions[0].time_limit_seconds == 60
