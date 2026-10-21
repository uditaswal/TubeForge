"""Focused checks for declarative, alignment-driven terminal scenes."""

from __future__ import annotations

import json
import hashlib
import os
import shutil
import subprocess
from pathlib import Path
from dataclasses import replace

import pytest

from tubeforge.pipeline.alignment import WordTiming
from tubeforge.pipeline.captions import render_highlighted_ass
from tubeforge.pipeline.scene_contracts import ScriptBoundSceneContract
from tubeforge.pipeline.scene_contracts import compile_scene_contract
from tubeforge.core.config import ShortsFinalRenderConfig
from tubeforge.domain.contracts import ContentPackage, ScenePlan
from tubeforge.rendering.animated_terminal import AnimatedTerminalScene, _display_command, render_animated_terminal, resolve_cues
from tubeforge.rendering.preview import PreviewRenderCancelled, PreviewRenderer, TimelineSegment, build_timeline, maximum_static_hold, pace_segments


ROOT = Path(__file__).resolve().parents[1]


def _scene(**changes: object) -> AnimatedTerminalScene:
    data = {
        "scene_id": "scene-03", "heading": "STAGE APP.PY", "command": "git add app.py",
        "output_label": "EXPLAINED STAGING STATE", "output_line": "app.py → index",
        "secondary_line": "notes.txt stays outside", "source_ids": ("git-add",),
        "section_id": "section-03", "scene_start_seconds": 12.0, "duration_seconds": 10.0,
        "command_start_word_index": 1, "command_end_word_index": 2,
        "output_word_index": 3, "secondary_word_index": 4,
        "step_number": 2, "step_count": 5,
    }
    data.update(changes)
    return AnimatedTerminalScene(**data)


def _words() -> tuple[WordTiming, ...]:
    return tuple(
        WordTiming(word, "phrase-1", "section-03", index, start, start + 0.4)
        for index, (word, start) in enumerate((
            ("Now", 12.1), ("git", 12.8), ("add", 13.2),
            ("index", 18.0), ("notes", 20.0),
        ))
    )


def test_reveal_cues_resolve_against_spoken_word_indices() -> None:
    assert resolve_cues(_scene(), _words()) == {
        "type_start": pytest.approx(0.8),
        "type_end": pytest.approx(1.6),
        "output_start": pytest.approx(6.0),
        "secondary_start": pytest.approx(8.0),
    }


def test_long_command_wraps_without_truncating_or_executing_it() -> None:
    command = "docker run --name web-a -d nginx:alpine"
    display = _display_command(command)
    assert display.replace("\n", " ") == command
    assert max(map(len, display.splitlines())) <= 26


@pytest.mark.parametrize("changes", [
    {"command_end_word_index": 3},
    {"secondary_word_index": 9},
    {"duration_seconds": 7.0},
])
def test_stale_or_ambiguous_reveal_cues_fail_closed(changes: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="anchors|indices"):
        resolve_cues(_scene(**changes), _words())


def test_speech_anchored_scene_does_not_count_as_a_static_hold() -> None:
    animated = TimelineSegment("scene-03", "section-03", 0, 10, Path("unused.png"), "a" * 64, "image", _scene(scene_start_seconds=0), _words())
    still = TimelineSegment("scene-04", "section-04", 10, 16, Path("unused.png"), "b" * 64, "image")
    assert len(pace_segments((animated, still), 3)) == 3
    assert maximum_static_hold((animated, still), 3) == 3


