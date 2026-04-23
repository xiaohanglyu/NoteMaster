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
)

_FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

app = FastAPI(title="NoteMaster")

_db: Database | None = None


def get_db() -> Database:
    global _db
    if _db is None:
        _db = Database()
    return _db


# --- Request / Response models ---

class SyncRequest(BaseModel):
    asset_id: str
    book_title: str


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
    )
    entries_synced = 0
    for h in highlights:
        db.save_highlight(h)
        if h.color in (HighlightColor.YELLOW, HighlightColor.BLUE):
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

    return SyncResponse(synced=len(highlights), entries_synced=entries_synced, book_id=book.id)


@app.post("/synthesize", response_model=SynthesizeResponse)
def synthesize(req: SynthesizeRequest, db: Database = Depends(get_db)):
    result = ai.synthesize(book_id=req.book_id, db=db)
    return SynthesizeResponse(**result)


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
    concept = db.update_concept(concept_id, title=req.title, summary=req.summary)
    if concept is None:
        raise HTTPException(status_code=404, detail="Concept not found")
    return concept


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

@app.get("/session/next", response_model=Concept)
def session_next(db: Database = Depends(get_db)):
    items = db.get_due_concepts(limit=1)
    if not items:
        raise HTTPException(status_code=404, detail="No concepts due for review")
    return items[0].concept


@app.get("/session/queue", response_model=list[ConceptWithPriority])
def session_queue(limit: int = 20, db: Database = Depends(get_db)):
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

@app.get("/graph", response_model=GraphResponse)
def graph(book_id: Optional[str] = None, db: Database = Depends(get_db)):
    concepts = db.get_concepts(book_id=book_id)
    edges = db.get_edges()
    # Filter edges to only those between concepts in this book
    concept_ids = {c.id for c in concepts}
    return GraphResponse(
        nodes=[
            {"id": c.id, "title": c.title, "weight": c.weight, "book_id": c.book_id}
            for c in concepts
        ],
        edges=[
            {"from": e.from_concept_id, "to": e.to_concept_id, "relation": e.relation.value}
            for e in edges
            if e.from_concept_id in concept_ids and e.to_concept_id in concept_ids
        ],
    )


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
        db.update_entry(entry_id, phonetics=result.get("phonetics"),
                        examples=result.get("examples"), context_note=result.get("context_note"))
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
