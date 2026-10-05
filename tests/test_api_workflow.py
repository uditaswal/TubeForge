"""Private HTTP control-plane coverage without starting a worker or provider."""

from __future__ import annotations

from argparse import Namespace
import hashlib
import io
import math
import struct
import wave
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from tubeforge.api.app import create_app
from tubeforge.core.config import AppConfig, DatabaseConfig, FakeProviderConfig, Settings, VideoPresetConfig
from tubeforge.db.repositories import Artifact
from tubeforge.domain.states import JobState
from tubeforge.providers.fake import FakeContentProvider, FakeVoiceProvider
from tubeforge.providers.content.prompts import build_content_prompt


def _migrate(path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    config.cmd_opts = Namespace(x=[f"database_url=sqlite:///{path}"])
    command.upgrade(config, "head")


def _music_wave() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as stream:
        stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(16_000)
        stream.writeframes(b"".join(struct.pack("<h", round(2_000 * math.sin(2 * math.pi * 220 * index / 16_000))) for index in range(16_000)))
    return buffer.getvalue()


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
        # Script approvals are bound to durable content bytes; a newly created
        # job has no script to review until the worker has checkpointed one.
        package = tmp_path / "content-package.json"
        package.write_text("{}", encoding="utf-8")
        client.app.state.runtime.artifacts.save(
            Artifact(job_id, JobState.CONTENT_GENERATING, "content_package", str(package), "c" * 64, {})
        )
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
        assert listed[0]["artifacts"] == ["content_package", "preview"]
        assert listed[0]["created_at"] is not None
        assert listed[0]["created_at"].endswith("+05:30")
        assert not listed[0]["deletable"]
        assert listed[0]["event_count"] == 2
        events = client.get(f"/api/jobs/{job_id}/events")
        assert events.status_code == 200
        assert [event["event_type"] for event in events.json()] == ["job_created", "approval_recorded"]
        assert all(event["created_at"].endswith("+05:30") for event in events.json())
        assert client.get("/api/jobs/missing").status_code == 404


def test_video_brief_uses_defaults_and_persists_user_options(tmp_path: Path) -> None:
    database_path = tmp_path / "brief.db"
    _migrate(database_path)
    settings = Settings(app=AppConfig(name="TubeForge test", environment="test"), database=DatabaseConfig(url=f"sqlite:///{database_path}"))
    settings.pipeline.media.provider = "hybrid"
    settings.pipeline.video_generation.presets["shorts"] = VideoPresetConfig(duration_seconds=45, minimum_duration_seconds=30, maximum_duration_seconds=55, aspect_ratio="9:16")
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/videos", json={"title": "Linux basics", "notes": ["Explain files", "Explain logs"], "source_url": "https://example.com/linux", "source_title": "Linux reference", "source_excerpt": "Files are organized in a hierarchy and logs record system events.", "captions_enabled": False, "review_mode": "auto", "mcp_servers": ["web"], "voice_id": "af_bella", "visual_source": "stock"})
        assert response.status_code == 201
        job = client.app.state.runtime.jobs.get(response.json()["id"])
        assert job.request.notes == ("Explain files", "Explain logs")
        assert not job.request.captions_enabled and job.request.review_mode == "auto"
        assert job.request.mcp_servers == ("web",)
        assert job.request.voice_id == "af_bella"
        assert job.request.visual_source == "stock"
        assert len(job.request.sources) == 2
        assert job.request.sources[1].title == "Linux reference"
        assert job.request.prompt_version == settings.pipeline.codex.prompt_template_version
        assert "REQUEST=" in build_content_prompt(job.request, template_version=job.request.prompt_version, max_chars=settings.pipeline.codex.max_prompt_chars)
        package = FakeContentProvider().generate_package(job.request)
        package_path = tmp_path / "linux-content-package.json"
        package_bytes = package.model_dump_json().encode()
        package_path.write_bytes(package_bytes)
        client.app.state.runtime.artifacts.save(
            Artifact(job.id, JobState.CONTENT_GENERATING, "content_package", str(package_path), hashlib.sha256(package_bytes).hexdigest(), {})
        )
        reviewed = client.get(f"/api/jobs/{job.id}/script")
        assert reviewed.status_code == 200
        assert reviewed.json()["package"]["request"]["sources"][1]["excerpt"].startswith("Files are organized")
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
        assert "Preview voice" in dashboard.text
        assert "Watch video" in dashboard.text
        assert "View / edit script" in dashboard.text
        assert "View script" in dashboard.text
        assert "Copy Codex prompt" in dashboard.text
        assert "Review script and sources" in dashboard.text
        assert "Approved source excerpt" in dashboard.text
        assert "Remove local files" in dashboard.text
        assert "Generate local scene art" in dashboard.text
        assert "Rights-safe stock (Wikimedia Commons; local fallback if unavailable)" in dashboard.text
        assert "Google Image results are not used" in dashboard.text
        assert "Created " in dashboard.text
        assert "Asia/Kolkata" in dashboard.text
        assert "presetSelect" in dashboard.text
        assert "Add licensed music" in dashboard.text
        assert "musicUpload" in dashboard.text
        assert "/api/music" in dashboard.text
        presets = client.get("/api/presets").json()
        assert next(value for value in presets if value["name"] == "shorts")["aspect_ratio"] == "9:16"
        short = client.post("/api/videos", json={"title": "A short", "notes": ["Open with a hook"], "preset": "shorts", "duration_seconds": 45})
        assert short.status_code == 201
        short_job = client.app.state.runtime.jobs.get(short.json()["id"])
        assert short_job.request.aspect_ratio == "9:16" and short_job.request.preset_name == "shorts"
        rejected = client.post("/api/videos", json={"title": "Too long", "notes": ["No"], "preset": "shorts", "duration_seconds": 56})
        assert rejected.status_code == 422
        incomplete_source = client.post("/api/videos", json={"title": "Missing source", "notes": ["A note"], "source_url": "https://example.com/source"})
        assert incomplete_source.status_code == 422
        assert client.get("/favicon.ico").status_code == 204
        # The dashboard must reject a preview request for a voice which is not
        # enabled in this runtime instead of pretending to play one.
        assert client.get("/api/voices/not-configured/preview").status_code == 404


def test_voice_preview_is_synthesized_once_then_served_from_persistent_cache(tmp_path: Path) -> None:
    database_path = tmp_path / "voice-preview.db"
    _migrate(database_path)
    settings = Settings(app=AppConfig(name="TubeForge test", environment="test"), database=DatabaseConfig(url=f"sqlite:///{database_path}"))
    settings.pipeline.voice_provider = "piper"
    model = tmp_path / "piper.onnx"
    model.write_bytes(b"test-model")
    settings.pipeline.piper.model_path = model
    settings.pipeline.voice.artifact_root = tmp_path / "artifacts"
    with TestClient(create_app(settings)) as client:
        voice = FakeVoiceProvider(FakeProviderConfig(artifact_root=tmp_path / "fake"))
        client.app.state.runtime.orchestrator.voice = voice
        first = client.get("/api/voices/piper/preview")
        second = client.get("/api/voices/piper/preview")
        assert first.status_code == second.status_code == 200
        assert first.content == second.content
        assert voice.calls == 1
        previews = list((tmp_path / "artifacts" / "voice-previews").glob("*.wav"))
        assert len(previews) == 1 and previews[0].stat().st_size > 44
        assert second.headers["cache-control"] == "private, max-age=31536000, immutable"


def test_dashboard_uploads_only_verified_licensed_music_and_selects_it_for_a_job(tmp_path: Path) -> None:
    database_path = tmp_path / "music-api.db"
    _migrate(database_path)
    settings = Settings(app=AppConfig(name="TubeForge test", environment="test"), database=DatabaseConfig(url=f"sqlite:///{database_path}"))
    settings.pipeline.voice.artifact_root = tmp_path / "artifacts"
    params = {
        "name": "Quiet Circuit",
        "filename": "quiet.wav",
        "source_url": "https://creator.example/quiet",
        "license_name": "CC BY 4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "attribution_required": "true",
        "attribution": "Quiet Circuit by Example Creator — CC BY 4.0",
    }
    with TestClient(create_app(settings)) as client:
        rejected = client.post("/api/music", params={**params, "publishing_allowed": "false"}, content=_music_wave(), headers={"content-type": "application/octet-stream"})
        assert rejected.status_code == 422
        accepted = client.post("/api/music", params={**params, "publishing_allowed": "true"}, content=_music_wave(), headers={"content-type": "application/octet-stream"})
        assert accepted.status_code == 201
        assert accepted.json()["license_name"] == "CC BY 4.0"
        listed = client.get("/api/music").json()
        assert listed[0]["name"] == "Quiet Circuit" and "path" not in listed[0]
        created = client.post("/api/videos", json={"title": "Music test", "notes": ["A source-backed note"], "music_track": "Quiet Circuit"})
        assert created.status_code == 201
        job = client.app.state.runtime.jobs.get(created.json()["id"])
        assert job.request.music_track == "Quiet Circuit"


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

        published_pending = client.post("/api/videos", json={"title": "Do not publish", "notes": ["A note"]}).json()["id"]
        client.app.state.runtime.jobs.update_state(published_pending, JobState.PUBLICATION_APPROVAL_REQUIRED)
        assert client.get("/api/jobs").json()[0]["deletable"]
        assert client.delete(f"/api/jobs/{published_pending}").status_code == 204


def test_dashboard_removes_published_local_artifacts_without_losing_audit(tmp_path: Path) -> None:
    database_path = tmp_path / "published-cleanup.db"
    _migrate(database_path)
    artifact_root = tmp_path / "artifacts"
    settings = Settings(app=AppConfig(name="TubeForge test", environment="test"), database=DatabaseConfig(url=f"sqlite:///{database_path}"))
    settings.pipeline.voice.artifact_root = artifact_root
    with TestClient(create_app(settings)) as client:
        created = client.post("/api/videos", json={"title": "Published", "notes": ["A note"]})
        job_id = created.json()["id"]
        path = artifact_root / job_id / "final.mp4"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"published-video")
        client.app.state.runtime.artifacts.save(Artifact(job_id, JobState.FINAL_RENDERING, "final", str(path), "c" * 64, {}))
        client.app.state.runtime.jobs.update_state(job_id, JobState.PUBLISHED)

        listed = client.get("/api/jobs").json()
        assert listed[0]["artifact_cleanup_eligible"]
        assert not listed[0]["deletable"]
        assert client.delete(f"/api/jobs/{job_id}/artifacts").status_code == 204
        assert not path.exists()
        assert client.get(f"/api/jobs/{job_id}").status_code == 200
        assert client.app.state.runtime.artifacts.list_for_job(job_id) == []
        assert client.get(f"/api/jobs/{job_id}/events").json()[-1]["event_type"] == "local_artifacts_removed"
