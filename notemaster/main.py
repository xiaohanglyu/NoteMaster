import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, UploadFile, Form, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Annotated
from notemaster import books, ai, stt, importer, ocr
from notemaster.db import Database
from notemaster.models import (
    Book, Concept, ConceptEdge, RelationType, ConceptWithPriority,
    EvaluationResult, StudySession, Score,
    Entry, EntryType, PronunciationResult,
    Application, ApplicationStatus, ApplicationRound,
    InterviewQuestion, QuestionType, QuestionSource, QuestionReviewRecord,
)

_FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

app = FastAPI(title="NoteMaster")

_db: Database | None = None


def get_db() -> Database:
    global _db
    if _db is None:
        _db = Database()
    return _db


_synthesis_status: dict = {
    "running": False,
    "phase": "idle",       # idle | phase1 | phase2 | done | error
    "batch_current": 0,
    "batch_total": 0,
    "concepts_created": 0,
    "batch_errors": 0,
    "last_error": None,
    "edges_created": 0,
}


def _run_synthesis_bg(book_id: str):
    global _synthesis_status
    _synthesis_status = {
        "running": True, "phase": "phase1",
        "batch_current": 0, "batch_total": 0,
        "concepts_created": 0, "batch_errors": 0,
        "last_error": None, "edges_created": 0,
    }

    def on_progress(phase, batch_current, batch_total, concepts_created, error=None):
        _synthesis_status["phase"] = phase
        _synthesis_status["batch_current"] = batch_current
        _synthesis_status["batch_total"] = batch_total
        _synthesis_status["concepts_created"] = concepts_created
        if error:
            _synthesis_status["batch_errors"] += 1
            _synthesis_status["last_error"] = error

    try:
        result = ai.synthesize(book_id=book_id, db=get_db(), on_progress=on_progress)
        _synthesis_status["edges_created"] = result.get("edges", 0)
        _synthesis_status["phase"] = "done"
    except Exception as e:
        _synthesis_status["phase"] = "error"
        _synthesis_status["last_error"] = str(e)
    finally:
        _synthesis_status["running"] = False


# --- Request / Response models ---

class SyncRequest(BaseModel):
    asset_id: str
    book_title: str
    sections: Optional[list[str]] = None


class SyncResponse(BaseModel):
    synced: int
    entries_synced: int
    book_id: str


class SynthesizeRequest(BaseModel):
    book_id: str


class SynthesizeResponse(BaseModel):
    concepts: int
    edges: int


class AnswerTextRequest(BaseModel):
    concept_id: str
    answer: str


class ConceptUpdateRequest(BaseModel):
    title: Optional[str] = None
    summary: Optional[str] = None
    weight: Optional[float] = None


class RecordReviewRequest(BaseModel):
    mastery_score: Score


class AddEdgeRequest(BaseModel):
    from_concept_id: str
    to_concept_id: str
    relation: RelationType


class GraphResponse(BaseModel):
    nodes: list[dict]
    edges: list[dict]


class StatsResponse(BaseModel):
    streak: int
    heatmap: dict[str, int]
    sessions: list[StudySession]


# --- Books ---

@app.get("/books", response_model=list[Book])
def get_books(db: Database = Depends(get_db)):
    return db.get_books()


@app.get("/apple-books")
def apple_books():
    return books.list_apple_books()


# --- Sync & Synthesize ---

