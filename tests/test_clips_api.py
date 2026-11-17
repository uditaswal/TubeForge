"""The Clips page API: status, listing, creation and checksum-bound approval of one clip."""
from __future__ import annotations

import hashlib
import json
from argparse import Namespace
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from tubeforge.api.app import create_app
from tubeforge.core.config import AppConfig, AuthConfig, DatabaseConfig, Settings
from tubeforge.db.repositories import Artifact
from tubeforge.domain.states import JobState


def _migrate(path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    config.cmd_opts = Namespace(x=[f"database_url=sqlite:///{path}"])
    command.upgrade(config, "head")


def _client(tmp_path: Path):
    database = tmp_path / "clips.db"
    _migrate(database)
    settings = Settings(app=AppConfig(name="TubeForge test", environment="test"), database=DatabaseConfig(url=f"sqlite:///{database}"), auth=AuthConfig(enabled=True))
    settings.pipeline.source_clips.enabled = True
    settings.pipeline.voice.artifact_root = tmp_path / "artifacts"
    settings.pipeline.claude.enabled = True
    settings.pipeline.claude.socket_path = tmp_path / "claude.sock"
    return create_app(settings)


def _login(app, client):
    app.state.runtime.auth.create_admin("operator", "a-long-test-password")
    assert client.post("/login", json={"username": "operator", "password": "a-long-test-password"}).status_code == 200
    client.headers["x-csrf-token"] = client.cookies["tubeforge_csrf"]


def _finished_clip_job(client, tmp_path: Path, count: int = 3) -> dict:
    runtime = client.app.state.runtime
    created = client.post("/api/clip-jobs", json={"source_url": "https://www.youtube.com/watch?v=abcdefghijk", "clip_count": count})
    assert created.status_code == 201, created.text
    job_id = created.json()["id"]
    work = tmp_path / "files"
    work.mkdir(exist_ok=True)

    def save(stage, name, path):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        runtime.artifacts.save(Artifact(job_id, stage, name, str(path), digest, {}))
        return digest

    metadata = work / "metadata.json"
    metadata.write_text(json.dumps({"url": "https://www.youtube.com/watch?v=abcdefghijk", "id": "abcdefghijk", "title": "A long talk", "duration_seconds": 600.0}))
    save(JobState.SOURCE_INSPECTING, "source_metadata", metadata)
    entries = []
    for index in range(1, count + 1):
        clip = work / f"clip-{index}.mp4"
        clip.write_bytes(b"clip-bytes-%d" % index)
        digest = save(JobState.CLIP_RENDERING, f"clip_{index:03d}", clip)
        entries.append({"name": f"clip_{index:03d}", "path": str(clip), "checksum_sha256": digest,
                        "candidate": {"hook_title": f"Hook {index}", "duration": 20.0, "virality_score": 90 - index, "start_time": "00:10"}})
    manifest = work / "manifest.json"
    manifest.write_text(json.dumps({"clips": entries}))
    save(JobState.CLIP_RENDERING, "clip_manifest", manifest)
    runtime.jobs.update_state(job_id, JobState.FINAL_READY)
    return {"id": job_id, "entries": entries}


def test_engine_status_reports_whether_clips_can_be_made(tmp_path):
    app = _client(tmp_path)
    with TestClient(app) as client:
        _login(app, client)
        status = client.get("/api/clips/engine/status").json()
        assert status["enabled"] is True and status["runner_reachable"] is False and status["can_create"] is False
        assert "runner" in status["reason"]
        (tmp_path / "claude.sock").write_text("")
        assert client.get("/api/clips/engine/status").json()["can_create"] is True


def test_clip_data_needs_a_login_and_the_page_renders_when_signed_in(tmp_path):
    app = _client(tmp_path)
    with TestClient(app) as client:
        # Pages are public shells like Settings; every data and action route is behind the login.
        assert client.get("/api/clip-jobs").status_code in {401, 403}
        assert client.post("/api/clip-jobs", json={"source_url": "https://www.youtube.com/watch?v=abcdefghijk"}).status_code in {401, 403}
        _login(app, client)
        page = client.get("/clips")
        assert page.status_code == 200 and "Make clips" in page.text and 'aria-current="page">Clips' in page.text


def test_a_clip_job_lists_its_clips_with_the_first_as_its_own_video(tmp_path):
    app = _client(tmp_path)
    with TestClient(app) as client:
        _login(app, client)
        job = _finished_clip_job(client, tmp_path)
        listed = client.get("/api/clip-jobs").json()["jobs"]
        assert [item["id"] for item in listed] == [job["id"]]
        item = listed[0]
        assert item["title"] == "A long talk" and item["percent"] == 100 and item["stage"] == "Clips ready"
        assert [clip["own_video"] for clip in item["clips"]] == [True, False, False]
        assert item["clips"][1]["can_approve"] and not item["clips"][0]["can_approve"]
        assert client.get(item["clips"][1]["video_url"]).content == b"clip-bytes-2"


def test_approving_a_clip_creates_one_checksum_bound_child_job(tmp_path):
    app = _client(tmp_path)
    with TestClient(app) as client:
        _login(app, client)
        job = _finished_clip_job(client, tmp_path)
        second = job["entries"][1]
        approved = client.post(f"/api/clip-jobs/{job['id']}/clips/clip_002/approve", json={"checksum_sha256": second["checksum_sha256"]})
        assert approved.status_code == 201 and approved.json()["already_approved"] is False
        child = app.state.runtime.jobs.get(approved.json()["id"])
        assert child.request.clip_of == f"{job['id']}:clip_002:{second['checksum_sha256']}" and child.request.clip_count == 1
        assert child.request.topic == "Hook 2"
        again = client.post(f"/api/clip-jobs/{job['id']}/clips/clip_002/approve", json={"checksum_sha256": second["checksum_sha256"]})
        assert again.json() == {"id": child.id, "state": child.state.value, "already_approved": True}
        listed = next(item for item in client.get("/api/clip-jobs").json()["jobs"] if item["id"] == job["id"])
        assert listed["clips"][1]["approved_job_id"] == child.id and not listed["clips"][1]["can_approve"]
        events = [event["event_type"] for event in client.get(f"/api/jobs/{child.id}/events").json()]
        assert "clip_approved_for_publishing" in events


def test_approval_refuses_a_stale_checksum_a_changed_file_and_the_jobs_own_video(tmp_path):
    app = _client(tmp_path)
    with TestClient(app) as client:
        _login(app, client)
        job = _finished_clip_job(client, tmp_path)
        url = f"/api/clip-jobs/{job['id']}/clips/clip_002/approve"
        assert client.post(url, json={"checksum_sha256": "0" * 64}).status_code == 409
        assert client.post(f"/api/clip-jobs/{job['id']}/clips/clip_001/approve", json={"checksum_sha256": job["entries"][0]["checksum_sha256"]}).status_code == 409
        Path(job["entries"][1]["path"]).write_bytes(b"edited after review")
        assert client.post(url, json={"checksum_sha256": job["entries"][1]["checksum_sha256"]}).status_code == 410
        assert client.post(f"/api/clip-jobs/{job['id']}/clips/clip_009/approve", json={"checksum_sha256": "0" * 64}).status_code == 404
        assert not [item for item in app.state.runtime.jobs.list_recent() if item.request.clip_of]


def test_clip_creation_is_refused_when_clipping_is_disabled(tmp_path):
    app = _client(tmp_path)
    app.state.settings.pipeline.source_clips.enabled = False
    with TestClient(app) as client:
        _login(app, client)
        response = client.post("/api/clip-jobs", json={"source_url": "https://www.youtube.com/watch?v=abcdefghijk"})
        assert response.status_code == 409


def test_a_running_job_shows_its_stage_percent_and_what_it_has_written(tmp_path):
    from tubeforge.pipeline.clip_runs import write_progress
    app = _client(tmp_path)
    with TestClient(app) as client:
        _login(app, client)
        created = client.post("/api/clip-jobs", json={"source_url": "https://www.youtube.com/watch?v=abcdefghijk"}).json()
        job_id = created["id"]
        app.state.runtime.jobs.update_state(job_id, JobState.SOURCE_ANALYZING)
        work = Path(app.state.settings.pipeline.voice.artifact_root) / job_id / "clip-work"
        write_progress(work, "analyze", 30, "Generating transcript...")
        (work / "temp").mkdir(exist_ok=True)
        (work / "temp" / "video.mp4").write_bytes(b"x" * 2048)
        job = client.get(f"/api/clip-jobs/{job_id}").json()
        assert job["short_id"] == job_id[:8] and job["percent"] == 30
        assert job["progress"]["message"] == "Generating transcript..." and job["progress"]["disk_bytes"] >= 2048
        assert job["progress"]["seconds_since_update"] <= 5
        page = client.get("/clips").text
        assert "liveBlock" in page and "On disk" in page and "clip.name" in page


def test_the_progress_file_is_written_atomically_and_never_fails_the_job(tmp_path):
    from tubeforge.pipeline.clip_runs import PROGRESS_FILE, write_progress
    write_progress(tmp_path / "w", "render", 80, "Creating clip 2/3...")
    assert json.loads((tmp_path / "w" / PROGRESS_FILE).read_text())["percent"] == 80
    blocked = tmp_path / "file"
    blocked.write_text("not a folder")
    write_progress(blocked / "sub", "render", 1, "x")  # an unwritable location is ignored


def test_every_page_has_the_same_sidebar_including_settings_and_clips(tmp_path):
    from tubeforge.api.studio_shell import STUDIO_NAV_ITEMS, STUDIO_SCRIPT, render_studio_sidebar
    for _key, _href, label in STUDIO_NAV_ITEMS:
        assert f">{label}<" in STUDIO_SCRIPT, f"the dashboard sidebar is missing {label}"
        assert f">{label}<" in render_studio_sidebar("clips")
    assert "__SPA_NAV__" not in STUDIO_SCRIPT
    app = _client(tmp_path)
    with TestClient(app) as client:
        _login(app, client)
        dashboard = client.get("/").text
        assert 'href="/settings">Settings<' in dashboard and 'href="/clips">Clips<' in dashboard
