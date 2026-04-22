import sqlite3
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional
from notemaster.models import Highlight, HighlightColor, ReviewRecord, StudySession

_DEFAULT_DB_PATH = Path(__file__).parent.parent / "data" / "notemaster.db"

_SM2_INTERVALS: dict[int, int] = {1: 1, 2: 3, 3: 7, 4: 14, 5: 30}


def _row_to_highlight(row: sqlite3.Row) -> Highlight:
    return Highlight(
        id=row["id"],
        text=row["text"],
        color=HighlightColor(row["color"]),
        book_title=row["book_title"],
        chapter=row["chapter"],
    )


class Database:
    def __init__(self, path: str | Path = _DEFAULT_DB_PATH):
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS highlights (
                id      TEXT PRIMARY KEY,
                text    TEXT NOT NULL,
                color   TEXT NOT NULL,
                book_title TEXT NOT NULL,
                chapter TEXT
            );
            CREATE TABLE IF NOT EXISTS review_records (
                highlight_id    TEXT PRIMARY KEY,
                mastery_score   INTEGER NOT NULL,
                last_reviewed_at TEXT NOT NULL,
                next_review_at   TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS study_sessions (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                date            TEXT NOT NULL,
                duration_minutes INTEGER NOT NULL,
                items_reviewed  INTEGER NOT NULL,
                quiz_score      REAL NOT NULL
            );
        """)

    # --- Highlights ---

    def save_highlight(self, h: Highlight):
        self.conn.execute(
            """
            INSERT INTO highlights (id, text, color, book_title, chapter)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                text=excluded.text,
                color=excluded.color,
                book_title=excluded.book_title,
                chapter=excluded.chapter
            """,
            (h.id, h.text, h.color.value, h.book_title, h.chapter),
        )
        self.conn.commit()

    def get_highlights(self, color: Optional[HighlightColor] = None) -> list[Highlight]:
        query = "SELECT * FROM highlights"
        params: tuple = ()
        if color:
            query += " WHERE color = ?"
            params = (color.value,)
        rows = self.conn.execute(query, params).fetchall()
        return [_row_to_highlight(row) for row in rows]

    # --- Review Records ---

    def save_review_record(
        self,
        highlight_id: str,
        mastery_score: int,
        next_review_at: Optional[datetime] = None,
    ):
        now = datetime.now()
        if next_review_at is None:
            days = _SM2_INTERVALS.get(mastery_score, 7)
            next_review_at = now + timedelta(days=days)
        self.conn.execute(
            """
            INSERT INTO review_records (highlight_id, mastery_score, last_reviewed_at, next_review_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(highlight_id) DO UPDATE SET
                mastery_score=excluded.mastery_score,
                last_reviewed_at=excluded.last_reviewed_at,
                next_review_at=excluded.next_review_at
            """,
            (highlight_id, mastery_score, now.isoformat(), next_review_at.isoformat()),
        )
        self.conn.commit()

    def get_review_record(self, highlight_id: str) -> Optional[ReviewRecord]:
        row = self.conn.execute(
            "SELECT * FROM review_records WHERE highlight_id = ?", (highlight_id,)
        ).fetchone()
        if row is None:
            return None
        return ReviewRecord(
            highlight_id=row["highlight_id"],
            mastery_score=row["mastery_score"],
            last_reviewed_at=datetime.fromisoformat(row["last_reviewed_at"]),
            next_review_at=datetime.fromisoformat(row["next_review_at"]),
        )

    def get_due_highlights(self) -> list[Highlight]:
        now = datetime.now().isoformat()
        rows = self.conn.execute(
            """
            SELECT h.* FROM highlights h
            LEFT JOIN review_records r ON h.id = r.highlight_id
            WHERE r.highlight_id IS NULL OR r.next_review_at <= ?
            """,
            (now,),
        ).fetchall()
        return [_row_to_highlight(row) for row in rows]

    # --- Study Sessions ---

    def save_study_session(self, session: StudySession):
        self.conn.execute(
            """
            INSERT INTO study_sessions (date, duration_minutes, items_reviewed, quiz_score)
            VALUES (?, ?, ?, ?)
            """,
            (session.date.isoformat(), session.duration_minutes, session.items_reviewed, session.quiz_score),
        )
        self.conn.commit()

    def get_study_sessions(self) -> list[StudySession]:
        rows = self.conn.execute(
            "SELECT * FROM study_sessions ORDER BY date DESC"
        ).fetchall()
        return [
            StudySession(
                date=date.fromisoformat(row["date"]),
                duration_minutes=row["duration_minutes"],
                items_reviewed=row["items_reviewed"],
                quiz_score=row["quiz_score"],
            )
            for row in rows
        ]

    def get_streak(self) -> int:
        rows = self.conn.execute(
            "SELECT DISTINCT date FROM study_sessions ORDER BY date DESC"
        ).fetchall()
        if not rows:
            return 0
        streak = 0
        expected = date.today()
        for row in rows:
            d = date.fromisoformat(row["date"])
            if d == expected:
                streak += 1
                expected -= timedelta(days=1)
            else:
                break
        return streak

    def get_heatmap(self) -> dict[str, int]:
        cutoff = (date.today() - timedelta(days=365)).isoformat()
        rows = self.conn.execute(
            """
            SELECT date, COUNT(*) as count
            FROM study_sessions
            WHERE date >= ?
            GROUP BY date
            """,
            (cutoff,),
        ).fetchall()
        return {row["date"]: row["count"] for row in rows}
