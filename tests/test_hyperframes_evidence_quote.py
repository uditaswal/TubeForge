"""Captured source cards in the opt-in HyperFrames path."""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from tubeforge.pipeline.reference_short import load_timeline
from tubeforge.rendering.hyperframes_proto import cli, compose
from tubeforge.rendering.shorts import hyperframes_compose as film
from tubeforge.rendering.shorts.plates import load_manifest
from tubeforge.rendering.shorts.schema import ShortsTopic

JOB = Path(__file__).resolve().parents[2] / "Youtube_Video_Producer" / "data" / "artifacts" / "e53f4e8387424f65b6a6b50fbb166efa"
REFERENCE = JOB / "reference"
needs_job = pytest.mark.skipif(not (REFERENCE / "plates" / "source-1-hl.png").is_file(),
                                reason="real captured-source fixture absent")


def _fixture():
    topic = ShortsTopic.model_validate_json((REFERENCE / "topic.json").read_text())
    return load_timeline(topic, REFERENCE)


def _words(timeline, index):
    timing = timeline.timings[index]
    return [(w.start - timing.start, w.end - timing.start) for w in timing.words]


@needs_job
def test_source_composition_uses_real_reveal_words_and_safe_footnote(tmp_path):
    timeline = _fixture()
    scene = timeline.topic.scenes[1]
    treatment, reason = film.source_treatment(scene, 1, timeline.topic, REFERENCE, load_manifest(REFERENCE))
    assert reason is None and treatment["highlight"].is_file()
    project = tmp_path / "project"
    compose.build_evidence_quote_project(scene, _words(timeline, 1), 4.427, project,
                                         plate=treatment["plate"], highlight=treatment["highlight"],
                                         source_label=treatment["source_label"])
    page = (project / "index.html").read_text()
    assert 'data-composition-id="evidence_quote"' in page
    assert 'id="source-base"' in page and 'id="source-highlight"' in page
    assert 'background-image:url("assets/source-base.png")' in page
    assert 'background-image:url("assets/source-highlight.png")' in page
    assert '1.081' in page and '2.230' in page and '3.328' in page
    assert 'duration:.5,ease:"none"' in page
    assert "What happened" in page and "Source: techcrunch.com" in page
    assert "left:90px; width:810px; top:" in page and "height:64px" in page
    assert "font:800 38px/1.2 Inter" in page and 'id="source-zoom"' in page and "scale:1.07" in page
    assert (project / "assets" / "source-base.png").read_bytes() == treatment["plate"].read_bytes()
    assert (project / "assets" / "source-highlight.png").read_bytes() == treatment["highlight"].read_bytes()


@needs_job
def test_missing_plate_uses_normal_template_and_missing_highlight_keeps_base(tmp_path):
    timeline = _fixture()
    manifest = load_manifest(REFERENCE)
    missing, reason = film.source_treatment(timeline.topic.scenes[5], 5, timeline.topic, REFERENCE, manifest)
    assert missing is None and "capture failed" in reason
    no_highlight = json.loads(json.dumps(manifest))
    no_highlight["scenes"]["1"]["highlight"] = "plates/not-present.png"
    treatment, reason = film.source_treatment(timeline.topic.scenes[1], 1, timeline.topic, REFERENCE, no_highlight)
    assert reason is None and treatment["highlight"] is None
    project = tmp_path / "base-only"
    compose.build_evidence_quote_project(timeline.topic.scenes[1], _words(timeline, 1), 4.427,
                                         project, plate=treatment["plate"], highlight=None,
                                         source_label=treatment["source_label"])
    page = (project / "index.html").read_text()
    assert 'id="source-base"' in page and 'id="source-highlight"' not in page
    assert not (project / "assets" / "source-highlight.png").exists()


