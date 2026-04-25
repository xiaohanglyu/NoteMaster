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
    questions: list[str] = []
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


class EntryData(BaseModel):
    phonetics: Optional[str] = None
    translation: Optional[str] = None
    context_note: Optional[str] = None
    examples: list[str] = []
    tenses: list[str] = []
    word_forms: list[str] = []
    root: Optional[str] = None
    synonyms: list[str] = []
    derivatives: list[str] = []


class Entry(BaseModel):
    id: str
    text: str
    source_type: EntryType = EntryType.MANUAL
    source_ref: Optional[str] = None
    data: EntryData = EntryData()
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


# ---------------------------------------------------------------------------
# Inbox
# ---------------------------------------------------------------------------

class InboxItem(BaseModel):
    id: str
    content: str
    tags: list[str] = []
    created_at: datetime
    processed_at: Optional[datetime] = None

    @property
    def is_pending(self) -> bool:
        return self.processed_at is None


_INBOX_TYPES = {"english", "concept", "question", "unknown"}


class InboxClassification(BaseModel):
    item_type: str
    reasoning: str
    preview: dict

    @field_validator("item_type")
    @classmethod
    def valid_type(cls, v: str) -> str:
        if v not in _INBOX_TYPES:
            raise ValueError(f"item_type must be one of {_INBOX_TYPES}")
        return v


# ---------------------------------------------------------------------------
# Job Hunt models
# ---------------------------------------------------------------------------

class ApplicationStatus(str, Enum):
    APPLIED = "applied"
    PHONE = "phone"
    TECHNICAL = "technical"
    ONSITE = "onsite"
    OFFER = "offer"
    REJECTED = "rejected"


class ApplicationRound(BaseModel):
    id: Optional[int] = None
    application_id: str
    name: str
    date: Optional[str] = None
    feedback: Optional[str] = None


class Application(BaseModel):
    id: str
    company: str
    role: str
    status: ApplicationStatus = ApplicationStatus.APPLIED
    location: Optional[str] = None
    work_model: Optional[str] = None
    salary_range: Optional[str] = None
    job_link: Optional[str] = None
    resume_version: Optional[str] = None
    notes: Optional[str] = None
    applied_at: Optional[date] = None
    created_at: datetime


class QuestionType(str, Enum):
    BEHAVIORAL = "behavioral"
    SYSTEM_DESIGN = "system_design"
    CODING = "coding"
    OTHER = "other"


class QuestionSource(str, Enum):
    REAL = "real"
    MOCK = "mock"


class QuestionCategory(str, Enum):
    STUDY = "study"
    INTERVIEW = "interview"


class InterviewQuestion(BaseModel):
    id: str
    question: str
    answer: Optional[str] = None
    q_type: QuestionType = QuestionType.OTHER
    source: QuestionSource = QuestionSource.MOCK
    category: QuestionCategory = QuestionCategory.INTERVIEW
    application_id: Optional[str] = None
    round: Optional[str] = None
    self_score: int = 0
    tags: list[str] = []
    notes: Optional[str] = None
    ef: float = 2.5
    interval: int = 0
    reps: int = 0
    next_review_at: Optional[datetime] = None
    created_at: datetime


class QuestionReviewRecord(BaseModel):
    question_id: str
    grade: int
    reviewed_at: datetime
    next_review_at: datetime
    interval: int
    reps: int
    ef: float


class AIProvider(BaseModel):
    id: str
    name: str
    provider_type: str  # 'openai_compatible' | 'anthropic'
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model: str
    is_active: bool = False
    created_at: datetime
