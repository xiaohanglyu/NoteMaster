from enum import Enum
from datetime import date, datetime
from typing import Optional, Annotated
from pydantic import BaseModel, Field, field_validator


class HighlightColor(str, Enum):
    YELLOW = "yellow"
    GREEN = "green"
    BLUE = "blue"


class FocusArea(str, Enum):
    CONCEPT = "concept"
    ENGLISH = "english"
    MIXED = "mixed"
    INTERVIEW = "interview"


class CardSelection(str, Enum):
    ALL = "all"
    WEAK_FIRST = "weak_first"
    NEW_ONLY = "new_only"


class Highlight(BaseModel):
    id: str
    text: str
    color: HighlightColor
    book_title: str
    chapter: Optional[str] = None


Score = Annotated[int, Field(ge=1, le=5)]


class SessionConfig(BaseModel):
    duration_minutes: Annotated[int, Field(gt=0)] = 10
    focus_area: FocusArea = FocusArea.MIXED
    card_selection: CardSelection = CardSelection.WEAK_FIRST


class EvaluationResult(BaseModel):
    concept_feedback: str
    english_feedback: str
    concept_score: Score
    english_score: Score
    concept_suggestions: list[str]
    english_suggestions: list[str]


class QuizQuestionType(str, Enum):
    DEFINE = "define"
    ERROR_CORRECTION = "error_correction"
    SCENARIO = "scenario"


class QuizQuestion(BaseModel):
    type: QuizQuestionType
    prompt: str
    time_limit_seconds: int = 60


class ReviewRecord(BaseModel):
    highlight_id: str
    mastery_score: Score
    last_reviewed_at: datetime
    next_review_at: datetime


class StudySession(BaseModel):
    date: date
    duration_minutes: int
    items_reviewed: int
    quiz_score: Annotated[float, Field(ge=0.0, le=1.0)]