@needs_job
def test_render_routing_records_source_and_fallback_provenance(tmp_path, monkeypatch):
    timeline = _fixture()
    built = []
    def normal(scene, words, duration, project):
        built.append((scene.scene_id, "normal"))
        project.mkdir()
    def evidence(scene, words, duration, project, **kwargs):
        built.append((scene.scene_id, "evidence_quote"))
        project.mkdir()
    monkeypatch.setattr(film, "BUILDERS", {key: normal for key in film.BUILDERS})
    monkeypatch.setattr(film.compose, "build_evidence_quote_project", evidence)
    monkeypatch.setattr(film.cli, "check", lambda *a, **k: {"ok": True})
    monkeypatch.setattr(film.cli, "render", lambda p, out, **k: out.write_bytes(b"clip"))
    def checked(command, **kwargs):
        if "-filter_complex" in command:
            Path(command[-1]).write_bytes(b"joined")
        return b""
    monkeypatch.setattr(film, "checked", checked)
    report = film.render_silent(timeline, tmp_path / "silent.mp4", draft=True,
                                hyperframes_bin="stub", plates_directory=REFERENCE)
    assert len(report["evidence_quote"]) == 4
    assert {e["scene_index"] for e in report["evidence_quote"]} == {1, 3, 6, 7}
    assert any(e["scene_index"] == 5 and "capture failed" in e["reason"] for e in report["source_fallbacks"])
    assert (timeline.topic.scenes[5].scene_id, "normal") in built


def _binary():
    found = shutil.which("hyperframes")
    local = Path.home() / "docker" / "tubeforge" / "hf-bench" / "node_modules" / ".bin" / "hyperframes"
    return found or (str(local) if local.is_file() else None)


@needs_job
@pytest.mark.skipif(_binary() is None, reason="existing HyperFrames binary absent")
def test_real_binary_evidence_quote_check_render_decode():
    scratch_root = Path(__file__).resolve().parents[1] / ".hyperframes-proto-test-tmp"
    scratch_root.mkdir(exist_ok=True)
    if shutil.disk_usage(scratch_root).free < 2_000_000_000:
        pytest.skip("less than 2 GB free for HyperFrames render")
    timeline = _fixture()
    treatment, _ = film.source_treatment(timeline.topic.scenes[1], 1, timeline.topic,
                                         REFERENCE, load_manifest(REFERENCE))
    with tempfile.TemporaryDirectory(dir=scratch_root) as raw:
        root = Path(raw)
        project = root / "evidence"
        compose.build_evidence_quote_project(timeline.topic.scenes[1], _words(timeline, 1),
                                             timeline.timings[1].end - timeline.timings[1].start,
                                             project, plate=treatment["plate"],
                                             highlight=treatment["highlight"],
                                             source_label=treatment["source_label"])
        env = {"TMPDIR": str(root), "HYPERFRAMES_EXTRACT_CACHE_DIR": str(root / "cache")}
        report = cli.check(project, hyperframes_bin=_binary(), timeout=90, extra_env=env)
        assert report["ok"]
        for group in ("lint", "runtime", "layout", "craft"):
            assert report.get(group, {}).get("errorCount", 0) == 0
        output = root / "silent.mp4"
        cli.render(project, output, quality="draft", hyperframes_bin=_binary(), timeout=180, extra_env=env)
        subprocess.run(["ffmpeg", "-xerror", "-v", "error", "-i", str(output), "-f", "null", "-"], check=True)
        def yellow_at(seconds):
            frame = root / f"frame-{seconds}.png"
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(seconds), "-i", str(output),
                            "-frames:v", "1", str(frame)], check=True)
            pixels = np.asarray(Image.open(frame).convert("RGB"))[470:1160, 40:940]
            return int(((pixels[:, :, 0] > 180) & (pixels[:, :, 1] > 150) &
                        (pixels[:, :, 2] < 150)).sum())
        assert yellow_at(.9) == 0
        assert yellow_at(1.5) > 10000


def test_source_treatment_prefers_native_resolution_plates(tmp_path):
    plates = tmp_path / "plates"
    plates.mkdir()
    for name in ("s.png", "s-hl.png", "s-2x.png", "s-hl-2x.png"):
        Image.new("RGB", (8, 4), "white").save(plates / name)
    entry = {"kind": "source", "file": "plates/s.png", "highlight": "plates/s-hl.png",
             "file_2x": "plates/s-2x.png", "highlight_2x": "plates/s-hl-2x.png",
             "url": "https://example.com/a"}
    timeline = _fixture() if (REFERENCE / "topic.json").is_file() else None
    if timeline is None:
        pytest.skip("real fixture absent")
    treatment, reason = film.source_treatment(timeline.topic.scenes[1], 1, timeline.topic, tmp_path,
                                              {"scenes": {"1": entry}})
    assert reason is None
    assert treatment["plate"].name == "s-2x.png" and treatment["highlight"].name == "s-hl-2x.png"
    entry.pop("highlight_2x")
    treatment, _ = film.source_treatment(timeline.topic.scenes[1], 1, timeline.topic, tmp_path,
                                         {"scenes": {"1": entry}})
    assert treatment["highlight"].name == "s-hl.png"
