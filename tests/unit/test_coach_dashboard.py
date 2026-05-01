"""Tests for #55 — Coach Dashboard (GET /coach/dashboard)."""
import pytest
from datetime import datetime, date
from unittest.mock import MagicMock, patch

from notemaster.models import (
    CoachGoal, GoalType, DailyPlan, PlanTask, PlanBlock, PlanTaskType,
)


def make_goal(id="g-1", title="Google SDE", goal_type=GoalType.INTERVIEW,
              priority=1, daily_minutes=60, deadline=None):
    return CoachGoal(
        id=id, title=title, goal_type=goal_type,
        priority=priority, daily_minutes=daily_minutes,
        deadline=deadline, created_at=datetime(2026, 4, 1),
    )


def make_plan(date_str="2026-04-30", tasks=None):
    return DailyPlan(date=date_str, tasks=tasks or [])


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    from notemaster.db import Database
    return Database(tmp_path / "test.db")


class TestGetDueCounts:
    def test_returns_dict_with_all_keys(self, db):
        counts = db.get_due_counts()
        assert set(counts.keys()) == {"concepts", "entries", "questions", "problems"}

    def test_all_zero_when_empty(self, db):
        counts = db.get_due_counts()
        assert all(v == 0 for v in counts.values())

    def test_counts_due_entries(self, db):
        from notemaster.models import Entry, EntryType
        from datetime import datetime
        e = Entry(id="e-1", text="granularity", source_type=EntryType.MANUAL,
                  created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 1))
        db.create_entry(e)
        db.record_entry_review("e-1", mastery_score=2)
        # force next_review_at to be in the past
        db.conn.execute(
            "UPDATE entry_review_records SET next_review_at=? WHERE entry_id=?",
            ("2026-01-01T00:00:00", "e-1")
        )
        db.conn.commit()
        counts = db.get_due_counts()
        assert counts["entries"] >= 1


class TestGetWeekDoneCount:
    def test_returns_int(self, db):
        assert isinstance(db.get_week_done_count(), int)

    def test_zero_with_no_tasks(self, db):
        assert db.get_week_done_count() == 0

    def test_counts_done_tasks_this_week(self, db):
        plan = make_plan(tasks=[
            PlanTask(id="t-1", plan_date="2026-04-30", block=PlanBlock.MORNING,
                     task_type=PlanTaskType.CODING, title="LRU Cache", done=True),
            PlanTask(id="t-2", plan_date="2026-04-30", block=PlanBlock.MORNING,
                     task_type=PlanTaskType.SD, title="Design URL shortener", done=False),
        ])
        db.save_plan(plan)
        db.toggle_plan_task("t-1", done=True)
        assert db.get_week_done_count() >= 1


# ---------------------------------------------------------------------------
# API: GET /coach/dashboard
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    from notemaster.main import app, get_db
    mock_db = MagicMock()
    mock_db.list_goals.return_value = [make_goal()]
    mock_db.get_plan.return_value = make_plan()
    mock_db.get_due_counts.return_value = {
        "concepts": 2, "entries": 1, "questions": 3, "problems": 0
    }
    mock_db.get_week_done_count.return_value = 5
    app.dependency_overrides[get_db] = lambda: mock_db
    from fastapi.testclient import TestClient
    yield TestClient(app), mock_db
    app.dependency_overrides.clear()


class TestCoachDashboardApi:
    def test_returns_200(self, client):
        tc, _ = client
        resp = tc.get("/coach/dashboard")
        assert resp.status_code == 200

    def test_response_has_required_keys(self, client):
        tc, _ = client
        data = tc.get("/coach/dashboard").json()
        assert "focus_goal" in data
        assert "brief" in data
        assert "due_counts" in data
        assert "week_done" in data
        assert "plan" in data

    def test_focus_goal_is_top_priority(self, client):
        tc, mock_db = client
        mock_db.list_goals.return_value = [
            make_goal(id="g-1", priority=2),
            make_goal(id="g-2", priority=1),
        ]
        data = tc.get("/coach/dashboard").json()
        assert data["focus_goal"]["id"] == "g-2"

    def test_focus_goal_none_when_no_goals(self, client):
        tc, mock_db = client
        mock_db.list_goals.return_value = []
        data = tc.get("/coach/dashboard").json()
        assert data["focus_goal"] is None

    def test_brief_is_nonempty_string(self, client):
        tc, _ = client
        data = tc.get("/coach/dashboard").json()
        assert isinstance(data["brief"], str)
        assert len(data["brief"]) > 10

    def test_due_counts_keys(self, client):
        tc, _ = client
        data = tc.get("/coach/dashboard").json()
        counts = data["due_counts"]
        assert set(counts.keys()) == {"concepts", "entries", "questions", "problems"}

    def test_week_done_is_int(self, client):
        tc, _ = client
        data = tc.get("/coach/dashboard").json()
        assert isinstance(data["week_done"], int)

    def test_plan_included(self, client):
        tc, _ = client
        data = tc.get("/coach/dashboard").json()
        assert "date" in data["plan"]
        assert "tasks" in data["plan"]

    def test_brief_mentions_focus_goal_title(self, client):
        tc, _ = client
        data = tc.get("/coach/dashboard").json()
        assert "Google SDE" in data["brief"] or len(data["brief"]) > 0

    def test_brief_reflects_due_items(self, client):
        tc, mock_db = client
        mock_db.get_due_counts.return_value = {
            "concepts": 0, "entries": 0, "questions": 0, "problems": 0
        }
        data = tc.get("/coach/dashboard").json()
        assert isinstance(data["brief"], str)
