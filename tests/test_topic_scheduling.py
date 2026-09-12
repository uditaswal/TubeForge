from __future__ import annotations

from argparse import Namespace
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config

from tubeforge.core.config import DatabaseConfig
from tubeforge.db.repositories import ScheduleRepository, TopicRepository
from tubeforge.db.session import create_database
from tubeforge.db.models import Base
from tubeforge.scheduling.service import SchedulerService, next_run


def test_schedule_reserves_highest_priority_topic_once(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    path = tmp_path / "queue.db"
    config = Config(str(root / "alembic.ini")); config.set_main_option("script_location", str(root / "migrations")); config.cmd_opts = Namespace(x=[f"database_url=sqlite:///{path}"])
    command.upgrade(config, "head")
    database = create_database(DatabaseConfig(url=f"sqlite:///{path}"))
    try:
        topics, schedules = TopicRepository(database.session_factory), ScheduleRepository(database.session_factory)
        low = topics.create("low", title="Low", priority=1)
        high = topics.create("high", title="High", notes="Strong hook", priority=9)
        now = datetime(2026, 8, 31, 9, 0, tzinfo=UTC)
        schedule = schedules.create("daily", name="Daily", cron="0 */12 * * *", timezone="UTC", next_run_at=next_run("0 */12 * * *", "UTC", now))
        service = SchedulerService(schedules, topics, scheduler_id="test")
        result = service.run(schedule, now=now, run_key="first")
        assert result["state"] == "created" and result["topic_id"] == high.id
        assert topics.get(high.id).generation_job_id == result["job_id"]
        assert topics.get(low.id).status == "ready"
        assert service.run(schedule, now=now, run_key="first")["state"] == "duplicate"
    finally:
        database.dispose()


def test_tick_only_fires_due_schedule_once(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]; path = tmp_path / "tick.db"
    config = Config(str(root / "alembic.ini")); config.set_main_option("script_location", str(root / "migrations")); config.cmd_opts = Namespace(x=[f"database_url=sqlite:///{path}"])
    command.upgrade(config, "head")
    database = create_database(DatabaseConfig(url=f"sqlite:///{path}"))
    try:
        topics, schedules = TopicRepository(database.session_factory), ScheduleRepository(database.session_factory)
        topics.create("topic", title="Scheduled")
        now = datetime(2026, 8, 31, 9, 0, tzinfo=UTC)
        schedule = schedules.create("due", name="Due", cron="0 * * * *", timezone="UTC", next_run_at=now)
        service = SchedulerService(schedules, topics, scheduler_id="test")
        assert service.tick(now=now)[0]["state"] == "created"
        assert service.tick(now=now) == []
        assert schedules.list()[0].id == schedule.id
    finally:
        database.dispose()


def test_bulk_topic_entry_is_atomic_and_ordered(tmp_path: Path) -> None:
    database = create_database(DatabaseConfig(url=f"sqlite:///{tmp_path / 'bulk.db'}"))
    Base.metadata.create_all(database.engine)
    try:
        topics = TopicRepository(database.session_factory)
        inserted = topics.create_many((("one", "First"), ("two", "Second")), priority=4)
        assert [item.title for item in inserted] == ["First", "Second"]
        assert [item.title for item in topics.list()] == ["First", "Second"]
    finally:
        database.dispose()
