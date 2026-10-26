"""Private HTTP control-plane coverage without starting a worker or provider."""

from __future__ import annotations

from argparse import Namespace
from datetime import UTC, datetime, timedelta
import hashlib
import io
import json
import math
import struct
import wave
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest

from tubeforge.api.app import create_app
from tubeforge.core.config import AppConfig, AuthConfig, DatabaseConfig, FakeProviderConfig, Settings, VideoPresetConfig
from tubeforge.db.repositories import Artifact
from tubeforge.domain.contracts import ContentPackage, ContentRequest, SourceReference
from tubeforge.domain.states import ApprovalGate, JobState
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
        diagnostics = client.get(f"/api/jobs/{job_id}/diagnostics")
        assert diagnostics.status_code == 200
        assert diagnostics.json()["stage_metrics"] == {}
        assert diagnostics.json()["performance_enforcement"] == "disabled"
        download = client.get(f"/api/jobs/{job_id}/diagnostics.jsonl")
        assert download.status_code == 200
        assert "attachment" in download.headers["content-disposition"]
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


@pytest.mark.parametrize("failed_stage", [JobState.ASSET_ACQUISITION, JobState.PREVIEW_RENDERING])
def test_signed_in_studio_retries_only_intact_exact_approved_asset_checkpoint(tmp_path: Path, failed_stage: JobState) -> None:
    database_path = tmp_path / "validation-retry.db"
    _migrate(database_path)
    settings = Settings(
        app=AppConfig(name="TubeForge test", environment="test"),
        database=DatabaseConfig(url=f"sqlite:///{database_path}"),
        auth=AuthConfig(enabled=True),
    )
    fixture = Path(__file__).parent / "fixtures" / "production" / "docker_images_containers"
    package_bytes = (fixture / "content_package.json").read_bytes()
    packet_bytes = (fixture / "source_packet.json").read_bytes()
    package = ContentPackage.model_validate_json(package_bytes)
    package_identity = hashlib.sha256(package_bytes).hexdigest()

    with TestClient(create_app(settings)) as client:
        runtime = client.app.state.runtime
        runtime.auth.create_admin("retry-operator", "correct-horse-battery-staple")
        assert client.post("/login", json={"username": "retry-operator", "password": "correct-horse-battery-staple"}).status_code == 200
        client.headers["x-csrf-token"] = client.cookies["tubeforge_csrf"]

        def failed_approved_job(job_id: str, *, damage_packet: bool = False) -> tuple[str, Path]:
            runtime.jobs.create(job_id, package.request)
            package_path, packet_path = tmp_path / f"{job_id}-package.json", tmp_path / f"{job_id}-source.json"
            package_path.write_bytes(package_bytes)
            packet_path.write_bytes(packet_bytes)
            runtime.artifacts.save(Artifact(job_id, JobState.CONTENT_GENERATING, "content_package", str(package_path), package_identity, {}))
            runtime.artifacts.save(Artifact(job_id, JobState.CONTENT_GENERATING, "source_packet", str(packet_path), hashlib.sha256(packet_bytes).hexdigest(), {}))
            response = client.post(f"/api/jobs/{job_id}/approvals/script", json={"status": "approved", "actor": "test-operator"})
            assert response.status_code == 200
            runtime.jobs.update_state(job_id, JobState.FAILED_VALIDATION, failed_stage, "scene contract validation failed")
            if damage_packet:
                packet_path.write_bytes(packet_bytes + b"tampered")
            return package_identity, packet_path

        expected_identity, _ = failed_approved_job("retry-valid-checkpoint")
        listed = {item["id"]: item for item in client.get("/api/jobs").json()}
        assert listed["retry-valid-checkpoint"]["can_retry_validation"] is True
        assert "Retry approved media stages" in client.get("/").text
        stale = client.post("/api/jobs/retry-valid-checkpoint/retry-validation", json={"expected_script_identity": "0" * 64})
        assert stale.status_code == 409
        resumed = client.post("/api/jobs/retry-valid-checkpoint/retry-validation", json={"expected_script_identity": expected_identity})
        assert resumed.status_code == 200
        assert resumed.json()["state"] == JobState.ASSET_ACQUISITION.value
        assert resumed.json()["script_identity"] == expected_identity
        job = runtime.jobs.get("retry-valid-checkpoint")
        assert job.claim_owner is None and job.resume_state is None and job.failure_message is None
        assert runtime.approvals.approved(job.id, ApprovalGate.SCRIPT, reviewed_identity=expected_identity) is not None
        event = runtime.events.list_for_job(job.id)[-1]
        assert event.event_type == "validation_retry_requested"
        assert event.details["reviewed_script_identity"] == expected_identity
        claimed = runtime.jobs.claim_oldest_eligible("retry-worker-test", now=datetime.now(UTC), lease_seconds=30)
        assert claimed is not None and claimed.id == job.id
        assert claimed.state is JobState.ASSET_ACQUISITION and claimed.attempt_count == 0
        runtime.jobs.release_claim(job.id, "retry-worker-test")

        _, damaged_path = failed_approved_job("retry-damaged-checkpoint", damage_packet=True)
        assert client.post("/api/jobs/retry-damaged-checkpoint/retry-validation", json={"expected_script_identity": expected_identity}).status_code == 409
        damaged_listing = {item["id"]: item for item in client.get("/api/jobs").json()}
        assert damaged_listing["retry-damaged-checkpoint"]["can_retry_validation"] is False
        assert damaged_path.read_bytes() == packet_bytes + b"tampered"

        failed_approved_job("retry-existing-preview")
        runtime.jobs.update_state("retry-existing-preview", JobState.FAILED_VALIDATION, JobState.PREVIEW_RENDERING, "render failed")
        preview_path = tmp_path / "existing-preview.mp4"
        preview_path.write_bytes(b"retained preview")
        runtime.artifacts.save(Artifact(
            "retry-existing-preview", JobState.PREVIEW_RENDERING, "preview",
            str(preview_path), hashlib.sha256(preview_path.read_bytes()).hexdigest(), {},
        ))
        assert client.post("/api/jobs/retry-existing-preview/retry-validation", json={
            "expected_script_identity": expected_identity,
        }).status_code == 409
        with pytest.raises(ValueError, match="existing preview"):
            runtime.jobs.retry_approved_asset_validation(
                "retry-existing-preview", package_identity=expected_identity, actor="test",
            )
        runtime.jobs.update_state("retry-existing-preview", JobState.PREVIEW_READY)
        assert client.post("/api/jobs/retry-existing-preview/retry-validation", json={
            "expected_script_identity": expected_identity,
        }).status_code == 200
        runtime.jobs.update_state("retry-existing-preview", JobState.PREVIEW_READY)
        runtime.approvals.record("preview-approved", "retry-existing-preview", ApprovalGate.PREVIEW,
                                 actor="test-operator", reviewed_identity="f" * 64)
        assert client.post("/api/jobs/retry-existing-preview/retry-validation", json={
            "expected_script_identity": expected_identity,
        }).status_code == 409
        with pytest.raises(ValueError, match="approved preview"):
            runtime.jobs.retry_approved_asset_validation(
                "retry-existing-preview", package_identity=expected_identity, actor="test",
            )