def test_animated_render_cancellation_removes_partial_and_textfiles(tmp_path: Path) -> None:
    class RunningProcess:
        returncode = None

        def __init__(self, command: list[str], **_: object) -> None:
            Path(command[-1]).write_bytes(b"partial")

        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            self.returncode = -15

        def wait(self, timeout: float | None = None) -> int:
            return -15

    narration = tmp_path / "narration.wav"
    captions = tmp_path / "captions.vtt"
    narration.write_bytes(b"test audio")
    captions.write_text("WEBVTT\n\n")
    asset = tmp_path / "still.png"
    asset.write_bytes(b"test asset")
    local_words = tuple(replace(word, start_seconds=word.start_seconds-12,
                                end_seconds=word.end_seconds-12) for word in _words())
    segment = TimelineSegment("scene-03", "section-03", 0, 10, asset, "a" * 64,
                              "image", _scene(scene_start_seconds=0), local_words)
    renderer = PreviewRenderer(
        ShortsFinalRenderConfig(minimum_free_bytes=1), process_factory=RunningProcess, poll_seconds=0,
    )
    checks = iter((False, False, False, True))
    with pytest.raises(PreviewRenderCancelled, match="cancelled during FFmpeg"):
        renderer.render((segment,), narration, captions, tmp_path / "final.mp4",
                        cancellation_requested=lambda: next(checks))
    assert not (tmp_path / "final.mp4").exists()
    assert not (tmp_path / "final.part.mp4").exists()
    assert not list(tmp_path.glob("final.part.segments-*"))


@pytest.mark.skipif(
    os.environ.get("TUBEFORGE_ANIMATED_SCENE_SMOKE") != "1" or shutil.which("ffmpeg") is None,
    reason="opt in with TUBEFORGE_ANIMATED_SCENE_SMOKE=1 and captured local media",
)
def test_captured_git_scene_renders_from_bound_contract(tmp_path: Path) -> None:
    fixture = ROOT / "tests/fixtures/production/git_stage_commit"
    media = ROOT / "data/artifacts/stage22_fixture_smoke/git_stage_commit"
    cue_data = json.loads((fixture / "animation_cues.json").read_text())["scene-03"]
    contract = ScriptBoundSceneContract.model_validate_json((fixture / "scene_contract.json").read_bytes())
    contract.validate_against(
        (fixture / "content_package.json").read_bytes(),
        (fixture / "source_packet.json").read_bytes(),
        accepted_script_identity=contract.package_sha256,
    )
    row = next(item for item in contract.scenes if item.scene_id == "scene-03")
    timing = json.loads((media / "timing.json").read_text())
    words = tuple(WordTiming(**item) for item in timing["words"])
    section_phrases = [item for item in timing["phrases"] if item["section_id"] == "section-03"]
    scene_start = section_phrases[0]["start_seconds"]
    scene_duration = section_phrases[-1]["end_seconds"] - scene_start
    scene = _scene(
        scene_id=row.scene_id,
        heading=row.heading,
        command=row.command,
        output_line=row.display_elements[0],
        secondary_line=row.display_elements[1],
        source_ids=tuple(row.source_ids),
        scene_start_seconds=scene_start,
        duration_seconds=scene_duration,
        **cue_data,
    )
    output = tmp_path / "scene.mp4"
    evidence = render_animated_terminal(scene, words, media / "narration.wav", media / "captions.ass", output)
    assert output.stat().st_size > 100_000
    assert evidence["source_ids"] == ["git-add"]
    section_words = [word for word in words if word.section_id == "section-03"]
    assert evidence["cues"]["output_start"] == pytest.approx(section_words[cue_data["output_word_index"]].start_seconds-scene_start)
    assert evidence["cues"]["secondary_start"] == pytest.approx(section_words[cue_data["secondary_word_index"]].start_seconds-scene_start)
    assert subprocess.run(["ffmpeg", "-v", "error", "-i", str(output), "-f", "null", "-"], capture_output=True, timeout=60).returncode == 0


