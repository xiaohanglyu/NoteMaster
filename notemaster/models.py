from enum import Enum
from datetime import date, datetime
from typing import Optional, Annotated
from pydantic import BaseModel, Field, field_validator


class HighlightColor(str, Enum):
    YELLOW = "yellow"
    GREEN = "green"
    BLUE = "blue"


class RelationType(str, Enum):
    DEPENDS_ON = "depends_on"
    CONTRASTS_WITH = "contrasts_with"
    PART_OF = "part_of"
    EXAMPLE_OF = "example_of"


class FocusArea(str, Enum):
    CONCEPT = "concept"
    ENGLISH = "english"
    MIXED = "mixed"
    INTERVIEW = "interview"


class CardSelection(str, Enum):
    ALL = "all"
    WEAK_FIRST = "weak_first"
    NEW_ONLY = "new_only"


class Book(BaseModel):
    id: str
    title: str
    asset_id: str
    synced_at: datetime


class Highlight(BaseModel):
    id: str
    text: str
    color: HighlightColor
    book_id: str
    book_title: str
    chapter: Optional[str] = None


class Concept(BaseModel):
    id: str
    title: str
    summary: str
    book_id: str
    highlight_ids: list[str]
    weight: float
    created_at: datetime
    updated_at: datetime


class ConceptEdge(BaseModel):
    from_concept_id: str
    to_concept_id: str
    relation: RelationType


Score = Annotated[int, Field(ge=1, le=5)]


class QuizQuestionType(str, Enum):
    DEFINE = "define"
    ERROR_CORRECTION = "error_correction"
    SCENARIO = "scenario"


class QuizQuestion(BaseModel):
    type: QuizQuestionType
    prompt: str
    time_limit_seconds: int = 60


# Legacy model used by session.py highlight-level filtering
class ReviewRecord(BaseModel):
    highlight_id: str
    mastery_score: Score
    last_reviewed_at: datetime
    next_review_at: datetime


# Concept-level review record returned by db.record_review()
class ConceptReviewRecord(BaseModel):
    concept_id: str
    mastery_score: Score
    reviewed_at: datetime
    next_review_at: datetime


class ConceptWithPriority(BaseModel):
    concept: Concept
    priority: float
    days_overdue: float
    last_mastery: Optional[Score] = None


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


class StudySession(BaseModel):
    date: date
    duration_minutes: int
    items_reviewed: int
    quiz_score: Annotated[float, Field(ge=0.0, le=1.0)]


class EntryType(str, Enum):
    MANUAL = "manual"
    HIGHLIGHT = "highlight"
    OCR = "ocr"


class Entry(BaseModel):
    id: str
    text: str
    source_type: EntryType = EntryType.MANUAL
    source_ref: Optional[str] = None
    phonetics: Optional[str] = None
    examples: list[str] = []
    context_note: Optional[str] = None
    weight: float = 1.0
    created_at: datetime
    updated_at: datetime


class EntryReviewRecord(BaseModel):
    entry_id: str
    mastery_score: Score
    reviewed_at: datetime
    next_review_at: datetime


class EntryWithPriority(BaseModel):
    entry: Entry
    priority: float
    days_overdue: float
    last_mastery: Optional[Score] = None


class PronunciationResult(BaseModel):
    heard: str
    match: bool
    score: float