def test_scheduled_alignment_retry_is_visible_as_pending_in_studio(tmp_path: Path) -> None:
    database_path = tmp_path / "retry-studio.db"
    _migrate(database_path)
    settings = Settings(app=AppConfig(name="TubeForge test", environment="test"), database=DatabaseConfig(url=f"sqlite:///{database_path}"), auth=AuthConfig(enabled=True))
    with TestClient(create_app(settings)) as client:
        runtime = client.app.state.runtime
        runtime.auth.create_admin("retry-reviewer", "correct-horse-battery-staple")
        assert client.get("/api/jobs").status_code == 401
        assert client.post("/login", json={"username": "retry-reviewer", "password": "correct-horse-battery-staple"}).status_code == 200
        job = runtime.jobs.create("alignment-retry-ui", ContentRequest(
            topic="Git staging", angle="Short tutorial", target_duration_seconds=45, language="en-IN", audience="general", prompt_version="test-v1",
            sources=(SourceReference(source_id="git", url="https://example.invalid/git", title="Git"),),
        ))
        now = datetime.now(UTC)
        assert runtime.jobs.claim_oldest_eligible("retry-worker", now=now, lease_seconds=300).id == job.id
        runtime.jobs.update_state(job.id, JobState.FAILED_RETRYABLE, resume_state=JobState.VOICE_GENERATION, failure_message="audio-grounded alignment model execution failed")
        runtime.jobs.schedule_retry(job.id, "retry-worker", now=now, next_retry_at=now + timedelta(seconds=30), exhausted=False)

        payload = client.get(f"/api/jobs/{job.id}").json()
        assert payload["state"] == "failed_retryable"
        assert payload["attempt_count"] == 1
        assert payload["next_retry_at"].endswith("+05:30")
        assert payload["failure_message"] == "audio-grounded alignment model execution failed"
        listed = client.get("/api/jobs").json()
        assert listed[0]["next_retry_at"] == payload["next_retry_at"]
        dashboard = client.get("/").text
        assert "Retry scheduled" in dashboard and "Next attempt" in dashboard


def test_video_brief_uses_defaults_and_persists_user_options(tmp_path: Path) -> None:
    database_path = tmp_path / "brief.db"
    _migrate(database_path)
    settings = Settings(app=AppConfig(name="TubeForge test", environment="test"), database=DatabaseConfig(url=f"sqlite:///{database_path}"))
    settings.pipeline.media.provider = "hybrid"
    settings.pipeline.video_generation.presets["shorts"] = VideoPresetConfig(duration_seconds=45, minimum_duration_seconds=30, maximum_duration_seconds=120, aspect_ratio="9:16")
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
        assert "Exact passage" in dashboard.text
        assert "Remove local files" in dashboard.text
        assert "Generate local scene art" in dashboard.text
        assert "Rights-safe stock (Wikimedia Commons; local fallback if unavailable)" in dashboard.text
        assert "Google Image results are not used" in dashboard.text
        assert "Created " in dashboard.text
        assert "Asia/Kolkata" in dashboard.text
        assert "presetSelect" in dashboard.text
        assert "Add licensed music" in dashboard.text
        assert "Target duration (seconds)" in dashboard.text
        assert "musicUpload" in dashboard.text
        assert "/api/music" in dashboard.text
        assert "musicPreviewButton" in dashboard.text and "musicPreviewAudio" in dashboard.text
        presets = client.get("/api/presets").json()
        assert next(value for value in presets if value["name"] == "shorts")["aspect_ratio"] == "9:16"
        short = client.post("/api/videos", json={"title": "A short", "notes": ["Open with a hook"], "preset": "shorts", "duration_seconds": 45})
        assert short.status_code == 201
        short_job = client.app.state.runtime.jobs.get(short.json()["id"])
        assert short_job.request.aspect_ratio == "9:16" and short_job.request.preset_name == "shorts"
        longer = client.post("/api/videos", json={"title": "Longer Short", "notes": ["No"], "preset": "shorts", "duration_seconds": 120})
        assert longer.status_code == 201
        rejected = client.post("/api/videos", json={"title": "Too long", "notes": ["No"], "preset": "shorts", "duration_seconds": 121})
        assert rejected.status_code == 422
        incomplete_source = client.post("/api/videos", json={"title": "Missing source", "notes": ["A note"], "source_url": "https://example.com/source"})
        assert incomplete_source.status_code == 422
        assert client.get("/favicon.ico").status_code == 204
        # The dashboard must reject a preview request for a voice which is not
        # enabled in this runtime instead of pretending to play one.
        assert client.get("/api/voices/not-configured/preview").status_code == 404


def test_source_url_without_excerpt_reads_the_whole_page(tmp_path: Path, monkeypatch) -> None:
    from tubeforge.domain.contracts import SourceReference
    from tubeforge.pipeline import sources as source_module

    database_path = tmp_path / "scrape-source.db"
    _migrate(database_path)
    settings = Settings(app=AppConfig(name="TubeForge test", environment="test"), database=DatabaseConfig(url=f"sqlite:///{database_path}"),
                        auth=AuthConfig(enabled=True, secure_cookies=False))
    settings.pipeline.codex.prompt_template_version = "m6-content-v7"

    def fake_ingest(self, source):
        assert source.url.unicode_string() == "https://example.com/advisory"
        return source_module.SourceSnapshot(source.source_id, str(source.url), source.title, datetime.now(UTC), "0" * 64, "Whole page text.", None)

    monkeypatch.setattr(source_module.SourceIngestor, "ingest", fake_ingest)
    app = create_app(settings)
    with TestClient(app) as client:
        app.state.runtime.auth.create_admin("operator", "a-long-test-password")
        assert client.post("/login", json={"username": "operator", "password": "a-long-test-password"}).status_code == 200
        client.headers["x-csrf-token"] = client.cookies["tubeforge_csrf"]
        created = client.post("/api/videos", json={"title": "Advisory", "notes": ["Explain it."], "source_url": "https://example.com/advisory"})
        assert created.status_code == 201, created.text
        sources = client.app.state.runtime.jobs.get(created.json()["id"]).request.sources
        assert [(item.source_id, item.title, item.excerpt) for item in sources][1] == ("approved-source-1", "example.com", "Whole page text.")


def test_studio_brief_preserves_separate_angle_and_exact_multi_source_cache_request(tmp_path: Path, monkeypatch) -> None:
    from tubeforge.db.repositories import GenerationCacheRepository
    from tubeforge.providers.content.youtube_skills import DEFAULT_VOICE

    database_path = tmp_path / "exact-source-brief.db"
    _migrate(database_path)
    settings = Settings(
        app=AppConfig(name="TubeForge test", environment="test"),
        database=DatabaseConfig(url=f"sqlite:///{database_path}"),
        auth=AuthConfig(enabled=True, secure_cookies=False),
    )
    settings.pipeline.codex.prompt_template_version = "m6-content-v7"
    settings.pipeline.video_generation.presets["shorts"] = VideoPresetConfig(
        duration_seconds=45, minimum_duration_seconds=30, maximum_duration_seconds=120,
        aspect_ratio="9:16", captions_enabled=True, review_mode="manual",
    )
    sources = [
        {"source_id": "official-one", "url": "https://example.com/one", "title": "Official one", "excerpt": "Exact approved excerpt one."},
        {"source_id": "official-two", "url": "https://example.com/two", "title": "Official two", "excerpt": "Exact approved excerpt two."},
    ]
    notes = ["Keep the named example literal.", "Label the displayed output as illustrative."]
    angle = "Explain the distinction with one concrete example, then show why the distinction matters."
    brief = {
        "title": "Image versus container",
        "notes": notes,
        "angle": angle,
        "audience": "new software developers",
        "sources": sources,
        "preset": "shorts",
        "duration_seconds": 45,
        "channel_identity": "default",
        "review_mode": "manual",
        "captions_enabled": True,
        "visual_source": "generated",
        "visual_style": "cinematic-tech",
    }
    app = create_app(settings)
    with TestClient(app) as client:
        app.state.runtime.auth.create_admin("operator", "a-long-test-password")
        assert client.post("/login", json={"username": "operator", "password": "a-long-test-password"}).status_code == 200
        client.headers["x-csrf-token"] = client.cookies["tubeforge_csrf"]
        created = client.post("/api/videos", json=brief)
        assert created.status_code == 201, created.text
        job = client.app.state.runtime.jobs.get(created.json()["id"])
        expected = ContentRequest(
            channel_identity="default", channel_voice_profile=DEFAULT_VOICE,
            topic="Image versus container", angle=angle, target_duration_seconds=45,
            language="en", audience="new software developers", prompt_version="m6-content-v7",
            sources=tuple(SourceReference.model_validate(source) for source in sources),
            notes=tuple(notes), review_mode="manual", captions_enabled=True,
            visual_style="cinematic-tech", visual_source="generated", preset_name="shorts",
            aspect_ratio="9:16",
        )
        assert job.request == expected
        cache = GenerationCacheRepository(client.app.state.runtime.database.session_factory)
        assert cache.cache_key(job.request, "host-codex-runner", settings.pipeline.codex.model, job.request.prompt_version) == cache.cache_key(expected, "host-codex-runner", settings.pipeline.codex.model, expected.prompt_version)

        duplicate = client.post("/api/videos", json={**brief, "sources": [sources[0], {**sources[1], "source_id": sources[0]["source_id"]}]})
        assert duplicate.status_code == 422 and "unique source IDs" in duplicate.text
        from tubeforge.core.errors import ProviderValidationError
        from tubeforge.pipeline import sources as source_module
        monkeypatch.setattr(source_module.SourceIngestor, "ingest", lambda self, source: (_ for _ in ()).throw(ProviderValidationError("blocked")))
        missing_excerpt = client.post("/api/videos", json={**brief, "sources": [{**sources[0], "excerpt": " "}]})
        assert missing_excerpt.status_code == 422 and "could not read the source page" in missing_excerpt.text
        ambiguous = client.post("/api/videos", json={**brief, "source_url": "https://example.com/extra", "source_title": "Extra", "source_excerpt": "Extra evidence"})
        assert ambiguous.status_code == 422 and "not both" in ambiguous.text

        html = client.get("/").text
        assert 'id="sourceList"' in html and 'name="source_url"' not in html and 'source_packet_json' not in html and 'name="angle"' in html and 'name="audience"' in html
        assert "collectSources" in html and "+ Add source" in html


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
        # The two reserved, always-available entries (video-quality review §4.5 / operator
        # finding, 26 Oct) come first, named and with nothing to preview; the uploaded track
        # follows, real and previewable.
        by_name = {track["name"]: track for track in listed}
        assert by_name["Synthesized Ambient (auto-generated mood-matched bed)"]["previewable"] is False
        assert by_name["No background music"]["previewable"] is False
        assert by_name["Quiet Circuit"]["previewable"] is True and "path" not in by_name["Quiet Circuit"]
        preview = client.get("/api/music/Quiet Circuit/preview")
        assert preview.status_code == 200 and preview.content == _music_wave()
        assert client.get("/api/music/Synthesized Ambient (auto-generated mood-matched bed)/preview").status_code == 404
        created = client.post("/api/videos", json={"title": "Music test", "notes": ["A source-backed note"], "music_track": "Quiet Circuit"})
        assert created.status_code == 201
        job = client.app.state.runtime.jobs.get(created.json()["id"])
        assert job.request.music_track == "Quiet Circuit"
        reserved_job = client.post("/api/videos", json={"title": "Silent test", "notes": ["A source-backed note"], "music_track": "No background music"})
        assert reserved_job.status_code == 201
        assert client.app.state.runtime.jobs.get(reserved_job.json()["id"]).request.music_track == "No background music"


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


def test_scene_revision_api_persists_layout_change_as_exact_child_draft(tmp_path: Path) -> None:
    database_path = tmp_path / "scene-revision.db"
    _migrate(database_path)
    artifact_root = tmp_path / "artifacts"
    settings = Settings(app=AppConfig(name="TubeForge test", environment="test"), database=DatabaseConfig(url=f"sqlite:///{database_path}"))
    settings.pipeline.voice.artifact_root = artifact_root
    request = {
        "topic": "Rain",
        "angle": "A short explainer",
        "target_duration_seconds": 45,
        "language": "en",
        "audience": "general",
        "prompt_version": "test-v1",
        "sources": [{"source_id": "rain", "url": "https://example.invalid/rain", "title": "Rain"}],
    }
    with TestClient(create_app(settings)) as client:
        parent_id = client.post("/api/jobs", json=request).json()["id"]
        runtime = client.app.state.runtime
        parent = runtime.jobs.get(parent_id)
        package = runtime.orchestrator.content.generate_package(parent.request)
        content = json.dumps(package.model_dump(mode="json"), sort_keys=True).encode()
        content_path = artifact_root / parent_id / "content_package.json"
        content_path.parent.mkdir(parents=True, exist_ok=True)
        content_path.write_bytes(content)
        content_identity = hashlib.sha256(content).hexdigest()
        runtime.artifacts.save(Artifact(parent_id, JobState.CONTENT_GENERATING, "content_package", str(content_path), content_identity, {}))
        runtime.jobs.update_state(parent_id, JobState.SCRIPT_APPROVAL_REQUIRED)

        revision = client.post(f"/api/jobs/{parent_id}/scene-revisions", json={
            "scene_id": package.scene_plans[0].scene_id,
            "expected_content_sha256": content_identity,
            "visual_type": "flow_diagram",
            "visual_elements": ["One image", "Container web-a", "Container web-b"],
            "visual_subject": "One image branching to two named containers",
            "actor": "test-operator",
        })
        assert revision.status_code == 201, revision.text
        child_id = revision.json()["job_id"]
        child_content = runtime.artifacts.get(child_id, JobState.CONTENT_GENERATING, "content_package")
        child_package = ContentPackage.model_validate_json(Path(child_content.path).read_bytes())
        assert child_content.checksum_sha256 == revision.json()["reviewed_identity"]
        assert child_content.checksum_sha256 != content_identity
        assert child_package.scene_plans[0].visual_type == "flow_diagram"
        assert runtime.jobs.get(child_id).state is JobState.SCRIPT_APPROVAL_REQUIRED
        assert runtime.artifacts.get(parent_id, JobState.CONTENT_GENERATING, "content_package").checksum_sha256 == content_identity


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


def test_failed_job_retry_creates_new_job_with_edited_request(tmp_path: Path) -> None:
    database_path = tmp_path / "retry-new.db"
    _migrate(database_path)
    settings = Settings(app=AppConfig(name="TubeForge test", environment="test"), database=DatabaseConfig(url=f"sqlite:///{database_path}"), auth=AuthConfig(enabled=True))
    with TestClient(create_app(settings)) as client:
        runtime = client.app.state.runtime
        runtime.auth.create_admin("retry-operator", "correct-horse-battery-staple")
        assert client.post("/login", json={"username": "retry-operator", "password": "correct-horse-battery-staple"}).status_code == 200
        client.headers["x-csrf-token"] = client.cookies["tubeforge_csrf"]
        base = ContentPackage.model_validate_json((Path(__file__).parent / "fixtures" / "production" / "docker_images_containers" / "content_package.json").read_bytes()).request
        runtime.jobs.create("failed-one", base.model_copy(update={"topic": "Original topic"}))
        runtime.jobs.create("busy-one", base.model_copy(update={"topic": "Still running"}))
        assert client.post("/api/jobs/busy-one/retry", json={}).status_code == 409
        runtime.jobs.update_state("failed-one", JobState.FAILED_EXHAUSTED, JobState.CONTENT_GENERATING, "script attempts exhausted")
        listed = {item["id"]: item for item in client.get("/api/jobs").json()}
        assert listed["failed-one"]["can_retry_as_new"] is True and listed["busy-one"]["can_retry_as_new"] is False
        assert "Retry generation" in client.get("/").text
        bad = client.post("/api/jobs/failed-one/retry", json={"request": {"topic": "x", "nonsense": 1}})
        assert bad.status_code == 422 and "nonsense" in bad.json()["detail"]
        edited = json.loads(runtime.jobs.get("failed-one").request.model_dump_json()) | {"topic": "Edited topic"}
        created = client.post("/api/jobs/failed-one/retry", json={"request": edited})
        assert created.status_code == 201 and created.json()["request_edited"] is True
        new = runtime.jobs.get(created.json()["id"])
        assert new.request.topic == "Edited topic" and new.state is JobState.TOPIC_CREATED
        assert runtime.jobs.get("failed-one").state is JobState.FAILED_EXHAUSTED
        same = client.post("/api/jobs/failed-one/retry", json={})
        assert same.status_code == 201 and same.json()["request_edited"] is False


def test_pause_parks_idle_and_running_jobs_and_resume_restores_the_stage(tmp_path: Path) -> None:
    database_path = tmp_path / "pause.db"
    _migrate(database_path)
    settings = Settings(app=AppConfig(name="TubeForge test", environment="test"), database=DatabaseConfig(url=f"sqlite:///{database_path}"), auth=AuthConfig(enabled=True))
    with TestClient(create_app(settings)) as client:
        runtime = client.app.state.runtime
        runtime.auth.create_admin("pause-operator", "correct-horse-battery-staple")
        assert client.post("/login", json={"username": "pause-operator", "password": "correct-horse-battery-staple"}).status_code == 200
        client.headers["x-csrf-token"] = client.cookies["tubeforge_csrf"]
        base = ContentPackage.model_validate_json((Path(__file__).parent / "fixtures" / "production" / "docker_images_containers" / "content_package.json").read_bytes()).request
        runtime.jobs.create("idle-job", base)
        runtime.jobs.create("done-job", base)
        runtime.jobs.update_state("done-job", JobState.FAILED_EXHAUSTED, JobState.CONTENT_GENERATING, "x")
        assert client.post("/api/jobs/done-job/pause").status_code == 409
        listed = {item["id"]: item for item in client.get("/api/jobs").json()}
        assert listed["idle-job"]["can_pause"] is True and listed["done-job"]["can_pause"] is False

        assert client.post("/api/jobs/idle-job/pause").json() == {"status": "paused"}
        paused = {item["id"]: item for item in client.get("/api/jobs").json()}["idle-job"]
        assert paused["paused"] is True and paused["can_resume"] is True and paused["deletable"] is True
        assert runtime.jobs.claim_oldest_eligible("w", now=datetime.now(UTC), lease_seconds=30) is None
        assert client.post("/api/jobs/idle-job/resume").status_code == 200
        assert runtime.jobs.get("idle-job").state is JobState.TOPIC_CREATED
        assert client.post("/api/jobs/idle-job/resume").status_code == 409

        claimed = runtime.jobs.claim_oldest_eligible("w", now=datetime.now(UTC), lease_seconds=300)
        assert claimed is not None and claimed.id == "idle-job"
        assert client.post("/api/jobs/idle-job/pause").json() == {"status": "pausing"}
        assert runtime.jobs.get("idle-job").cancellation_requested_at is not None
        assert client.delete("/api/jobs/idle-job").status_code == 409
        assert client.post("/api/jobs/idle-job/resume").status_code == 409


