"""Tests for DailyPlan models."""
import pytest
from datetime import date
from notemaster.models import DailyPlan, PlanTask, PlanBlock, PlanTaskType


class TestPlanTask:
    def test_create_task(self):
        t = PlanTask(
            id="t-1", plan_date="2026-04-27",
            block=PlanBlock.MORNING, task_type=PlanTaskType.SD,
            title="Design Bitly", done=False,
        )
        assert t.id == "t-1"
        assert t.done is False

    def test_task_with_url(self):
        t = PlanTask(
            id="t-2", plan_date="2026-04-27",
            block=PlanBlock.MORNING, task_type=PlanTaskType.SD,
            title="Design Bitly", url="https://hellointerview.com/...", done=False,
        )
        assert t.url is not None

    def test_task_with_ref_id(self):
        t = PlanTask(
            id="t-3", plan_date="2026-04-27",
            block=PlanBlock.EVENING, task_type=PlanTaskType.ENGLISH,
            title="Review vocabulary", ref_id="entry-123", done=False,
        )
        assert t.ref_id == "entry-123"


class TestDailyPlan:
    def test_create_plan(self):
        p = DailyPlan(date="2026-04-27", tasks=[])
        assert p.date == "2026-04-27"
        assert p.tasks == []

    def test_plan_with_tasks(self):
        tasks = [
            PlanTask(id="t-1", plan_date="2026-04-27", block=PlanBlock.MORNING,
                     task_type=PlanTaskType.SD, title="Design Bitly", done=False),
            PlanTask(id="t-2", plan_date="2026-04-27", block=PlanBlock.EVENING,
                     task_type=PlanTaskType.ENGLISH, title="Review 8 words", done=False),
        ]
        p = DailyPlan(date="2026-04-27", tasks=tasks)
        assert len(p.tasks) == 2

    def test_blocks(self):
        assert PlanBlock.MORNING == "morning"
        assert PlanBlock.AFTERNOON == "afternoon"
        assert PlanBlock.EVENING == "evening"

    def test_task_types(self):
        assert PlanTaskType.SD == "sd"
        assert PlanTaskType.BEHAVIORAL == "behavioral"
        assert PlanTaskType.ENGLISH == "english"
        assert PlanTaskType.INBOX == "inbox"
