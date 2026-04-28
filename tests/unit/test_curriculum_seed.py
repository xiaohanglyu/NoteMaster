"""Tests for curriculum pre-seeding (#47)."""
import pytest
from notemaster.models import ProblemType


@pytest.fixture
def db(tmp_path):
    from notemaster.db import Database
    return Database(tmp_path / "test.db")


class TestSeedCurriculum:
    def test_seed_creates_sd_problems(self, db):
        db.seed_curriculum()
        sd = db.list_problems(problem_type=ProblemType.SD)
        assert len(sd) >= 10  # at least 10 SD problems

    def test_seed_creates_lld_problems(self, db):
        db.seed_curriculum()
        lld = db.list_problems(problem_type=ProblemType.LLD)
        assert len(lld) >= 5

    def test_seed_creates_coding_problems(self, db):
        db.seed_curriculum()
        coding = db.list_problems(problem_type=ProblemType.CODING)
        assert len(coding) >= 10  # NeetCode categories

    def test_seed_idempotent(self, db):
        db.seed_curriculum()
        count1 = len(db.list_problems())
        db.seed_curriculum()
        count2 = len(db.list_problems())
        assert count1 == count2  # second call adds nothing

    def test_sd_has_difficulties(self, db):
        db.seed_curriculum()
        sd = db.list_problems(problem_type=ProblemType.SD)
        diffs = {p.difficulty for p in sd if p.difficulty}
        assert len(diffs) >= 2  # easy + medium + hard

    def test_sd_problems_have_urls(self, db):
        db.seed_curriculum()
        sd = db.list_problems(problem_type=ProblemType.SD)
        with_url = [p for p in sd if p.url]
        assert len(with_url) > 0

    def test_coding_problems_have_urls(self, db):
        db.seed_curriculum()
        coding = db.list_problems(problem_type=ProblemType.CODING)
        with_url = [p for p in coding if p.url]
        assert len(with_url) > 0

    def test_seed_skips_if_already_seeded(self, db):
        db.seed_curriculum()
        from notemaster.models import Problem, ProblemType
        from datetime import datetime
        # Manually add an extra problem
        db.create_problem(Problem(
            id="manual-1", title="Custom Problem",
            problem_type=ProblemType.SD, created_at=datetime.now()
        ))
        db.seed_curriculum()
        # Should still only have seed count + 1 manual
        sd = db.list_problems(problem_type=ProblemType.SD)
        custom = [p for p in sd if p.id == "manual-1"]
        assert len(custom) == 1


class TestSeedCurriculumAPI:
    @pytest.fixture
    def client(self):
        from notemaster.main import app, get_db
        from unittest.mock import MagicMock
        mock_db = MagicMock()
        mock_db.seed_curriculum.return_value = {"sd": 28, "lld": 10, "coding": 18}
        app.dependency_overrides[get_db] = lambda: mock_db
        from fastapi.testclient import TestClient
        yield TestClient(app), mock_db
        app.dependency_overrides.clear()

    def test_seed_endpoint_returns_200(self, client):
        tc, mock_db = client
        resp = tc.post("/admin/seed-curriculum")
        assert resp.status_code == 200
        mock_db.seed_curriculum.assert_called_once()
