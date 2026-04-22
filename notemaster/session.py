from datetime import datetime
from notemaster.models import (
    Highlight,
    HighlightColor,
    ReviewRecord,
    SessionConfig,
    FocusArea,
    CardSelection,
    QuizQuestion,
    QuizQuestionType,
)

_CONCEPT_COLORS = {HighlightColor.GREEN, HighlightColor.BLUE}
_ENGLISH_COLORS = {HighlightColor.YELLOW, HighlightColor.BLUE}


def _filter_by_focus(highlights: list[Highlight], focus: FocusArea) -> list[Highlight]:
    if focus in (FocusArea.CONCEPT, FocusArea.INTERVIEW):
        return [h for h in highlights if h.color in _CONCEPT_COLORS]
    if focus == FocusArea.ENGLISH:
        return [h for h in highlights if h.color in _ENGLISH_COLORS]
    return highlights  # MIXED


def select_highlights(
    highlights: list[Highlight],
    review_records: dict[str, ReviewRecord],
    config: SessionConfig,
) -> list[Highlight]:
    filtered = _filter_by_focus(highlights, config.focus_area)
    now = datetime.now()

    if config.card_selection == CardSelection.NEW_ONLY:
        return [h for h in filtered if h.id not in review_records]

    if config.card_selection == CardSelection.WEAK_FIRST:
        due = [h for h in filtered if _is_due(h, review_records, now)]
        return sorted(due, key=lambda h: review_records[h.id].mastery_score if h.id in review_records else 0)

    # ALL — include everything regardless of schedule
    return filtered


def _is_due(h: Highlight, records: dict[str, ReviewRecord], now: datetime) -> bool:
    if h.id not in records:
        return True
    return records[h.id].next_review_at <= now


def generate_quiz_questions(highlights: list[Highlight], count: int = 5) -> list[QuizQuestion]:
    selected = highlights[:count]
    questions = []
    for h in selected:
        if h.color in _CONCEPT_COLORS:
            q_type = QuizQuestionType.DEFINE
            prompt = f"Explain this concept in your own words: \"{h.text}\""
        else:
            q_type = QuizQuestionType.ERROR_CORRECTION
            prompt = f"Identify any unnatural or incorrect English in this sentence and suggest a better version: \"{h.text}\""
        questions.append(QuizQuestion(type=q_type, prompt=prompt))
    return questions
