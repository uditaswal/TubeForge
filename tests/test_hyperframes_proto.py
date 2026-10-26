"""The HyperFrames renderer prototype (video-quality review phase 4): two scene templates
(``hook``, ``loop``) proven end to end — not wired into production rendering yet.

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
    _word_groups,
    build_hook_project,
    build_loop_project,
)
from tubeforge.rendering.shorts.schema import Hook, Loop


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


WORDS_10 = [(0.0, 0.27), (0.27, 0.58), (0.58, 0.77), (0.77, 1.21), (1.21, 1.52),
           (1.52, 2.04), (2.04, 2.48), (2.48, 2.73), (2.73, 2.9), (2.9, 3.44)]
WORDS_9 = [(0.0, 0.3), (0.3, 0.6), (0.6, 0.9), (0.9, 1.2), (1.2, 1.5),
          (1.5, 1.8), (1.8, 2.1), (2.1, 2.4), (2.4, 2.69)]


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
