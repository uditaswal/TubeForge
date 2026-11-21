"""Run one job alone: the worker takes only that job, and the focus ends when that job rests."""
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from tests.test_clips_api import _client, _login
from tubeforge.core.config import DatabaseConfig, WorkerConfig
from tubeforge.core.job_focus import JobFocus
from tubeforge.db.models import Base
from tubeforge.db.repositories import JobRepository
from tubeforge.db.session import create_database
from tubeforge.domain.contracts import ContentRequest, SourceReference
from tubeforge.domain.states import JobState
from tubeforge.workers.service import WorkerService


def _request(topic="Rain"):
    return ContentRequest(topic=topic, angle="Explainer", target_duration_seconds=60, language="en", audience="general", prompt_version="test-v1",
                          sources=(SourceReference(source_id="s", url="https://example.invalid/r", title="Rain"),))


class _Orchestrator:
    def __init__(self, jobs): self.jobs, self.ran = jobs, []
    def run(self, job_id, **_):
        self.ran.append(job_id)
        return self.jobs.update_state(job_id, JobState.SCRIPT_APPROVAL_REQUIRED)


def test_the_worker_takes_only_the_focused_job_and_the_focus_ends_when_it_rests(tmp_path: Path):
    database = create_database(DatabaseConfig(url=f"sqlite:///{tmp_path / 'w.db'}"))
    Base.metadata.create_all(database.engine)
    jobs = JobRepository(database.session_factory)
    jobs.create("old", _request("older"))
    jobs.create("chosen", _request("chosen"))
    orchestrator = _Orchestrator(jobs)
    worker = WorkerService("w", jobs, orchestrator, WorkerConfig(), clock=lambda: datetime.now(UTC))
    worker.focus = JobFocus(tmp_path / "run" / "job-focus.json")
    worker.focus.set("chosen")
    worker.run_once()
    assert orchestrator.ran == ["chosen"]  # the older job waited
    worker.run_once()
    assert worker.focus.job_id() is None  # the focused job rests, so the focus ended by itself
    worker.run_once()
    assert "old" in orchestrator.ran  # and the queue moves again


def test_the_focus_api_sets_reports_and_releases(tmp_path: Path):
    app = _client(tmp_path)
    with TestClient(app) as client:
        _login(app, client)
        job_id = client.post("/api/clip-jobs", json={"source_url": "https://www.youtube.com/watch?v=abcdefghijk"}).json()["id"]
        assert client.get("/api/job-focus").json() == {"active": False, "job_id": None, "since": None}
        assert client.post(f"/api/jobs/{job_id}/focus").json() == {"active": True, "job_id": job_id}
        assert client.get("/api/job-focus").json()["job_id"] == job_id
        assert client.delete("/api/job-focus").json()["active"] is False
        assert client.get("/api/job-focus").json()["active"] is False
        app.state.runtime.jobs.update_state(job_id, JobState.FINAL_READY)
        assert client.post(f"/api/jobs/{job_id}/focus").status_code == 409  # nothing left to run
        assert client.post("/api/jobs/nope/focus").status_code == 404


def test_the_generations_cards_show_thumbnails_publish_and_run_only_this(tmp_path: Path):
    app = _client(tmp_path)
    with TestClient(app) as client:
        _login(app, client)
        page = client.get("/").text
        for needle in ("job-thumb", "Create thumbnail", "Publish…", "Run only this", "window.focusJob", "tubeforge:publish-job", "focusBanner"):
            assert needle in page, needle


def test_studio_brief_carries_thumbnail_guidance_into_the_notes(tmp_path: Path):
    from tubeforge.api.app import THUMBNAIL_NOTE_PREFIX, VideoBriefRequest, _video_request
    from tubeforge.core.config import load_settings
    app = _client(tmp_path)
    request = _video_request(VideoBriefRequest(title="T", notes=("Explain it.",), thumbnail_guidance="  the number 8x   in yellow "), app.state.settings)
    assert THUMBNAIL_NOTE_PREFIX + "the number 8x in yellow" in request.notes
    plain = _video_request(VideoBriefRequest(title="T", notes=("Explain it.",)), app.state.settings)
    assert not any(note.startswith("Thumbnail direction") for note in plain.notes)
    with TestClient(app) as client:
        _login(app, client)
        page = client.get("/").text
        assert "thumbnailGuidance" in page and "Thumbnail guidance (optional)" in page


def test_the_scene_dialog_names_each_scene_and_thumbnails_open_full_size(tmp_path: Path):
    app = _client(tmp_path)
    with TestClient(app) as client:
        _login(app, client)
        page = client.get("/").text
        for needle in ("function sceneName", "function buildTiles", "'Scene '+(packageData.scene_plans.indexOf(item)+1)", "sceneTiles", "Click a scene below",
                       "thumb-lightbox", "Click to see the full thumbnail", "thumbLightbox"):
            assert needle in page, needle
