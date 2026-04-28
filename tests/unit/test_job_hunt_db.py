import pytest
from datetime import datetime, timedelta

from notemaster.db import Database
from notemaster.models import (
    Application, ApplicationStatus, ApplicationRound,
    InterviewQuestion, QuestionType, QuestionSource,
    QuestionReviewRecord,
)


@pytest.fixture
def db():
    return Database(":memory:")


@pytest.fixture
def app():
    return Application(
        id="app-1",
        company="Stripe",
        role="Software Engineer",
        status=ApplicationStatus.APPLIED,
        applied_at=datetime(2026, 4, 1).date(),
        created_at=datetime(2026, 4, 1, 10, 0),
    )


@pytest.fixture
def question():
    return InterviewQuestion(
        id="q-1",
        question="Tell me about yourself",
        answer="I'm a backend engineer with 5 years of experience.",
        q_type=QuestionType.BEHAVIORAL,
        source=QuestionSource.MOCK,
        created_at=datetime(2026, 4, 1, 10, 0),
    )


# ---------------------------------------------------------------------------
# Applications CRUD
# ---------------------------------------------------------------------------

class TestApplicationCrud:
    def test_create_and_get(self, db, app):
        db.create_application(app)
        retrieved = db.get_application(app.id)
        assert retrieved is not None
        assert retrieved.company == "Stripe"
        assert retrieved.role == "Software Engineer"
        assert retrieved.status == ApplicationStatus.APPLIED

    def test_list_all(self, db, app):
        db.create_application(app)
        apps = db.get_applications()
        assert len(apps) == 1
        assert apps[0].id == app.id

    def test_list_filter_by_status(self, db, app):
        db.create_application(app)
        app2 = app.model_copy(update={"id": "app-2", "status": ApplicationStatus.OFFER})
        db.create_application(app2)
        applied = db.get_applications(status=ApplicationStatus.APPLIED)
        assert len(applied) == 1
        assert applied[0].id == "app-1"

    def test_update_status(self, db, app):
        db.create_application(app)
        updated = db.update_application(app.id, status=ApplicationStatus.PHONE)
        assert updated.status == ApplicationStatus.PHONE
        assert db.get_application(app.id).status == ApplicationStatus.PHONE

    def test_update_notes(self, db, app):
        db.create_application(app)
        updated = db.update_application(app.id, notes="Great culture fit")
        assert updated.notes == "Great culture fit"

    def test_delete(self, db, app):
        db.create_application(app)
        db.delete_application(app.id)
        assert db.get_application(app.id) is None

    def test_get_nonexistent_returns_none(self, db):
        assert db.get_application("does-not-exist") is None


# ---------------------------------------------------------------------------
# Application Rounds
# ---------------------------------------------------------------------------

class TestApplicationRounds:
    def test_add_round(self, db, app):
        db.create_application(app)
        r = db.add_application_round(ApplicationRound(application_id=app.id, name="Phone Screen", date="2026-04-10", feedback="Went well"))
        assert r.id is not None
        assert r.name == "Phone Screen"
        assert r.application_id == app.id

    def test_get_rounds(self, db, app):
        db.create_application(app)
        db.add_application_round(ApplicationRound(application_id=app.id, name="Phone Screen"))
        db.add_application_round(ApplicationRound(application_id=app.id, name="Technical"))
        rounds = db.get_application_rounds(app.id)
        assert len(rounds) == 2

    def test_update_round(self, db, app):
        db.create_application(app)
        r = db.add_application_round(ApplicationRound(application_id=app.id, name="Phone Screen"))
        updated = db.update_application_round(r.id, feedback="Strong hire")
        assert updated.feedback == "Strong hire"

    def test_delete_application_cascades_rounds(self, db, app):
        db.create_application(app)
        db.add_application_round(ApplicationRound(application_id=app.id, name="Phone Screen"))
        db.delete_application(app.id)
        assert db.get_application_rounds(app.id) == []


# ---------------------------------------------------------------------------
# Interview Questions CRUD
# ---------------------------------------------------------------------------

