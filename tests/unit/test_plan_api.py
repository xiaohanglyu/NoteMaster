"""Tests for /plan REST endpoints."""
import pytest
from unittest.mock import MagicMock
from notemaster.models import DailyPlan, PlanTask, PlanBlock, PlanTaskType


def make_plan(date="2026-04-27"):
    return DailyPlan(date=date, tasks=[
        PlanTask(id="t-1", plan_date=date, block=PlanBlock.MORNING,
                 task_type=PlanTaskType.SD, title="Design Bitly", done=False),
        PlanTask(id="t-2", plan_date=date, block=PlanBlock.EVENING,
                 task_type=PlanTaskType.ENGLISH, title="Review 6 words", done=False),
    ])


@pytest.fixture
def client():
    from notemaster.main import app, get_db
    mock_db = MagicMock()
    mock_db.get_plan.return_value = make_plan()
    mock_db.save_plan.return_value = None
    mock_db.toggle_plan_task.return_value = None
    mock_db.list_entries_due.return_value = []
    mock_db.get_inbox_pending_count.return_value = 0
    mock_db.get_questions.return_value = []
    mock_db.get_next_due_problem.return_value = None
    mock_db.list_applications.return_value = []
    app.dependency_overrides[get_db] = lambda: mock_db
    from fastapi.testclient import TestClient
    yield TestClient(app), mock_db
    app.dependency_overrides.clear()


class TestGetTodayPlan:
    def test_returns_200(self, client):
        tc, _ = client
        resp = tc.get("/plan/today")
        assert resp.status_code == 200

    def test_returns_date_and_tasks(self, client):
        tc, _ = client
        data = tc.get("/plan/today").json()
        assert "date" in data
        assert "tasks" in data
        assert isinstance(data["tasks"], list)

    def test_tasks_have_required_fields(self, client):
        tc, _ = client
        tasks = tc.get("/plan/today").json()["tasks"]
        for t in tasks:
            assert "id" in t
            assert "block" in t
            assert "task_type" in t
            assert "title" in t
            assert "done" in t

    def test_generates_if_no_existing_plan(self, client):
        tc, mock_db = client
        mock_db.get_plan.return_value = None
        resp = tc.get("/plan/today")
        assert resp.status_code == 200
        mock_db.save_plan.assert_called_once()

    def test_returns_existing_plan(self, client):
        tc, mock_db = client
        resp = tc.get("/plan/today")
        assert resp.status_code == 200
        mock_db.save_plan.assert_not_called()


class TestToggleTask:
    def test_toggle_done_returns_200(self, client):
        tc, mock_db = client
        resp = tc.post("/plan/tasks/t-1/toggle", json={"done": True})
        assert resp.status_code == 200
        mock_db.toggle_plan_task.assert_called_once_with("t-1", done=True)

    def test_toggle_undone(self, client):
        tc, mock_db = client
        resp = tc.post("/plan/tasks/t-1/toggle", json={"done": False})
        assert resp.status_code == 200


class TestRegeneratePlan:
    def test_regenerate_returns_200(self, client):
        tc, mock_db = client
        resp = tc.post("/plan/regenerate")
        assert resp.status_code == 200
        mock_db.save_plan.assert_called_once()
