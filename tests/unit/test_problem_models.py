"""Tests for Problem models."""
import pytest
from datetime import datetime
from notemaster.models import Problem, ProblemType, ProblemDifficulty, ProblemReviewRecord


def make_problem(**kwargs):
    defaults = dict(
        id="p-1",
        title="Design Bitly",
        problem_type=ProblemType.SD,
        created_at=datetime(2026, 4, 27),
    )
    return Problem(**{**defaults, **kwargs})


class TestProblemModel:
    def test_create_sd(self):
        p = make_problem()
        assert p.id == "p-1"
        assert p.problem_type == ProblemType.SD

    def test_create_lld(self):
        p = make_problem(title="Design Parking Lot", problem_type=ProblemType.LLD)
        assert p.problem_type == ProblemType.LLD

    def test_create_coding(self):
        p = make_problem(
            title="LRU Cache", problem_type=ProblemType.CODING,
            difficulty=ProblemDifficulty.MEDIUM,
        )
        assert p.problem_type == ProblemType.CODING
        assert p.difficulty == ProblemDifficulty.MEDIUM

    def test_url_optional(self):
        p = make_problem(url="https://leetcode.com/problems/lru-cache")
        assert p.url is not None

    def test_tags_default_empty(self):
        p = make_problem()
        assert p.tags == []

    def test_sm2_defaults(self):
        p = make_problem()
        assert p.ef == 2.5
        assert p.interval == 0
        assert p.reps == 0
        assert p.next_review_at is None

    def test_difficulty_optional(self):
        p = make_problem()
        assert p.difficulty is None


class TestProblemTypes:
    def test_sd_value(self):
        assert ProblemType.SD == "sd"

    def test_lld_value(self):
        assert ProblemType.LLD == "lld"

    def test_coding_value(self):
        assert ProblemType.CODING == "coding"

    def test_difficulty_values(self):
        assert ProblemDifficulty.EASY == "easy"
        assert ProblemDifficulty.MEDIUM == "medium"
        assert ProblemDifficulty.HARD == "hard"


class TestProblemReviewRecord:
    def test_create(self):
        r = ProblemReviewRecord(
            problem_id="p-1", grade=4,
            reviewed_at=datetime(2026, 4, 27),
            next_review_at=datetime(2026, 4, 28),
            interval=1, reps=1, ef=2.5,
        )
        assert r.problem_id == "p-1"
        assert r.grade == 4
