"""Real-media checks for declarative flow, comparison, timeline and source scenes."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError

from tubeforge.core.config import ShortsFinalRenderConfig
from tubeforge.domain.contracts import ContentPackage, ScenePlan
from tubeforge.pipeline.alignment import WordTiming
from tubeforge.pipeline.captions import render_highlighted_ass
from tubeforge.pipeline.scene_contracts import ScriptBoundSceneContract, compile_scene_contract
from tubeforge.rendering.animated_teaching import AnimatedTeachingScene, resolve_teaching_cues
from tubeforge.rendering.preview import PreviewRenderCancelled, PreviewRenderer, TimelineSegment, build_timeline


ROOT = Path(__file__).resolve().parents[1]


def test_teaching_cues_fail_closed_on_stale_or_unresolved_alignment() -> None:
    from tubeforge.pipeline.scene_contracts import SceneLayout

    scene = AnimatedTeachingScene(
        scene_id="scene", section_id="section", layout=SceneLayout.FLOW_DIAGRAM,
        heading="ONE IMAGE TWO CONTAINERS", elements=("image", "first", "second"),
        source_ids=("docker-image",), scene_start_seconds=0, duration_seconds=6,
        first_word_index=0, second_word_index=1, third_word_index=2,
        step_number=1, step_count=6,
    )
    words = tuple(WordTiming(str(index), "phrase", "section", index, start, start+0.2)
                  for index, start in enumerate((0.5, 2.0, 3.0)))
    assert resolve_teaching_cues(scene, words) == pytest.approx((0.5, 2.0, 3.0))
    with pytest.raises(ValueError, match="indices"):
        resolve_teaching_cues(replace(scene, third_word_index=5), words)
    with pytest.raises(ValueError, match="anchors"):
        resolve_teaching_cues(replace(scene, duration_seconds=2.5), words)


def test_comparison_reveal_order_is_source_bound_and_changes_render_identity(tmp_path: Path) -> None:
    from tubeforge.pipeline.scene_contracts import SceneLayout

    cue = {"first_word_index": 0, "second_word_index": 1,
           "third_word_index": 2, "comparison_panels_first": True}
    base = {"scene_id": "scene", "search_queries": ("example",),
            "fallback_visual": "text_card", "visual_elements": ("image", "container", "consequence"),
            "teaching_cues": cue}
    with pytest.raises(ValidationError, match="comparison scene"):
        ScenePlan.model_validate({**base, "visual_type": "flow_diagram"})
    assert ScenePlan.model_validate({**base, "visual_type": "comparison"}).teaching_cues.comparison_panels_first

    scene = AnimatedTeachingScene(
        scene_id="scene", section_id="section", layout=SceneLayout.COMPARISON,
        heading="IMAGE AND CONTAINER", elements=("image", "container", "consequence"),
        source_ids=("docker-image",), scene_start_seconds=0, duration_seconds=6,
        first_word_index=0, second_word_index=1, third_word_index=2,
        step_number=1, step_count=6,
    )
    words = tuple(WordTiming(str(index), "phrase", "section", index, start, start+0.2)
                  for index, start in enumerate((0.5, 2.0, 3.0)))
    asset = tmp_path / "asset.png"
    narration = tmp_path / "narration.wav"
    captions = tmp_path / "captions.ass"
    for path in (asset, narration, captions):
        path.write_bytes(b"test input")
    normal = TimelineSegment("scene", "section", 0, 6, asset, "a" * 64,
                             "image", scene, words)
    panels_first = replace(normal, animation=replace(scene, comparison_panels_first=True))
    renderer = PreviewRenderer(ShortsFinalRenderConfig(minimum_free_bytes=1))
    assert "comparison_panels_first" not in renderer._animation_data(normal)
    assert renderer.identity((normal,), narration, captions) != renderer.identity(
        (panels_first,), narration, captions,
    )


def test_teaching_render_cancellation_cleans_partial_output(tmp_path: Path) -> None:
    from tubeforge.pipeline.scene_contracts import SceneLayout

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

    animation = AnimatedTeachingScene(
        scene_id="scene", section_id="section", layout=SceneLayout.FLOW_DIAGRAM,
        heading="ONE IMAGE TWO CONTAINERS", elements=("image", "first", "second"),
        source_ids=("docker-image",), scene_start_seconds=0, duration_seconds=6,
        first_word_index=0, second_word_index=1, third_word_index=2,
        step_number=1, step_count=6,
    )
    words = tuple(WordTiming(str(index), "phrase", "section", index, start, start+0.2)
                  for index, start in enumerate((0.5, 2.0, 3.0)))
    narration = tmp_path / "narration.wav"
    captions = tmp_path / "captions.vtt"
    asset = tmp_path / "asset.png"
    narration.write_bytes(b"test audio")
    captions.write_text("WEBVTT\n\n")
    asset.write_bytes(b"test asset")
    segment = TimelineSegment("scene", "section", 0, 6, asset, "a" * 64,
                              "image", animation, words)
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


def _timeline(tmp_path: Path, topic: str, *, timeline_proof: bool = False) -> tuple[tuple[TimelineSegment, ...], str, str]:
    fixture = ROOT / "tests/fixtures/production" / topic
    original_bytes = (fixture / "content_package.json").read_bytes()
    packet_bytes = (fixture / "source_packet.json").read_bytes()
    original_contract = ScriptBoundSceneContract.model_validate_json((fixture / "scene_contract.json").read_bytes())
    original = original_contract.validate_against(original_bytes, packet_bytes, accepted_script_identity=original_contract.package_sha256)
    rows = {row.scene_id: row for row in original_contract.scenes}
    card_file = fixture / "card_motion_overlay.json"
    card_overlays = json.loads(card_file.read_text()) if card_file.is_file() and not timeline_proof else {}
    teaching_overlays = json.loads((fixture / "teaching_motion_overlay.json").read_text())
    if timeline_proof:
        teaching_overlays.update(json.loads((fixture / "timeline_proof_overlay.json").read_text()))
    plans = []
    for plan in original.scene_plans:
        row = rows[plan.scene_id]
        card = card_overlays.get(plan.scene_id, {})
        teaching = teaching_overlays.get(plan.scene_id, {})
        plans.append(ScenePlan.model_validate({
            **plan.model_dump(mode="json"), "visual_type": row.layout.value,
            "on_screen_text": row.command or card.get("heading", row.heading),
            "visual_subject": card.get("heading", row.heading),
            "visual_elements": card.get("display_elements", teaching.get("display_elements", row.display_elements)),
            **({"card_cues": card["card_cues"]} if card else {}),
            **({"teaching_cues": teaching["teaching_cues"]} if teaching else {}),
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
    timing = json.loads((ROOT / "data/artifacts/stage22_fixture_smoke" / topic / "timing.json").read_text())
    output = build_timeline(package, timing, assets, tolerance=0.25, scene_contract=contract)
    return output, accepted_identity, hashlib.sha256(contract.model_dump_json().encode()).hexdigest()


@pytest.mark.skipif(
    os.environ.get("TUBEFORGE_ANIMATED_SCENE_SMOKE") != "1" or shutil.which("ffmpeg") is None,
    reason="opt in with TUBEFORGE_ANIMATED_SCENE_SMOKE=1 and captured local media",
)
@pytest.mark.parametrize("topic,scene_id,label,timeline_proof", [
    ("docker_images_containers", "scene-1", "flow", False),
    ("docker_images_containers", "scene-2", "comparison", False),
    ("docker_images_containers", "scene-6", "consequence", False),
    ("git_stage_commit", "scene-02", "source", False),
    ("git_stage_commit", "scene-06", "timeline", True),
])
def test_bounded_teaching_scene_from_source_bound_data(
    tmp_path: Path, topic: str, scene_id: str, label: str, timeline_proof: bool,
) -> None:
    timeline, accepted_identity, contract_digest = _timeline(tmp_path, topic, timeline_proof=timeline_proof)
    selected = next(segment for segment in timeline if segment.scene_id == scene_id)
    assert isinstance(selected.animation, AnimatedTeachingScene)
    if label == "consequence":
        assert selected.animation.comparison_panels_first
    animation = replace(selected.animation, scene_start_seconds=0)
    words = tuple(replace(word, start_seconds=word.start_seconds-selected.start_seconds,
                          end_seconds=word.end_seconds-selected.start_seconds)
                  for word in selected.animation_words if word.section_id == selected.section_id)
    local = TimelineSegment(selected.scene_id, selected.section_id, 0, selected.duration_seconds,
                            selected.asset_path, selected.asset_checksum, "image", animation, words)
    media = ROOT / "data/artifacts/stage22_fixture_smoke" / topic
    narration = tmp_path / "narration.wav"
    assert subprocess.run([
        "ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", str(selected.start_seconds),
        "-t", str(selected.duration_seconds), "-i", str(media / "narration.wav"), str(narration),
    ], capture_output=True, timeout=60).returncode == 0
    captions = tmp_path / "captions.ass"
    captions.write_text(render_highlighted_ass(words, width=1080, height=1920, font_size=80,
                                               margin_vertical=360, margin_horizontal=96))
    renderer = PreviewRenderer(ShortsFinalRenderConfig(minimum_free_bytes=1, timeout_seconds=180, threads=2))
    identity = renderer.identity((local,), narration, captions, approval_identity=accepted_identity)
    output = tmp_path / f"{label}.mp4"
    result = renderer.render((local,), narration, captions, output)
    assert result["render_strategy"] == "bounded-segments"
    assert result["metadata"]["width"] == 1080 and result["metadata"]["height"] == 1920
    assert subprocess.run(["ffmpeg", "-v", "error", "-i", str(output), "-f", "null", "-"],
                          capture_output=True, timeout=60).returncode == 0
    retained = ROOT / "data/artifacts/stage22_teaching_proof"
    retained.mkdir(parents=True, exist_ok=True)
    basename = f"{topic}-{label}"
    shutil.copyfile(output, retained / f"{basename}.mp4")
    (retained / f"{basename}-manifest.json").write_text(json.dumps({
        "accepted_test_package_sha256": accepted_identity,
        "scene_contract_sha256": contract_digest,
        "render_identity": identity,
        "output_sha256": result["checksum_sha256"],
        "layout": animation.layout.value,
        "source_ids": animation.source_ids,
        "cue_seconds": resolve_teaching_cues(animation, words),
        "render_strategy": result["render_strategy"],
        "metadata": result["metadata"],
    }, indent=2) + "\n")