@app.post("/sync", response_model=SyncResponse)
def sync(req: SyncRequest, db: Database = Depends(get_db)):
    book = db.get_book_by_asset_id(req.asset_id)
    if book is None:
        book = Book(
            id=str(uuid.uuid4()),
            title=req.book_title,
            asset_id=req.asset_id,
            synced_at=datetime.now(),
        )
    else:
        book = Book(id=book.id, title=req.book_title, asset_id=req.asset_id,
                    synced_at=datetime.now())
    db.save_book(book)

    from notemaster.models import HighlightColor
    highlights = books.get_highlights(
        asset_id=req.asset_id, book_id=book.id, book_title=book.title,
        sections=req.sections or None,
    )
    entries_synced = 0
    for h in highlights:
        if h.color == HighlightColor.YELLOW:
            # Yellow = English expression; goes to vocabulary entries only, not concept graph
            entry = Entry(
                id=str(uuid.uuid4()),
                text=h.text,
                source_type=EntryType.HIGHLIGHT,
                source_ref=book.title,
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
            db.create_entry(entry)
            entries_synced += 1
        else:
            db.save_highlight(h)

    db.record_sync(book.id, highlights_synced=len(highlights),
                   sections=req.sections or None, book_title=book.title)
    return SyncResponse(synced=len(highlights), entries_synced=entries_synced, book_id=book.id)


@app.get("/sync/history")
def sync_history(book_id: Optional[str] = None, db: Database = Depends(get_db)):
    return db.get_sync_history(book_id=book_id)


@app.get("/apple-books/{asset_id}/sections")
def apple_book_sections(asset_id: str):
    return books.get_highlight_sections(asset_id)


@app.post("/synthesize")
def synthesize(req: SynthesizeRequest, background_tasks: BackgroundTasks):
    if _synthesis_status["running"]:
        raise HTTPException(status_code=409, detail="Synthesis already running")
    background_tasks.add_task(_run_synthesis_bg, req.book_id)
    return {"started": True, "book_id": req.book_id}


@app.get("/synthesize/status")
def synthesis_status():
    return _synthesis_status


# --- Concepts ---

@app.get("/concepts", response_model=list[Concept])
def list_concepts(book_id: Optional[str] = None, db: Database = Depends(get_db)):
    return db.get_concepts(book_id=book_id)


@app.get("/concepts/{concept_id}")
def get_concept(concept_id: str, db: Database = Depends(get_db)):
    concept = db.get_concept(concept_id)
    if concept is None:
        raise HTTPException(status_code=404, detail="Concept not found")
    # Return concept with full highlight texts
    all_highlights = db.get_highlights(book_id=concept.book_id)
    h_map = {h.id: h for h in all_highlights}
    highlight_texts = [
        {"id": hid, "text": h_map[hid].text, "color": h_map[hid].color.value}
        for hid in concept.highlight_ids if hid in h_map
    ]
    edges = db.get_edges(concept_id=concept_id)
    return {
        "id": concept.id,
        "title": concept.title,
        "summary": concept.summary,
        "book_id": concept.book_id,
        "weight": concept.weight,
        "highlight_ids": concept.highlight_ids,
        "highlights": highlight_texts,
        "edges": [
            {"from": e.from_concept_id, "to": e.to_concept_id, "relation": e.relation.value}
            for e in edges
        ],
        "created_at": concept.created_at.isoformat(),
        "updated_at": concept.updated_at.isoformat(),
    }


@app.patch("/concepts/{concept_id}", response_model=Concept)
def update_concept(concept_id: str, req: ConceptUpdateRequest, db: Database = Depends(get_db)):
    concept = db.update_concept(concept_id, title=req.title, summary=req.summary, weight=req.weight)
    if concept is None:
        raise HTTPException(status_code=404, detail="Concept not found")
    return concept


@app.delete("/concepts/{concept_id}", status_code=204)
def delete_concept(concept_id: str, db: Database = Depends(get_db)):
    deleted = db.delete_concept(concept_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Concept not found")


@app.post("/concepts/{concept_id}/review")
def record_review(concept_id: str, req: RecordReviewRequest, db: Database = Depends(get_db)):
    try:
        record = db.record_review(concept_id, req.mastery_score)
        concept = db.get_concept(concept_id)
        return {
            "concept_id": concept_id,
            "mastery_score": req.mastery_score,
            "new_weight": concept.weight if concept else None,
            "next_review_at": record.next_review_at.isoformat(),
        }
    except ValueError:
        raise HTTPException(status_code=404, detail="Concept not found")


# --- Session ---

def _build_unified_queue(db: Database, limit: int = 20) -> list[dict]:
    from datetime import datetime as dt

    items: list[dict] = []

    for cwp in db.get_due_concepts(limit=limit):
        items.append({
            "note_type": "concept",
            "priority": cwp.priority,
            "days_overdue": cwp.days_overdue,
            "item": {
                "id": cwp.concept.id,
                "title": cwp.concept.title,
                "summary": cwp.concept.summary,
                "weight": cwp.concept.weight,
            },
        })

    for ewp in db.get_due_entries(limit=limit):
        items.append({
            "note_type": "entry",
            "priority": ewp.priority,
            "days_overdue": ewp.days_overdue,
            "item": {
                "id": ewp.entry.id,
                "text": ewp.entry.text,
                "weight": ewp.entry.weight,
            },
        })

    for q in db.get_questions(due_only=True):
        now = dt.now()
        next_rev = q.next_review_at or now
        days_overdue = max(0.0, (now - next_rev).total_seconds() / 86400)
        priority = 1.0 * (1 + days_overdue)
        items.append({
            "note_type": "question",
            "priority": priority,
            "days_overdue": days_overdue,
            "item": _question_to_dict(q),
        })

    items.sort(key=lambda x: x["priority"], reverse=True)
    return items[:limit]


@app.get("/session/next")
def session_next(include_questions: bool = False, db: Database = Depends(get_db)):
    if include_questions:
        items = _build_unified_queue(db, limit=1)
        if not items:
            raise HTTPException(status_code=404, detail="Nothing due for review")
        return items[0]

    items = db.get_due_concepts(limit=1)
    if not items:
        raise HTTPException(status_code=404, detail="No concepts due for review")
    return items[0].concept


@app.get("/session/queue")
def session_queue(limit: int = 20, include_questions: bool = False, db: Database = Depends(get_db)):
    if include_questions:
        return _build_unified_queue(db, limit=limit)
    return db.get_due_concepts(limit=limit)


# --- Answer ---

@app.post("/answer/text", response_model=EvaluationResult)
def answer_text(req: AnswerTextRequest, db: Database = Depends(get_db)):
    concept = db.get_concept(req.concept_id)
    if concept is None:
        raise HTTPException(status_code=404, detail="Concept not found")
    return ai.evaluate(concept, req.answer)


@app.post("/answer/voice", response_model=EvaluationResult)
async def answer_voice(
    concept_id: str = Form(...),
    audio: UploadFile = ...,
    db: Database = Depends(get_db),
):
    concept = db.get_concept(concept_id)
    if concept is None:
        raise HTTPException(status_code=404, detail="Concept not found")
    audio_bytes = await audio.read()
    transcript = stt.transcribe(audio_bytes, mime_type=audio.content_type or "audio/webm")
    return ai.evaluate(concept, transcript)


# --- Graph ---

@app.get("/graph/books")
def graph_books(db: Database = Depends(get_db)):
    return [{"id": b.id, "title": b.title} for b in db.get_books()]


@app.get("/graph")
def graph(book_id: Optional[str] = None, include_questions: bool = False, db: Database = Depends(get_db)):
    concepts = db.get_concepts(book_id=book_id)
    edges = db.get_edges()
    concept_ids = {c.id for c in concepts}

    nodes = [
        {"id": c.id, "title": c.title, "weight": c.weight, "book_id": c.book_id, "node_type": "concept"}
        for c in concepts
    ]
    filtered_edges = [
        {"from": e.from_concept_id, "to": e.to_concept_id, "relation": e.relation.value}
        for e in edges
        if e.from_concept_id in concept_ids and e.to_concept_id in concept_ids
    ]

    if include_questions:
        questions = db.get_questions()
        for q in questions:
            linked = db.get_question_concepts(q.id)
            linked_in_view = [c for c in linked if c.id in concept_ids]
            if linked_in_view or not book_id:
                nodes.append({
                    "id": q.id,
                    "title": q.question[:60],
                    "q_type": q.q_type.value,
                    "node_type": "question",
                })
                for c in linked_in_view if book_id else linked:
                    filtered_edges.append({"from": c.id, "to": q.id, "relation": "tested_by"})

    return {"nodes": nodes, "edges": filtered_edges}


@app.post("/graph/edges")
def add_edge(req: AddEdgeRequest, db: Database = Depends(get_db)):
    edge = ConceptEdge(
        from_concept_id=req.from_concept_id,
        to_concept_id=req.to_concept_id,
        relation=req.relation,
    )
    db.create_edge(edge)
    return {"from": edge.from_concept_id, "to": edge.to_concept_id, "relation": edge.relation.value}


@app.delete("/graph/edges/{from_concept_id}/{to_concept_id}")
def delete_edge(from_concept_id: str, to_concept_id: str, db: Database = Depends(get_db)):
    db.delete_edge(from_concept_id, to_concept_id)
    return {"ok": True}


# --- Stats ---

@app.get("/stats", response_model=StatsResponse)
def stats(db: Database = Depends(get_db)):
    return StatsResponse(
        streak=db.get_streak(),
        heatmap=db.get_heatmap(),
        sessions=db.get_study_sessions(),
    )


# --- Entries ---

class CreateEntryRequest(BaseModel):
    text: str
    source_type: EntryType = EntryType.MANUAL
    source_ref: Optional[str] = None
    context_note: Optional[str] = None


class UpdateEntryRequest(BaseModel):
    text: Optional[str] = None
    phonetics: Optional[str] = None
    examples: Optional[list[str]] = None
    context_note: Optional[str] = None


class RecordEntryReviewRequest(BaseModel):
    mastery_score: Score


def _bg_enrich(entry_id: str, db: Database):
    try:
        entry = db.get_entry(entry_id)
        if entry is None:
            return
        result = ai.enrich_entry(entry)
        # Only set context_note from AI if user hasn't written one manually
        context_note = None if entry.context_note else result.get("context_note")
        db.update_entry(entry_id, phonetics=result.get("phonetics"),
                        examples=result.get("examples"), context_note=context_note)
    except Exception:
        pass


@app.post("/entries", response_model=Entry)
def create_entry(req: CreateEntryRequest, background_tasks: BackgroundTasks, db: Database = Depends(get_db)):
    entry = Entry(
        id=str(uuid.uuid4()),
        text=req.text,
        source_type=req.source_type,
        source_ref=req.source_ref,
        context_note=req.context_note,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    db.create_entry(entry)
    background_tasks.add_task(_bg_enrich, entry.id, db)
    return entry


@app.post("/entries/enrich-all")
def enrich_all_entries(background_tasks: BackgroundTasks, db: Database = Depends(get_db)):
    pending = [e for e in db.get_entries() if not e.phonetics]
    for e in pending:
        background_tasks.add_task(_bg_enrich, e.id, db)
    return {"queued": len(pending)}


@app.post("/entries/{entry_id}/answer/voice", response_model=PronunciationResult)
async def entry_answer_voice(
    entry_id: str,
    audio: UploadFile = ...,
    db: Database = Depends(get_db),
):
    entry = db.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Entry not found")
    audio_bytes = await audio.read()
    transcript = stt.transcribe(audio_bytes, mime_type=audio.content_type or "audio/webm")
    return ai.check_pronunciation(entry, transcript)


@app.post("/entries/{entry_id}/enrich", response_model=Entry)
def enrich_entry(entry_id: str, db: Database = Depends(get_db)):
    entry = db.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Entry not found")
    result = ai.enrich_entry(entry)
    return db.update_entry(entry_id,
                           phonetics=result.get("phonetics"),
                           examples=result.get("examples"),
                           context_note=result.get("context_note"))


@app.get("/entries/next", response_model=Entry)
def next_entry(db: Database = Depends(get_db)):
    items = db.get_due_entries(limit=1)
    if not items:
        raise HTTPException(status_code=404, detail="No entries due for review")
    return items[0].entry


@app.get("/entries", response_model=list[Entry])
def list_entries(source_type: Optional[EntryType] = None, db: Database = Depends(get_db)):
    return db.get_entries(source_type=source_type)


@app.get("/entries/{entry_id}", response_model=Entry)
def get_entry(entry_id: str, db: Database = Depends(get_db)):
    entry = db.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Entry not found")
    return entry


@app.patch("/entries/{entry_id}", response_model=Entry)
def update_entry(entry_id: str, req: UpdateEntryRequest, db: Database = Depends(get_db)):
    entry = db.update_entry(
        entry_id,
        text=req.text,
        phonetics=req.phonetics,
        examples=req.examples,
        context_note=req.context_note,
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="Entry not found")
    return entry


@app.delete("/entries/{entry_id}", status_code=204)
def delete_entry(entry_id: str, db: Database = Depends(get_db)):
    deleted = db.delete_entry(entry_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Entry not found")


@app.post("/entries/{entry_id}/review")
def record_entry_review(entry_id: str, req: RecordEntryReviewRequest, db: Database = Depends(get_db)):
    try:
        record = db.record_entry_review(entry_id, req.mastery_score)
        entry = db.get_entry(entry_id)
        return {
            "entry_id": entry_id,
            "mastery_score": req.mastery_score,
            "new_weight": round(entry.weight, 3) if entry else None,
            "next_review_at": record.next_review_at.isoformat(),
        }
    except ValueError:
        raise HTTPException(status_code=404, detail="Entry not found")


# --- Applications ---

class CreateApplicationRequest(BaseModel):
    company: str
    role: str
    status: ApplicationStatus = ApplicationStatus.APPLIED
    location: Optional[str] = None
    work_model: Optional[str] = None
    salary_range: Optional[str] = None
    job_link: Optional[str] = None
    resume_version: Optional[str] = None
    notes: Optional[str] = None
    applied_at: Optional[str] = None


class UpdateApplicationRequest(BaseModel):
    status: Optional[ApplicationStatus] = None
    location: Optional[str] = None
    work_model: Optional[str] = None
    salary_range: Optional[str] = None
    job_link: Optional[str] = None
    resume_version: Optional[str] = None
    notes: Optional[str] = None
    applied_at: Optional[str] = None


class AddRoundRequest(BaseModel):
    name: str
    date: Optional[str] = None
    feedback: Optional[str] = None


class UpdateRoundRequest(BaseModel):
    name: Optional[str] = None
    date: Optional[str] = None
    feedback: Optional[str] = None


class ApplicationWithRounds(BaseModel):
    id: str
    company: str
    role: str
    status: ApplicationStatus
    location: Optional[str] = None
    work_model: Optional[str] = None
    salary_range: Optional[str] = None
    job_link: Optional[str] = None
    resume_version: Optional[str] = None
    notes: Optional[str] = None
    applied_at: Optional[str] = None
    created_at: str
    rounds: list[ApplicationRound] = []


def _app_to_dict(app: Application) -> dict:
    return {
        "id": app.id,
        "company": app.company,
        "role": app.role,
        "status": app.status.value,
        "location": app.location,
        "work_model": app.work_model,
        "salary_range": app.salary_range,
        "job_link": app.job_link,
        "resume_version": app.resume_version,
        "notes": app.notes,
        "applied_at": app.applied_at.isoformat() if app.applied_at else None,
        "created_at": app.created_at.isoformat(),
    }


@app.get("/applications")
def list_applications(status: Optional[ApplicationStatus] = None, db: Database = Depends(get_db)):
    apps = db.get_applications(status=status)
    return [_app_to_dict(a) for a in apps]


@app.post("/applications", status_code=201)
def create_application(req: CreateApplicationRequest, db: Database = Depends(get_db)):
    from datetime import date as date_type
    app_obj = Application(
        id=str(uuid.uuid4()),
        company=req.company,
        role=req.role,
        status=req.status,
        location=req.location,
        work_model=req.work_model,
        salary_range=req.salary_range,
        job_link=req.job_link,
        resume_version=req.resume_version,
        notes=req.notes,
        applied_at=date_type.fromisoformat(req.applied_at) if req.applied_at else None,
        created_at=datetime.now(),
    )
    db.create_application(app_obj)
    return _app_to_dict(app_obj)


@app.get("/applications/{app_id}")
def get_application(app_id: str, db: Database = Depends(get_db)):
    app_obj = db.get_application(app_id)
    if app_obj is None:
        raise HTTPException(status_code=404, detail="Application not found")
    rounds = db.get_application_rounds(app_id)
    result = _app_to_dict(app_obj)
    result["rounds"] = [
        {"id": r.id, "name": r.name, "date": r.date, "feedback": r.feedback}
        for r in rounds
    ]
    return result


@app.patch("/applications/{app_id}")
def update_application(app_id: str, req: UpdateApplicationRequest, db: Database = Depends(get_db)):
    updates = req.model_dump(exclude_none=True)
    updated = db.update_application(app_id, **updates)
    if updated is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return _app_to_dict(updated)


@app.delete("/applications/{app_id}", status_code=204)
def delete_application(app_id: str, db: Database = Depends(get_db)):
    if db.get_application(app_id) is None:
        raise HTTPException(status_code=404, detail="Application not found")
    db.delete_application(app_id)


@app.post("/applications/{app_id}/rounds", status_code=201)
def add_round(app_id: str, req: AddRoundRequest, db: Database = Depends(get_db)):
    if db.get_application(app_id) is None:
        raise HTTPException(status_code=404, detail="Application not found")
    r = db.add_application_round(app_id, name=req.name, date=req.date, feedback=req.feedback)
    return {"id": r.id, "application_id": r.application_id, "name": r.name,
            "date": r.date, "feedback": r.feedback}


@app.patch("/applications/{app_id}/rounds/{round_id}")
def update_round(app_id: str, round_id: int, req: UpdateRoundRequest, db: Database = Depends(get_db)):
    updates = req.model_dump(exclude_none=True)
    r = db.update_application_round(round_id, **updates)
    if r is None:
        raise HTTPException(status_code=404, detail="Round not found")
    return {"id": r.id, "application_id": r.application_id, "name": r.name,
            "date": r.date, "feedback": r.feedback}


# --- Questions ---

class CreateQuestionRequest(BaseModel):
    question: str
    answer: Optional[str] = None
    q_type: QuestionType = QuestionType.OTHER
    source: QuestionSource = QuestionSource.MOCK
    application_id: Optional[str] = None
    round: Optional[str] = None
    self_score: int = 0
    tags: list[str] = []
    notes: Optional[str] = None


class UpdateQuestionRequest(BaseModel):
    question: Optional[str] = None
    answer: Optional[str] = None
    q_type: Optional[QuestionType] = None
    source: Optional[QuestionSource] = None
    application_id: Optional[str] = None
    round: Optional[str] = None
    self_score: Optional[int] = None
    tags: Optional[list[str]] = None
    notes: Optional[str] = None


class ReviewQuestionRequest(BaseModel):
    grade: Annotated[int, Field(ge=1, le=3)]


def _question_to_dict(q: InterviewQuestion) -> dict:
    return {
        "id": q.id,
        "question": q.question,
        "answer": q.answer,
        "q_type": q.q_type.value,
        "source": q.source.value,
        "application_id": q.application_id,
        "round": q.round,
        "self_score": q.self_score,
        "tags": q.tags,
        "notes": q.notes,
        "ef": q.ef,
        "interval": q.interval,
        "reps": q.reps,
        "next_review_at": q.next_review_at.isoformat() if q.next_review_at else None,
        "created_at": q.created_at.isoformat(),
    }


@app.get("/questions")
def list_questions(
    q_type: Optional[QuestionType] = None,
    source: Optional[QuestionSource] = None,
    application_id: Optional[str] = None,
    due_only: bool = False,
    db: Database = Depends(get_db),
):
    questions = db.get_questions(
        q_type=q_type, source=source, application_id=application_id, due_only=due_only
    )
    return [_question_to_dict(q) for q in questions]


@app.get("/questions/next")
def next_due_question(db: Database = Depends(get_db)):
    q = db.get_next_due_question()
    if q is None:
        raise HTTPException(status_code=404, detail="No questions due for review")
    return _question_to_dict(q)


@app.post("/questions", status_code=201)
def create_question(req: CreateQuestionRequest, db: Database = Depends(get_db)):
    q = InterviewQuestion(
        id=str(uuid.uuid4()),
        question=req.question,
        answer=req.answer,
        q_type=req.q_type,
        source=req.source,
        application_id=req.application_id,
        round=req.round,
        self_score=req.self_score,
        tags=req.tags,
        notes=req.notes,
        created_at=datetime.now(),
    )
    db.create_question(q)
    return _question_to_dict(q)


class ExtractQuestionsRequest(BaseModel):
    text: Annotated[str, Field(min_length=1)]


@app.post("/questions/extract")
def extract_questions_from_text(req: ExtractQuestionsRequest):
    """Use AI to extract Q&A pairs from a transcript or markdown text."""
    return ai.extract_questions(req.text)


@app.post("/questions/import")
def import_questions(questions: list[CreateQuestionRequest], db: Database = Depends(get_db)):
    objs = [
        InterviewQuestion(
            id=str(uuid.uuid4()),
            question=q.question,
            answer=q.answer,
            q_type=q.q_type,
            source=q.source,
            application_id=q.application_id,
            round=q.round,
            self_score=q.self_score,
            tags=q.tags,
            notes=q.notes,
            created_at=datetime.now(),
        )
        for q in questions
    ]
    count = db.bulk_import_questions(objs)
    return {"imported": count}


@app.get("/questions/{question_id}")
def get_question(question_id: str, db: Database = Depends(get_db)):
    q = db.get_question(question_id)
    if q is None:
        raise HTTPException(status_code=404, detail="Question not found")
    return _question_to_dict(q)


@app.patch("/questions/{question_id}")
def update_question(question_id: str, req: UpdateQuestionRequest, db: Database = Depends(get_db)):
    updates = req.model_dump(exclude_none=True)
    q = db.update_question(question_id, **updates)
    if q is None:
        raise HTTPException(status_code=404, detail="Question not found")
    return _question_to_dict(q)


@app.delete("/questions/{question_id}", status_code=204)
def delete_question(question_id: str, db: Database = Depends(get_db)):
    if db.get_question(question_id) is None:
        raise HTTPException(status_code=404, detail="Question not found")
    db.delete_question(question_id)


@app.get("/questions/{question_id}/concepts")
def get_question_concepts(question_id: str, db: Database = Depends(get_db)):
    if db.get_question(question_id) is None:
        raise HTTPException(status_code=404, detail="Question not found")
    concepts = db.get_question_concepts(question_id)
    return [{"id": c.id, "title": c.title, "book_id": c.book_id} for c in concepts]


class LinkConceptRequest(BaseModel):
    concept_id: str


@app.post("/questions/{question_id}/concepts", status_code=201)
def link_concept(question_id: str, req: LinkConceptRequest, db: Database = Depends(get_db)):
    if db.get_question(question_id) is None:
        raise HTTPException(status_code=404, detail="Question not found")
    if db.get_concept(req.concept_id) is None:
        raise HTTPException(status_code=404, detail="Concept not found")
    db.link_question_concept(question_id, req.concept_id)
    return {"question_id": question_id, "concept_id": req.concept_id}


@app.delete("/questions/{question_id}/concepts/{concept_id}", status_code=204)
def unlink_concept(question_id: str, concept_id: str, db: Database = Depends(get_db)):
    db.unlink_question_concept(question_id, concept_id)


@app.get("/concepts/{concept_id}/questions")
def get_concept_questions(concept_id: str, db: Database = Depends(get_db)):
    if db.get_concept(concept_id) is None:
        raise HTTPException(status_code=404, detail="Concept not found")
    questions = db.get_concept_questions(concept_id)
    return [_question_to_dict(q) for q in questions]


@app.post("/questions/{question_id}/review")
def review_question(question_id: str, req: ReviewQuestionRequest, db: Database = Depends(get_db)):
    try:
        record = db.record_question_review(question_id, grade=req.grade)
        return {
            "question_id": record.question_id,
            "grade": record.grade,
            "next_review_at": record.next_review_at.isoformat(),
            "interval": record.interval,
            "reps": record.reps,
            "ef": round(record.ef, 4),
        }
    except ValueError:
        raise HTTPException(status_code=404, detail="Question not found")


# --- Import: file ---

class ImportFileResponse(BaseModel):
    book_id: str
    highlights: int


@app.post("/import/file", response_model=ImportFileResponse)
async def import_file(file: UploadFile, db: Database = Depends(get_db)):
    mime = (file.content_type or "").split(";")[0].strip()
    raw = await file.read()
    if mime == "text/plain":
        paragraphs = importer.parse_text_file(raw.decode("utf-8", errors="replace"))
    elif mime == "text/markdown":
        paragraphs = importer.parse_md_file(raw.decode("utf-8", errors="replace"))
    elif mime == "application/pdf":
        paragraphs = importer.parse_pdf_file(raw)
    else:
        raise HTTPException(status_code=422, detail=f"Unsupported file type: {mime}")

    book_id = str(uuid.uuid4())
    book_title = file.filename or "Imported file"
    book = Book(id=book_id, title=book_title,
                asset_id=f"import-{book_id}", synced_at=datetime.now())
    db.save_book(book)

    for para in paragraphs:
        from notemaster.models import Highlight, HighlightColor
        h = Highlight(id=str(uuid.uuid4()), text=para, color=HighlightColor.GREEN,
                      book_id=book_id, book_title=book_title)
        db.save_highlight(h)

    return ImportFileResponse(book_id=book_id, highlights=len(paragraphs))


# --- Import: image (OCR) ---

@app.post("/import/image", response_model=list[Entry])
async def import_image(
    image: UploadFile,
    background_tasks: BackgroundTasks,
    db: Database = Depends(get_db),
):
    image_bytes = await image.read()
    raw_text = ocr.ocr_image(image_bytes)

    lines = [ln.strip() for ln in raw_text.splitlines() if len(ln.strip()) >= 3]
    entries = []
    for line in lines:
        entry = Entry(
            id=str(uuid.uuid4()),
            text=line,
            source_type=EntryType.OCR,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        db.create_entry(entry)
        background_tasks.add_task(_bg_enrich, entry.id, db)
        entries.append(entry)

    return entries


# Serve frontend — must be mounted after all API routes
if _FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIR), html=True), name="frontend")


# --- CLI ---

def main():
    import uvicorn
    if len(sys.argv) < 2:
        print("Usage: python -m notemaster [serve|sync]")
        sys.exit(1)

    command = sys.argv[1]

    if command == "serve":
        uvicorn.run("notemaster.main:app", host="0.0.0.0", port=8000, reload=True)

    elif command == "sync":
        if len(sys.argv) < 4:
            print("Usage: python -m notemaster sync <asset_id> <book_title>")
            sys.exit(1)
        asset_id, book_title = sys.argv[2], sys.argv[3]
        db = get_db()
        book = db.get_book_by_asset_id(asset_id)
        if book is None:
            book = Book(id=str(uuid.uuid4()), title=book_title, asset_id=asset_id,
                        synced_at=datetime.now())
            db.save_book(book)
        highlights = books.get_highlights(
            asset_id=asset_id, book_id=book.id, book_title=book_title
        )
        for h in highlights:
            db.save_highlight(h)
        print(f"Synced {len(highlights)} highlights from '{book_title}' (book_id={book.id})")

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
