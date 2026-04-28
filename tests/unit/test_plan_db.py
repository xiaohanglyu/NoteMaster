"""Tests for DailyPlan DB CRUD."""
import pytest
from notemaster.models import DailyPlan, PlanTask, PlanBlock, PlanTaskType


@pytest.fixture
def db(tmp_path):
    from notemaster.db import Database
    return Database(tmp_path / "test.db")


def make_task(tid="t-1", block=PlanBlock.MORNING, task_type=PlanTaskType.SD,
              title="Design Bitly", done=False):
    return PlanTask(id=tid, plan_date="2026-04-27", block=block,
                    task_type=task_type, title=title, done=done)


class TestSaveAndGetPlan:
    def test_save_and_retrieve(self, db):
        plan = DailyPlan(date="2026-04-27", tasks=[make_task()])
        db.save_plan(plan)
        loaded = db.get_plan("2026-04-27")
        assert loaded is not None
        assert loaded.date == "2026-04-27"
        assert len(loaded.tasks) == 1

    def test_get_missing_returns_none(self, db):
        assert db.get_plan("2099-01-01") is None

    def test_save_multiple_tasks(self, db):
        tasks = [
            make_task("t-1", PlanBlock.MORNING, PlanTaskType.SD, "Design Bitly"),
            make_task("t-2", PlanBlock.EVENING, PlanTaskType.ENGLISH, "Review vocab"),
        ]
        db.save_plan(DailyPlan(date="2026-04-27", tasks=tasks))
        loaded = db.get_plan("2026-04-27")
        assert len(loaded.tasks) == 2

    def test_tasks_preserve_block(self, db):
        tasks = [
            make_task("t-1", PlanBlock.MORNING),
            make_task("t-2", PlanBlock.EVENING),
        ]
        db.save_plan(DailyPlan(date="2026-04-27", tasks=tasks))
        loaded = db.get_plan("2026-04-27")
        blocks = {t.id: t.block for t in loaded.tasks}
        assert blocks["t-1"] == PlanBlock.MORNING
        assert blocks["t-2"] == PlanBlock.EVENING

    def test_overwrite_existing_plan(self, db):
        db.save_plan(DailyPlan(date="2026-04-27", tasks=[make_task("t-1")]))
        db.save_plan(DailyPlan(date="2026-04-27", tasks=[make_task("t-2")]))
        loaded = db.get_plan("2026-04-27")
        assert len(loaded.tasks) == 1
        assert loaded.tasks[0].id == "t-2"


class TestToggleTask:
    def test_mark_done(self, db):
        db.save_plan(DailyPlan(date="2026-04-27", tasks=[make_task("t-1", done=False)]))
        db.toggle_plan_task("t-1", done=True)
        loaded = db.get_plan("2026-04-27")
        assert loaded.tasks[0].done is True

    def test_mark_undone(self, db):
        db.save_plan(DailyPlan(date="2026-04-27", tasks=[make_task("t-1", done=True)]))
        db.toggle_plan_task("t-1", done=False)
        loaded = db.get_plan("2026-04-27")
        assert loaded.tasks[0].done is False
