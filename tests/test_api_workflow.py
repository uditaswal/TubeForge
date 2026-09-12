"""Private HTTP control-plane coverage without starting a worker or provider."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from tubeforge.api.app import create_app
from tubeforge.core.config import AppConfig, DatabaseConfig, Settings
from tubeforge.db.repositories import Artifact
from tubeforge.domain.states import JobState


def _migrate(path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    config.cmd_opts = Namespace(x=[f"database_url=sqlite:///{path}"])
    command.upgrade(config, "head")


def test_private_job_api_creates_and_records_an_approval(tmp_path: Path) -> None:
    database_path = tmp_path / "api.db"
    _migrate(database_path)
    settings = Settings(
        app=AppConfig(name="TubeForge test", environment="test"),
        database=DatabaseConfig(url=f"sqlite:///{database_path}"),
    )
    request = {
        "topic": "Rain",
        "angle": "A 30-second explainer",
        "target_duration_seconds": 30,
        "language": "en-IN",
        "audience": "general",
        "prompt_version": "test-v1",
        "sources": [{"source_id": "rain", "url": "https://example.invalid/rain", "title": "Rain"}],
    }
    with TestClient(create_app(settings)) as client:
        created = client.post("/api/jobs", json=request)
        assert created.status_code == 201
        job_id = created.json()["id"]
        assert client.get(f"/api/jobs/{job_id}").json()["state"] == "topic_created"
        approval = client.post(
            f"/api/jobs/{job_id}/approvals/script",
            json={"status": "approved", "actor": "test-operator"},
        )
        assert approval.status_code == 200
        preview = tmp_path / "preview.mp4"
        preview.write_bytes(b"synthetic-preview")
        runtime = client.app.state.runtime
        runtime.artifacts.save(Artifact(job_id, JobState.PREVIEW_RENDERING, "preview", str(preview), "a" * 64, {}))
        assert client.get(f"/api/jobs/{job_id}/artifacts/preview").content == b"synthetic-preview"
        assert client.get(f"/api/jobs/{job_id}/artifacts/preview.mp4").content == b"synthetic-preview"
        listed = client.get("/api/jobs").json()
        assert listed[0]["artifacts"] == ["preview"]
        assert listed[0]["created_at"] is not None
        assert not listed[0]["deletable"]
        assert listed[0]["event_count"] == 2
        events = client.get(f"/api/jobs/{job_id}/events")
        assert events.status_code == 200
        assert [event["event_type"] for event in events.json()] == ["job_created", "approval_recorded"]
        assert client.get("/api/jobs/missing").status_code == 404


def test_video_brief_uses_defaults_and_persists_user_options(tmp_path: Path) -> None:
    database_path = tmp_path / "brief.db"
    _migrate(database_path)
    settings = Settings(app=AppConfig(name="TubeForge test", environment="test"), database=DatabaseConfig(url=f"sqlite:///{database_path}"))
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/videos", json={"title": "Linux basics", "notes": ["Explain files", "Explain logs"], "captions_enabled": False, "review_mode": "auto", "mcp_servers": ["web"], "voice_id": "af_bella"})
        assert response.status_code == 201
        job = client.app.state.runtime.jobs.get(response.json()["id"])
        assert job.request.notes == ("Explain files", "Explain logs")
        assert not job.request.captions_enabled and job.request.review_mode == "auto"
        assert job.request.mcp_servers == ("web",)
        assert job.request.voice_id == "af_bella"
        dashboard = client.get("/")
        assert dashboard.status_code == 200
        assert "id=\"videoDialog\"" in dashboard.text
        assert "autoplay=false" in dashboard.text
        assert r"split('\n')" in dashboard.text
        assert r"join('\n')" in dashboard.text
        assert "jobsRoot.innerHTML=j.map" not in dashboard.text
        assert "sourceClipCreate" in dashboard.text
        assert "/api/source-clips" in dashboard.text
        assert "/api/voices" in dashboard.text
        assert "View / edit script" in dashboard.text
        assert "Copy Codex prompt" in dashboard.text
        assert "Created " in dashboard.text
        assert client.get("/favicon.ico").status_code == 204


def test_source_clip_api_records_a_durable_source_job(tmp_path: Path) -> None:
    database_path = tmp_path / "source-clip.db"
    _migrate(database_path)
    settings = Settings(app=AppConfig(name="TubeForge test", environment="test"), database=DatabaseConfig(url=f"sqlite:///{database_path}"))
    settings.pipeline.source_clips.enabled = True
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/source-clips", json={"source_url": "https://www.youtube.com/watch?v=example", "title": "Demo", "clip_count": 2})
        assert response.status_code == 201
        job = client.app.state.runtime.jobs.get(response.json()["id"])
        assert job.request.production_mode == "source_clip"
        assert job.request.clip_count == 2
        assert client.get(f"/api/jobs/{job.id}/events").json()[0]["event_type"] == "source_clip_job_created"


def test_source_clip_api_accepts_a_short_source_without_breaking_job_contract(tmp_path: Path) -> None:
    database_path = tmp_path / "short-source-clip.db"
    _migrate(database_path)
    settings = Settings(app=AppConfig(name="TubeForge test", environment="test"), database=DatabaseConfig(url=f"sqlite:///{database_path}"))
    settings.pipeline.source_clips.enabled = True
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/source-clips", json={"source_url": "https://example.com/short.mp4", "max_duration_seconds": 10})
        assert response.status_code == 201
        job = client.app.state.runtime.jobs.get(response.json()["id"])
        assert job.request.target_duration_seconds == 30


def test_dashboard_deletes_only_paused_local_generations(tmp_path: Path) -> None:
    database_path = tmp_path / "delete.db"
    _migrate(database_path)
    artifact_root = tmp_path / "artifacts"
    settings = Settings(app=AppConfig(name="TubeForge test", environment="test"), database=DatabaseConfig(url=f"sqlite:///{database_path}"))
    settings.pipeline.voice.artifact_root = artifact_root
    with TestClient(create_app(settings)) as client:
        created = client.post("/api/videos", json={"title": "Disposable", "notes": ["A note"]})
        job_id = created.json()["id"]
        assert client.delete(f"/api/jobs/{job_id}").status_code == 409
        client.app.state.runtime.jobs.update_state(job_id, JobState.SCRIPT_APPROVAL_REQUIRED)
        path = artifact_root / job_id / "preview.mp4"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"preview")
        client.app.state.runtime.artifacts.save(Artifact(job_id, JobState.PREVIEW_RENDERING, "preview", str(path), "b" * 64, {}))
        assert client.delete(f"/api/jobs/{job_id}").status_code == 204
        assert not path.exists()
        assert client.get(f"/api/jobs/{job_id}").status_code == 404
