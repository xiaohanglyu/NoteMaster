"""Tests for /providers REST endpoints."""
import pytest
from datetime import datetime
from unittest.mock import MagicMock
from notemaster.models import AIProvider


def make_provider(pid="p-1", is_active=False):
    return AIProvider(
        id=pid, name="Local Gemma", provider_type="openai_compatible",
        base_url="http://192.168.1.81:8080/v1", api_key=None,
        model="gemma-4-26b", is_active=is_active,
        created_at=datetime(2026, 4, 24),
    )


@pytest.fixture
def client():
    from notemaster.main import app, get_db
    mock_db = MagicMock()
    mock_db.list_providers.return_value = [make_provider()]
    mock_db.get_provider.return_value = make_provider()
    mock_db.create_provider.side_effect = lambda p: p
    mock_db.update_provider.return_value = make_provider()
    mock_db.get_active_provider.return_value = make_provider(is_active=True)
    app.dependency_overrides[get_db] = lambda: mock_db
    from fastapi.testclient import TestClient
    yield TestClient(app), mock_db
    app.dependency_overrides.clear()


class TestListProviders:
    def test_returns_200(self, client):
        tc, _ = client
        assert tc.get("/providers").status_code == 200

    def test_returns_list(self, client):
        tc, _ = client
        assert isinstance(tc.get("/providers").json(), list)


class TestCreateProvider:
    def test_create_openai_compatible(self, client):
        tc, mock_db = client
        resp = tc.post("/providers", json={
            "name": "Groq", "provider_type": "openai_compatible",
            "base_url": "https://api.groq.com/openai/v1",
            "api_key": "gsk_test", "model": "llama-3.3-70b-versatile",
        })
        assert resp.status_code == 201
        mock_db.create_provider.assert_called_once()

    def test_create_anthropic(self, client):
        tc, mock_db = client
        resp = tc.post("/providers", json={
            "name": "Claude Sonnet", "provider_type": "anthropic",
            "api_key": "sk-ant-test", "model": "claude-sonnet-4-6",
        })
        assert resp.status_code == 201

    def test_requires_name(self, client):
        tc, _ = client
        resp = tc.post("/providers", json={"provider_type": "openai_compatible", "model": "gpt-4o"})
        assert resp.status_code == 422

    def test_requires_model(self, client):
        tc, _ = client
        resp = tc.post("/providers", json={"name": "Test", "provider_type": "openai_compatible"})
        assert resp.status_code == 422


class TestUpdateProvider:
    def test_patch_name(self, client):
        tc, mock_db = client
        resp = tc.patch("/providers/p-1", json={"name": "New Name"})
        assert resp.status_code == 200
        mock_db.update_provider.assert_called_once_with("p-1", {"name": "New Name"})

    def test_returns_404_when_not_found(self, client):
        tc, mock_db = client
        mock_db.get_provider.return_value = None
        mock_db.update_provider.return_value = None
        resp = tc.patch("/providers/missing", json={"name": "X"})
        assert resp.status_code == 404


class TestDeleteProvider:
    def test_delete_returns_204(self, client):
        tc, mock_db = client
        resp = tc.delete("/providers/p-1")
        assert resp.status_code == 204
        mock_db.delete_provider.assert_called_once_with("p-1")

    def test_delete_active_returns_409(self, client):
        tc, mock_db = client
        mock_db.get_provider.return_value = make_provider(is_active=True)
        resp = tc.delete("/providers/p-1")
        assert resp.status_code == 409


class TestActivateProvider:
    def test_activate_returns_200(self, client):
        tc, mock_db = client
        resp = tc.post("/providers/p-1/activate")
        assert resp.status_code == 200
        mock_db.activate_provider.assert_called_once_with("p-1")

    def test_activate_missing_returns_404(self, client):
        tc, mock_db = client
        mock_db.get_provider.return_value = None
        resp = tc.post("/providers/missing/activate")
        assert resp.status_code == 404


class TestTestConnection:
    def test_test_returns_ok(self, client):
        tc, _ = client
        from unittest.mock import patch
        with patch("notemaster.main.providers.build_provider") as mock_build:
            mock_provider = MagicMock()
            mock_provider.ping.return_value = {"ok": True, "latency_ms": 120, "model": "gemma-4-26b"}
            mock_build.return_value = mock_provider
            resp = tc.post("/providers/p-1/test")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_test_returns_error_on_failure(self, client):
        tc, _ = client
        from unittest.mock import patch
        with patch("notemaster.main.providers.build_provider") as mock_build:
            mock_provider = MagicMock()
            mock_provider.ping.return_value = {"ok": False, "error": "connection refused", "model": "gemma-4-26b"}
            mock_build.return_value = mock_provider
            resp = tc.post("/providers/p-1/test")
        assert resp.status_code == 200
        assert resp.json()["ok"] is False
