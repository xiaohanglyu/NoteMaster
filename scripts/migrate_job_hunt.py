#!/usr/bin/env python3
"""
Migrate job-hunt localStorage export into NoteMaster SQLite.

Usage:
    python scripts/migrate_job_hunt.py data/job_hunt_export.json
    python scripts/migrate_job_hunt.py data/job_hunt_export.json --dry-run
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from notemaster.db import Database
from notemaster.models import (
    Application, ApplicationStatus,
    InterviewQuestion, QuestionType, QuestionSource,
)

_STATUS_MAP = {
    "applied":  ApplicationStatus.APPLIED,
    "phone":    ApplicationStatus.PHONE,
    "tech":     ApplicationStatus.TECHNICAL,
    "technical":ApplicationStatus.TECHNICAL,
    "onsite":   ApplicationStatus.ONSITE,
    "offer":    ApplicationStatus.OFFER,
    "rejected": ApplicationStatus.REJECTED,
}

_TYPE_MAP = {
    "behavioral": QuestionType.BEHAVIORAL,
    "system":     QuestionType.SYSTEM_DESIGN,
    "system_design": QuestionType.SYSTEM_DESIGN,
    "coding":     QuestionType.CODING,
    "other":      QuestionType.OTHER,
}


def _ms_to_datetime(ms) -> datetime | None:
    if not ms:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).replace(tzinfo=None)


def migrate(export_path: str, dry_run: bool = False) -> dict:
    data = json.loads(Path(export_path).read_text())
    apps_raw = data.get("apps", [])
    questions_raw = data.get("questions", [])

    db = Database()

    apps_imported = 0
    rounds_imported = 0
    questions_imported = 0

    # Map old job-hunt appId → NoteMaster application id
    app_id_map: dict[str, str] = {}

    for a in apps_raw:
        old_id = a.get("id", "")
        app_id = old_id  # reuse same id for idempotency

        existing = db.get_application(app_id)
        if existing:
            app_id_map[old_id] = app_id
            continue

        applied_at = None
        date_raw = a.get("date") or a.get("applied_at")
        if date_raw:
            if isinstance(date_raw, (int, float)):
                applied_at = _ms_to_datetime(date_raw).date()
            else:
                try:
                    applied_at = datetime.fromisoformat(str(date_raw)).date()
                except ValueError:
                    pass

        status = _STATUS_MAP.get(str(a.get("status", "applied")).lower(), ApplicationStatus.APPLIED)

        app_obj = Application(
            id=app_id,
            company=a.get("company", "Unknown"),
            role=a.get("role", "Unknown"),
            status=status,
            location=a.get("location") or None,
            work_model=a.get("workmodel") or a.get("work_model") or None,
            salary_range=a.get("salary") or a.get("salary_range") or None,
            job_link=a.get("joblink") or a.get("job_link") or None,
            resume_version=a.get("resumev") or a.get("resume_version") or None,
            notes=a.get("notes") or None,
            applied_at=applied_at,
            created_at=datetime.now(),
        )

        if not dry_run:
            db.create_application(app_obj)
            for r in a.get("rounds", []):
                db.add_application_round(
                    app_id,
                    name=r.get("name", "Round"),
                    date=r.get("date") or None,
                    feedback=r.get("feedback") or None,
                )
                rounds_imported += 1

        apps_imported += 1
        app_id_map[old_id] = app_id
        print(f"  {'[dry-run] ' if dry_run else ''}App: {app_obj.company} — {app_obj.role}")

    for q in questions_raw:
        old_id = q.get("id", "")
        q_id = old_id

        existing = db.get_question(q_id)
        if existing:
            continue

        q_type = _TYPE_MAP.get(str(q.get("type", "other")).lower(), QuestionType.OTHER)
        source = QuestionSource.REAL if q.get("source") == "real" else QuestionSource.MOCK
        app_id = app_id_map.get(q.get("appId") or "")

        next_review_at = _ms_to_datetime(q.get("nextReview"))
        created_at = _ms_to_datetime(q.get("created")) or datetime.now()

        q_obj = InterviewQuestion(
            id=q_id,
            question=q.get("q", ""),
            answer=q.get("a") or None,
            q_type=q_type,
            source=source,
            application_id=app_id,
            round=q.get("round") or None,
            self_score=min(3, max(0, int(q.get("score") or 0))),
            tags=q.get("tags") or [],
            notes=q.get("note") or None,
            ef=float(q.get("ef") or 2.5),
            interval=int(q.get("interval") or 0),
            reps=int(q.get("reps") or 0),
            next_review_at=next_review_at,
            created_at=created_at,
        )

        if not dry_run:
            db.create_question(q_obj)

        questions_imported += 1
        print(f"  {'[dry-run] ' if dry_run else ''}Question: {q_obj.question[:60]}")

    return {
        "apps": apps_imported,
        "rounds": rounds_imported,
        "questions": questions_imported,
        "dry_run": dry_run,
    }


def main():
    parser = argparse.ArgumentParser(description="Migrate job-hunt data into NoteMaster")
    parser.add_argument("file", help="Path to job-hunt JSON export")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be imported without writing")
    args = parser.parse_args()

    print(f"{'[DRY RUN] ' if args.dry_run else ''}Migrating from {args.file} …\n")
    result = migrate(args.file, dry_run=args.dry_run)
    print(f"\n{'─'*40}")
    print(f"Applications : {result['apps']} imported")
    print(f"Rounds       : {result['rounds']} imported")
    print(f"Questions    : {result['questions']} imported")
    if result["dry_run"]:
        print("\n(dry-run — nothing written)")


if __name__ == "__main__":
    main()
