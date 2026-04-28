"""Tests for Entry register + content_type (#49)."""
import pytest
from datetime import datetime
from notemaster.models import Entry, EntryData, EntryRegister, EntryContentType, EntryType


def make_entry(**kwargs):
    defaults = dict(
        id="e-1", text="granularity",
        created_at=datetime(2026, 4, 27),
        updated_at=datetime(2026, 4, 27),
    )
    return Entry(**{**defaults, **kwargs})


class TestEntryRegisterModel:
    def test_register_defaults_none(self):
        e = make_entry()
        assert e.data.usage_register is None

    def test_content_type_defaults_none(self):
        e = make_entry()
        assert e.data.content_type is None

    def test_register_formal(self):
        e = make_entry(data=EntryData(usage_register=EntryRegister.FORMAL))
        assert e.data.usage_register == EntryRegister.FORMAL

    def test_register_colloquial(self):
        e = make_entry(data=EntryData(usage_register=EntryRegister.COLLOQUIAL))
        assert e.data.usage_register == "colloquial"

    def test_content_type_spoken(self):
        e = make_entry(data=EntryData(content_type=EntryContentType.SPOKEN))
        assert e.data.content_type == EntryContentType.SPOKEN

    def test_content_type_written(self):
        e = make_entry(data=EntryData(content_type=EntryContentType.WRITTEN))
        assert e.data.content_type == "written"

    def test_content_type_both(self):
        e = make_entry(data=EntryData(content_type=EntryContentType.BOTH))
        assert e.data.content_type == "both"


class TestEntryRegisterEnum:
    def test_values(self):
        assert EntryRegister.FORMAL == "formal"
        assert EntryRegister.INFORMAL == "informal"
        assert EntryRegister.COLLOQUIAL == "colloquial"
        assert EntryRegister.SLANG == "slang"

    def test_content_type_values(self):
        assert EntryContentType.SPOKEN == "spoken"
        assert EntryContentType.WRITTEN == "written"
        assert EntryContentType.BOTH == "both"


class TestEntryRegisterDB:
    @pytest.fixture
    def db(self, tmp_path):
        from notemaster.db import Database
        return Database(tmp_path / "test.db")

    def test_persists_register(self, db):
        e = make_entry(data=EntryData(usage_register=EntryRegister.COLLOQUIAL, translation="随意的"))
        db.create_entry(e)
        loaded = db.get_entry("e-1")
        assert loaded.data.usage_register == EntryRegister.COLLOQUIAL

    def test_persists_content_type(self, db):
        e = make_entry(data=EntryData(content_type=EntryContentType.SPOKEN))
        db.create_entry(e)
        loaded = db.get_entry("e-1")
        assert loaded.data.content_type == EntryContentType.SPOKEN

    def test_none_register_roundtrips(self, db):
        e = make_entry()
        db.create_entry(e)
        loaded = db.get_entry("e-1")
        assert loaded.data.usage_register is None


class TestEntryRegisterAPI:
    @pytest.fixture
    def client(self):
        from notemaster.main import app, get_db
        from unittest.mock import MagicMock
        mock_db = MagicMock()
        e = make_entry(data=EntryData(usage_register=EntryRegister.FORMAL, content_type=EntryContentType.WRITTEN))
        mock_db.create_entry.side_effect = lambda x: x
        mock_db.get_entry.return_value = e
        mock_db.update_entry.return_value = e
        app.dependency_overrides[get_db] = lambda: mock_db
        from fastapi.testclient import TestClient
        yield TestClient(app), mock_db
        app.dependency_overrides.clear()

    def test_create_with_register(self, client):
        tc, mock_db = client
        resp = tc.post("/entries", json={
            "text": "granularity",
            "data": {"usage_register": "formal", "content_type": "written"},
        })
        assert resp.status_code == 200

    def test_patch_register(self, client):
        tc, mock_db = client
        resp = tc.patch("/entries/e-1", json={"data": {"usage_register": "colloquial"}})
        assert resp.status_code == 200