@pytest.mark.skipif(
    os.environ.get("TUBEFORGE_ANIMATED_SCENE_SMOKE") != "1" or shutil.which("ffmpeg") is None,
    reason="opt in with TUBEFORGE_ANIMATED_SCENE_SMOKE=1 and captured local media",
)
def test_terminal_cues_use_bounded_approved_render_path(tmp_path: Path) -> None:
    fixture = ROOT / "tests/fixtures/production/git_stage_commit"
    media = ROOT / "data/artifacts/stage22_fixture_smoke/git_stage_commit"
    cue_data = json.loads((fixture / "animation_cues.json").read_text())["scene-03"]
    original = ContentPackage.model_validate_json((fixture / "content_package.json").read_bytes())
    fixture_contract = ScriptBoundSceneContract.model_validate_json((fixture / "scene_contract.json").read_bytes())
    rows = {row.scene_id: row for row in fixture_contract.scenes}
    plans = []
    for plan in original.scene_plans:
        row = rows[plan.scene_id]
        data = {**plan.model_dump(mode="json"), "visual_type": row.layout.value,
                "visual_subject": row.heading, "on_screen_text": row.command or row.heading,
                "visual_elements": row.display_elements}
        if plan.scene_id == "scene-03":
            data["terminal_cues"] = cue_data
        plans.append(ScenePlan.model_validate(data))
    package = ContentPackage.model_validate({**original.model_dump(mode="json"), "scene_plans": [plan.model_dump(mode="json") for plan in plans]})
    package_bytes = package.model_dump_json().encode()
    packet_bytes = (fixture / "source_packet.json").read_bytes()
    accepted_identity = hashlib.sha256(package_bytes).hexdigest()
    contract = compile_scene_contract(package_bytes, packet_bytes, accepted_script_identity=accepted_identity)
    assert contract is not None and contract.scenes[2].terminal_cues is not None
    still = tmp_path / "accepted-still.png"
    still.write_bytes(b"nonempty test placeholder")
    still_hash = hashlib.sha256(still.read_bytes()).hexdigest()
    assets = {row.scene_id: {
        "path": str(still), "checksum_sha256": still_hash,
        "validation": {"media_type": "image", "checksum_sha256": still_hash},
        "candidate": {"license_name": "isolated-fixture-test", "editorial_only": False,
                      "review_required": False, "attribution_required": False},
    } for row in contract.scenes}
    timing = json.loads((media / "timing.json").read_text())
    timeline = build_timeline(package, timing, assets, tolerance=0.25, scene_contract=contract)
    animated = next(segment for segment in timeline if segment.scene_id == "scene-03")
    assert animated.animation is not None
    assert len([segment for segment in pace_segments(timeline, 3.0) if segment.scene_id == "scene-03"]) == 1

    scene = replace(animated.animation, scene_start_seconds=0)
    words = tuple(replace(word, start_seconds=word.start_seconds-animated.start_seconds,
                          end_seconds=word.end_seconds-animated.start_seconds)
                  for word in animated.animation_words if word.section_id == "section-03")
    local = TimelineSegment(animated.scene_id, animated.section_id, 0, animated.duration_seconds,
                            still, still_hash, "image", scene, words)
    narration = tmp_path / "narration.wav"
    assert subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", str(animated.start_seconds),
                           "-t", str(animated.duration_seconds), "-i", str(media / "narration.wav"),
                           str(narration)], capture_output=True, timeout=60).returncode == 0
    captions = tmp_path / "captions.vtt"
    captions.write_text("WEBVTT\n\n", encoding="utf-8")
    renderer = PreviewRenderer(ShortsFinalRenderConfig(minimum_free_bytes=1, timeout_seconds=180))
    identity = renderer.identity((local,), narration, captions, approval_identity=accepted_identity)
    assert identity != renderer.identity((replace(local, animation=None, animation_words=()),), narration, captions, approval_identity=accepted_identity)
    result = renderer.render((local,), narration, captions, tmp_path / "integrated.mp4")
    assert result["render_strategy"] == "bounded-segments"
    assert result["metadata"]["width"] == 1080 and result["metadata"]["height"] == 1920
    retained = ROOT / "data/artifacts/stage22_animated_scene_proof"
    retained.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(tmp_path / "integrated.mp4", retained / "integrated.mp4")
    (retained / "integrated-manifest.json").write_text(json.dumps({
        "accepted_test_package_sha256": accepted_identity,
        "scene_contract_sha256": hashlib.sha256(contract.model_dump_json().encode()).hexdigest(),
        "render_identity": identity,
        "output_sha256": result["checksum_sha256"],
        "render_strategy": result["render_strategy"],
        "metadata": result["metadata"],
    }, indent=2) + "\n")


