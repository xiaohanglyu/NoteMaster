"""Tests for ApplicationRound round_type + status (#48)."""
import pytest
from datetime import datetime
from notemaster.models import ApplicationRound, RoundType, RoundStatus


def make_round(**kwargs):
    defaults = dict(application_id="app-1", name="Technical Interview")
    return ApplicationRound(**{**defaults, **kwargs})


class TestRoundTypeModel:
    def test_round_type_defaults_none(self):
        r = make_round()
        assert r.round_type is None

    def test_status_defaults_scheduled(self):
        r = make_round()
        assert r.status == RoundStatus.SCHEDULED

    def test_round_type_coding(self):
        r = make_round(round_type=RoundType.CODING)
        assert r.round_type == RoundType.CODING

    def test_status_passed(self):
        r = make_round(status=RoundStatus.PASSED)
        assert r.status == RoundStatus.PASSED


class TestRoundTypeEnum:
    def test_types(self):
        assert RoundType.HR_SCREEN == "hr_screen"
        assert RoundType.MANAGER_SCREEN == "manager_screen"
        assert RoundType.BEHAVIORAL == "behavioral"
        assert RoundType.CODING == "coding"
        assert RoundType.SYSTEM_DESIGN == "system_design"
        assert RoundType.LLD == "lld"

    def test_statuses(self):
        assert RoundStatus.SCHEDULED == "scheduled"
        assert RoundStatus.COMPLETED == "completed"
        assert RoundStatus.PASSED == "passed"
        assert RoundStatus.FAILED == "failed"


class TestRoundTypeDB:
    @pytest.fixture
    def db(self, tmp_path):
        from notemaster.db import Database
        from notemaster.models import Application, ApplicationStatus
        db = Database(tmp_path / "test.db")
        app = Application(
            id="app-1", company="Acme", role="SWE",
            status=ApplicationStatus.TECHNICAL,
            created_at=datetime(2026, 4, 27),
        )
        db.create_application(app)
        return db

    def test_persists_round_type(self, db):
        r = make_round(round_type=RoundType.CODING)
        db.add_application_round(r)
        rounds = db.get_application_rounds("app-1")
        assert rounds[0].round_type == RoundType.CODING

    def test_persists_status(self, db):
        r = make_round(status=RoundStatus.PASSED)
        db.add_application_round(r)
        rounds = db.get_application_rounds("app-1")
        assert rounds[0].status == RoundStatus.PASSED

    def test_none_round_type_roundtrips(self, db):
        db.add_application_round(make_round())
        rounds = db.get_application_rounds("app-1")
        assert rounds[0].round_type is None

    def test_update_round_type(self, db):
        db.add_application_round(make_round())
        rounds = db.get_application_rounds("app-1")
        rid = rounds[0].id
        updated = db.update_application_round(rid, round_type="system_design", status="completed")
        assert updated.round_type == RoundType.SYSTEM_DESIGN
        assert updated.status == RoundStatus.COMPLETED


class TestRoundTypeAPI:
    @pytest.fixture
    def client(self):
        from notemaster.main import app, get_db
        from unittest.mock import MagicMock
        mock_db = MagicMock()
        r = make_round(id=1, round_type=RoundType.CODING, status=RoundStatus.SCHEDULED)
        mock_db.add_application_round.return_value = r
        mock_db.get_application.return_value = MagicMock()
        mock_db.get_application_rounds.return_value = [r]
        mock_db.update_application_round.return_value = r
        app.dependency_overrides[get_db] = lambda: mock_db
        from fastapi.testclient import TestClient
        yield TestClient(app), mock_db
        app.dependency_overrides.clear()

    def test_create_round_with_type(self, client):
        tc, mock_db = client
        resp = tc.post("/applications/app-1/rounds", json={
            "name": "Technical",
            "round_type": "coding",
            "status": "scheduled",
        })
        assert resp.status_code == 201

    def test_update_round_status(self, client):
        tc, mock_db = client
        resp = tc.patch("/applications/app-1/rounds/1", json={"status": "passed"})
        assert resp.status_code == 200
