"""Small scheduler that delegates all expensive work to the existing worker."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from croniter import croniter

from tubeforge.db.repositories import Schedule, ScheduleRepository, Topic, TopicRepository
from tubeforge.domain.contracts import ContentRequest, SourceReference
from tubeforge.domain.video_duration import SHORTS_MAX_DURATION_SECONDS, SHORTS_MIN_DURATION_SECONDS


def next_run(cron: str, timezone: str, after: datetime) -> datetime:
    """Return the next cron occurrence in UTC, rejecting invalid zones/rules."""
    local = after.astimezone(ZoneInfo(timezone))
    return croniter(cron, local).get_next(datetime).astimezone(UTC)


def schedule_destination_options(options: dict[str, object]) -> tuple[tuple[str, ...], str | None]:
    """Validate the local delivery plan saved on a schedule."""
    raw_ids = options.get("destination_account_ids", [])
    if not isinstance(raw_ids, (list, tuple)) or len(raw_ids) > 20 or any(not isinstance(item, str) or not item for item in raw_ids) or len(set(raw_ids)) != len(raw_ids):
        raise ValueError("select at most 20 distinct destination accounts")
    description = options.get("video_description")
    if description is not None and (not isinstance(description, str) or not description.strip() or len(description) > 5000):
        raise ValueError("video description must contain 1–5000 characters")
    return tuple(raw_ids), description.strip() if description is not None else None


def request_from_topic(topic: Topic, schedule: Schedule, codex_config=None) -> ContentRequest:
    """Build the same provider-neutral request accepted by manual generation."""
    options = {**schedule.options, **topic.options}
    notes = tuple(line.strip() for line in topic.notes.splitlines() if line.strip()) or ("Operator supplied topic.",)
    from tubeforge.core.config import CodexProviderConfig
    from tubeforge.providers.content.youtube_skills import voice_for
    config = codex_config or CodexProviderConfig()
    channel, profile = voice_for(config, options.get("channel_identity"))
    aspect = str(options.get("aspect_ratio", "16:9"))
    duration = int(options.get("duration_seconds", 45 if aspect == "9:16" else 60))
    if aspect == "9:16" and not SHORTS_MIN_DURATION_SECONDS <= duration <= SHORTS_MAX_DURATION_SECONDS:
        raise ValueError(f"scheduled Shorts require {SHORTS_MIN_DURATION_SECONDS}–{SHORTS_MAX_DURATION_SECONDS} seconds")
    return ContentRequest(
        channel_identity=channel, channel_voice_profile=profile, aspect_ratio=aspect,
        preset_name=str(options.get("preset_name", "shorts" if aspect == "9:16" else "default")),
        topic=topic.title, angle="\n".join(notes), target_duration_seconds=duration,
        language=str(options.get("language", "en")), audience=str(options.get("audience", "general")),
        prompt_version=config.prompt_template_version, sources=(SourceReference(source_id="operator-notes", url="https://local.invalid/operator-notes", title="Operator-provided notes", excerpt="\n".join(notes)),),
        notes=notes, review_mode=str(options.get("review_mode", "auto")), captions_enabled=bool(options.get("captions_enabled", True)),
        visual_style=str(options.get("visual_style", "cinematic-tech")),
    )


class SchedulerService:
    def __init__(self, schedules: ScheduleRepository, topics: TopicRepository, *, scheduler_id: str, reservation_seconds: int = 600, codex_config=None) -> None:
        self.codex_config = codex_config
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
        from tubeforge.core.errors import ProviderValidationError
        try:
            request = request_from_topic(topic, schedule, self.codex_config)
            destination_ids, description = schedule_destination_options(schedule.options)
        except (ValueError, ProviderValidationError) as error:
            self.schedules.finish_run(run_id=run_id, state="invalid_request", now=now, topic_id=topic.id, details={"reason": str(error)[:1000]})
            return {"state": "invalid_request", "schedule_id": schedule.id, "topic_id": topic.id, "reason": str(error)[:1000]}
        try:
            job = self.topics.reserve_and_create_job(topic_id=topic.id, scheduler_id=self.scheduler_id, job_id=job_id, request=request, lease_seconds=self.reservation_seconds, destination_account_ids=destination_ids, video_description=description)
        except ValueError as error:
            self.schedules.finish_run(run_id=run_id, state="invalid_request", now=now, topic_id=topic.id, details={"reason": str(error)[:1000]})
            return {"state": "invalid_request", "schedule_id": schedule.id, "topic_id": topic.id, "reason": str(error)[:1000]}
        if job is None:
            self.schedules.finish_run(run_id=run_id, state="contention", now=now, topic_id=topic.id)
            return {"state": "contention", "schedule_id": schedule.id}
        self.schedules.finish_run(run_id=run_id, state="created", now=now, topic_id=topic.id, job_id=job.id)
        return {"state": "created", "schedule_id": schedule.id, "topic_id": topic.id, "job_id": job.id}

    def tick(self, *, now: datetime | None = None) -> list[dict[str, object]]:
        now = now or datetime.now(UTC)
        return [self.run(schedule, now=now, run_key=schedule.next_run_at.astimezone(UTC).isoformat() if schedule.next_run_at else None) for schedule in self.schedules.due(now)]
