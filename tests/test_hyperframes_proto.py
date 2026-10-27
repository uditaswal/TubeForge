"""The seven standalone HyperFrames scene templates (video-quality phase 4).

Six use real-job scene evidence; ``terminal`` uses a labelled SYNTHETIC fixture with
Kokoro audio and Whisper word timings. None is wired into production rendering.

The real-binary integration test (project build -> ``hyperframes check`` -> ``hyperframes
render`` -> real decode) only runs when a working ``hyperframes`` CLI is on PATH, matching
this repository's own convention for render-dependent tests (skip, don't mock). It is the
test that matters: the logic-only tests below just guard the pure Python half.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from tubeforge.rendering.hyperframes_proto import cli
from tubeforge.rendering.hyperframes_proto.compose import (
    ASSETS,
    FONTS,
    _format_stat,
    _word_groups,
    build_before_after_project,
    build_checklist_project,
    build_flow_project,
    build_terminal_project,
    build_big_stat_project,
    build_hook_project,
    build_loop_project,
)
from tubeforge.rendering.shorts.schema import BeforeAfter, BigStat, Checklist, Flow, Hook, Loop, Terminal


def _hook_scene(**overrides) -> Hook:
    data = {"scene_id": "s0", "template": "hook", "vo": "You host on Railway? Stop scrolling, hackers hit it Wednesday.",
           "caption": "You host on Railway? Stop scrolling, hackers hit it Wednesday.",
           "reveal_words": [3], "headline": ["You host on", "Railway?"], "chips": ["Rotate", "keys", "today"],
           "icon": "warning", **overrides}
    return Hook.model_validate(data)


def _loop_scene(**overrides) -> Loop:
    data = {"scene_id": "s9", "template": "loop", "vo": "and that is exactly why the real question is",
           "caption": "and that is exactly why the real question is",
           "reveal_words": [2], "headline": ["You host on", "Railway?"], "chips": ["Rotate", "keys", "today"],
           "icon": "warning", **overrides}
    return Loop.model_validate(data)


def _big_stat_scene(**overrides) -> BigStat:
    data = {"scene_id": "scene-8", "template": "big_stat",
           "vo": "Earlier this week, hackers took over 1 percent of OpenCode's customer keys.",
           "caption": "Earlier this week, hackers took over 1 percent of OpenCode's customer keys.",
           "reveal_words": [3, 6], "heading": "OpenCode hit days earlier",
           "before": 0.0, "after": 1.0, "unit": "%", "before_label": "Before attack",
           "after_label": "OpenCode keys", "icon": "chart_up", **overrides}
    return BigStat.model_validate(data)


WORDS_10 = [(0.0, 0.27), (0.27, 0.58), (0.58, 0.77), (0.77, 1.21), (1.21, 1.52),
           (1.52, 2.04), (2.04, 2.48), (2.48, 2.73), (2.73, 2.9), (2.9, 3.44)]
WORDS_9 = [(0.0, 0.3), (0.3, 0.6), (0.6, 0.9), (0.9, 1.2), (1.2, 1.5),
          (1.5, 1.8), (1.8, 2.1), (2.1, 2.4), (2.4, 2.69)]
# Real measured word timings from job e53f4e8387424f65b6a6b50fbb166efa's scene-8 (scene-relative
# seconds, from reference/timeline.json), matching _big_stat_scene's caption and reveal_words.
WORDS_12 = [(0.16, 0.18), (0.18, 0.5), (0.5, 0.72), (0.93, 1.27), (1.27, 1.47), (1.47, 1.63),
           (1.63, 1.85), (1.85, 2.13), (2.13, 2.35), (2.35, 3.15), (3.15, 3.47), (3.47, 3.81)]
BIG_STAT_DURATION = 4.403


def _before_after_scene(**overrides) -> BeforeAfter:
    data = {"scene_id": "scene-4", "template": "before_after",
            "vo": "Railway says hackers even obtained decrypted contents for some of them.",
            "caption": "Railway says hackers even obtained decrypted contents for some of them.",
            "reveal_words": [2, 5], "heading": "Encrypted vs decrypted",
            "before": "Encrypted: unreadable", "after": "Decrypted: readable", "icon": "lock", **overrides}
    return BeforeAfter.model_validate(data)


# Job e53f4e8387424f65b6a6b50fbb166efa, scene-4, scene-relative measured word times.
BEFORE_AFTER_WORDS = [(0.35, 0.43), (0.43, 0.89), (0.89, 1.13), (1.13, 1.61),
                      (1.61, 1.93), (1.93, 2.49), (2.49, 2.81), (2.81, 3.27),
                      (3.27, 3.45), (3.45, 3.51), (3.51, 3.67)]
BEFORE_AFTER_DURATION = 4.005


def _flow_scene(**overrides) -> Flow:
    data = {"scene_id": "scene-2", "template": "flow",
            "vo": "Railway confirmed a cyberattack that let hackers reach some customer secrets.",
            "caption": "Railway confirmed a cyberattack that let hackers reach some customer secrets.",
            "reveal_words": [3, 6, 9], "heading": "What happened",
            "nodes": ["Cyberattack", "Hackers in", "Secrets taken"], "icon": "warning", **overrides}
    return Flow.model_validate(data)


# Job e53f4e8387424f65b6a6b50fbb166efa, scene-2, scene-relative measured word times.
FLOW_WORDS = [(0.0, 0.44), (0.44, 0.957), (0.957, 1.081), (1.081, 1.671),
              (1.671, 1.976), (1.976, 2.23), (2.23, 2.669), (2.669, 3.023),
              (3.023, 3.328), (3.328, 3.807), (3.807, 4.247)]
FLOW_DURATION = 4.427


def _checklist_scene(**overrides) -> Checklist:
    data = {"scene_id": "scene-3", "template": "checklist",
            "vo": "Those secrets are passwords and API keys your apps use to reach databases.",
            "caption": "Those secrets are passwords and API keys your apps use to reach databases.",
            "reveal_words": [3, 5, 12], "heading": "Inside env variables",
            "items": ["Passwords", "API keys", "Database access"], "icon": "lock", **overrides}
    return Checklist.model_validate(data)


# Job e53f4e8387424f65b6a6b50fbb166efa, scene-3, scene-relative measured word times.
CHECKLIST_WORDS = [(0.0, 0.18), (0.18, 0.48), (0.48, 0.76), (0.76, 1.1),
                   (1.1, 1.7), (1.7, 2.12), (2.12, 2.34), (2.34, 2.54),
                   (2.54, 2.74), (2.74, 3.0), (3.0, 3.2), (3.2, 3.34), (3.34, 3.86)]
CHECKLIST_DURATION = 4.39


def _synthetic_terminal_scene(**overrides) -> Terminal:
    """SYNTHETIC fixture, never an approved script or real TubeForge job."""
    data = {"scene_id": "synthetic-terminal-01", "template": "terminal",
            "vo": "Run the status command, read its running result, then check whether the service responds cleanly.",
            "caption": "Run the status command, read its running result, then check whether the service responds cleanly.",
            "reveal_words": [0, 6, 9], "heading": "Service health",
            "evidence_label": "ILLUSTRATIVE OUTPUT",
            "lines": [{"kind": "command", "text": "service status"},
                      {"kind": "output", "text": "running"},
                      {"kind": "command", "text": "service check"}],
            "icon": "code", **overrides}
    return Terminal.model_validate(data)


# SYNTHETIC fixture: Kokoro af_bella 1.15x, then local Whisper base.en DTW (no estimate).
# Local audio/timing evidence: .hyperframes-proto-test-tmp/terminal-synthetic-review/.
SYNTHETIC_TERMINAL_WORDS = [(0.0, 0.12), (0.12, 0.26), (0.26, 0.5), (0.5, 0.88),
                            (1.37, 1.63), (1.63, 1.75), (1.75, 1.97), (1.97, 2.37),
                            (2.79, 3.09), (3.09, 3.29), (3.29, 3.51), (3.51, 3.69),
                            (3.69, 4.01), (4.01, 4.47), (4.47, 5.17)]
SYNTHETIC_TERMINAL_DURATION = 5.535  # Kokoro audio 5.355 s + the standard 0.18 s scene tail.


def test_word_groups_matches_the_pil_renderers_own_grouping_and_maps_real_timing():
    groups = _word_groups(_hook_scene().caption, WORDS_10)
    assert [g["words"] for g in groups] == [["YOU", "HOST", "ON"], ["RAILWAY?", "STOP"],
                                            ["SCROLLING,", "HACKERS"], ["HIT", "IT", "WEDNESDAY."]]
    assert groups[0]["start"] == WORDS_10[0][0] and groups[0]["end"] == WORDS_10[2][1]
    assert groups[-1]["start"] == WORDS_10[7][0] and groups[-1]["end"] == WORDS_10[9][1]


def test_word_groups_rejects_a_word_count_mismatch():
    with pytest.raises(ValueError, match="display words"):
        _word_groups(_hook_scene().caption, WORDS_10[:5])


def test_build_hook_project_writes_a_self_contained_tree(tmp_path):
    project = tmp_path / "proj"
    build_hook_project(_hook_scene(), WORDS_10, 3.63, project)

    assert (project / "index.html").is_file() and (project / "hyperframes.json").is_file()
    assets = project / "assets"
    for name in ("gsap.min.js", "Anton-Regular.ttf", "Inter-Variable.ttf", "badge.png"):
        assert (assets / name).is_file(), name
    html = (project / "index.html").read_text()
    assert 'data-width="1080"' in html and 'data-height="1920"' in html
    assert 'data-composition-id="hook"' in html and 'window.__timelines["hook"]' in html
    assert "YOU HOST ON" not in html  # content is injected by JS from the data, not baked as text
    assert "Rotate" in html and "Railway?" in html  # the JSON payload is present verbatim
    # No remote fetches: the only <script src> is the vendored local copy.
    srcs = re.findall(r'<script src="([^"]+)"', html)
    assert srcs == ["assets/gsap.min.js"]


def test_build_hook_project_omits_the_badge_image_when_the_scene_has_no_icon_or_logo(tmp_path):
    project = tmp_path / "proj"
    build_hook_project(_hook_scene(icon=None), WORDS_10, 3.63, project)
    assert not (project / "assets" / "badge.png").is_file()


def test_build_loop_project_reuses_the_hook_composition_with_its_own_id(tmp_path):
    """A Loop IS a Hook (schema.py) and the PIL compositor already treats them identically
    ("the loop scene reuses the hook composition so the last frame matches the first",
    layout.py) - same builder, named ``build_loop_project`` for callers, its own
    ``data-composition-id`` so the two never collide if ever placed in one project."""
    assert build_loop_project is build_hook_project
    project = tmp_path / "proj"
    build_loop_project(_loop_scene(), WORDS_9, 2.69, project)
    html = (project / "index.html").read_text()
    assert 'data-composition-id="loop"' in html and 'window.__timelines["loop"]' in html
    assert 'data-composition-id="hook"' not in html


def test_format_stat_matches_the_pil_renderers_own_rule():
    assert _format_stat(0.0, "%") == "0%"
    assert _format_stat(1.0, "%") == "1%"
    assert _format_stat(2.5, "x") == "2.5x"


def test_build_big_stat_project_times_the_two_reveals_off_their_own_words(tmp_path):
    project = tmp_path / "proj"
    build_big_stat_project(_big_stat_scene(), WORDS_12, BIG_STAT_DURATION, project)
    html = (project / "index.html").read_text()

    assert 'data-composition-id="big_stat"' in html
    assert "OpenCode hit days earlier" in html  # heading is static JS-free markup, unlike hook's
    assert "Before attack" in html and "OpenCode keys" in html
    # reveal_words = [3, 6]: word 3 starts at 0.93s (before stat), word 6 at 1.63s (after stat
    # + its count-up), both scene-relative, matching the PIL renderer's timeline.py.
    assert "}, 0.930);" in html
    assert "}, 1.630);" in html
    assert "AFTER_VALUE = 1.0" in html
    srcs = re.findall(r'<script src="([^"]+)"', html)
    assert srcs == ["assets/gsap.min.js"]


def test_build_big_stat_project_omits_the_badge_image_when_the_scene_has_no_icon_or_logo(tmp_path):
    project = tmp_path / "proj"
    build_big_stat_project(_big_stat_scene(icon=None), WORDS_12, BIG_STAT_DURATION, project)
    assert not (project / "assets" / "badge.png").is_file()


def test_build_before_after_project_uses_real_reveal_words_and_its_own_id(tmp_path):
    project = tmp_path / "proj"
    build_before_after_project(_before_after_scene(), BEFORE_AFTER_WORDS, BEFORE_AFTER_DURATION, project)
    html = (project / "index.html").read_text()
    assert 'data-composition-id="before_after"' in html
    assert 'window.__timelines["before_after"]' in html
    assert 'Encrypted: unreadable' in html and 'Decrypted: readable' in html
    assert '},0.890);' in html and '},1.930);' in html
    assert re.findall(r'<script src="([^"]+)"', html) == ["assets/gsap.min.js"]


def test_build_before_after_project_omits_badge_without_icon_or_logo(tmp_path):
    project = tmp_path / "proj"
    build_before_after_project(_before_after_scene(icon=None), BEFORE_AFTER_WORDS, BEFORE_AFTER_DURATION, project)
    assert not (project / "assets" / "badge.png").exists()
    assert '<img src="assets/badge.png"' not in (project / "index.html").read_text()


def test_build_flow_project_uses_three_real_reveal_words_and_its_own_id(tmp_path):
    project = tmp_path / "proj"
    build_flow_project(_flow_scene(), FLOW_WORDS, FLOW_DURATION, project)
    html = (project / "index.html").read_text()
    assert 'data-composition-id="flow"' in html and 'window.__timelines["flow"]' in html
    assert all(node in html for node in ("Cyberattack", "Hackers in", "Secrets taken"))
    assert all(f'}},{at:.3f});' in html for at in (1.081, 2.23, 3.328))
    assert html.count('class="arrow"') == 2
    assert re.findall(r'<script src="([^"]+)"', html) == ["assets/gsap.min.js"]


def test_build_flow_project_omits_badge_without_icon_or_logo(tmp_path):
    project = tmp_path / "proj"
    build_flow_project(_flow_scene(icon=None), FLOW_WORDS, FLOW_DURATION, project)
    assert not (project / "assets" / "badge.png").exists()
    assert '<img src="assets/badge.png"' not in (project / "index.html").read_text()


def test_build_checklist_project_uses_real_reveals_without_flow_arrows(tmp_path):
    project = tmp_path / "proj"
    build_checklist_project(_checklist_scene(), CHECKLIST_WORDS, CHECKLIST_DURATION, project)
    html = (project / "index.html").read_text()
    assert 'data-composition-id="checklist"' in html and 'window.__timelines["checklist"]' in html
    assert all(label in html for label in ("✓  Passwords", "✓  API keys", "✓  Database access"))
    assert all(f'}},{at:.3f});' in html for at in (0.76, 1.7, 3.34))
    assert 'class="arrow"' not in html
    assert re.findall(r'<script src="([^"]+)"', html) == ["assets/gsap.min.js"]


def test_build_checklist_project_omits_badge_without_icon_or_logo(tmp_path):
    project = tmp_path / "proj"
    build_checklist_project(_checklist_scene(icon=None), CHECKLIST_WORDS, CHECKLIST_DURATION, project)
    assert not (project / "assets" / "badge.png").exists()
    assert '<img src="assets/badge.png"' not in (project / "index.html").read_text()


def test_build_synthetic_terminal_project_uses_whisper_reveals_and_mono_font(tmp_path):
    project = tmp_path / "proj"
    build_terminal_project(_synthetic_terminal_scene(), SYNTHETIC_TERMINAL_WORDS,
                           SYNTHETIC_TERMINAL_DURATION, project)
    html = (project / "index.html").read_text()
    assert 'data-composition-id="terminal"' in html and 'window.__timelines["terminal"]' in html
    assert all(label in html for label in ("$ service status", "running", "$ service check"))
    assert all(f'}},{at:.3f});' in html for at in (0.0, 1.75, 3.09))
    assert 'ILLUSTRATIVE OUTPUT' in html
    assert (project / "assets" / "DejaVuSansMono-Bold.ttf").is_file()
    assert re.findall(r'<script src="([^"]+)"', html) == ["assets/gsap.min.js"]


def test_build_synthetic_terminal_project_omits_badge_without_icon_or_logo(tmp_path):
    project = tmp_path / "proj"
    build_terminal_project(_synthetic_terminal_scene(icon=None), SYNTHETIC_TERMINAL_WORDS,
                           SYNTHETIC_TERMINAL_DURATION, project)
    assert not (project / "assets" / "badge.png").exists()
    assert '<img src="assets/badge.png"' not in (project / "index.html").read_text()


def test_vendored_assets_exist_on_disk():
    assert (ASSETS / "hyperframes" / "gsap.min.js").is_file()
    assert (ASSETS / "hyperframes" / "LICENSE-gsap.md").is_file()
    assert (FONTS / "Anton-Regular.ttf").is_file() and (FONTS / "Inter-Variable.ttf").is_file()


def _hyperframes_bin() -> str | None:
    found = shutil.which("hyperframes")
    if found:
        return found
    # This host's throwaway benchmark install (video-quality review phase 0), not part of the repo.
    local = Path.home() / "docker" / "tubeforge" / "hf-bench" / "node_modules" / ".bin" / "hyperframes"
    return str(local) if local.is_file() else None


HYPERFRAMES_BIN = _hyperframes_bin()
needs_hyperframes = pytest.mark.skipif(HYPERFRAMES_BIN is None, reason="no hyperframes CLI on PATH or at the phase-0 benchmark install")
needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg required to probe the rendered file")


def _real_check_render_decode(builder, scene, words, duration, expected_composition_id):
    """Shared real-binary path for every template: build -> real `hyperframes check` (zero
    errors) -> real `hyperframes render` -> real ffprobe/ffmpeg decode at the right spec."""
    # Real disk, not pytest's default tmp_path (under /tmp): on this host /tmp is a 1.9 GB
    # tmpfs (video-quality review phase 0 finding) and the CLI refuses to render into a
    # low-disk location even when TMPDIR points elsewhere. Scratch under the repository's own
    # working tree (always real disk, gitignored), so this stays portable to any checkout.
    scratch_root = Path(__file__).resolve().parents[1] / ".hyperframes-proto-test-tmp"
    scratch_root.mkdir(exist_ok=True)
    if shutil.disk_usage(scratch_root).free < 2_000_000_000:
        pytest.skip("less than 2 GB free on the repository's own disk; skipping the real render")

    with tempfile.TemporaryDirectory(dir=scratch_root) as raw:
        tmp_path = Path(raw)
        project = tmp_path / "proj"
        builder(scene, words, duration, project)
        assert f'data-composition-id="{expected_composition_id}"' in (project / "index.html").read_text()

        env = {"TMPDIR": str(tmp_path / "tmp"), "HYPERFRAMES_EXTRACT_CACHE_DIR": str(tmp_path / ".hf-cache")}
        (tmp_path / "tmp").mkdir()

        report = cli.check(project, hyperframes_bin=HYPERFRAMES_BIN, timeout=60, extra_env=env)
        assert report["ok"] is True
        for group in ("lint", "runtime", "layout", "craft"):
            errors = [f for f in report.get(group, {}).get("findings", []) if f.get("severity") == "error"]
            assert not errors, errors

        output = tmp_path / "silent.mp4"
        cli.render(project, output, quality="draft", hyperframes_bin=HYPERFRAMES_BIN, timeout=120, extra_env=env)

        probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=width,height,codec_name",
                               "-of", "json", str(output)], capture_output=True, text=True, check=True)
        data = json.loads(probe.stdout)
        video = next(s for s in data["streams"] if s["codec_name"] == "h264")
        assert (video["width"], video["height"]) == (1080, 1920)
        assert abs(float(data["format"]["duration"]) - duration) < 0.1
        subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-i", str(output), "-f", "null", "-"], check=True)


@needs_hyperframes
@needs_ffmpeg
def test_real_hook_render_passes_check_and_decodes_to_the_right_spec():
    _real_check_render_decode(build_hook_project, _hook_scene(), WORDS_10, 3.63, "hook")


@needs_hyperframes
@needs_ffmpeg
def test_real_loop_render_passes_check_and_decodes_to_the_right_spec():
    _real_check_render_decode(build_loop_project, _loop_scene(), WORDS_9, 2.69, "loop")


@needs_hyperframes
@needs_ffmpeg
def test_real_big_stat_render_passes_check_and_decodes_to_the_right_spec():
    _real_check_render_decode(build_big_stat_project, _big_stat_scene(), WORDS_12, BIG_STAT_DURATION, "big_stat")


@needs_hyperframes
@needs_ffmpeg
def test_real_before_after_render_passes_check_and_decodes_to_the_right_spec():
    _real_check_render_decode(build_before_after_project, _before_after_scene(), BEFORE_AFTER_WORDS,
                              BEFORE_AFTER_DURATION, "before_after")


@needs_hyperframes
@needs_ffmpeg
def test_real_flow_render_passes_check_and_decodes_to_the_right_spec():
    _real_check_render_decode(build_flow_project, _flow_scene(), FLOW_WORDS, FLOW_DURATION, "flow")


@needs_hyperframes
@needs_ffmpeg
def test_real_checklist_render_passes_check_and_decodes_to_the_right_spec():
    _real_check_render_decode(build_checklist_project, _checklist_scene(), CHECKLIST_WORDS,
                              CHECKLIST_DURATION, "checklist")


@needs_hyperframes
@needs_ffmpeg
def test_synthetic_terminal_real_binary_check_render_and_decode():
    _real_check_render_decode(build_terminal_project, _synthetic_terminal_scene(), SYNTHETIC_TERMINAL_WORDS,
                              SYNTHETIC_TERMINAL_DURATION, "terminal")
