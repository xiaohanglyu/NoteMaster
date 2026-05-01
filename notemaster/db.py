import sqlite3
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from typing import Optional
from notemaster.models import (
    Highlight, HighlightColor, Book, Concept, ConceptEdge, RelationType,
    ConceptReviewRecord, StudySession, ConceptWithPriority,
    Entry, EntryData, EntryType, EntryReviewRecord, EntryWithPriority,
    Application, ApplicationStatus, ApplicationRound,
    InterviewQuestion, QuestionType, QuestionSource, QuestionReviewRecord,
    RoundType, RoundStatus,
    InboxItem, AIProvider,
    DailyPlan, PlanTask, PlanBlock, PlanTaskType,
    Source, SourceType,
    Problem, ProblemType, ProblemDifficulty, ProblemReviewRecord,
    CoachGoal, GoalType,
    QuestionAttempt,
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
        import json as _json

        # entries: add tags column if missing
        row = self.conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='entries'"
        ).fetchone()
        if row and "tags" not in row[0]:
            self.conn.execute("ALTER TABLE entries ADD COLUMN tags TEXT NOT NULL DEFAULT '[]'")
            self.conn.commit()

        # interview_questions: add category column if missing
        row = self.conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='interview_questions'"
        ).fetchone()
        if row and "category" not in row[0]:
            self.conn.execute(
                "ALTER TABLE interview_questions ADD COLUMN category TEXT NOT NULL DEFAULT 'interview'"
            )
            self.conn.commit()

        # interview_questions: add source_id column if missing
        row = self.conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='interview_questions'"
        ).fetchone()
        if row and "source_id" not in row[0]:
            self.conn.execute(
                "ALTER TABLE interview_questions ADD COLUMN source_id TEXT"
            )
            self.conn.commit()

        # interview_questions: add problem_id column if missing
        row = self.conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='interview_questions'"
        ).fetchone()
        if row and "problem_id" not in row[0]:
            self.conn.execute(
                "ALTER TABLE interview_questions ADD COLUMN problem_id TEXT"
            )
            self.conn.commit()

        # interview_questions: add key_points + sub_questions columns if missing
        row = self.conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='interview_questions'"
        ).fetchone()
        if row and "key_points" not in row[0]:
            self.conn.execute(
                "ALTER TABLE interview_questions ADD COLUMN key_points TEXT NOT NULL DEFAULT '[]'"
            )
            self.conn.commit()
        if row and "sub_questions" not in row[0]:
            self.conn.execute(
                "ALTER TABLE interview_questions ADD COLUMN sub_questions TEXT NOT NULL DEFAULT '[]'"
            )
            self.conn.commit()

        # application_rounds: add round_type + status columns if missing
        row = self.conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='application_rounds'"
        ).fetchone()
        if row and "round_type" not in row[0]:
            self.conn.execute("ALTER TABLE application_rounds ADD COLUMN round_type TEXT")
            self.conn.commit()
        if row and "status" not in row[0]:
            self.conn.execute(
                "ALTER TABLE application_rounds ADD COLUMN status TEXT NOT NULL DEFAULT 'scheduled'"
            )
            self.conn.commit()

        # review_records: old schema used highlight_id; new schema uses concept_id
        row = self.conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='review_records'"
        ).fetchone()
        if row and "highlight_id" in row[0]:
            self.conn.execute("DROP TABLE review_records")
            self.conn.commit()

        # entries: collapse flat columns into a single data JSON column
        row = self.conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='entries'"
        ).fetchone()
        if row and "phonetics" in row[0]:
            # Step 1: add data column
            self.conn.execute("ALTER TABLE entries ADD COLUMN data TEXT NOT NULL DEFAULT '{}'")
            # Step 2: pack existing flat columns into data JSON
            rows = self.conn.execute(
                "SELECT id, phonetics, translation, examples, context_note FROM entries"
            ).fetchall()
            for r in rows:
                packed = _json.dumps({
                    "phonetics": r[1],
                    "translation": r[2],
                    "examples": _json.loads(r[3] or "[]"),
                    "context_note": r[4],
                })
                self.conn.execute("UPDATE entries SET data = ? WHERE id = ?", (packed, r[0]))
            # Step 3: rebuild table without old columns
            self.conn.executescript("""
                CREATE TABLE entries_new (
                    id          TEXT PRIMARY KEY,
                    text        TEXT NOT NULL,
                    source_type TEXT NOT NULL DEFAULT 'manual',
                    source_ref  TEXT,
                    data        TEXT NOT NULL DEFAULT '{}',
                    weight      REAL NOT NULL DEFAULT 1.0,
                    created_at  TEXT NOT NULL,
                    updated_at  TEXT NOT NULL
                );
                INSERT INTO entries_new SELECT id, text, source_type, source_ref, data, weight, created_at, updated_at FROM entries;
                DROP TABLE entries;
                ALTER TABLE entries_new RENAME TO entries;
            """)
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
                questions   TEXT NOT NULL DEFAULT '[]',
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
                id          TEXT PRIMARY KEY,
                text        TEXT NOT NULL,
                source_type TEXT NOT NULL DEFAULT 'manual',
                source_ref  TEXT,
                data        TEXT NOT NULL DEFAULT '{}',
                tags        TEXT NOT NULL DEFAULT '[]',
                weight      REAL NOT NULL DEFAULT 1.0,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS entry_review_records (
                entry_id       TEXT PRIMARY KEY,
                mastery_score  INTEGER NOT NULL,
                reviewed_at    TEXT NOT NULL,
                next_review_at TEXT NOT NULL,
                FOREIGN KEY (entry_id) REFERENCES entries(id)
            );

            CREATE TABLE IF NOT EXISTS applications (
                id              TEXT PRIMARY KEY,
                company         TEXT NOT NULL,
                role            TEXT NOT NULL,
                status          TEXT NOT NULL DEFAULT 'applied',
                location        TEXT,
                work_model      TEXT,
                salary_range    TEXT,
                job_link        TEXT,
                resume_version  TEXT,
                notes           TEXT,
                applied_at      TEXT,
                created_at      TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS application_rounds (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                application_id  TEXT NOT NULL,
                name            TEXT NOT NULL,
                round_type      TEXT,
                status          TEXT NOT NULL DEFAULT 'scheduled',
                date            TEXT,
                feedback        TEXT,
                FOREIGN KEY (application_id) REFERENCES applications(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS question_concept_links (
                question_id TEXT NOT NULL,
                concept_id  TEXT NOT NULL,
                PRIMARY KEY (question_id, concept_id),
                FOREIGN KEY (question_id) REFERENCES interview_questions(id) ON DELETE CASCADE,
                FOREIGN KEY (concept_id)  REFERENCES concepts(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS interview_questions (
                id              TEXT PRIMARY KEY,
                question        TEXT NOT NULL,
                answer          TEXT,
                q_type          TEXT NOT NULL DEFAULT 'other',
                source          TEXT NOT NULL DEFAULT 'mock',
                category        TEXT NOT NULL DEFAULT 'interview',
                application_id  TEXT,
                source_id       TEXT,
                problem_id      TEXT,
                round           TEXT,
                self_score      INTEGER NOT NULL DEFAULT 0,
                tags            TEXT NOT NULL DEFAULT '[]',
                notes           TEXT,
                key_points      TEXT NOT NULL DEFAULT '[]',
                sub_questions   TEXT NOT NULL DEFAULT '[]',
                ef              REAL NOT NULL DEFAULT 2.5,
                interval        INTEGER NOT NULL DEFAULT 0,
                reps            INTEGER NOT NULL DEFAULT 0,
                next_review_at  TEXT,
                created_at      TEXT NOT NULL,
                FOREIGN KEY (application_id) REFERENCES applications(id) ON DELETE SET NULL,
                FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE SET NULL,
                FOREIGN KEY (problem_id) REFERENCES problems(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS sync_log (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id         TEXT NOT NULL,
                book_title      TEXT NOT NULL DEFAULT '',
                highlights_synced INTEGER NOT NULL DEFAULT 0,
                sections        TEXT,
                synced_at       TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS inbox_items (
                id           TEXT PRIMARY KEY,
                content      TEXT NOT NULL,
                tags         TEXT NOT NULL DEFAULT '[]',
                created_at   TEXT NOT NULL,
                processed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS embeddings (
                note_type  TEXT NOT NULL,
                note_id    TEXT NOT NULL,
                vector     TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (note_type, note_id)
            );

            CREATE TABLE IF NOT EXISTS ai_providers (
                id            TEXT PRIMARY KEY,
                name          TEXT NOT NULL,
                provider_type TEXT NOT NULL,
                base_url      TEXT,
                api_key       TEXT,
                model         TEXT NOT NULL,
                is_active     INTEGER NOT NULL DEFAULT 0,
                created_at    TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS plan_tasks (
                id         TEXT PRIMARY KEY,
                plan_date  TEXT NOT NULL,
                block      TEXT NOT NULL,
                task_type  TEXT NOT NULL,
                title      TEXT NOT NULL,
                url        TEXT,
                ref_id     TEXT,
                done       INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS problems (
                id             TEXT PRIMARY KEY,
                title          TEXT NOT NULL,
                problem_type   TEXT NOT NULL,
                difficulty     TEXT,
                url            TEXT,
                tags           TEXT NOT NULL DEFAULT '[]',
                notes          TEXT,
                ef             REAL NOT NULL DEFAULT 2.5,
                interval       INTEGER NOT NULL DEFAULT 0,
                reps           INTEGER NOT NULL DEFAULT 0,
                next_review_at TEXT,
                created_at     TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sources (
                id             TEXT PRIMARY KEY,
                title          TEXT NOT NULL,
                source_type    TEXT NOT NULL,
                source_ref     TEXT,
                content_cache  TEXT,
                tags           TEXT NOT NULL DEFAULT '[]',
                created_at     TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS coach_goals (
                id             TEXT PRIMARY KEY,
                title          TEXT NOT NULL,
                goal_type      TEXT NOT NULL,
                ref_id         TEXT,
                deadline       TEXT,
                priority       INTEGER NOT NULL DEFAULT 2,
                daily_minutes  INTEGER NOT NULL DEFAULT 30,
                created_at     TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS question_attempts (
                id             TEXT PRIMARY KEY,
                question_id    TEXT NOT NULL,
                response_text  TEXT NOT NULL,
                coverage       TEXT NOT NULL DEFAULT '[]',
                ai_feedback    TEXT,
                score          REAL NOT NULL DEFAULT 0.0,
                attempted_at   TEXT NOT NULL,
                FOREIGN KEY (question_id) REFERENCES interview_questions(id) ON DELETE CASCADE
            );
        """)

    # --- Sync log ---

    def record_sync(self, book_id: str, highlights_synced: int, sections: Optional[list] = None,
                    book_title: str = "") -> None:
        import json
        self.conn.execute(
            "INSERT INTO sync_log (book_id, book_title, highlights_synced, sections, synced_at) VALUES (?,?,?,?,?)",
            (book_id, book_title, highlights_synced,
             json.dumps(sections) if sections is not None else None,
             datetime.now().isoformat()),
        )
        self.conn.commit()

    def get_sync_history(self, book_id: Optional[str] = None) -> list[dict]:
        import json
        if book_id:
            rows = self.conn.execute(
                "SELECT id, book_id, book_title, highlights_synced, sections, synced_at "
                "FROM sync_log WHERE book_id = ? ORDER BY synced_at DESC", (book_id,)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT id, book_id, book_title, highlights_synced, sections, synced_at "
                "FROM sync_log ORDER BY synced_at DESC"
            ).fetchall()
        result = []
        for row in rows:
            result.append({
                "id": row[0], "book_id": row[1], "book_title": row[2],
                "highlights_synced": row[3],
                "sections": json.loads(row[4]) if row[4] else None,
                "synced_at": row[5],
            })
        return result

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
        import json as _json
        now = concept.created_at.isoformat()
        self.conn.execute(
            """
            INSERT INTO concepts (id, title, summary, book_id, weight, questions, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (concept.id, concept.title, concept.summary, concept.book_id,
             concept.weight, _json.dumps(concept.questions), now, now),
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
        weight: Optional[float] = None,
        questions: Optional[list[str]] = None,
        add_highlight_ids: Optional[list[str]] = None,
    ) -> Optional[Concept]:
        import json as _json
        updates = []
        params: list = []
        now = datetime.now().isoformat()

        if title is not None:
            updates.append("title = ?")
            params.append(title)
        if summary is not None:
            updates.append("summary = ?")
            params.append(summary)
        if weight is not None:
            updates.append("weight = ?")
            params.append(weight)
        if questions is not None:
            updates.append("questions = ?")
            params.append(_json.dumps(questions))

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

    def delete_concept(self, concept_id: str) -> bool:
        cur = self.conn.execute("DELETE FROM concepts WHERE id = ?", (concept_id,))
        self.conn.commit()
        return cur.rowcount > 0

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
                (id, text, source_type, source_ref, data, tags, weight, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.id, entry.text, entry.source_type.value, entry.source_ref,
                json.dumps(entry.data.model_dump()),
                json.dumps(entry.tags),
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

    def get_entries(self, source_type: Optional[EntryType] = None, tag: Optional[str] = None) -> list[Entry]:
        import json
        clauses, params = [], []
        if source_type:
            clauses.append("source_type = ?")
            params.append(source_type.value)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.conn.execute(
            f"SELECT * FROM entries {where} ORDER BY created_at DESC", params
        ).fetchall()
        entries = [_row_to_entry(r) for r in rows]
        if tag:
            entries = [e for e in entries if tag in e.tags]
        return entries

    def update_entry(
        self,
        entry_id: str,
        text: Optional[str] = None,
        data: Optional[EntryData] = None,
        tags: Optional[list] = None,
    ) -> Optional[Entry]:
        import json
        existing = self.get_entry(entry_id)
        if existing is None:
            return None

        updates = []
        params: list = []
        now = datetime.now().isoformat()

        if text is not None:
            updates.append("text = ?")
            params.append(text)
        if data is not None:
            merged = existing.data.model_dump()
            incoming = data.model_dump(exclude_unset=True)
            merged.update(incoming)
            updates.append("data = ?")
            params.append(json.dumps(merged))
        if tags is not None:
            updates.append("tags = ?")
            params.append(json.dumps(tags))

        if not updates:
            return existing

        updates.append("updated_at = ?")
        params.append(now)
        params.append(entry_id)
        self.conn.execute(
            f"UPDATE entries SET {', '.join(updates)} WHERE id = ?", params
        )
        self.conn.commit()
        return self.get_entry(entry_id)

    def delete_entry(self, entry_id: str) -> bool:
        cur = self.conn.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
        self.conn.commit()
        return cur.rowcount > 0

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

    # --- Applications ---

    def create_application(self, app: Application) -> Application:
        self.conn.execute(
            """
            INSERT INTO applications
                (id, company, role, status, location, work_model, salary_range,
                 job_link, resume_version, notes, applied_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                app.id, app.company, app.role, app.status.value,
                app.location, app.work_model, app.salary_range,
                app.job_link, app.resume_version, app.notes,
                app.applied_at.isoformat() if app.applied_at else None,
                app.created_at.isoformat(),
            ),
        )
        self.conn.commit()
        return app

    def get_application(self, app_id: str) -> Optional[Application]:
        row = self.conn.execute(
            "SELECT * FROM applications WHERE id = ?", (app_id,)
        ).fetchone()
        return _row_to_application(row) if row else None

    def get_applications(self, status: Optional[ApplicationStatus] = None) -> list[Application]:
        if status:
            rows = self.conn.execute(
                "SELECT * FROM applications WHERE status = ? ORDER BY created_at DESC",
                (status.value,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM applications ORDER BY created_at DESC"
            ).fetchall()
        return [_row_to_application(r) for r in rows]

    def update_application(self, app_id: str, **kwargs) -> Optional[Application]:
        allowed = {"status", "location", "work_model", "salary_range",
                   "job_link", "resume_version", "notes", "applied_at"}
        updates, params = [], []
        for key, value in kwargs.items():
            if key not in allowed:
                continue
            updates.append(f"{key} = ?")
            if key == "status" and isinstance(value, ApplicationStatus):
                params.append(value.value)
            elif key == "applied_at" and hasattr(value, "isoformat"):
                params.append(value.isoformat())
            else:
                params.append(value)
        if not updates:
            return self.get_application(app_id)
        params.append(app_id)
        self.conn.execute(
            f"UPDATE applications SET {', '.join(updates)} WHERE id = ?", params
        )
        self.conn.commit()
        return self.get_application(app_id)

    def delete_application(self, app_id: str):
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("DELETE FROM applications WHERE id = ?", (app_id,))
        self.conn.commit()

    # --- Application Rounds ---

    def add_application_round(self, round: "ApplicationRound") -> "ApplicationRound":
        cur = self.conn.execute(
            "INSERT INTO application_rounds (application_id, name, round_type, status, date, feedback) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (round.application_id, round.name,
             round.round_type.value if round.round_type else None,
             round.status.value if round.status else "scheduled",
             round.date, round.feedback),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT * FROM application_rounds WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return _row_to_round(row)

    def get_application_rounds(self, app_id: str) -> list[ApplicationRound]:
        rows = self.conn.execute(
            "SELECT * FROM application_rounds WHERE application_id = ? ORDER BY id",
            (app_id,),
        ).fetchall()
        return [_row_to_round(r) for r in rows]

    def update_application_round(self, round_id: int, **kwargs) -> Optional[ApplicationRound]:
        allowed = {"name", "date", "feedback", "round_type", "status"}
        updates, params = [], []
        for key, value in kwargs.items():
            if key in allowed:
                updates.append(f"{key} = ?")
                params.append(value)
        if not updates:
            row = self.conn.execute(
                "SELECT * FROM application_rounds WHERE id = ?", (round_id,)
            ).fetchone()
            return _row_to_round(row) if row else None
        params.append(round_id)
        self.conn.execute(
            f"UPDATE application_rounds SET {', '.join(updates)} WHERE id = ?", params
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT * FROM application_rounds WHERE id = ?", (round_id,)
        ).fetchone()
        return _row_to_round(row) if row else None

    # --- Interview Questions ---

    def create_question(self, q: InterviewQuestion) -> InterviewQuestion:
        import json
        self.conn.execute(
            """
            INSERT INTO interview_questions
                (id, question, answer, q_type, source, category, application_id, source_id,
                 problem_id, round, self_score, tags, notes, key_points, sub_questions,
                 ef, interval, reps, next_review_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                q.id, q.question, q.answer, q.q_type.value, q.source.value,
                q.category.value, q.application_id, q.source_id, q.problem_id,
                q.round, q.self_score,
                json.dumps(q.tags), q.notes,
                json.dumps(q.key_points), json.dumps(q.sub_questions),
                q.ef, q.interval, q.reps,
                q.next_review_at.isoformat() if q.next_review_at else None,
                q.created_at.isoformat(),
            ),
        )
        self.conn.commit()
        return q

    def get_question(self, question_id: str) -> Optional[InterviewQuestion]:
        row = self.conn.execute(
            "SELECT * FROM interview_questions WHERE id = ?", (question_id,)
        ).fetchone()
        return _row_to_question(row) if row else None

    def get_questions(
        self,
        q_type: Optional[QuestionType] = None,
        source: Optional[QuestionSource] = None,
        category: Optional[str] = None,
        application_id: Optional[str] = None,
        due_only: bool = False,
    ) -> list[InterviewQuestion]:
        clauses, params = [], []
        if q_type:
            clauses.append("q_type = ?")
            params.append(q_type.value)
        if source:
            clauses.append("source = ?")
            params.append(source.value)
        if category:
            clauses.append("category = ?")
            params.append(category)
        if application_id:
            clauses.append("application_id = ?")
            params.append(application_id)
        if due_only:
            now = datetime.now().isoformat()
            clauses.append("(next_review_at IS NULL OR next_review_at <= ?)")
            params.append(now)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.conn.execute(
            f"SELECT * FROM interview_questions {where} ORDER BY created_at DESC",
            params,
        ).fetchall()
        return [_row_to_question(r) for r in rows]

    def get_questions_by_problem(self, problem_id: str) -> list[InterviewQuestion]:
        rows = self.conn.execute(
            "SELECT * FROM interview_questions WHERE problem_id = ? ORDER BY created_at ASC",
            (problem_id,),
        ).fetchall()
        return [_row_to_question(r) for r in rows]

    def update_question(self, question_id: str, **kwargs) -> Optional[InterviewQuestion]:
        import json
        allowed = {"question", "answer", "q_type", "source", "application_id",
                   "round", "self_score", "tags", "notes", "key_points", "sub_questions"}
        updates, params = [], []
        for key, value in kwargs.items():
            if key not in allowed:
                continue
            updates.append(f"{key} = ?")
            if key == "q_type" and isinstance(value, QuestionType):
                params.append(value.value)
            elif key == "source" and isinstance(value, QuestionSource):
                params.append(value.value)
            elif key in {"tags", "key_points", "sub_questions"} and isinstance(value, list):
                params.append(json.dumps(value))
            else:
                params.append(value)
        if not updates:
            return self.get_question(question_id)
        params.append(question_id)
        self.conn.execute(
            f"UPDATE interview_questions SET {', '.join(updates)} WHERE id = ?", params
        )
        self.conn.commit()
        return self.get_question(question_id)

    def delete_question(self, question_id: str):
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute(
            "DELETE FROM interview_questions WHERE id = ?", (question_id,)
        )
        self.conn.commit()

    def bulk_import_questions(self, questions: list[InterviewQuestion]) -> int:
        imported = 0
        for q in questions:
            existing = self.get_question(q.id)
            if existing is None:
                self.create_question(q)
                imported += 1
        return imported

    # --- Question-Concept Links ---

    def link_question_concept(self, question_id: str, concept_id: str):
        self.conn.execute(
            "INSERT OR IGNORE INTO question_concept_links (question_id, concept_id) VALUES (?, ?)",
            (question_id, concept_id),
        )
        self.conn.commit()

    def unlink_question_concept(self, question_id: str, concept_id: str):
        self.conn.execute(
            "DELETE FROM question_concept_links WHERE question_id = ? AND concept_id = ?",
            (question_id, concept_id),
        )
        self.conn.commit()

    def get_question_concepts(self, question_id: str) -> list[Concept]:
        rows = self.conn.execute(
            """
            SELECT c.* FROM concepts c
            JOIN question_concept_links l ON c.id = l.concept_id
            WHERE l.question_id = ?
            """,
            (question_id,),
        ).fetchall()
        return [self._row_to_concept(r) for r in rows]

    def get_concept_questions(self, concept_id: str) -> list[InterviewQuestion]:
        rows = self.conn.execute(
            """
            SELECT q.* FROM interview_questions q
            JOIN question_concept_links l ON q.id = l.question_id
            WHERE l.concept_id = ?
            """,
            (concept_id,),
        ).fetchall()
        return [_row_to_question(r) for r in rows]

    def get_next_due_question(self) -> Optional[InterviewQuestion]:
        now = datetime.now().isoformat()
        row = self.conn.execute(
            """
            SELECT * FROM interview_questions
            WHERE next_review_at IS NULL OR next_review_at <= ?
            ORDER BY COALESCE(next_review_at, '1970-01-01') ASC
            LIMIT 1
            """,
            (now,),
        ).fetchone()
        return _row_to_question(row) if row else None

    def record_question_review(self, question_id: str, grade: int) -> QuestionReviewRecord:
        q = self.get_question(question_id)
        if q is None:
            raise ValueError(f"Question {question_id} not found")

        ef, interval, reps = q.ef, q.interval, q.reps

        if grade >= 2:
            if reps == 0:
                interval = 1
            elif reps == 1:
                interval = 3
            else:
                interval = round(interval * ef)
            reps += 1
            ef = max(1.3, ef + 0.1 - (3 - grade) * (0.08 + (3 - grade) * 0.02))
        else:
            reps = 0
            interval = 1

        now = datetime.now()
        next_review = now + timedelta(days=interval)

        self.conn.execute(
            """
            UPDATE interview_questions
            SET ef = ?, interval = ?, reps = ?, next_review_at = ?
            WHERE id = ?
            """,
            (ef, interval, reps, next_review.isoformat(), question_id),
        )
        self.conn.commit()

        return QuestionReviewRecord(
            question_id=question_id,
            grade=grade,
            reviewed_at=now,
            next_review_at=next_review,
            interval=interval,
            reps=reps,
            ef=ef,
        )

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

    # ------------------------------------------------------------------
    # Inbox
    # ------------------------------------------------------------------

    def create_inbox_item(self, item: InboxItem) -> InboxItem:
        import json as _json
        self.conn.execute(
            "INSERT INTO inbox_items (id, content, tags, created_at, processed_at) VALUES (?, ?, ?, ?, ?)",
            (
                item.id,
                item.content,
                _json.dumps(item.tags),
                item.created_at.isoformat(),
                item.processed_at.isoformat() if item.processed_at else None,
            ),
        )
        self.conn.commit()
        return item

    def get_inbox_item(self, item_id: str) -> Optional[InboxItem]:
        row = self.conn.execute(
            "SELECT * FROM inbox_items WHERE id = ?", (item_id,)
        ).fetchone()
        return self._row_to_inbox_item(row) if row else None

    def get_inbox_items(self, pending_only: bool = False) -> list[InboxItem]:
        if pending_only:
            rows = self.conn.execute(
                "SELECT * FROM inbox_items WHERE processed_at IS NULL ORDER BY created_at DESC"
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM inbox_items ORDER BY created_at DESC"
            ).fetchall()
        return [self._row_to_inbox_item(r) for r in rows]

    def update_inbox_item(self, item_id: str, content: Optional[str] = None, tags: Optional[list] = None) -> Optional[InboxItem]:
        import json as _json
        item = self.get_inbox_item(item_id)
        if item is None:
            return None
        if content is not None:
            self.conn.execute("UPDATE inbox_items SET content = ? WHERE id = ?", (content, item_id))
        if tags is not None:
            self.conn.execute("UPDATE inbox_items SET tags = ? WHERE id = ?", (_json.dumps(tags), item_id))
        self.conn.commit()
        return self.get_inbox_item(item_id)

    def mark_inbox_processed(self, item_id: str) -> None:
        self.conn.execute(
            "UPDATE inbox_items SET processed_at = ? WHERE id = ?",
            (datetime.now(tz=timezone.utc).replace(tzinfo=None).isoformat(), item_id),
        )
        self.conn.commit()

    def delete_inbox_item(self, item_id: str) -> bool:
        cur = self.conn.execute("DELETE FROM inbox_items WHERE id = ?", (item_id,))
        self.conn.commit()
        return cur.rowcount > 0

    def get_inbox_pending_count(self) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) FROM inbox_items WHERE processed_at IS NULL"
        ).fetchone()
        return row[0]

    # ------------------------------------------------------------------
    # Embeddings
    # ------------------------------------------------------------------

    def save_embedding(self, note_type: str, note_id: str, vector: list) -> None:
        from notemaster.embeddings import serialize
        self.conn.execute(
            """INSERT INTO embeddings (note_type, note_id, vector, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(note_type, note_id) DO UPDATE SET vector=excluded.vector, updated_at=excluded.updated_at""",
            (note_type, note_id, serialize(vector), datetime.now(tz=timezone.utc).replace(tzinfo=None).isoformat()),
        )
        self.conn.commit()

    def get_related(self, note_type: str, note_id: str, limit: int = 5) -> list[dict]:
        from notemaster.embeddings import deserialize, cosine_similarity
        target_row = self.conn.execute(
            "SELECT vector FROM embeddings WHERE note_type=? AND note_id=?",
            (note_type, note_id),
        ).fetchone()
        if target_row is None:
            return []
        target = deserialize(target_row["vector"])
        rows = self.conn.execute(
            "SELECT note_type, note_id, vector FROM embeddings WHERE NOT (note_type=? AND note_id=?)",
            (note_type, note_id),
        ).fetchall()
        scored = [
            {"note_type": r["note_type"], "note_id": r["note_id"],
             "score": cosine_similarity(target, deserialize(r["vector"]))}
            for r in rows
        ]
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:limit]

    # --- AI Providers ---

    def create_provider(self, provider: AIProvider) -> AIProvider:
        self.conn.execute(
            "INSERT INTO ai_providers (id, name, provider_type, base_url, api_key, model, is_active, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (provider.id, provider.name, provider.provider_type, provider.base_url,
             provider.api_key, provider.model, 1 if provider.is_active else 0,
             provider.created_at.isoformat()),
        )
        self.conn.commit()
        return provider

    def get_provider(self, provider_id: str) -> Optional[AIProvider]:
        row = self.conn.execute(
            "SELECT * FROM ai_providers WHERE id = ?", (provider_id,)
        ).fetchone()
        return self._row_to_provider(row) if row else None

    def list_providers(self) -> list[AIProvider]:
        rows = self.conn.execute(
            "SELECT * FROM ai_providers ORDER BY created_at DESC"
        ).fetchall()
        return [self._row_to_provider(r) for r in rows]

    def get_active_provider(self) -> Optional[AIProvider]:
        row = self.conn.execute(
            "SELECT * FROM ai_providers WHERE is_active = 1 LIMIT 1"
        ).fetchone()
        return self._row_to_provider(row) if row else None

    def activate_provider(self, provider_id: str) -> None:
        self.conn.execute("UPDATE ai_providers SET is_active = 0")
        self.conn.execute("UPDATE ai_providers SET is_active = 1 WHERE id = ?", (provider_id,))
        self.conn.commit()

    def update_provider(self, provider_id: str, fields: dict) -> Optional[AIProvider]:
        allowed = {"name", "base_url", "api_key", "model"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return self.get_provider(provider_id)
        params = list(updates.values()) + [provider_id]
        self.conn.execute(
            f"UPDATE ai_providers SET {', '.join(f'{k} = ?' for k in updates)} WHERE id = ?",
            params,
        )
        self.conn.commit()
        return self.get_provider(provider_id)

    def delete_provider(self, provider_id: str) -> None:
        self.conn.execute("DELETE FROM ai_providers WHERE id = ?", (provider_id,))
        self.conn.commit()

    def _row_to_provider(self, row: sqlite3.Row) -> AIProvider:
        return AIProvider(
            id=row["id"],
            name=row["name"],
            provider_type=row["provider_type"],
            base_url=row["base_url"],
            api_key=row["api_key"],
            model=row["model"],
            is_active=bool(row["is_active"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def _row_to_inbox_item(self, row: sqlite3.Row) -> InboxItem:
        import json as _json
        return InboxItem(
            id=row["id"],
            content=row["content"],
            tags=_json.loads(row["tags"] or "[]"),
            created_at=datetime.fromisoformat(row["created_at"]),
            processed_at=datetime.fromisoformat(row["processed_at"]) if row["processed_at"] else None,
        )

    def _row_to_concept(self, row: sqlite3.Row) -> Concept:
        import json as _json
        h_rows = self.conn.execute(
            "SELECT highlight_id FROM concept_highlights WHERE concept_id = ?",
            (row["id"],),
        ).fetchall()
        raw_q = row["questions"] if "questions" in row.keys() else "[]"
        return Concept(
            id=row["id"],
            title=row["title"],
            summary=row["summary"],
            book_id=row["book_id"],
            highlight_ids=[r["highlight_id"] for r in h_rows],
            weight=row["weight"],
            questions=_json.loads(raw_q or "[]"),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    # ---------------------------------------------------------------------------
    # Daily plan
    # ---------------------------------------------------------------------------

    def save_plan(self, plan: DailyPlan) -> None:
        self.conn.execute("DELETE FROM plan_tasks WHERE plan_date = ?", (plan.date,))
        for t in plan.tasks:
            self.conn.execute(
                "INSERT INTO plan_tasks (id, plan_date, block, task_type, title, url, ref_id, done) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (t.id, t.plan_date, t.block, t.task_type, t.title, t.url, t.ref_id, int(t.done)),
            )
        self.conn.commit()

    def get_plan(self, date: str) -> Optional[DailyPlan]:
        rows = self.conn.execute(
            "SELECT * FROM plan_tasks WHERE plan_date = ? ORDER BY rowid", (date,)
        ).fetchall()
        if not rows:
            return None
        tasks = [
            PlanTask(
                id=r["id"], plan_date=r["plan_date"],
                block=PlanBlock(r["block"]), task_type=PlanTaskType(r["task_type"]),
                title=r["title"], url=r["url"], ref_id=r["ref_id"],
                done=bool(r["done"]),
            )
            for r in rows
        ]
        return DailyPlan(date=date, tasks=tasks)

    def toggle_plan_task(self, task_id: str, done: bool) -> None:
        self.conn.execute(
            "UPDATE plan_tasks SET done = ? WHERE id = ?", (int(done), task_id)
        )
        self.conn.commit()

    # --- Question Attempts ---

    def create_attempt(self, a: QuestionAttempt) -> QuestionAttempt:
        import json
        self.conn.execute(
            "INSERT INTO question_attempts (id, question_id, response_text, coverage, ai_feedback, score, attempted_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (a.id, a.question_id, a.response_text, json.dumps(a.coverage),
             a.ai_feedback, a.score, a.attempted_at.isoformat()),
        )
        self.conn.commit()
        return a

    def list_attempts(self, question_id: str) -> list[QuestionAttempt]:
        rows = self.conn.execute(
            "SELECT * FROM question_attempts WHERE question_id = ? ORDER BY attempted_at DESC",
            (question_id,),
        ).fetchall()
        return [_row_to_attempt(r) for r in rows]

    def delete_attempt(self, attempt_id: str) -> bool:
        cur = self.conn.execute("DELETE FROM question_attempts WHERE id = ?", (attempt_id,))
        self.conn.commit()
        return cur.rowcount > 0

    # --- Coach Goals ---

    def create_goal(self, g: CoachGoal) -> CoachGoal:
        self.conn.execute(
            "INSERT INTO coach_goals (id, title, goal_type, ref_id, deadline, priority, daily_minutes, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (g.id, g.title, g.goal_type.value, g.ref_id,
             g.deadline.isoformat() if g.deadline else None,
             g.priority, g.daily_minutes, g.created_at.isoformat()),
        )
        self.conn.commit()
        return g

    def get_goal(self, goal_id: str) -> Optional[CoachGoal]:
        row = self.conn.execute("SELECT * FROM coach_goals WHERE id = ?", (goal_id,)).fetchone()
        return _row_to_goal(row) if row else None

    def list_goals(self) -> list[CoachGoal]:
        rows = self.conn.execute("SELECT * FROM coach_goals ORDER BY priority ASC, created_at ASC").fetchall()
        return [_row_to_goal(r) for r in rows]

    def update_goal(self, goal_id: str, **kwargs) -> Optional[CoachGoal]:
        allowed = {"title", "goal_type", "ref_id", "deadline", "priority", "daily_minutes"}
        updates, params = [], []
        for key, value in kwargs.items():
            if key not in allowed:
                continue
            updates.append(f"{key} = ?")
            if key == "goal_type" and isinstance(value, GoalType):
                params.append(value.value)
            elif key == "deadline" and hasattr(value, "isoformat"):
                params.append(value.isoformat())
            else:
                params.append(value)
        if not updates:
            return self.get_goal(goal_id)
        params.append(goal_id)
        self.conn.execute(f"UPDATE coach_goals SET {', '.join(updates)} WHERE id = ?", params)
        self.conn.commit()
        return self.get_goal(goal_id)

    def delete_goal(self, goal_id: str) -> bool:
        cur = self.conn.execute("DELETE FROM coach_goals WHERE id = ?", (goal_id,))
        self.conn.commit()
        return cur.rowcount > 0

    def get_due_counts(self) -> dict:
        now = datetime.now().isoformat()
        concepts = self.conn.execute(
            "SELECT COUNT(*) FROM review_records WHERE next_review_at <= ?", (now,)
        ).fetchone()[0]
        entries = self.conn.execute(
            "SELECT COUNT(*) FROM entry_review_records WHERE next_review_at <= ?", (now,)
        ).fetchone()[0]
        questions = self.conn.execute(
            "SELECT COUNT(*) FROM interview_questions WHERE next_review_at IS NOT NULL AND next_review_at <= ?", (now,)
        ).fetchone()[0]
        problems = self.conn.execute(
            "SELECT COUNT(*) FROM problems WHERE next_review_at IS NOT NULL AND next_review_at <= ?", (now,)
        ).fetchone()[0]
        return {
            "concepts": concepts,
            "entries": entries,
            "questions": questions,
            "problems": problems,
        }

    def get_week_done_count(self) -> int:
        from datetime import date, timedelta
        today = date.today()
        monday = (today - timedelta(days=today.weekday())).isoformat()
        row = self.conn.execute(
            "SELECT COUNT(*) FROM plan_tasks WHERE done = 1 AND plan_date >= ?", (monday,)
        ).fetchone()
        return row[0] if row else 0

    # --- Problems ---

    def create_problem(self, p: Problem) -> Problem:
        import json
        self.conn.execute(
            "INSERT INTO problems (id, title, problem_type, difficulty, url, tags, notes, "
            "ef, interval, reps, next_review_at, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (p.id, p.title, p.problem_type.value,
             p.difficulty.value if p.difficulty else None,
             p.url, json.dumps(p.tags), p.notes,
             p.ef, p.interval, p.reps,
             p.next_review_at.isoformat() if p.next_review_at else None,
             p.created_at.isoformat()),
        )
        self.conn.commit()
        return p

    def get_problem(self, problem_id: str) -> Optional[Problem]:
        row = self.conn.execute(
            "SELECT * FROM problems WHERE id = ?", (problem_id,)
        ).fetchone()
        return _row_to_problem(row) if row else None

    def list_problems(
        self,
        problem_type: Optional[ProblemType] = None,
        due_only: bool = False,
    ) -> list[Problem]:
        clauses, params = [], []
        if problem_type:
            clauses.append("problem_type = ?")
            params.append(problem_type.value)
        if due_only:
            now = datetime.now().isoformat()
            clauses.append("(next_review_at IS NULL OR next_review_at <= ?)")
            params.append(now)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.conn.execute(
            f"SELECT * FROM problems {where} ORDER BY created_at DESC", params
        ).fetchall()
        return [_row_to_problem(r) for r in rows]

    def update_problem(self, problem_id: str, **kwargs) -> Optional[Problem]:
        import json
        allowed = {"title", "difficulty", "url", "tags", "notes"}
        updates, params = [], []
        for key, value in kwargs.items():
            if key not in allowed:
                continue
            updates.append(f"{key} = ?")
            if key == "tags":
                params.append(json.dumps(value))
            elif key == "difficulty" and isinstance(value, ProblemDifficulty):
                params.append(value.value)
            else:
                params.append(value)
        if not updates:
            return self.get_problem(problem_id)
        params.append(problem_id)
        self.conn.execute(
            f"UPDATE problems SET {', '.join(updates)} WHERE id = ?", params
        )
        self.conn.commit()
        return self.get_problem(problem_id)

    def delete_problem(self, problem_id: str) -> bool:
        cur = self.conn.execute("DELETE FROM problems WHERE id = ?", (problem_id,))
        self.conn.commit()
        return cur.rowcount > 0

    def record_problem_review(self, problem_id: str, grade: int) -> ProblemReviewRecord:
        p = self.get_problem(problem_id)
        if p is None:
            raise ValueError(f"Problem {problem_id} not found")
        ef, interval, reps = p.ef, p.interval, p.reps
        if grade >= 2:
            if reps == 0:
                interval = 1
            elif reps == 1:
                interval = 3
            else:
                interval = round(interval * ef)
            reps += 1
            ef = max(1.3, ef + 0.1 - (3 - grade) * (0.08 + (3 - grade) * 0.02))
        else:
            reps = 0
            interval = 1
        now = datetime.now()
        next_review = now + timedelta(days=interval)
        self.conn.execute(
            "UPDATE problems SET ef = ?, interval = ?, reps = ?, next_review_at = ? WHERE id = ?",
            (ef, interval, reps, next_review.isoformat(), problem_id),
        )
        self.conn.commit()
        return ProblemReviewRecord(
            problem_id=problem_id, grade=grade,
            reviewed_at=now, next_review_at=next_review,
            interval=interval, reps=reps, ef=ef,
        )

    def get_next_due_problem(
        self, problem_type: Optional[ProblemType] = None
    ) -> Optional[Problem]:
        now = datetime.now().isoformat()
        clauses = ["(next_review_at IS NULL OR next_review_at <= ?)"]
        params: list = [now]
        if problem_type:
            clauses.append("problem_type = ?")
            params.append(problem_type.value)
        where = "WHERE " + " AND ".join(clauses)
        row = self.conn.execute(
            f"SELECT * FROM problems {where} ORDER BY next_review_at ASC LIMIT 1", params
        ).fetchone()
        return _row_to_problem(row) if row else None

    def seed_curriculum(self) -> dict:
        existing = {p.title for p in self.list_problems()}

        _SD = [
            # Easy
            ("Design Bitly", "easy", "https://www.hellointerview.com/learn/system-design/in-a-hurry/bitly"),
            ("Design Dropbox", "easy", "https://www.hellointerview.com/learn/system-design/in-a-hurry/dropbox"),
            ("Design Local Delivery Service", "easy", "https://www.hellointerview.com/learn/system-design/in-a-hurry/local-delivery-service"),
            ("Design News Aggregator", "easy", "https://www.hellointerview.com/learn/system-design/in-a-hurry/news-aggregator"),
            # Medium
            ("Design Ticketmaster", "medium", "https://www.hellointerview.com/learn/system-design/in-a-hurry/ticketmaster"),
            ("Design Facebook News Feed", "medium", "https://www.hellointerview.com/learn/system-design/in-a-hurry/fb-news-feed"),
            ("Design Tinder", "medium", "https://www.hellointerview.com/learn/system-design/in-a-hurry/tinder"),
            ("Design WhatsApp", "medium", "https://www.hellointerview.com/learn/system-design/in-a-hurry/whatsapp"),
            ("Design Yelp", "medium", "https://www.hellointerview.com/learn/system-design/in-a-hurry/yelp"),
            ("Design Strava", "medium", "https://www.hellointerview.com/learn/system-design/in-a-hurry/strava"),
            ("Design Rate Limiter", "medium", "https://www.hellointerview.com/learn/system-design/in-a-hurry/rate-limiter"),
            ("Design Online Auction", "medium", "https://www.hellointerview.com/learn/system-design/in-a-hurry/online-auction"),
            ("Design Facebook Live Comments", "medium", "https://www.hellointerview.com/learn/system-design/in-a-hurry/fb-live-comments"),
            ("Design Facebook Post Search", "medium", "https://www.hellointerview.com/learn/system-design/in-a-hurry/fb-post-search"),
            ("Design Price Tracking Service", "medium", "https://www.hellointerview.com/learn/system-design/in-a-hurry/price-tracking"),
            ("Design Twitter", "medium", "https://www.hellointerview.com/learn/system-design/in-a-hurry/twitter"),
            # Hard
            ("Design Instagram", "hard", "https://www.hellointerview.com/learn/system-design/in-a-hurry/instagram"),
            ("Design YouTube Top K", "hard", "https://www.hellointerview.com/learn/system-design/in-a-hurry/youtube-top-k"),
            ("Design Uber", "hard", "https://www.hellointerview.com/learn/system-design/in-a-hurry/uber"),
            ("Design Robinhood", "hard", "https://www.hellointerview.com/learn/system-design/in-a-hurry/robinhood"),
            ("Design Google Docs", "hard", "https://www.hellointerview.com/learn/system-design/in-a-hurry/google-docs"),
            ("Design Distributed Cache", "hard", "https://www.hellointerview.com/learn/system-design/in-a-hurry/distributed-cache"),
            ("Design YouTube", "hard", "https://www.hellointerview.com/learn/system-design/in-a-hurry/youtube"),
            ("Design Job Scheduler", "hard", "https://www.hellointerview.com/learn/system-design/in-a-hurry/job-scheduler"),
            ("Design Web Crawler", "hard", "https://www.hellointerview.com/learn/system-design/in-a-hurry/web-crawler"),
            ("Design Ad Click Aggregator", "hard", "https://www.hellointerview.com/learn/system-design/in-a-hurry/ad-click-aggregator"),
            ("Design Payment System", "hard", "https://www.hellointerview.com/learn/system-design/in-a-hurry/payment-system"),
            ("Design Metrics Monitoring", "hard", "https://www.hellointerview.com/learn/system-design/in-a-hurry/metrics-monitoring"),
        ]

        _LLD = [
            ("Design a Parking Lot", None, "https://www.hellointerview.com/learn/system-design/in-a-hurry/lld-parking-lot"),
            ("Design an Elevator System", None, "https://www.hellointerview.com/learn/system-design/in-a-hurry/lld-elevator"),
            ("Design a Library Management System", None, None),
            ("Design a Vending Machine", None, None),
            ("Design an ATM", None, None),
            ("Design a Chess Game", None, None),
            ("Design a Hotel Management System", None, None),
            ("Design a Ride-Sharing Service (LLD)", None, None),
            ("Design a Food Ordering System", None, None),
            ("Design an Online Shopping Cart", None, None),
        ]

        _CODING = [
            ("Arrays & Hashing", None, "https://neetcode.io/roadmap"),
            ("Two Pointers", None, "https://neetcode.io/roadmap"),
            ("Sliding Window", None, "https://neetcode.io/roadmap"),
            ("Stack", None, "https://neetcode.io/roadmap"),
            ("Binary Search", None, "https://neetcode.io/roadmap"),
            ("Linked List", None, "https://neetcode.io/roadmap"),
            ("Trees", None, "https://neetcode.io/roadmap"),
            ("Tries", None, "https://neetcode.io/roadmap"),
            ("Heap / Priority Queue", None, "https://neetcode.io/roadmap"),
            ("Backtracking", None, "https://neetcode.io/roadmap"),
            ("Graphs", None, "https://neetcode.io/roadmap"),
            ("Advanced Graphs", None, "https://neetcode.io/roadmap"),
            ("1-D Dynamic Programming", None, "https://neetcode.io/roadmap"),
            ("2-D Dynamic Programming", None, "https://neetcode.io/roadmap"),
            ("Greedy", None, "https://neetcode.io/roadmap"),
            ("Intervals", None, "https://neetcode.io/roadmap"),
            ("Math & Geometry", None, "https://neetcode.io/roadmap"),
            ("Bit Manipulation", None, "https://neetcode.io/roadmap"),
        ]

        added = {"sd": 0, "lld": 0, "coding": 0}
        import uuid as _uuid

        for title, diff, url in _SD:
            if title not in existing:
                self.create_problem(Problem(
                    id=str(_uuid.uuid4()), title=title,
                    problem_type=ProblemType.SD,
                    difficulty=ProblemDifficulty(diff) if diff else None,
                    url=url, created_at=datetime.now(),
                ))
                added["sd"] += 1

        for title, diff, url in _LLD:
            if title not in existing:
                self.create_problem(Problem(
                    id=str(_uuid.uuid4()), title=title,
                    problem_type=ProblemType.LLD,
                    difficulty=ProblemDifficulty(diff) if diff else None,
                    url=url, created_at=datetime.now(),
                ))
                added["lld"] += 1

        for title, diff, url in _CODING:
            if title not in existing:
                self.create_problem(Problem(
                    id=str(_uuid.uuid4()), title=title,
                    problem_type=ProblemType.CODING,
                    difficulty=ProblemDifficulty(diff) if diff else None,
                    url=url, created_at=datetime.now(),
                ))
                added["coding"] += 1

        return added

    # --- Sources ---

    def create_source(self, s: "Source") -> "Source":
        import json
        self.conn.execute(
            "INSERT INTO sources (id, title, source_type, source_ref, content_cache, tags, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (s.id, s.title, s.source_type.value, s.source_ref, s.content_cache,
             json.dumps(s.tags), s.created_at.isoformat()),
        )
        self.conn.commit()
        return s

    def get_source(self, source_id: str) -> "Optional[Source]":
        row = self.conn.execute(
            "SELECT * FROM sources WHERE id = ?", (source_id,)
        ).fetchone()
        return _row_to_source(row) if row else None

    def list_sources(self) -> "list[Source]":
        rows = self.conn.execute(
            "SELECT * FROM sources ORDER BY created_at DESC"
        ).fetchall()
        return [_row_to_source(r) for r in rows]

    def delete_source(self, source_id: str) -> None:
        self.conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))
        self.conn.commit()

    def get_questions_by_source(self, source_id: str) -> list:
        rows = self.conn.execute(
            "SELECT * FROM interview_questions WHERE source_id = ? ORDER BY created_at DESC",
            (source_id,),
        ).fetchall()
        return [_row_to_question(r) for r in rows]


def _row_to_highlight(row: sqlite3.Row) -> Highlight:
    return Highlight(
        id=row["id"],
        text=row["text"],
        color=HighlightColor(row["color"]),
        book_id=row["book_id"],
        book_title=row["book_title"],
        chapter=row["chapter"],
    )


def _row_to_application(row: sqlite3.Row) -> Application:
    from datetime import date as date_type
    return Application(
        id=row["id"],
        company=row["company"],
        role=row["role"],
        status=ApplicationStatus(row["status"]),
        location=row["location"],
        work_model=row["work_model"],
        salary_range=row["salary_range"],
        job_link=row["job_link"],
        resume_version=row["resume_version"],
        notes=row["notes"],
        applied_at=date_type.fromisoformat(row["applied_at"]) if row["applied_at"] else None,
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _row_to_round(row: sqlite3.Row) -> ApplicationRound:
    keys = row.keys()
    round_type = RoundType(row["round_type"]) if "round_type" in keys and row["round_type"] else None
    status_val = row["status"] if "status" in keys and row["status"] else "scheduled"
    return ApplicationRound(
        id=row["id"],
        application_id=row["application_id"],
        name=row["name"],
        round_type=round_type,
        status=RoundStatus(status_val),
        date=row["date"],
        feedback=row["feedback"],
    )


def _row_to_question(row: sqlite3.Row) -> InterviewQuestion:
    import json
    from notemaster.models import QuestionCategory
    keys = row.keys()
    return InterviewQuestion(
        id=row["id"],
        question=row["question"],
        answer=row["answer"],
        q_type=QuestionType(row["q_type"]),
        source=QuestionSource(row["source"]),
        category=QuestionCategory(row["category"]) if row["category"] else QuestionCategory.INTERVIEW,
        application_id=row["application_id"],
        source_id=row["source_id"] if "source_id" in keys else None,
        problem_id=row["problem_id"] if "problem_id" in keys else None,
        round=row["round"],
        self_score=row["self_score"],
        tags=json.loads(row["tags"]),
        notes=row["notes"],
        key_points=json.loads(row["key_points"]) if "key_points" in keys and row["key_points"] else [],
        sub_questions=json.loads(row["sub_questions"]) if "sub_questions" in keys and row["sub_questions"] else [],
        ef=row["ef"],
        interval=row["interval"],
        reps=row["reps"],
        next_review_at=datetime.fromisoformat(row["next_review_at"]) if row["next_review_at"] else None,
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _row_to_problem(row: sqlite3.Row) -> Problem:
    import json
    return Problem(
        id=row["id"],
        title=row["title"],
        problem_type=ProblemType(row["problem_type"]),
        difficulty=ProblemDifficulty(row["difficulty"]) if row["difficulty"] else None,
        url=row["url"],
        tags=json.loads(row["tags"] or "[]"),
        notes=row["notes"],
        ef=row["ef"],
        interval=row["interval"],
        reps=row["reps"],
        next_review_at=datetime.fromisoformat(row["next_review_at"]) if row["next_review_at"] else None,
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _row_to_source(row: sqlite3.Row) -> Source:
    import json
    return Source(
        id=row["id"],
        title=row["title"],
        source_type=SourceType(row["source_type"]),
        source_ref=row["source_ref"],
        content_cache=row["content_cache"],
        tags=json.loads(row["tags"] or "[]"),
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _row_to_entry(row: sqlite3.Row) -> Entry:
    import json
    keys = row.keys()
    raw = json.loads(row["data"] or "{}")
    return Entry(
        id=row["id"],
        text=row["text"],
        source_type=EntryType(row["source_type"]),
        source_ref=row["source_ref"],
        data=EntryData(**{k: v for k, v in raw.items() if v is not None}),
        tags=json.loads(row["tags"]) if "tags" in keys and row["tags"] else [],
        weight=row["weight"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )



def _row_to_goal(row: sqlite3.Row) -> CoachGoal:
    from datetime import date as date_type
    deadline = date_type.fromisoformat(row["deadline"]) if row["deadline"] else None
    return CoachGoal(
        id=row["id"],
        title=row["title"],
        goal_type=GoalType(row["goal_type"]),
        ref_id=row["ref_id"],
        deadline=deadline,
        priority=row["priority"],
        daily_minutes=row["daily_minutes"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _row_to_attempt(row: sqlite3.Row) -> QuestionAttempt:
    import json
    return QuestionAttempt(
        id=row["id"],
        question_id=row["question_id"],
        response_text=row["response_text"],
        coverage=json.loads(row["coverage"]) if row["coverage"] else [],
        ai_feedback=row["ai_feedback"],
        score=row["score"],
        attempted_at=datetime.fromisoformat(row["attempted_at"]),
    )
