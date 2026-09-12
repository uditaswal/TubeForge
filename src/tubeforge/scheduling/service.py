"""Small scheduler that delegates all expensive work to the existing worker."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from croniter import croniter

from tubeforge.db.repositories import Schedule, ScheduleRepository, Topic, TopicRepository
from tubeforge.domain.contracts import ContentRequest, SourceReference


def next_run(cron: str, timezone: str, after: datetime) -> datetime:
    """Return the next cron occurrence in UTC, rejecting invalid zones/rules."""
    local = after.astimezone(ZoneInfo(timezone))
    return croniter(cron, local).get_next(datetime).astimezone(UTC)


def request_from_topic(topic: Topic, schedule: Schedule) -> ContentRequest:
    """Build the same provider-neutral request accepted by manual generation."""
    options = {**schedule.options, **topic.options}
    notes = tuple(line.strip() for line in topic.notes.splitlines() if line.strip()) or ("Operator supplied topic.",)
    return ContentRequest(
        topic=topic.title, angle="\n".join(notes), target_duration_seconds=int(options.get("duration_seconds", 60)),
        language=str(options.get("language", "en")), audience=str(options.get("audience", "general")),
        prompt_version="topic-queue-v1", sources=(SourceReference(source_id="operator-notes", url="https://local.invalid/operator-notes", title="Operator-provided notes", excerpt="\n".join(notes)),),
        notes=notes, review_mode=str(options.get("review_mode", "auto")), captions_enabled=bool(options.get("captions_enabled", True)),
        visual_style=str(options.get("visual_style", "cinematic-tech")),
    )


class SchedulerService:
    def __init__(self, schedules: ScheduleRepository, topics: TopicRepository, *, scheduler_id: str, reservation_seconds: int = 600) -> None:
        self.schedules, self.topics, self.scheduler_id, self.reservation_seconds = schedules, topics, scheduler_id, reservation_seconds

    def run(self, schedule: Schedule, *, now: datetime | None = None, run_key: str | None = None) -> dict[str, object]:
        now = now or datetime.now(UTC)
        key = run_key or now.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
        run_id = uuid4().hex
        if not self.schedules.begin_run(run_id=run_id, schedule_id=schedule.id, run_key=key, now=now):
            return {"state": "duplicate", "schedule_id": schedule.id}
        ready = self.topics.list(status="ready", limit=1)
        next_at = next_run(schedule.cron, schedule.timezone, now)
        self.schedules.advance(schedule.id, now=now, next_run_at=next_at)
        if not ready:
            self.schedules.finish_run(run_id=run_id, state="no_topic", now=now, details={"next_run_at": next_at.isoformat()})
            return {"state": "no_topic", "schedule_id": schedule.id}
        topic = ready[0]
        job_id = uuid4().hex
        job = self.topics.reserve_and_create_job(topic_id=topic.id, scheduler_id=self.scheduler_id, job_id=job_id, request=request_from_topic(topic, schedule), lease_seconds=self.reservation_seconds)
        if job is None:
            self.schedules.finish_run(run_id=run_id, state="contention", now=now, topic_id=topic.id)
            return {"state": "contention", "schedule_id": schedule.id}
        self.schedules.finish_run(run_id=run_id, state="created", now=now, topic_id=topic.id, job_id=job.id)
        return {"state": "created", "schedule_id": schedule.id, "topic_id": topic.id, "job_id": job.id}

    def tick(self, *, now: datetime | None = None) -> list[dict[str, object]]:
        now = now or datetime.now(UTC)
        return [self.run(schedule, now=now, run_key=schedule.next_run_at.astimezone(UTC).isoformat() if schedule.next_run_at else None) for schedule in self.schedules.due(now)]
