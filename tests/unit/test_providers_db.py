"""Tests for ai_providers DB CRUD."""
import pytest
from datetime import datetime
from notemaster.db import Database


def make_provider(**kwargs):
    from notemaster.models import AIProvider
    defaults = dict(
        id="p-1",
        name="Local Gemma",
        provider_type="openai_compatible",
        base_url="http://192.168.1.81:8080/v1",
        api_key=None,
        model="gemma-4-26b",
        is_active=False,
        created_at=datetime(2026, 4, 24),
    )
    defaults.update(kwargs)
    return AIProvider(**defaults)


@pytest.fixture
def db():
    return Database(":memory:")


class TestAIProvidersCRUD:
    def test_create_and_get(self, db):
        p = make_provider()
        db.create_provider(p)
        fetched = db.get_provider("p-1")
        assert fetched is not None
        assert fetched.name == "Local Gemma"
        assert fetched.model == "gemma-4-26b"

    def test_list_providers_empty(self, db):
        assert db.list_providers() == []

    def test_list_providers_returns_all(self, db):
        db.create_provider(make_provider(id="p-1"))
        db.create_provider(make_provider(id="p-2", name="OpenAI GPT-4o", model="gpt-4o"))
        providers = db.list_providers()
        assert len(providers) == 2

    def test_update_provider(self, db):
        db.create_provider(make_provider())
        updated = db.update_provider("p-1", {"name": "Updated Name", "model": "gemma-3-12b"})
        assert updated.name == "Updated Name"
        assert updated.model == "gemma-3-12b"

    def test_delete_provider(self, db):
        db.create_provider(make_provider())
        db.delete_provider("p-1")
        assert db.get_provider("p-1") is None

    def test_activate_provider(self, db):
        db.create_provider(make_provider(id="p-1", is_active=False))
        db.create_provider(make_provider(id="p-2", name="OpenAI", model="gpt-4o", is_active=True))
        db.activate_provider("p-1")
        assert db.get_provider("p-1").is_active is True
        assert db.get_provider("p-2").is_active is False

    def test_only_one_active_at_a_time(self, db):
        db.create_provider(make_provider(id="p-1", is_active=True))
        db.create_provider(make_provider(id="p-2", name="OpenAI", model="gpt-4o", is_active=False))
        db.activate_provider("p-2")
        active = [p for p in db.list_providers() if p.is_active]
        assert len(active) == 1
        assert active[0].id == "p-2"

    def test_get_active_provider(self, db):
        db.create_provider(make_provider(id="p-1", is_active=False))
        db.create_provider(make_provider(id="p-2", name="OpenAI", model="gpt-4o", is_active=True))
        active = db.get_active_provider()
        assert active is not None
        assert active.id == "p-2"

    def test_get_active_provider_none_when_empty(self, db):
        assert db.get_active_provider() is None

    def test_provider_type_stored(self, db):
        db.create_provider(make_provider(provider_type="anthropic", model="claude-sonnet-4-6", base_url=None))
        p = db.get_provider("p-1")
        assert p.provider_type == "anthropic"

    def test_api_key_stored(self, db):
        db.create_provider(make_provider(api_key="sk-secret"))
        p = db.get_provider("p-1")
        assert p.api_key == "sk-secret"
