import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
from notemaster.models import InboxItem, InboxClassification


def make_item(id="i-1", content="granularity", tags=None, processed_at=None):
    return InboxItem(
        id=id,
        content=content,
        tags=tags or [],
        created_at=datetime(2026, 4, 24, 10, 0),
        processed_at=processed_at,
    )


def make_db():
    db = MagicMock()
    db.create_inbox_item.return_value = make_item()
    db.get_inbox_item.return_value = make_item()
    db.get_inbox_items.return_value = [make_item()]
    db.update_inbox_item.return_value = make_item(tags=["english"])
    db.delete_inbox_item.return_value = True
    db.get_inbox_pending_count.return_value = 3
    db.mark_inbox_processed.return_value = None
    return db


@pytest.fixture
def client():
    from notemaster.main import app, get_db
    mock_db = make_db()
    app.dependency_overrides[get_db] = lambda: mock_db
    from fastapi.testclient import TestClient
    yield TestClient(app), mock_db
    app.dependency_overrides.clear()


class TestCreateInboxItem:
    def test_returns_created_item(self, client):
        tc, _ = client
        resp = tc.post("/inbox", json={"content": "granularity"})
        assert resp.status_code == 200
        assert resp.json()["content"] == "granularity"

    def test_empty_content_fails(self, client):
        tc, _ = client
        resp = tc.post("/inbox", json={})
        assert resp.status_code == 422


class TestListInboxItems:
    def test_returns_list(self, client):
        tc, mock_db = client
        resp = tc.get("/inbox")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_pending_only_query(self, client):
        tc, mock_db = client
        tc.get("/inbox?pending_only=true")
        mock_db.get_inbox_items.assert_called_with(pending_only=True)

    def test_default_not_pending_only(self, client):
        tc, mock_db = client
        tc.get("/inbox")
        mock_db.get_inbox_items.assert_called_with(pending_only=False)


class TestPendingCount:
    def test_returns_count(self, client):
        tc, _ = client
        resp = tc.get("/inbox/pending-count")
        assert resp.status_code == 200
        assert resp.json()["count"] == 3


class TestUpdateInboxItem:
    def test_update_tags(self, client):
        tc, mock_db = client
        resp = tc.patch("/inbox/i-1", json={"tags": ["english"]})
        assert resp.status_code == 200
        mock_db.update_inbox_item.assert_called_once()

    def test_returns_404_for_unknown(self, client):
        tc, mock_db = client
        mock_db.update_inbox_item.return_value = None
        resp = tc.patch("/inbox/nope", json={"tags": []})
        assert resp.status_code == 404


class TestDeleteInboxItem:
    def test_delete_returns_true(self, client):
        tc, _ = client
        resp = tc.delete("/inbox/i-1")
        assert resp.status_code == 200
        assert resp.json() is True

    def test_delete_unknown_returns_404(self, client):
        tc, mock_db = client
        mock_db.delete_inbox_item.return_value = False
        resp = tc.delete("/inbox/nope")
        assert resp.status_code == 404


class TestClassifyInboxItem:
    def test_returns_classification(self, client):
        tc, mock_db = client
        classification = InboxClassification(
            item_type="english",
            reasoning="vocab word",
            preview={"text": "granularity"},
        )
        with patch("notemaster.main.ai.classify_inbox_item", return_value=classification):
            resp = tc.post("/inbox/i-1/classify")
        assert resp.status_code == 200
        assert resp.json()["item_type"] == "english"

    def test_returns_404_for_unknown_item(self, client):
        tc, mock_db = client
        mock_db.get_inbox_item.return_value = None
        with patch("notemaster.main.ai.classify_inbox_item"):
            resp = tc.post("/inbox/nope/classify")
        assert resp.status_code == 404


class TestRouteInboxItem:
    def test_route_english(self, client):
        tc, mock_db = client
        from notemaster.models import Entry, EntryData
        created_entry = Entry(
            id="e-new",
            text="granularity",
            data=EntryData(),
            created_at=datetime(2026, 4, 24, 10, 0),
            updated_at=datetime(2026, 4, 24, 10, 0),
        )
        mock_db.create_entry.return_value = created_entry
        resp = tc.post("/inbox/i-1/route", json={"item_type": "english"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["routed_to"] == "english"
        mock_db.mark_inbox_processed.assert_called_once_with("i-1")

    def test_route_unknown_item_returns_404(self, client):
        tc, mock_db = client
        mock_db.get_inbox_item.return_value = None
        resp = tc.post("/inbox/nope/route", json={"item_type": "english"})
        assert resp.status_code == 404

    def test_route_invalid_type_returns_422(self, client):
        tc, _ = client
        resp = tc.post("/inbox/i-1/route", json={"item_type": "banana"})
        assert resp.status_code == 422
