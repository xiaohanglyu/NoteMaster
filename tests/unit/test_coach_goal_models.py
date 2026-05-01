"""Tests for CoachGoal model (#50)."""
import pytest
from datetime import date, datetime
from notemaster.models import CoachGoal, GoalType


class TestCoachGoalModel:
    def test_defaults(self):
        g = CoachGoal(
            id="g-1", title="Google SD Interview",
            goal_type=GoalType.INTERVIEW, created_at=datetime(2026, 4, 30),
        )
        assert g.priority == 2
        assert g.daily_minutes == 30
        assert g.deadline is None
        assert g.ref_id is None

    def test_goal_types(self):
        assert GoalType.INTERVIEW == "interview"
        assert GoalType.SKILL == "skill"
        assert GoalType.CURRICULUM == "curriculum"

    def test_full_fields(self):
        g = CoachGoal(
            id="g-1", title="Finish Blind 75",
            goal_type=GoalType.CURRICULUM,
            deadline=date(2026, 5, 15),
            priority=1,
            daily_minutes=45,
            ref_id="coding",
            created_at=datetime(2026, 4, 30),
        )
        assert g.deadline == date(2026, 5, 15)
        assert g.priority == 1
        assert g.ref_id == "coding"


class TestCoachGoalDB:
    @pytest.fixture
    def db(self, tmp_path):
        from notemaster.db import Database
        return Database(tmp_path / "test.db")

    def test_create_and_get(self, db):
        g = CoachGoal(
            id="g-1", title="Google SD",
            goal_type=GoalType.INTERVIEW,
            priority=1, daily_minutes=30,
            created_at=datetime(2026, 4, 30),
        )
        db.create_goal(g)
        loaded = db.get_goal("g-1")
        assert loaded.title == "Google SD"
        assert loaded.goal_type == GoalType.INTERVIEW
        assert loaded.priority == 1

    def test_list_goals(self, db):
        for i in range(3):
            db.create_goal(CoachGoal(
                id=f"g-{i}", title=f"Goal {i}",
                goal_type=GoalType.SKILL,
                created_at=datetime(2026, 4, 30),
            ))
        goals = db.list_goals()
        assert len(goals) == 3

    def test_update_goal(self, db):
        g = CoachGoal(id="g-1", title="Old", goal_type=GoalType.SKILL, created_at=datetime(2026, 4, 30))
        db.create_goal(g)
        db.update_goal("g-1", title="New", priority=1)
        loaded = db.get_goal("g-1")
        assert loaded.title == "New"
        assert loaded.priority == 1

    def test_delete_goal(self, db):
        g = CoachGoal(id="g-1", title="G", goal_type=GoalType.SKILL, created_at=datetime(2026, 4, 30))
        db.create_goal(g)
        db.delete_goal("g-1")
        assert db.get_goal("g-1") is None

    def test_deadline_roundtrips(self, db):
        g = CoachGoal(
            id="g-1", title="G", goal_type=GoalType.INTERVIEW,
            deadline=date(2026, 5, 15), created_at=datetime(2026, 4, 30),
        )
        db.create_goal(g)
        loaded = db.get_goal("g-1")
        assert loaded.deadline == date(2026, 5, 15)

    def test_list_ordered_by_priority(self, db):
        db.create_goal(CoachGoal(id="g-1", title="P2", goal_type=GoalType.SKILL, priority=2, created_at=datetime(2026, 4, 30)))
        db.create_goal(CoachGoal(id="g-2", title="P1", goal_type=GoalType.SKILL, priority=1, created_at=datetime(2026, 4, 30)))
        goals = db.list_goals()
        assert goals[0].priority == 1


class TestCoachGoalAPI:
    @pytest.fixture
    def client(self):
        from notemaster.main import app, get_db
        from unittest.mock import MagicMock
        mock_db = MagicMock()
        g = CoachGoal(id="g-1", title="Google SD", goal_type=GoalType.INTERVIEW, created_at=datetime(2026, 4, 30))
        mock_db.list_goals.return_value = [g]
        mock_db.get_goal.return_value = g
        mock_db.create_goal.side_effect = lambda x: x
        mock_db.update_goal.return_value = g
        app.dependency_overrides[get_db] = lambda: mock_db
        from fastapi.testclient import TestClient
        yield TestClient(app), mock_db
        app.dependency_overrides.clear()

    def test_list_goals(self, client):
        tc, _ = client
        resp = tc.get("/goals")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_create_goal(self, client):
        tc, mock_db = client
        resp = tc.post("/goals", json={"title": "Google SD", "goal_type": "interview"})
        assert resp.status_code == 200
        mock_db.create_goal.assert_called_once()

    def test_update_goal(self, client):
        tc, _ = client
        resp = tc.patch("/goals/g-1", json={"priority": 1})
        assert resp.status_code == 200

    def test_delete_goal(self, client):
        tc, mock_db = client
        mock_db.delete_goal.return_value = True
        resp = tc.delete("/goals/g-1")
        assert resp.status_code == 204

    def test_get_goal_not_found(self, client):
        tc, mock_db = client
        mock_db.get_goal.return_value = None
        resp = tc.patch("/goals/ghost", json={"priority": 1})
        assert resp.status_code == 404
