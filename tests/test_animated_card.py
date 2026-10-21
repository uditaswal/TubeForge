"""Hook/close motion is source-bound data, resolved only after alignment."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from tubeforge.core.config import ShortsFinalRenderConfig
from tubeforge.domain.contracts import CardMotionKind, ContentPackage, ScenePlan
from tubeforge.pipeline.alignment import WordTiming
from tubeforge.pipeline.captions import render_highlighted_ass
from tubeforge.pipeline.scene_contracts import ScriptBoundSceneContract, compile_scene_contract
from tubeforge.rendering.animated_card import AnimatedCardScene, resolve_card_cues
from tubeforge.rendering.preview import PreviewRenderer, TimelineSegment, build_timeline


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/production/git_stage_commit"
MEDIA = ROOT / "data/artifacts/stage22_fixture_smoke/git_stage_commit"


def _scene() -> AnimatedCardScene:
    return AnimatedCardScene(
        scene_id="scene-01", section_id="section-01", kind=CardMotionKind.HOOK, heading="TWO FILES. ONE COMMIT.",
        elements=("app.py changed", "notes.txt changed", "Choose app.py only"), source_ids=(),
        scene_start_seconds=0, duration_seconds=6, first_word_index=0,
        second_word_index=1, third_word_index=2, step_number=1, step_count=6,
    )


def test_card_cues_follow_local_spoken_word_indices() -> None:
    words = tuple(WordTiming(word, "phrase", "section-01", i, start, start+0.2)
                  for i, (word, start) in enumerate((("two", 1.2), ("files", 2.0), ("choose", 2.4))))
    assert resolve_card_cues(_scene(), words) == pytest.approx((1.2, 2.0, 2.4))
    with pytest.raises(ValueError, match="indices"):
        resolve_card_cues(replace(_scene(), third_word_index=9), words)
    with pytest.raises(ValueError, match="anchors"):
        resolve_card_cues(replace(_scene(), duration_seconds=2.3), words)


@pytest.mark.parametrize("caption_type", ["vtt", "ass"])
def test_landscape_card_renders_on_native_canvas(tmp_path: Path, caption_type: str) -> None:
    from tubeforge.rendering.animated_card import prepare_card_visual_command
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg required")
    words = tuple(WordTiming(word, "phrase", "section-01", i, start, start + .2)
                  for i, (word, start) in enumerate((("two", .1), ("files", .5), ("choose", .9))))
    output = tmp_path / "wide.mp4"
    command = prepare_card_visual_command(
        replace(_scene(), duration_seconds=1.5), words, output, tmp_path / "text",
        ffmpeg="ffmpeg", threads=1, crf=30, width=640, height=360, fps=30,
    )
    assert any("s=1920x1080" in part for part in command)
    subprocess.run(command, check=True, capture_output=True, timeout=60)
    probe = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_streams", "-of", "json", str(output),
    ]))
    assert (probe["streams"][0]["width"], probe["streams"][0]["height"]) == (640, 360)
    # Exercise the full render path, including the rounded 854x480 default
    # profile and final audio/caption composition, not only its scene helper.
    from tubeforge.core.config import PreviewRenderConfig
    audio = tmp_path / "speech.wav"
    subprocess.run([
        "ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i",
        "sine=frequency=440:sample_rate=48000:duration=1.5", str(audio),
    ], check=True, capture_output=True)
    captions = tmp_path / f"captions.{caption_type}"
    captions.write_text(
        render_highlighted_ass(words, width=1920, height=1080, font_size=64,
                               margin_vertical=65, margin_horizontal=100, center_x=960)
        if caption_type == "ass" else "WEBVTT\n\n00:00.000 --> 00:01.500\nLocal render test.\n"
    )
    scene = replace(_scene(), duration_seconds=1.5)
    segment = TimelineSegment(scene.scene_id, scene.section_id, 0, 1.5, output,
                              hashlib.sha256(output.read_bytes()).hexdigest(), "video", scene, words)
    renderer = PreviewRenderer(PreviewRenderConfig(minimum_free_bytes=1))
    result = renderer.render((segment,), audio, captions, tmp_path / "preview.mp4")
    assert result["render_strategy"] == "bounded-segments"
    assert (tmp_path / "preview.mp4").is_file()
    if caption_type == "ass":
        assert "force_style=''" in result["command"][result["command"].index("-filter_complex") + 1]


def _captured_timeline(tmp_path: Path) -> tuple[tuple[TimelineSegment, ...], str, str]:
    original_bytes = (FIXTURE / "content_package.json").read_bytes()
    packet_bytes = (FIXTURE / "source_packet.json").read_bytes()
    original_contract = ScriptBoundSceneContract.model_validate_json((FIXTURE / "scene_contract.json").read_bytes())
    original = original_contract.validate_against(original_bytes, packet_bytes, accepted_script_identity=original_contract.package_sha256)
    rows = {row.scene_id: row for row in original_contract.scenes}
    overlays = json.loads((FIXTURE / "card_motion_overlay.json").read_text())
    plans = []
    for plan in original.scene_plans:
        row = rows[plan.scene_id]
        overlay = overlays.get(plan.scene_id, {})
        plans.append(ScenePlan.model_validate({
            **plan.model_dump(mode="json"), "visual_type": row.layout.value,
            "on_screen_text": row.command or overlay.get("heading", row.heading),
            "visual_subject": overlay.get("heading", row.heading),
            "visual_elements": overlay.get("display_elements", row.display_elements),
            **({"card_cues": overlay["card_cues"]} if overlay else {}),
        }))
    package = ContentPackage.model_validate({**original.model_dump(mode="json"),
                                            "scene_plans": [plan.model_dump(mode="json") for plan in plans]})
    package_bytes = package.model_dump_json().encode()
    accepted_identity = hashlib.sha256(package_bytes).hexdigest()
    contract = compile_scene_contract(package_bytes, packet_bytes, accepted_script_identity=accepted_identity)
    assert contract is not None
    still = tmp_path / "asset.png"
    still.write_bytes(b"test asset")
    digest = hashlib.sha256(still.read_bytes()).hexdigest()
    assets = {row.scene_id: {
        "path": str(still), "checksum_sha256": digest,
        "validation": {"media_type": "image", "checksum_sha256": digest},
        "candidate": {"license_name": "isolated-fixture-test", "editorial_only": False,
                      "review_required": False, "attribution_required": False},
    } for row in contract.scenes}
    timeline = build_timeline(package, json.loads((MEDIA / "timing.json").read_text()), assets,
                              tolerance=0.25, scene_contract=contract)
    return timeline, accepted_identity, hashlib.sha256(contract.model_dump_json().encode()).hexdigest()


@pytest.mark.skipif(
    os.environ.get("TUBEFORGE_ANIMATED_SCENE_SMOKE") != "1" or shutil.which("ffmpeg") is None,
    reason="opt in with TUBEFORGE_ANIMATED_SCENE_SMOKE=1 and captured local media",
)
@pytest.mark.parametrize("scene_id,name", [("scene-01", "hook"), ("scene-06", "close")])
def test_bounded_hook_and_close_render_from_approved_data(tmp_path: Path, scene_id: str, name: str) -> None:
    timeline, accepted_identity, contract_digest = _captured_timeline(tmp_path)
    selected = next(segment for segment in timeline if segment.scene_id == scene_id)
    assert isinstance(selected.animation, AnimatedCardScene)
    animation = replace(selected.animation, scene_start_seconds=0)
    words = tuple(replace(word, start_seconds=word.start_seconds-selected.start_seconds,
                          end_seconds=word.end_seconds-selected.start_seconds)
                  for word in selected.animation_words if word.section_id == selected.section_id)
    local = TimelineSegment(selected.scene_id, selected.section_id, 0, selected.duration_seconds,
                            selected.asset_path, selected.asset_checksum, "image", animation, words)
    narration = tmp_path / "narration.wav"
    assert subprocess.run([
        "ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", str(selected.start_seconds),
        "-t", str(selected.duration_seconds), "-i", str(MEDIA / "narration.wav"), str(narration),
    ], capture_output=True, timeout=60).returncode == 0
    captions = tmp_path / "captions.ass"
    captions.write_text(render_highlighted_ass(words, width=1080, height=1920, font_size=80,
                                               margin_vertical=360, margin_horizontal=96))
    renderer = PreviewRenderer(ShortsFinalRenderConfig(minimum_free_bytes=1, timeout_seconds=180, threads=2))
    output = tmp_path / f"{name}.mp4"
    identity = renderer.identity((local,), narration, captions, approval_identity=accepted_identity)
    result = renderer.render((local,), narration, captions, output)
    assert result["render_strategy"] == "bounded-segments"
    assert result["metadata"]["width"] == 1080 and result["metadata"]["height"] == 1920
    assert subprocess.run(["ffmpeg", "-v", "error", "-i", str(output), "-f", "null", "-"],
                          capture_output=True, timeout=60).returncode == 0
    retained = ROOT / "data/artifacts/stage22_card_proof"
    retained.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(output, retained / f"{name}.mp4")
    (retained / f"{name}-manifest.json").write_text(json.dumps({
        "accepted_test_package_sha256": accepted_identity,
        "scene_contract_sha256": contract_digest,
        "render_identity": identity,
        "output_sha256": result["checksum_sha256"],
        "cue_seconds": resolve_card_cues(animation, words),
        "render_strategy": result["render_strategy"],
        "metadata": result["metadata"],
    }, indent=2) + "\n")