@pytest.mark.skipif(
    os.environ.get("TUBEFORGE_ANIMATED_SCENE_SMOKE") != "1" or shutil.which("ffmpeg") is None,
    reason="opt in with TUBEFORGE_ANIMATED_SCENE_SMOKE=1 and captured local media",
)
@pytest.mark.parametrize("scene_id,label", [
    ("scene-3", "run-web-a"), ("scene-4", "run-web-b"), ("scene-5", "docker-ps"),
])
def test_docker_terminal_commands_render_from_source_bound_data(tmp_path: Path, scene_id: str, label: str) -> None:
    fixture = ROOT / "tests/fixtures/production/docker_images_containers"
    media = ROOT / "data/artifacts/stage22_fixture_smoke/docker_images_containers"
    original_bytes = (fixture / "content_package.json").read_bytes()
    packet_bytes = (fixture / "source_packet.json").read_bytes()
    original_contract = ScriptBoundSceneContract.model_validate_json((fixture / "scene_contract.json").read_bytes())
    original = original_contract.validate_against(original_bytes, packet_bytes, accepted_script_identity=original_contract.package_sha256)
    rows = {row.scene_id: row for row in original_contract.scenes}
    overlays = json.loads((fixture / "terminal_motion_overlay.json").read_text())
    plans = []
    for plan in original.scene_plans:
        row = rows[plan.scene_id]
        overlay = overlays.get(plan.scene_id, {})
        plans.append(ScenePlan.model_validate({
            **plan.model_dump(mode="json"), "visual_type": row.layout.value,
            "on_screen_text": row.command or row.heading,
            "visual_subject": row.heading,
            "visual_elements": overlay.get("display_elements", row.display_elements),
            **({"terminal_cues": overlay["terminal_cues"]} if overlay else {}),
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
    timing = json.loads((media / "timing.json").read_text())
    timeline = build_timeline(package, timing, assets, tolerance=0.25, scene_contract=contract)
    selected = next(segment for segment in timeline if segment.scene_id == scene_id)
    assert isinstance(selected.animation, AnimatedTerminalScene)
    animation = replace(selected.animation, scene_start_seconds=0)
    words = tuple(replace(word, start_seconds=word.start_seconds-selected.start_seconds,
                          end_seconds=word.end_seconds-selected.start_seconds)
                  for word in selected.animation_words if word.section_id == selected.section_id)
    local = TimelineSegment(selected.scene_id, selected.section_id, 0, selected.duration_seconds,
                            still, digest, "image", animation, words)
    narration = tmp_path / "narration.wav"
    assert subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", str(selected.start_seconds),
                           "-t", str(selected.duration_seconds), "-i", str(media / "narration.wav"),
                           str(narration)], capture_output=True, timeout=60).returncode == 0
    captions = tmp_path / "captions.ass"
    captions.write_text(render_highlighted_ass(words, width=1080, height=1920, font_size=80,
                                               margin_vertical=360, margin_horizontal=96))
    renderer = PreviewRenderer(ShortsFinalRenderConfig(minimum_free_bytes=1, timeout_seconds=180, threads=2))
    identity = renderer.identity((local,), narration, captions, approval_identity=accepted_identity)
    output = tmp_path / f"{label}.mp4"
    result = renderer.render((local,), narration, captions, output)
    assert result["render_strategy"] == "bounded-segments"
    assert subprocess.run(["ffmpeg", "-v", "error", "-i", str(output), "-f", "null", "-"],
                          capture_output=True, timeout=60).returncode == 0
    retained = ROOT / "data/artifacts/stage22_teaching_proof"
    retained.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(output, retained / f"docker-{label}.mp4")
    (retained / f"docker-{label}-manifest.json").write_text(json.dumps({
        "accepted_test_package_sha256": accepted_identity,
        "scene_contract_sha256": hashlib.sha256(contract.model_dump_json().encode()).hexdigest(),
        "render_identity": identity,
        "output_sha256": result["checksum_sha256"],
        "cue_seconds": resolve_cues(animation, words),
        "metadata": result["metadata"],
    }, indent=2) + "\n")
