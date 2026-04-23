import sqlite3
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional
from notemaster.models import (
    Highlight, HighlightColor, Book, Concept, ConceptEdge, RelationType,
    ConceptReviewRecord, StudySession, ConceptWithPriority,
    Entry, EntryType, EntryReviewRecord, EntryWithPriority,
)

_DEFAULT_DB_PATH = Path(__file__).parent.parent / "data" / "notemaster.db"

# SM-2 base intervals (days), modified by weight at query time
_SM2_INTERVALS: dict[int, int] = {1: 1, 2: 3, 3: 7, 4: 14, 5: 30}

# Weight multipliers applied per review outcome
_WEIGHT_FACTORS: dict[int, float] = {1: 1.4, 2: 1.15, 3: 1.0, 4: 0.85, 5: 0.7}

# Color contribution to initial concept weight
_COLOR_WEIGHT: dict[str, float] = {"green": 1.5, "blue": 1.3, "yellow": 1.0}

_WEIGHT_FLOOR = 0.1


def _initial_weight(highlight_colors: list[str]) -> float:
    return max(_WEIGHT_FLOOR, sum(_COLOR_WEIGHT.get(c, 1.0) for c in highlight_colors))


def _update_weight(current: float, mastery_score: int) -> float:
    return max(_WEIGHT_FLOOR, current * _WEIGHT_FACTORS[mastery_score])


def _sm2_interval(mastery_score: int, weight: float) -> int:
    base = _SM2_INTERVALS.get(mastery_score, 7)
    # High-weight concepts get shorter intervals (reviewed more frequently)
    factor = max(0.5, min(2.0, 1.0 / weight))
    return max(1, round(base * factor))


