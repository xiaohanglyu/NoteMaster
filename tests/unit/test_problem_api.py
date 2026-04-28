"""Tests for /problems REST endpoints."""
import pytest
from datetime import datetime
from unittest.mock import MagicMock
from notemaster.models import Problem, ProblemType, ProblemDifficulty, ProblemReviewRecord


def make_problem(pid="p-1"):
    return Problem(
        id=pid, title="Design Bitly", problem_type=ProblemType.SD,
        tags=["url-shortener"], created_at=datetime(2026, 4, 27),
    )


@pytest.fixture
def client():
    from notemaster.main import app, get_db
    mock_db = MagicMock()
    mock_db.list_problems.return_value = [make_problem()]
    mock_db.get_problem.return_value = make_problem()
    mock_db.create_problem.side_effect = lambda p: p
    mock_db.update_problem.return_value = make_problem()
    mock_db.delete_problem.return_value = True
    mock_db.record_problem_review.return_value = ProblemReviewRecord(
        problem_id="p-1", grade=4,
        reviewed_at=datetime(2026, 4, 27),
        next_review_at=datetime(2026, 4, 28),
        interval=1, reps=1, ef=2.5,
    )
    app.dependency_overrides[get_db] = lambda: mock_db
    from fastapi.testclient import TestClient
    yield TestClient(app), mock_db
    app.dependency_overrides.clear()


class TestListProblems:
    def test_returns_200(self, client):
        tc, _ = client
        assert tc.get("/problems").status_code == 200

    def test_returns_list(self, client):
        tc, _ = client
        assert isinstance(tc.get("/problems").json(), list)

    def test_filter_by_type(self, client):
        tc, mock_db = client
        tc.get("/problems?problem_type=sd")
        mock_db.list_problems.assert_called_once_with(
            problem_type=ProblemType.SD, due_only=False
        )

    def test_due_only(self, client):
        tc, mock_db = client
        tc.get("/problems?due_only=true")
        mock_db.list_problems.assert_called_once_with(
            problem_type=None, due_only=True
        )


class TestCreateProblem:
    def test_create_sd(self, client):
        tc, mock_db = client
        resp = tc.post("/problems", json={
            "title": "Design Bitly",
            "problem_type": "sd",
        })
        assert resp.status_code == 201
        mock_db.create_problem.assert_called_once()

    def test_create_coding_with_difficulty(self, client):
        tc, mock_db = client
        resp = tc.post("/problems", json={
            "title": "LRU Cache",
            "problem_type": "coding",
            "difficulty": "medium",
        })
        assert resp.status_code == 201

    def test_requires_title(self, client):
        tc, _ = client
        assert tc.post("/problems", json={"problem_type": "sd"}).status_code == 422

    def test_requires_type(self, client):
        tc, _ = client
        assert tc.post("/problems", json={"title": "X"}).status_code == 422


class TestGetProblem:
    def test_get_existing(self, client):
        tc, _ = client
        resp = tc.get("/problems/p-1")
        assert resp.status_code == 200
        assert resp.json()["id"] == "p-1"

    def test_get_missing_returns_404(self, client):
        tc, mock_db = client
        mock_db.get_problem.return_value = None
        assert tc.get("/problems/missing").status_code == 404


class TestUpdateProblem:
    def test_patch_title(self, client):
        tc, mock_db = client
        resp = tc.patch("/problems/p-1", json={"title": "Design TinyURL"})
        assert resp.status_code == 200
        mock_db.update_problem.assert_called_once()

    def test_patch_missing_returns_404(self, client):
        tc, mock_db = client
        mock_db.update_problem.return_value = None
        assert tc.patch("/problems/missing", json={"title": "X"}).status_code == 404


class TestDeleteProblem:
    def test_delete_returns_204(self, client):
        tc, mock_db = client
        assert tc.delete("/problems/p-1").status_code == 204

    def test_delete_missing_returns_404(self, client):
        tc, mock_db = client
        mock_db.delete_problem.return_value = False
        assert tc.delete("/problems/missing").status_code == 404


class TestReviewProblem:
    def test_review_returns_200(self, client):
        tc, mock_db = client
        resp = tc.post("/problems/p-1/review", json={"grade": 4})
        assert resp.status_code == 200
        mock_db.record_problem_review.assert_called_once_with("p-1", grade=4)

    def test_grade_out_of_range(self, client):
        tc, _ = client
        assert tc.post("/problems/p-1/review", json={"grade": 6}).status_code == 422

    def test_review_missing_returns_404(self, client):
        tc, mock_db = client
        mock_db.record_problem_review.side_effect = ValueError("not found")
        assert tc.post("/problems/missing/review", json={"grade": 4}).status_code == 404
