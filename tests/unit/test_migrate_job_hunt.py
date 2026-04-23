import json
import pytest
from pathlib import Path
from datetime import datetime

from notemaster.db import Database
from notemaster.models import ApplicationStatus, QuestionType, QuestionSource


def make_export(tmp_path, apps=None, questions=None) -> str:
    data = {
        "apps": apps or [],
        "questions": questions or [],
        "sessions": [],
    }
    p = tmp_path / "export.json"
    p.write_text(json.dumps(data))
    return str(p)


SAMPLE_APP = {
    "id": "abc123",
    "company": "Stripe",
    "role": "Backend Engineer",
    "status": "applied",
    "location": "Remote",
    "workmodel": "remote",
    "salary": "$150k",
    "joblink": "https://stripe.com/jobs/1",
    "notes": "Great company",
    "date": 1745000000000,
    "rounds": [
        {"name": "Phone Screen", "date": "2026-04-10", "feedback": "Positive"},
    ],
}

SAMPLE_QUESTION = {
    "id": "q123",
    "q": "Tell me about yourself",
    "a": "Backend engineer with 5 years exp.",
    "type": "behavioral",
    "source": "real",
    "appId": "abc123",
    "round": "Phone Screen",
    "score": 2,
    "tags": ["intro", "amazon"],
    "note": "Practice more",
    "ef": 2.5,
    "interval": 3,
    "reps": 1,
    "nextReview": 1746000000000,
    "created": 1745000000000,
}


class TestMigrateApps:
    def test_imports_app(self, tmp_path, monkeypatch):
        from scripts import migrate_job_hunt
        export = make_export(tmp_path, apps=[SAMPLE_APP])
        db = Database(":memory:")
        monkeypatch.setattr(migrate_job_hunt, "Database", lambda: db)

        result = migrate_job_hunt.migrate(export)
        assert result["apps"] == 1
        app = db.get_application("abc123")
        assert app is not None
        assert app.company == "Stripe"
        assert app.status == ApplicationStatus.APPLIED
        assert app.location == "Remote"
        assert app.work_model == "remote"

    def test_imports_rounds(self, tmp_path, monkeypatch):
        from scripts import migrate_job_hunt
        export = make_export(tmp_path, apps=[SAMPLE_APP])
        db = Database(":memory:")
        monkeypatch.setattr(migrate_job_hunt, "Database", lambda: db)

        migrate_job_hunt.migrate(export)
        rounds = db.get_application_rounds("abc123")
        assert len(rounds) == 1
        assert rounds[0].name == "Phone Screen"

    def test_idempotent_apps(self, tmp_path, monkeypatch):
        from scripts import migrate_job_hunt
        export = make_export(tmp_path, apps=[SAMPLE_APP])
        db = Database(":memory:")
        monkeypatch.setattr(migrate_job_hunt, "Database", lambda: db)

        r1 = migrate_job_hunt.migrate(export)
        r2 = migrate_job_hunt.migrate(export)
        assert r1["apps"] == 1
        assert r2["apps"] == 0

    def test_status_mapping_tech(self, tmp_path, monkeypatch):
        from scripts import migrate_job_hunt
        app = {**SAMPLE_APP, "id": "a2", "status": "tech"}
        export = make_export(tmp_path, apps=[app])
        db = Database(":memory:")
        monkeypatch.setattr(migrate_job_hunt, "Database", lambda: db)

        migrate_job_hunt.migrate(export)
        assert db.get_application("a2").status == ApplicationStatus.TECHNICAL

    def test_dry_run_does_not_write(self, tmp_path, monkeypatch):
        from scripts import migrate_job_hunt
        export = make_export(tmp_path, apps=[SAMPLE_APP])
        db = Database(":memory:")
        monkeypatch.setattr(migrate_job_hunt, "Database", lambda: db)

        result = migrate_job_hunt.migrate(export, dry_run=True)
        assert result["apps"] == 1
        assert result["dry_run"] is True
        assert db.get_application("abc123") is None


class TestMigrateQuestions:
    def test_imports_question(self, tmp_path, monkeypatch):
        from scripts import migrate_job_hunt
        export = make_export(tmp_path, apps=[SAMPLE_APP], questions=[SAMPLE_QUESTION])
        db = Database(":memory:")
        monkeypatch.setattr(migrate_job_hunt, "Database", lambda: db)

        result = migrate_job_hunt.migrate(export)
        assert result["questions"] == 1
        q = db.get_question("q123")
        assert q is not None
        assert q.question == "Tell me about yourself"
        assert q.q_type == QuestionType.BEHAVIORAL
        assert q.source == QuestionSource.REAL

    def test_preserves_sm2_state(self, tmp_path, monkeypatch):
        from scripts import migrate_job_hunt
        export = make_export(tmp_path, apps=[SAMPLE_APP], questions=[SAMPLE_QUESTION])
        db = Database(":memory:")
        monkeypatch.setattr(migrate_job_hunt, "Database", lambda: db)

        migrate_job_hunt.migrate(export)
        q = db.get_question("q123")
        assert q.ef == 2.5
        assert q.interval == 3
        assert q.reps == 1
        assert q.next_review_at is not None

    def test_links_question_to_app(self, tmp_path, monkeypatch):
        from scripts import migrate_job_hunt
        export = make_export(tmp_path, apps=[SAMPLE_APP], questions=[SAMPLE_QUESTION])
        db = Database(":memory:")
        monkeypatch.setattr(migrate_job_hunt, "Database", lambda: db)

        migrate_job_hunt.migrate(export)
        q = db.get_question("q123")
        assert q.application_id == "abc123"

    def test_type_mapping_system(self, tmp_path, monkeypatch):
        from scripts import migrate_job_hunt
        q = {**SAMPLE_QUESTION, "id": "q2", "type": "system"}
        export = make_export(tmp_path, questions=[q])
        db = Database(":memory:")
        monkeypatch.setattr(migrate_job_hunt, "Database", lambda: db)

        migrate_job_hunt.migrate(export)
        assert db.get_question("q2").q_type == QuestionType.SYSTEM_DESIGN

    def test_idempotent_questions(self, tmp_path, monkeypatch):
        from scripts import migrate_job_hunt
        export = make_export(tmp_path, questions=[SAMPLE_QUESTION])
        db = Database(":memory:")
        monkeypatch.setattr(migrate_job_hunt, "Database", lambda: db)

        r1 = migrate_job_hunt.migrate(export)
        r2 = migrate_job_hunt.migrate(export)
        assert r1["questions"] == 1
        assert r2["questions"] == 0

    def test_dry_run_questions_not_written(self, tmp_path, monkeypatch):
        from scripts import migrate_job_hunt
        export = make_export(tmp_path, questions=[SAMPLE_QUESTION])
        db = Database(":memory:")
        monkeypatch.setattr(migrate_job_hunt, "Database", lambda: db)

        migrate_job_hunt.migrate(export, dry_run=True)
        assert db.get_question("q123") is None

    def test_tags_preserved(self, tmp_path, monkeypatch):
        from scripts import migrate_job_hunt
        export = make_export(tmp_path, questions=[SAMPLE_QUESTION])
        db = Database(":memory:")
        monkeypatch.setattr(migrate_job_hunt, "Database", lambda: db)

        migrate_job_hunt.migrate(export)
        q = db.get_question("q123")
        assert q.tags == ["intro", "amazon"]
