import sys
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, UploadFile, Form
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from notemaster import books, ai, stt
from notemaster.db import Database
from notemaster.models import (
    Highlight, EvaluationResult, FocusArea, CardSelection, SessionConfig, StudySession
)
from notemaster.session import select_highlights
from datetime import date

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


class AnswerTextRequest(BaseModel):
    highlight_id: str
    answer: str


class StatsResponse(BaseModel):
    streak: int
    heatmap: dict[str, int]
    sessions: list[StudySession]


# --- Endpoints ---

@app.post("/sync", response_model=SyncResponse)
def sync(req: SyncRequest, db: Database = Depends(get_db)):
    highlights = books.get_highlights(asset_id=req.asset_id)
    for h in highlights:
        h = Highlight(id=h.id, text=h.text, color=h.color, book_title=req.book_title, chapter=h.chapter)
        db.save_highlight(h)
    return SyncResponse(synced=len(highlights))


@app.get("/session/next", response_model=Highlight)
def session_next(
    focus_area: FocusArea = FocusArea.MIXED,
    card_selection: CardSelection = CardSelection.WEAK_FIRST,
    db: Database = Depends(get_db),
):
    config = SessionConfig(focus_area=focus_area, card_selection=card_selection)
    all_highlights = db.get_highlights()
    records = {
        h.id: db.get_review_record(h.id)
        for h in all_highlights
        if db.get_review_record(h.id) is not None
    }
    selected = select_highlights(all_highlights, records, config)
    if not selected:
        raise HTTPException(status_code=404, detail="No highlights due for review")
    return selected[0]


@app.post("/answer/text", response_model=EvaluationResult)
def answer_text(req: AnswerTextRequest, db: Database = Depends(get_db)):
    highlights = db.get_highlights()
    highlight = next((h for h in highlights if h.id == req.highlight_id), None)
    if highlight is None:
        raise HTTPException(status_code=404, detail="Highlight not found")
    result = ai.evaluate(highlight, req.answer)
    db.save_review_record(req.highlight_id, result.concept_score)
    return result


@app.post("/answer/voice", response_model=EvaluationResult)
async def answer_voice(
    highlight_id: str = Form(...),
    audio: UploadFile = ...,
    db: Database = Depends(get_db),
):
    highlights = db.get_highlights()
    highlight = next((h for h in highlights if h.id == highlight_id), None)
    if highlight is None:
        raise HTTPException(status_code=404, detail="Highlight not found")
    audio_bytes = await audio.read()
    transcript = stt.transcribe(audio_bytes, mime_type=audio.content_type or "audio/webm")
    result = ai.evaluate(highlight, transcript)
    db.save_review_record(highlight_id, result.concept_score)
    return result


@app.get("/stats", response_model=StatsResponse)
def stats(db: Database = Depends(get_db)):
    return StatsResponse(
        streak=db.get_streak(),
        heatmap=db.get_heatmap(),
        sessions=db.get_study_sessions(),
    )


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
        highlights = books.get_highlights(asset_id=asset_id)
        for h in highlights:
            h = Highlight(id=h.id, text=h.text, color=h.color, book_title=book_title, chapter=h.chapter)
            db.save_highlight(h)
        print(f"Synced {len(highlights)} highlights from '{book_title}'")

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