class Database:
    def __init__(self, path: str | Path = _DEFAULT_DB_PATH):
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._migrate()
        self._create_tables()

    def _migrate(self):
        # review_records: old schema used highlight_id; new schema uses concept_id
        row = self.conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='review_records'"
        ).fetchone()
        if row and "highlight_id" in row[0]:
            self.conn.execute("DROP TABLE review_records")
            self.conn.commit()

    def _create_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS books (
                id          TEXT PRIMARY KEY,
                title       TEXT NOT NULL,
                asset_id    TEXT NOT NULL UNIQUE,
                synced_at   TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS highlights (
                id          TEXT PRIMARY KEY,
                text        TEXT NOT NULL,
                color       TEXT NOT NULL,
                book_id     TEXT NOT NULL,
                book_title  TEXT NOT NULL,
                chapter     TEXT,
                FOREIGN KEY (book_id) REFERENCES books(id)
            );

            CREATE TABLE IF NOT EXISTS concepts (
                id          TEXT PRIMARY KEY,
                title       TEXT NOT NULL,
                summary     TEXT NOT NULL,
                book_id     TEXT NOT NULL,
                weight      REAL NOT NULL DEFAULT 1.0,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL,
                FOREIGN KEY (book_id) REFERENCES books(id)
            );

            CREATE TABLE IF NOT EXISTS concept_highlights (
                concept_id   TEXT NOT NULL,
                highlight_id TEXT NOT NULL,
                PRIMARY KEY (concept_id, highlight_id),
                FOREIGN KEY (concept_id)   REFERENCES concepts(id),
                FOREIGN KEY (highlight_id) REFERENCES highlights(id)
            );

            CREATE TABLE IF NOT EXISTS concept_edges (
                from_concept_id TEXT NOT NULL,
                to_concept_id   TEXT NOT NULL,
                relation        TEXT NOT NULL,
                PRIMARY KEY (from_concept_id, to_concept_id),
                FOREIGN KEY (from_concept_id) REFERENCES concepts(id),
                FOREIGN KEY (to_concept_id)   REFERENCES concepts(id)
            );

            CREATE TABLE IF NOT EXISTS review_records (
                concept_id      TEXT PRIMARY KEY,
                mastery_score   INTEGER NOT NULL,
                reviewed_at     TEXT NOT NULL,
                next_review_at  TEXT NOT NULL,
                FOREIGN KEY (concept_id) REFERENCES concepts(id)
            );

            CREATE TABLE IF NOT EXISTS study_sessions (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                date             TEXT NOT NULL,
                duration_minutes INTEGER NOT NULL,
                items_reviewed   INTEGER NOT NULL,
                quiz_score       REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS entries (
                id           TEXT PRIMARY KEY,
                text         TEXT NOT NULL,
                source_type  TEXT NOT NULL DEFAULT 'manual',
                source_ref   TEXT,
                phonetics    TEXT,
                examples     TEXT NOT NULL DEFAULT '[]',
                context_note TEXT,
                weight       REAL NOT NULL DEFAULT 1.0,
                created_at   TEXT NOT NULL,
                updated_at   TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS entry_review_records (
                entry_id       TEXT PRIMARY KEY,
                mastery_score  INTEGER NOT NULL,
                reviewed_at    TEXT NOT NULL,
                next_review_at TEXT NOT NULL,
                FOREIGN KEY (entry_id) REFERENCES entries(id)
            );
        """)

    # --- Books ---

    def save_book(self, book: Book):
        self.conn.execute(
            """
            INSERT INTO books (id, title, asset_id, synced_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title=excluded.title,
                synced_at=excluded.synced_at
            """,
            (book.id, book.title, book.asset_id, book.synced_at.isoformat()),
        )
        self.conn.commit()

    def get_book_by_asset_id(self, asset_id: str) -> Optional[Book]:
        row = self.conn.execute(
            "SELECT * FROM books WHERE asset_id = ?", (asset_id,)
        ).fetchone()
        if row is None:
            return None
        return Book(
            id=row["id"],
            title=row["title"],
            asset_id=row["asset_id"],
            synced_at=datetime.fromisoformat(row["synced_at"]),
        )

    def get_books(self) -> list[Book]:
        rows = self.conn.execute("SELECT * FROM books ORDER BY title").fetchall()
        return [
            Book(id=r["id"], title=r["title"], asset_id=r["asset_id"],
                 synced_at=datetime.fromisoformat(r["synced_at"]))
            for r in rows
        ]

    # --- Highlights ---

    def save_highlight(self, h: Highlight):
        self.conn.execute(
            """
            INSERT INTO highlights (id, text, color, book_id, book_title, chapter)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                text=excluded.text,
                color=excluded.color,
                book_id=excluded.book_id,
                book_title=excluded.book_title,
                chapter=excluded.chapter
            """,
            (h.id, h.text, h.color.value, h.book_id, h.book_title, h.chapter),
        )
        self.conn.commit()

    def get_highlights(self, book_id: Optional[str] = None, unprocessed_only: bool = False) -> list[Highlight]:
        query = "SELECT h.* FROM highlights h"
        params: list = []

        if unprocessed_only:
            query += " LEFT JOIN concept_highlights ch ON h.id = ch.highlight_id WHERE ch.highlight_id IS NULL"
            if book_id:
                query += " AND h.book_id = ?"
                params.append(book_id)
        else:
            if book_id:
                query += " WHERE h.book_id = ?"
                params.append(book_id)

        rows = self.conn.execute(query, params).fetchall()
        return [_row_to_highlight(row) for row in rows]

    # --- Concepts ---

    def create_concept(self, concept: Concept) -> Concept:
        now = concept.created_at.isoformat()
        self.conn.execute(
            """
            INSERT INTO concepts (id, title, summary, book_id, weight, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (concept.id, concept.title, concept.summary, concept.book_id,
             concept.weight, now, now),
        )
        for h_id in concept.highlight_ids:
            self.conn.execute(
                "INSERT OR IGNORE INTO concept_highlights (concept_id, highlight_id) VALUES (?, ?)",
                (concept.id, h_id),
            )
        self.conn.commit()
        return concept

    def update_concept(
        self,
        concept_id: str,
        title: Optional[str] = None,
        summary: Optional[str] = None,
        add_highlight_ids: Optional[list[str]] = None,
    ) -> Optional[Concept]:
        updates = []
        params: list = []
        now = datetime.now().isoformat()

        if title is not None:
            updates.append("title = ?")
            params.append(title)
        if summary is not None:
            updates.append("summary = ?")
            params.append(summary)

        if updates:
            updates.append("updated_at = ?")
            params.append(now)
            params.append(concept_id)
            self.conn.execute(
                f"UPDATE concepts SET {', '.join(updates)} WHERE id = ?", params
            )

        if add_highlight_ids:
            for h_id in add_highlight_ids:
                self.conn.execute(
                    "INSERT OR IGNORE INTO concept_highlights (concept_id, highlight_id) VALUES (?, ?)",
                    (concept_id, h_id),
                )
            # Recalculate weight from updated highlight set
            colors = self._get_concept_highlight_colors(concept_id)
            new_weight = _initial_weight(colors)
            self.conn.execute(
                "UPDATE concepts SET weight = ?, updated_at = ? WHERE id = ?",
                (new_weight, now, concept_id),
            )

        self.conn.commit()
        return self.get_concept(concept_id)

    def get_concept(self, concept_id: str) -> Optional[Concept]:
        row = self.conn.execute(
            "SELECT * FROM concepts WHERE id = ?", (concept_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_concept(row)

    def get_concepts(self, book_id: Optional[str] = None) -> list[Concept]:
        query = "SELECT * FROM concepts"
        params: list = []
        if book_id:
            query += " WHERE book_id = ?"
            params.append(book_id)
        query += " ORDER BY weight DESC"
        rows = self.conn.execute(query, params).fetchall()
        return [self._row_to_concept(row) for row in rows]

    def get_due_concepts(self, limit: int = 20) -> list[ConceptWithPriority]:
        now = datetime.now()
        rows = self.conn.execute(
            """
            SELECT c.*, r.mastery_score, r.next_review_at
            FROM concepts c
            LEFT JOIN review_records r ON c.id = r.concept_id
            WHERE r.concept_id IS NULL OR r.next_review_at <= ?
            ORDER BY c.weight DESC
            LIMIT ?
            """,
            (now.isoformat(), limit),
        ).fetchall()

        result = []
        for row in rows:
            concept = self._row_to_concept(row)
            next_review = (
                datetime.fromisoformat(row["next_review_at"])
                if row["next_review_at"] else now
            )
            days_overdue = max(0.0, (now - next_review).total_seconds() / 86400)
            priority = concept.weight * (1 + days_overdue)
            result.append(ConceptWithPriority(
                concept=concept,
                priority=priority,
                days_overdue=days_overdue,
                last_mastery=row["mastery_score"],
            ))

        result.sort(key=lambda x: x.priority, reverse=True)
        return result

    # --- Edges ---

    def create_edge(self, edge: ConceptEdge):
        self.conn.execute(
            """
            INSERT INTO concept_edges (from_concept_id, to_concept_id, relation)
            VALUES (?, ?, ?)
            ON CONFLICT(from_concept_id, to_concept_id) DO UPDATE SET relation=excluded.relation
            """,
            (edge.from_concept_id, edge.to_concept_id, edge.relation.value),
        )
        self.conn.commit()

    def delete_edge(self, from_concept_id: str, to_concept_id: str):
        self.conn.execute(
            "DELETE FROM concept_edges WHERE from_concept_id = ? AND to_concept_id = ?",
            (from_concept_id, to_concept_id),
        )
        self.conn.commit()

    def get_edges(self, concept_id: Optional[str] = None) -> list[ConceptEdge]:
        if concept_id:
            rows = self.conn.execute(
                """
                SELECT * FROM concept_edges
                WHERE from_concept_id = ? OR to_concept_id = ?
                """,
                (concept_id, concept_id),
            ).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM concept_edges").fetchall()
        return [
            ConceptEdge(
                from_concept_id=r["from_concept_id"],
                to_concept_id=r["to_concept_id"],
                relation=RelationType(r["relation"]),
            )
            for r in rows
        ]

    # --- Reviews ---

    def record_review(self, concept_id: str, mastery_score: int) -> ReviewRecord:
        concept = self.get_concept(concept_id)
        if concept is None:
            raise ValueError(f"Concept {concept_id} not found")

        new_weight = _update_weight(concept.weight, mastery_score)
        interval_days = _sm2_interval(mastery_score, new_weight)
        now = datetime.now()
        next_review = now + timedelta(days=interval_days)

        self.conn.execute(
            "UPDATE concepts SET weight = ?, updated_at = ? WHERE id = ?",
            (new_weight, now.isoformat(), concept_id),
        )
        self.conn.execute(
            """
            INSERT INTO review_records (concept_id, mastery_score, reviewed_at, next_review_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(concept_id) DO UPDATE SET
                mastery_score=excluded.mastery_score,
                reviewed_at=excluded.reviewed_at,
                next_review_at=excluded.next_review_at
            """,
            (concept_id, mastery_score, now.isoformat(), next_review.isoformat()),
        )
        self.conn.commit()

        return ConceptReviewRecord(
            concept_id=concept_id,
            mastery_score=mastery_score,
            reviewed_at=now,
            next_review_at=next_review,
        )

    # --- Study Sessions ---

    def save_study_session(self, session: StudySession):
        self.conn.execute(
            """
            INSERT INTO study_sessions (date, duration_minutes, items_reviewed, quiz_score)
            VALUES (?, ?, ?, ?)
            """,
            (session.date.isoformat(), session.duration_minutes,
             session.items_reviewed, session.quiz_score),
        )
        self.conn.commit()

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

    def get_heatmap(self) -> dict[str, int]:
        cutoff = (date.today() - timedelta(days=365)).isoformat()
        rows = self.conn.execute(
            """
            SELECT date, COUNT(*) as count FROM study_sessions
            WHERE date >= ? GROUP BY date
            """,
            (cutoff,),
        ).fetchall()
        return {row["date"]: row["count"] for row in rows}

    # --- Entries ---

    def create_entry(self, entry: Entry) -> Entry:
        import json
        now = entry.created_at.isoformat()
        self.conn.execute(
            """
            INSERT INTO entries
                (id, text, source_type, source_ref, phonetics, examples, context_note, weight, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.id, entry.text, entry.source_type.value, entry.source_ref,
                entry.phonetics, json.dumps(entry.examples), entry.context_note,
                entry.weight, now, now,
            ),
        )
        self.conn.commit()
        return entry

    def get_entry(self, entry_id: str) -> Optional[Entry]:
        row = self.conn.execute(
            "SELECT * FROM entries WHERE id = ?", (entry_id,)
        ).fetchone()
        return _row_to_entry(row) if row else None

    def get_entries(self, source_type: Optional[EntryType] = None) -> list[Entry]:
        if source_type:
            rows = self.conn.execute(
                "SELECT * FROM entries WHERE source_type = ? ORDER BY created_at DESC",
                (source_type.value,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM entries ORDER BY created_at DESC"
            ).fetchall()
        return [_row_to_entry(r) for r in rows]

    def update_entry(
        self,
        entry_id: str,
        text: Optional[str] = None,
        phonetics: Optional[str] = None,
        examples: Optional[list[str]] = None,
        context_note: Optional[str] = None,
    ) -> Optional[Entry]:
        import json
        updates = []
        params: list = []
        now = datetime.now().isoformat()

        if text is not None:
            updates.append("text = ?")
            params.append(text)
        if phonetics is not None:
            updates.append("phonetics = ?")
            params.append(phonetics)
        if examples is not None:
            updates.append("examples = ?")
            params.append(json.dumps(examples))
        if context_note is not None:
            updates.append("context_note = ?")
            params.append(context_note)

        if not updates:
            return self.get_entry(entry_id)

        updates.append("updated_at = ?")
        params.append(now)
        params.append(entry_id)
        self.conn.execute(
            f"UPDATE entries SET {', '.join(updates)} WHERE id = ?", params
        )
        self.conn.commit()
        return self.get_entry(entry_id)

    def record_entry_review(self, entry_id: str, mastery_score: int) -> EntryReviewRecord:
        entry = self.get_entry(entry_id)
        if entry is None:
            raise ValueError(f"Entry {entry_id} not found")

        new_weight = _update_weight(entry.weight, mastery_score)
        interval_days = _sm2_interval(mastery_score, new_weight)
        now = datetime.now()
        next_review = now + timedelta(days=interval_days)

        self.conn.execute(
            "UPDATE entries SET weight = ?, updated_at = ? WHERE id = ?",
            (new_weight, now.isoformat(), entry_id),
        )
        self.conn.execute(
            """
            INSERT INTO entry_review_records (entry_id, mastery_score, reviewed_at, next_review_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(entry_id) DO UPDATE SET
                mastery_score=excluded.mastery_score,
                reviewed_at=excluded.reviewed_at,
                next_review_at=excluded.next_review_at
            """,
            (entry_id, mastery_score, now.isoformat(), next_review.isoformat()),
        )
        self.conn.commit()
        return EntryReviewRecord(
            entry_id=entry_id,
            mastery_score=mastery_score,
            reviewed_at=now,
            next_review_at=next_review,
        )

    def get_due_entries(self, limit: int = 20) -> list[EntryWithPriority]:
        now = datetime.now()
        rows = self.conn.execute(
            """
            SELECT e.*, r.mastery_score, r.next_review_at as review_due
            FROM entries e
            LEFT JOIN entry_review_records r ON e.id = r.entry_id
            WHERE r.entry_id IS NULL OR r.next_review_at <= ?
            ORDER BY e.weight DESC
            LIMIT ?
            """,
            (now.isoformat(), limit),
        ).fetchall()

        result = []
        for row in rows:
            entry = _row_to_entry(row)
            next_review = (
                datetime.fromisoformat(row["review_due"])
                if row["review_due"] else now
            )
            days_overdue = max(0.0, (now - next_review).total_seconds() / 86400)
            priority = entry.weight * (1 + days_overdue)
            result.append(EntryWithPriority(
                entry=entry,
                priority=priority,
                days_overdue=days_overdue,
                last_mastery=row["mastery_score"],
            ))

        result.sort(key=lambda x: x.priority, reverse=True)
        return result

    # --- Helpers ---

    def _get_concept_highlight_colors(self, concept_id: str) -> list[str]:
        rows = self.conn.execute(
            """
            SELECT h.color FROM highlights h
            JOIN concept_highlights ch ON h.id = ch.highlight_id
            WHERE ch.concept_id = ?
            """,
            (concept_id,),
        ).fetchall()
        return [r["color"] for r in rows]

    def _row_to_concept(self, row: sqlite3.Row) -> Concept:
        h_rows = self.conn.execute(
            "SELECT highlight_id FROM concept_highlights WHERE concept_id = ?",
            (row["id"],),
        ).fetchall()
        return Concept(
            id=row["id"],
            title=row["title"],
            summary=row["summary"],
            book_id=row["book_id"],
            highlight_ids=[r["highlight_id"] for r in h_rows],
            weight=row["weight"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )


def _row_to_highlight(row: sqlite3.Row) -> Highlight:
    return Highlight(
        id=row["id"],
        text=row["text"],
        color=HighlightColor(row["color"]),
        book_id=row["book_id"],
        book_title=row["book_title"],
        chapter=row["chapter"],
    )


def _row_to_entry(row: sqlite3.Row) -> Entry:
    import json
    return Entry(
        id=row["id"],
        text=row["text"],
        source_type=EntryType(row["source_type"]),
        source_ref=row["source_ref"],
        phonetics=row["phonetics"],
        examples=json.loads(row["examples"]),
        context_note=row["context_note"],
        weight=row["weight"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )
