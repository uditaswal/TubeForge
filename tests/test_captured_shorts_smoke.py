"""Opt-in real-media acceptance of captured test packages, never production scripts."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tubeforge.core.config import (
    AppConfig, DatabaseConfig, FakeProviderConfig, MediaPipelineConfig,
    PipelineConfig, PiperProviderConfig, Settings, ShortsFinalRenderConfig,
    ShortsPreviewRenderConfig, VoicePipelineConfig,
)
from tubeforge.core.runtime import create_runtime
from tubeforge.db.models import Base
from tubeforge.domain.contracts import ContentPackage, ContentRequest, ScenePlan
from tubeforge.domain.states import ApprovalGate, JobState
from tubeforge.pipeline.scene_contracts import ScriptBoundSceneContract
from tubeforge.rendering.animated_card import AnimatedCardScene, resolve_card_cues
from tubeforge.rendering.animated_teaching import AnimatedTeachingScene, resolve_teaching_cues
from tubeforge.rendering.animated_terminal import AnimatedTerminalScene, resolve_cues


ROOT = Path(__file__).resolve().parents[1]
MODEL = os.environ.get("TUBEFORGE_SMOKE_PIPER_MODEL")
PIPER_SERVER_URL = os.environ.get("TUBEFORGE_SMOKE_PIPER_SERVER_URL")
PIPER_VOICE_ID = os.environ.get("TUBEFORGE_SMOKE_PIPER_VOICE_ID", "en_US-lessac-medium" if PIPER_SERVER_URL else "piper")
NORMALIZE_AUDIO = os.environ.get("TUBEFORGE_SMOKE_NORMALIZE_AUDIO") == "1"
MUSIC_FILE = os.environ.get("TUBEFORGE_SMOKE_MUSIC_FILE")
OUTPUT_ROOT = Path(os.environ.get("TUBEFORGE_SMOKE_ARTIFACT_ROOT", str(ROOT / "data/artifacts/stage22_fixture_smoke")))
pytestmark = pytest.mark.skipif(
    not MODEL or not Path(MODEL).is_file()
    or any(shutil.which(name) is None for name in ("ffmpeg", "ffprobe"))
    or (not PIPER_SERVER_URL and shutil.which("piper") is None),
    reason="set TUBEFORGE_SMOKE_PIPER_MODEL and use the local Piper server or install Piper/FFmpeg",
)


@pytest.mark.parametrize("topic", ["git_stage_commit", "docker_images_containers"])
def test_captured_package_renders_technically_valid_portrait_final(tmp_path: Path, topic: str) -> None:
    """Check media plumbing with exact test approval; creative acceptance is separate."""
    fixture = ROOT / "tests" / "fixtures" / "production" / topic
    original_bytes = (fixture / "content_package.json").read_bytes()
    packet_bytes = (fixture / "source_packet.json").read_bytes()
    contract = ScriptBoundSceneContract.model_validate_json((fixture / "scene_contract.json").read_bytes())
    original = contract.validate_against(original_bytes, packet_bytes, accepted_script_identity=contract.package_sha256)
    layouts = {row.scene_id: row for row in contract.scenes}
    cue_file = fixture / "animation_cues.json"
    animation_cues = json.loads(cue_file.read_text()) if cue_file.is_file() else {}
    terminal_file = fixture / "terminal_motion_overlay.json"
    terminal_overlays = json.loads(terminal_file.read_text()) if terminal_file.is_file() else {}
    card_file = fixture / "card_motion_overlay.json"
    card_overlays = json.loads(card_file.read_text()) if card_file.is_file() else {}
    teaching_file = fixture / "teaching_motion_overlay.json"
    teaching_overlays = json.loads(teaching_file.read_text()) if teaching_file.is_file() else {}
    scenes = tuple(
        ScenePlan.model_validate({
            **scene.model_dump(mode="json"),
            "visual_type": layouts[scene.scene_id].layout.value,
            "on_screen_text": layouts[scene.scene_id].command or card_overlays.get(scene.scene_id, {}).get("heading", layouts[scene.scene_id].heading),
            "visual_elements": terminal_overlays.get(scene.scene_id, {}).get("display_elements", card_overlays.get(scene.scene_id, {}).get("display_elements", teaching_overlays.get(scene.scene_id, {}).get("display_elements", layouts[scene.scene_id].display_elements))),
            "visual_subject": card_overlays.get(scene.scene_id, {}).get("heading", layouts[scene.scene_id].heading),
            "visual_purpose": scene.visual_purpose or layouts[scene.scene_id].heading,
            "composition": layouts[scene.scene_id].layout.value,
            **({"terminal_cues": terminal_overlays[scene.scene_id]["terminal_cues"]} if scene.scene_id in terminal_overlays else {"terminal_cues": animation_cues[scene.scene_id]} if scene.scene_id in animation_cues else {}),
            **({"card_cues": card_overlays[scene.scene_id]["card_cues"]} if scene.scene_id in card_overlays else {}),
            **({"teaching_cues": teaching_overlays[scene.scene_id]["teaching_cues"]} if scene.scene_id in teaching_overlays else {}),
        })
        for scene in original.scene_plans
    )
    # The visual overlay creates a distinct test package. Its narration and
    # source request remain byte-for-byte the captured model output; the test
    # DB approves the new exact package artifact before rendering.
    music_fixture = None
    if MUSIC_FILE:
        music_fixture = json.loads((ROOT / "tests/fixtures/production/music/chill_beat.json").read_text())
        selected_audio = Path(MUSIC_FILE)
        assert selected_audio.is_file()
        assert hashlib.sha1(selected_audio.read_bytes()).hexdigest() == music_fixture["sha1"]
        assert hashlib.sha256(selected_audio.read_bytes()).hexdigest() == music_fixture["sha256"]
    request_data = original.request.model_dump(mode="json")
    if music_fixture:
        request_data["music_track"] = music_fixture["name"]
    package = ContentPackage.model_validate({**original.model_dump(mode="json"), "request": request_data, "scene_plans": [scene.model_dump(mode="json") for scene in scenes]})
    assert package.script_sections == original.script_sections
    assert package.request.model_dump(mode="json", exclude={"music_track"}) == original.request.model_dump(mode="json", exclude={"music_track"})

    model_path = Path(MODEL)  # type: ignore[arg-type]
    settings = Settings(
        app=AppConfig(name="Captured Short smoke", environment="test"),
        database=DatabaseConfig(url=f"sqlite:///{tmp_path / 'captured.db'}"),
        pipeline=PipelineConfig(
            content_provider="fake", voice_provider="piper-http" if PIPER_SERVER_URL else "piper",
            fake=FakeProviderConfig(artifact_root=tmp_path / "graphics"),
            piper=PiperProviderConfig(model_path=model_path, server_url=PIPER_SERVER_URL, voice_id=PIPER_VOICE_ID, cache_root=tmp_path / "piper-cache", timeout_seconds=300),
            voice=VoicePipelineConfig(artifact_root=tmp_path / "artifacts"),
            media=MediaPipelineConfig(provider="hybrid", cache_root=tmp_path / "asset-cache", min_width=64, min_height=64),
            shorts_preview=ShortsPreviewRenderConfig(width=360, height=640, minimum_free_bytes=1, timeout_seconds=900, threads=2, audio_normalization_enabled=NORMALIZE_AUDIO),
            shorts_final=ShortsFinalRenderConfig(minimum_free_bytes=1, timeout_seconds=1800, threads=2, audio_normalization_enabled=NORMALIZE_AUDIO),
        ),
    )
    runtime = create_runtime(settings)
    Base.metadata.create_all(runtime.database.engine)
    if music_fixture:
        assert runtime.orchestrator.music_catalog is not None
        record = runtime.orchestrator.music_catalog.upload(
            name=music_fixture["name"], filename=music_fixture["filename"], payload=selected_audio.read_bytes(),
            source_url=music_fixture["source_url"], license_name=music_fixture["license_name"],
            license_url=music_fixture["license_url"], attribution_required=music_fixture["attribution_required"],
            attribution=music_fixture["attribution"], publishing_allowed=music_fixture["publishing_allowed"],
        )
        assert record.checksum_sha256 == music_fixture["sha256"]

    class CapturedTestWriter:
        def generate_package(self, request: ContentRequest) -> ContentPackage:
            assert request == package.request
            return package

    try:
        runtime.orchestrator.content = CapturedTestWriter()
        job_id = f"stage22-{topic}"
        runtime.jobs.create(job_id, package.request)
        assert runtime.orchestrator.run(job_id).state is JobState.SCRIPT_APPROVAL_REQUIRED
        saved_package = runtime.artifacts.get(job_id, JobState.CONTENT_GENERATING, "content_package")
        assert saved_package is not None
        runtime.approvals.record(f"{job_id}-script", job_id, ApprovalGate.SCRIPT, actor="isolated-fixture-test", reviewed_identity=saved_package.checksum_sha256)
        preview = runtime.orchestrator.run(job_id)
        assert preview.state is JobState.PREVIEW_READY, preview.failure_message
        preview_manifest = runtime.artifacts.get(job_id, JobState.PREVIEW_RENDERING, "preview_manifest")
        assert preview_manifest is not None
        preview_manifest_data = json.loads(Path(preview_manifest.path).read_text())
        preview_identity = preview_manifest_data["render_identity"]
        segments, *_ = runtime.orchestrator._render_inputs(preview, runtime.orchestrator._preview_renderer_for(preview))
        assert len(segments) == len(scenes) == 6
        assert all(segment.animation is not None for segment in segments)
        for segment in segments:
            animation = segment.animation
            if isinstance(animation, AnimatedCardScene):
                resolve_card_cues(animation, segment.animation_words)
            elif isinstance(animation, AnimatedTeachingScene):
                resolve_teaching_cues(animation, segment.animation_words)
            elif isinstance(animation, AnimatedTerminalScene):
                resolve_cues(animation, segment.animation_words)
            else:
                pytest.fail(f"{segment.scene_id} lacks a supported teaching animation")
        runtime.approvals.record(f"{job_id}-preview", job_id, ApprovalGate.PREVIEW, actor="isolated-fixture-test", reviewed_identity=preview_identity)
        if music_fixture:
            # Final rendering must resume from durable approval and catalog
            # records; the new runtime cannot depend on in-memory track state.
            runtime.database.dispose()
            runtime = create_runtime(settings)
            assert runtime.orchestrator.music_catalog is not None
            assert runtime.orchestrator.music_catalog.resolve(music_fixture["name"]).checksum_sha256 == music_fixture["sha256"]
        final_job = runtime.orchestrator.run(job_id)
        if final_job.state is not JobState.FINAL_READY:
            diagnostics = OUTPUT_ROOT / topic
            diagnostics.mkdir(parents=True, exist_ok=True)
            quality_artifact = runtime.artifacts.get(job_id, JobState.FINAL_READY, "quality_report")
            if quality_artifact is not None:
                shutil.copyfile(quality_artifact.path, diagnostics / "failed-quality.json")
                findings = json.loads(Path(quality_artifact.path).read_text()).get("findings", [])
            else:
                findings = []
            pytest.fail(f"{final_job.failure_message}: {findings}")

        out = OUTPUT_ROOT / topic
        out.mkdir(parents=True, exist_ok=True)
        final_manifest_artifact = runtime.artifacts.get(job_id, JobState.FINAL_RENDERING, "final_manifest")
        assert final_manifest_artifact is not None
        final_manifest_data = json.loads(Path(final_manifest_artifact.path).read_text())
        assert final_manifest_data["approval_identity"] == preview_identity
        assert final_manifest_data["inputs"] == preview_manifest_data["inputs"]
        assert final_manifest_data["probe"]["sample_rate"] == 48_000
        if music_fixture:
            for manifest in (preview_manifest_data, final_manifest_data):
                assert manifest["inputs"]["music"]["checksum_sha256"] == music_fixture["sha256"]
                assert manifest["inputs"]["music"]["license_url"] == music_fixture["license_url"]
                assert manifest["inputs"]["audio_mix_version"] == manifest["probe"]["audio_loudness"]["version"]
        records = {
            "preview": (JobState.PREVIEW_RENDERING, "preview", "preview.mp4"),
            "preview_manifest": (JobState.PREVIEW_RENDERING, "preview_manifest", "preview-manifest.json"),
            "final": (JobState.FINAL_RENDERING, "final", "final.mp4"),
            "final_manifest": (JobState.FINAL_RENDERING, "final_manifest", "final-manifest.json"),
            "narration": (JobState.VOICE_GENERATION, "narration", "narration.wav"),
            "timing": (JobState.VOICE_GENERATION, "timing_map", "timing.json"),
            "quality": (JobState.FINAL_READY, "quality_report", "quality.json"),
            "storyboard": (JobState.ASSET_ACQUISITION, "storyboard_manifest", "storyboard.json"),
            "captions": (JobState.CAPTION_GENERATION, "captions", "captions.ass"),
        }
        for state, name, filename in records.values():
            artifact = runtime.artifacts.get(job_id, state, name)
            assert artifact is not None
            shutil.copyfile(artifact.path, out / filename)
        quality = json.loads((out / "quality.json").read_text())
        timing = json.loads((out / "timing.json").read_text())
        if NORMALIZE_AUDIO:
            for manifest in (preview_manifest_data, final_manifest_data):
                loudness = manifest["probe"]["audio_loudness"]
                assert -15 <= loudness["encoded"]["input_i"] <= -13
                assert loudness["encoded"]["input_tp"] <= -1
        assert quality["passed"] and timing["alignment"]["verified"]
        assert timing["duration_policy"] == "shorts_30_to_120"
        assert 30 <= timing["final_duration_seconds"] <= 120
        assert subprocess.run(["ffmpeg", "-v", "error", "-i", str(out / "final.mp4"), "-f", "null", "-"], capture_output=True, timeout=300).returncode == 0
        (out / "fixture_evidence.json").write_text(json.dumps({
            "original_package_sha256": hashlib.sha256(original_bytes).hexdigest(),
            "rendered_package_sha256": saved_package.checksum_sha256,
            "source_packet_sha256": hashlib.sha256(packet_bytes).hexdigest(),
            "preview_identity": preview_identity,
            "final_approval_identity": final_manifest_data["approval_identity"],
            "animated_scene_ids": [segment.scene_id for segment in segments],
            "final_sha256": hashlib.sha256((out / "final.mp4").read_bytes()).hexdigest(),
            "duration_seconds": timing["final_duration_seconds"],
            "quality_passed": quality["passed"],
            "music_source_sha256": music_fixture["sha256"] if music_fixture else None,
        }, indent=2) + "\n")
    finally:
        runtime.database.dispose()