class TestInterviewQuestionCrud:
    def test_create_and_get(self, db, question):
        db.create_question(question)
        retrieved = db.get_question(question.id)
        assert retrieved is not None
        assert retrieved.question == "Tell me about yourself"
        assert retrieved.q_type == QuestionType.BEHAVIORAL
        assert retrieved.source == QuestionSource.MOCK

    def test_list_all(self, db, question):
        db.create_question(question)
        questions = db.get_questions()
        assert len(questions) == 1

    def test_list_filter_by_type(self, db, question):
        db.create_question(question)
        q2 = question.model_copy(update={"id": "q-2", "q_type": QuestionType.CODING})
        db.create_question(q2)
        behavioral = db.get_questions(q_type=QuestionType.BEHAVIORAL)
        assert len(behavioral) == 1
        assert behavioral[0].id == "q-1"

    def test_list_filter_by_application(self, db, question, app):
        db.create_application(app)
        q_linked = question.model_copy(update={"id": "q-linked", "application_id": app.id})
        db.create_question(question)
        db.create_question(q_linked)
        linked = db.get_questions(application_id=app.id)
        assert len(linked) == 1
        assert linked[0].id == "q-linked"

    def test_list_due_only(self, db, question):
        past = datetime.now() - timedelta(days=1)
        future = datetime.now() + timedelta(days=1)
        q_due = question.model_copy(update={"id": "q-due", "next_review_at": past})
        q_future = question.model_copy(update={"id": "q-future", "next_review_at": future})
        db.create_question(q_due)
        db.create_question(q_future)
        due = db.get_questions(due_only=True)
        assert len(due) == 1
        assert due[0].id == "q-due"

    def test_new_question_counts_as_due(self, db, question):
        db.create_question(question)
        due = db.get_questions(due_only=True)
        assert len(due) == 1

    def test_update_question(self, db, question):
        db.create_question(question)
        updated = db.update_question(question.id, answer="Updated answer", self_score=2)
        assert updated.answer == "Updated answer"
        assert updated.self_score == 2

    def test_delete_question(self, db, question):
        db.create_question(question)
        db.delete_question(question.id)
        assert db.get_question(question.id) is None

    def test_tags_round_trip(self, db, question):
        q = question.model_copy(update={"tags": ["behavioral", "amazon"]})
        db.create_question(q)
        retrieved = db.get_question(q.id)
        assert retrieved.tags == ["behavioral", "amazon"]

    def test_delete_application_nullifies_question_app_id(self, db, app, question):
        db.create_application(app)
        q = question.model_copy(update={"application_id": app.id})
        db.create_question(q)
        db.delete_application(app.id)
        retrieved = db.get_question(q.id)
        assert retrieved.application_id is None

    def test_bulk_import(self, db):
        questions = [
            InterviewQuestion(
                id=f"q-{i}",
                question=f"Question {i}",
                q_type=QuestionType.BEHAVIORAL,
                source=QuestionSource.MOCK,
                created_at=datetime(2026, 4, 1, 10, 0),
            )
            for i in range(3)
        ]
        count = db.bulk_import_questions(questions)
        assert count == 3
        assert len(db.get_questions()) == 3

    def test_bulk_import_idempotent(self, db, question):
        db.create_question(question)
        count = db.bulk_import_questions([question])
        assert count == 0
        assert len(db.get_questions()) == 1


# ---------------------------------------------------------------------------
# SM-2 Review for Questions
# ---------------------------------------------------------------------------

class TestQuestionReview:
    def test_review_returns_record(self, db, question):
        db.create_question(question)
        record = db.record_question_review(question.id, grade=3)
        assert isinstance(record, QuestionReviewRecord)
        assert record.question_id == question.id

    def test_grade_3_schedules_future_review(self, db, question):
        db.create_question(question)
        record = db.record_question_review(question.id, grade=3)
        assert record.next_review_at > datetime.now()
        assert record.interval >= 1

    def test_grade_1_resets_to_one_day(self, db, question):
        db.create_question(question)
        db.record_question_review(question.id, grade=3)
        record = db.record_question_review(question.id, grade=1)
        assert record.interval == 1
        assert record.reps == 0

    def test_consecutive_strong_reviews_grow_interval(self, db, question):
        db.create_question(question)
        r1 = db.record_question_review(question.id, grade=3)
        r2 = db.record_question_review(question.id, grade=3)
        r3 = db.record_question_review(question.id, grade=3)
        assert r3.interval >= r2.interval >= r1.interval

    def test_review_persisted_on_question(self, db, question):
        db.create_question(question)
        db.record_question_review(question.id, grade=3)
        retrieved = db.get_question(question.id)
        assert retrieved.reps == 1
        assert retrieved.next_review_at is not None

    def test_get_next_due_question(self, db, question):
        db.create_question(question)
        next_q = db.get_next_due_question()
        assert next_q is not None
        assert next_q.id == question.id

    def test_no_due_question_returns_none(self, db, question):
        db.create_question(question)
        db.record_question_review(question.id, grade=3)
        q = db.get_question(question.id)
        if q.next_review_at > datetime.now():
            assert db.get_next_due_question() is None

    def test_review_nonexistent_raises(self, db):
        with pytest.raises(ValueError):
            db.record_question_review("ghost-id", grade=3)