def test_source_card_scene_without_a_cited_claim_is_rejected_at_script_time() -> None:
    from tubeforge.core.errors import ProviderValidationError
    from tubeforge.providers.content.prompts import validate_video_package

    package = ContentPackage.model_validate_json((Path(__file__).parent / "fixtures" / "production" / "docker_images_containers" / "content_package.json").read_bytes())
    first = package.script_sections[0]
    claims = tuple(claim.model_copy(update={"source_ids": ()}) if claim.claim_id in first.claim_ids else claim for claim in package.claims)
    scenes = (package.scene_plans[0].model_copy(update={"visual_type": "source_card"}), *package.scene_plans[1:])
    broken = package.model_copy(update={"claims": claims, "scene_plans": scenes})
    with pytest.raises(ProviderValidationError, match="source_card scenes must narrate a claim that cites a source"):
        validate_video_package(broken, broken.request, provider_name="Claude")


def test_retired_formats_cannot_start_from_studio_api_or_retry(tmp_path: Path) -> None:
    from tubeforge.core.config import PipelineConfig, VideoGenerationConfig

    database_path = tmp_path / "retired.db"
    _migrate(database_path)
    generation = VideoGenerationConfig(default_preset="legacy", presets={"legacy": VideoPresetConfig()}, retired_prompt_versions=("m6-content-v7",))
    settings = Settings(app=AppConfig(name="TubeForge test", environment="test"), database=DatabaseConfig(url=f"sqlite:///{database_path}"), auth=AuthConfig(enabled=True), pipeline=PipelineConfig(video_generation=generation))
    with pytest.raises(ValueError, match="retired prompt version"):
        VideoGenerationConfig(default_preset="old", presets={"old": VideoPresetConfig(prompt_version="m6-content-v7")}, retired_prompt_versions=("m6-content-v7",))
    with TestClient(create_app(settings)) as client:
        runtime = client.app.state.runtime
        runtime.auth.create_admin("retired-operator", "correct-horse-battery-staple")
        assert client.post("/login", json={"username": "retired-operator", "password": "correct-horse-battery-staple"}).status_code == 200
        client.headers["x-csrf-token"] = client.cookies["tubeforge_csrf"]
        brief = client.post("/api/videos", json={"title": "Old format", "notes": ["one", "two"]})
        assert brief.status_code == 422 and "retired" in brief.json()["detail"]
        base = ContentPackage.model_validate_json((Path(__file__).parent / "fixtures" / "production" / "docker_images_containers" / "content_package.json").read_bytes()).request
        legacy = base.model_copy(update={"prompt_version": "m6-content-v7"})
        assert client.post("/api/jobs", json=json.loads(legacy.model_dump_json())).status_code == 422
        runtime.jobs.create("legacy-failed", legacy)
        runtime.jobs.update_state("legacy-failed", JobState.FAILED_VALIDATION, JobState.PREVIEW_RENDERING, "x")
        assert client.post("/api/jobs/legacy-failed/retry", json={}).status_code == 422
        assert runtime.jobs.get("legacy-failed").state is JobState.FAILED_VALIDATION
