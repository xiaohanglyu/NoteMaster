"""Tests for Problem DB CRUD."""
import pytest
from datetime import datetime
from notemaster.models import Problem, ProblemType, ProblemDifficulty


@pytest.fixture
def db(tmp_path):
    from notemaster.db import Database
    return Database(tmp_path / "test.db")


def make_problem(pid="p-1", problem_type=ProblemType.SD, title="Design Bitly", **kwargs):
    return Problem(
        id=pid, title=title, problem_type=problem_type,
        created_at=datetime(2026, 4, 27), **kwargs
    )


class TestCreateProblem:
    def test_create_returns_problem(self, db):
        p = db.create_problem(make_problem())
        assert p.id == "p-1"
        assert p.title == "Design Bitly"

    def test_create_stores_type(self, db):
        db.create_problem(make_problem(problem_type=ProblemType.LLD))
        fetched = db.get_problem("p-1")
        assert fetched.problem_type == ProblemType.LLD

    def test_create_stores_difficulty(self, db):
        db.create_problem(make_problem(
            problem_type=ProblemType.CODING, difficulty=ProblemDifficulty.MEDIUM
        ))
        fetched = db.get_problem("p-1")
        assert fetched.difficulty == ProblemDifficulty.MEDIUM

    def test_create_stores_tags(self, db):
        db.create_problem(make_problem(tags=["cache", "design"]))
        fetched = db.get_problem("p-1")
        assert "cache" in fetched.tags

    def test_create_stores_url(self, db):
        db.create_problem(make_problem(url="https://leetcode.com/lru-cache"))
        fetched = db.get_problem("p-1")
        assert fetched.url == "https://leetcode.com/lru-cache"


class TestGetProblem:
    def test_get_existing(self, db):
        db.create_problem(make_problem())
        p = db.get_problem("p-1")
        assert p is not None
        assert p.title == "Design Bitly"

    def test_get_missing_returns_none(self, db):
        assert db.get_problem("nonexistent") is None


class TestListProblems:
    def test_empty_list(self, db):
        assert db.list_problems() == []

    def test_returns_all(self, db):
        db.create_problem(make_problem("p-1", ProblemType.SD, "Bitly"))
        db.create_problem(make_problem("p-2", ProblemType.LLD, "Parking"))
        assert len(db.list_problems()) == 2

    def test_filter_by_type(self, db):
        db.create_problem(make_problem("p-1", ProblemType.SD, "Bitly"))
        db.create_problem(make_problem("p-2", ProblemType.LLD, "Parking"))
        sd = db.list_problems(problem_type=ProblemType.SD)
        assert len(sd) == 1
        assert sd[0].problem_type == ProblemType.SD

    def test_due_only_filters(self, db):
        from datetime import timedelta
        past = datetime(2026, 1, 1)
        future = datetime(2099, 1, 1)
        p1 = make_problem("p-1", ProblemType.SD, "A")
        p1.next_review_at = past
        p2 = make_problem("p-2", ProblemType.SD, "B")
        p2.next_review_at = future
        p3 = make_problem("p-3", ProblemType.SD, "C")  # no next_review_at = due
        db.create_problem(p1)
        db.create_problem(p2)
        db.create_problem(p3)
        due = db.list_problems(due_only=True)
        ids = {p.id for p in due}
        assert "p-1" in ids
        assert "p-3" in ids
        assert "p-2" not in ids


class TestUpdateProblem:
    def test_update_title(self, db):
        db.create_problem(make_problem())
        db.update_problem("p-1", title="Design TinyURL")
        p = db.get_problem("p-1")
        assert p.title == "Design TinyURL"

    def test_update_notes(self, db):
        db.create_problem(make_problem())
        db.update_problem("p-1", notes="Focus on consistent hashing")
        p = db.get_problem("p-1")
        assert p.notes == "Focus on consistent hashing"

    def test_update_tags(self, db):
        db.create_problem(make_problem())
        db.update_problem("p-1", tags=["hashing", "scale"])
        p = db.get_problem("p-1")
        assert "hashing" in p.tags

    def test_update_missing_returns_none(self, db):
        result = db.update_problem("nonexistent", title="X")
        assert result is None


class TestDeleteProblem:
    def test_delete_removes(self, db):
        db.create_problem(make_problem())
        assert db.delete_problem("p-1") is True
        assert db.get_problem("p-1") is None

    def test_delete_missing_returns_false(self, db):
        assert db.delete_problem("nonexistent") is False


class TestRecordProblemReview:
    def test_grade_4_advances(self, db):
        db.create_problem(make_problem())
        rec = db.record_problem_review("p-1", grade=4)
        assert rec.interval >= 1
        assert rec.reps == 1

    def test_grade_0_resets(self, db):
        db.create_problem(make_problem())
        db.record_problem_review("p-1", grade=4)
        rec = db.record_problem_review("p-1", grade=0)
        assert rec.reps == 0
        assert rec.interval == 1

    def test_next_review_set(self, db):
        db.create_problem(make_problem())
        rec = db.record_problem_review("p-1", grade=4)
        p = db.get_problem("p-1")
        assert p.next_review_at is not None

    def test_review_missing_raises(self, db):
        with pytest.raises(ValueError):
            db.record_problem_review("nonexistent", grade=4)


class TestGetNextDueProblem:
    def test_returns_due(self, db):
        p = make_problem("p-1", ProblemType.SD, "Bitly")
        p.next_review_at = datetime(2026, 1, 1)
        db.create_problem(p)
        nxt = db.get_next_due_problem()
        assert nxt is not None
        assert nxt.id == "p-1"

    def test_returns_none_when_empty(self, db):
        assert db.get_next_due_problem() is None

    def test_filter_by_type(self, db):
        p1 = make_problem("p-1", ProblemType.SD, "Bitly")
        p1.next_review_at = datetime(2026, 1, 1)
        p2 = make_problem("p-2", ProblemType.LLD, "Parking")
        p2.next_review_at = datetime(2026, 1, 1)
        db.create_problem(p1)
        db.create_problem(p2)
        nxt = db.get_next_due_problem(problem_type=ProblemType.LLD)
        assert nxt.problem_type == ProblemType.LLD
