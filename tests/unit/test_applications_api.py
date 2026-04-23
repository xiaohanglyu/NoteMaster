import pytest
from datetime import datetime
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from notemaster.models import (
    Application, ApplicationStatus, ApplicationRound,
)


def make_app(id="app-1", status=ApplicationStatus.APPLIED):
    return Application(
        id=id,
        company="Stripe",
        role="Software Engineer",
        status=status,
        applied_at=datetime(2026, 4, 1).date(),
        created_at=datetime(2026, 4, 1, 10, 0),
    )


def make_round(id=1, app_id="app-1"):
    return ApplicationRound(id=id, application_id=app_id, name="Phone Screen", date="2026-04-10")


def make_db():
    db = MagicMock()
    db.get_applications.return_value = [make_app()]
    db.get_application.return_value = make_app()
    db.create_application.side_effect = lambda a: a
    db.update_application.return_value = make_app(status=ApplicationStatus.PHONE)
    db.add_application_round.return_value = make_round()
    db.get_application_rounds.return_value = [make_round()]
    db.update_application_round.return_value = make_round()
    return db


@pytest.fixture
def client():
    from notemaster.main import app, get_db
    mock_db = make_db()
    app.dependency_overrides[get_db] = lambda: mock_db
    yield TestClient(app), mock_db
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# GET /applications
# ---------------------------------------------------------------------------

class TestListApplications:
    def test_returns_list(self, client):
        tc, _ = client
        resp = tc.get("/applications")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_has_expected_fields(self, client):
        tc, _ = client
        data = tc.get("/applications").json()
        assert data[0]["company"] == "Stripe"
        assert "status" in data[0]

    def test_filter_by_status(self, client):
        tc, mock_db = client
        mock_db.get_applications.return_value = [make_app()]
        tc.get("/applications?status=applied")
        mock_db.get_applications.assert_called_with(status=ApplicationStatus.APPLIED)


# ---------------------------------------------------------------------------
# POST /applications
# ---------------------------------------------------------------------------

class TestCreateApplication:
    def test_creates_and_returns_201(self, client):
        tc, mock_db = client
        payload = {
            "company": "Stripe",
            "role": "Backend Engineer",
            "status": "applied",
        }
        resp = tc.post("/applications", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["company"] == "Stripe"
        assert "id" in data

    def test_missing_company_returns_422(self, client):
        tc, _ = client
        resp = tc.post("/applications", json={"role": "Engineer"})
        assert resp.status_code == 422

    def test_missing_role_returns_422(self, client):
        tc, _ = client
        resp = tc.post("/applications", json={"company": "Stripe"})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /applications/{id}
# ---------------------------------------------------------------------------

class TestGetApplication:
    def test_returns_application(self, client):
        tc, _ = client
        resp = tc.get("/applications/app-1")
        assert resp.status_code == 200
        assert resp.json()["id"] == "app-1"

    def test_not_found_returns_404(self, client):
        tc, mock_db = client
        mock_db.get_application.return_value = None
        resp = tc.get("/applications/ghost")
        assert resp.status_code == 404

    def test_includes_rounds(self, client):
        tc, mock_db = client
        mock_db.get_application_rounds.return_value = [make_round()]
        resp = tc.get("/applications/app-1")
        assert resp.status_code == 200
        assert "rounds" in resp.json()
        assert len(resp.json()["rounds"]) == 1


# ---------------------------------------------------------------------------
# PATCH /applications/{id}
# ---------------------------------------------------------------------------

class TestUpdateApplication:
    def test_updates_status(self, client):
        tc, mock_db = client
        resp = tc.patch("/applications/app-1", json={"status": "phone"})
        assert resp.status_code == 200
        mock_db.update_application.assert_called_once()

    def test_not_found_returns_404(self, client):
        tc, mock_db = client
        mock_db.update_application.return_value = None
        resp = tc.patch("/applications/ghost", json={"status": "phone"})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /applications/{id}
# ---------------------------------------------------------------------------

class TestDeleteApplication:
    def test_deletes_returns_204(self, client):
        tc, mock_db = client
        resp = tc.delete("/applications/app-1")
        assert resp.status_code == 204
        mock_db.delete_application.assert_called_once_with("app-1")

    def test_not_found_returns_404(self, client):
        tc, mock_db = client
        mock_db.get_application.return_value = None
        resp = tc.delete("/applications/ghost")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /applications/{id}/rounds
# ---------------------------------------------------------------------------

class TestAddRound:
    def test_adds_round_returns_201(self, client):
        tc, mock_db = client
        resp = tc.post("/applications/app-1/rounds", json={"name": "Technical"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Phone Screen"  # mock returns make_round()
        mock_db.add_application_round.assert_called_once()

    def test_app_not_found_returns_404(self, client):
        tc, mock_db = client
        mock_db.get_application.return_value = None
        resp = tc.post("/applications/ghost/rounds", json={"name": "Technical"})
        assert resp.status_code == 404

    def test_missing_name_returns_422(self, client):
        tc, _ = client
        resp = tc.post("/applications/app-1/rounds", json={})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# PATCH /applications/{id}/rounds/{rid}
# ---------------------------------------------------------------------------

class TestUpdateRound:
    def test_updates_feedback(self, client):
        tc, mock_db = client
        resp = tc.patch("/applications/app-1/rounds/1", json={"feedback": "Strong hire"})
        assert resp.status_code == 200
        mock_db.update_application_round.assert_called_once()

    def test_not_found_returns_404(self, client):
        tc, mock_db = client
        mock_db.update_application_round.return_value = None
        resp = tc.patch("/applications/app-1/rounds/999", json={"feedback": "x"})
        assert resp.status_code == 404
