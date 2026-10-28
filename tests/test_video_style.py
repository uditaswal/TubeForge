"""Video style choice (classic cards vs story) from the Studio form to the render routing."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from test_ending_and_length import request
from tubeforge.domain.contracts import generation_request_content, generation_request_key_payload
from tubeforge.pipeline import reference_short
from tubeforge.providers.content.host_runner_protocol import GenerateShortsScriptRequest

JOB = Path(__file__).resolve().parents[2] / "Youtube_Video_Producer" / "data" / "artifacts" / "e53f4e8387424f65b6a6b50fbb166efa" / "reference"


def test_style_defaults_to_classic_and_is_omitted_from_the_request():
    assert request().video_style == "classic" and "video_style" not in request().model_dump(mode="json")
    assert request(video_style="story").model_dump(mode="json")["video_style"] == "story"
    with pytest.raises(ValidationError):
        request(video_style="neon")


def test_story_style_is_not_sent_to_the_host_writer_or_script_cache():
    classic = request()
    story = request(video_style="story", show_source_credit=True, show_mascot=True,
                    channel_watermark="TubeForge")
    assert generation_request_key_payload(story) == generation_request_key_payload(classic)
    assert story.video_style == "story"  # the job still keeps its render choice
    writer = generation_request_content(story)
    assert writer.video_style == "classic"
    for operation in ("PreflightContentV1", "GenerateShortsScriptV1", "ResearchSourcesV1"):
        payload = json.loads(GenerateShortsScriptRequest(operation=operation, request=writer).model_dump_json())
        assert all(field not in payload["request"] for field in
                   ("video_style", "show_source_credit", "show_mascot", "channel_watermark"))


def test_options_file_records_only_a_non_default_style(tmp_path):
    reference_short.write_options(tmp_path, show_sources=False, watermark=None)
    assert not (tmp_path / reference_short.OPTIONS_FILE).exists() and reference_short.load_style(tmp_path) == "classic"
    classic_identity = reference_short.options_identity(tmp_path)
    reference_short.write_options(tmp_path, show_sources=False, watermark=None, style="story")
    assert reference_short.load_style(tmp_path) == "story"
    assert reference_short.options_identity(tmp_path) != classic_identity
    reference_short.write_options(tmp_path, show_sources=False, watermark=None, style="classic")
    assert reference_short.load_style(tmp_path) == "classic" and reference_short.options_identity(tmp_path) == "none"
    (tmp_path / reference_short.OPTIONS_FILE).write_text(json.dumps({"style": "unknown"}))
    assert reference_short.load_style(tmp_path) == "classic"


def test_studio_api_accepts_and_stores_the_video_style(tmp_path):
    from fastapi.testclient import TestClient
    from test_api_workflow import _migrate
    from tubeforge.api.app import create_app
    from tubeforge.core.config import AppConfig, DatabaseConfig, Settings, VideoPresetConfig

    database = tmp_path / "style.db"
    _migrate(database)
    settings = Settings(app=AppConfig(name="TubeForge test", environment="test"), database=DatabaseConfig(url=f"sqlite:///{database}"))
    settings.pipeline.video_generation.presets["reference-short"] = VideoPresetConfig(
        duration_seconds=60, minimum_duration_seconds=30, maximum_duration_seconds=90, aspect_ratio="9:16", prompt_version="m6-content-v8")
    brief = {"title": "Railway", "notes": ["Rotate keys"], "preset": "reference-short",
             "source_url": "https://example.com/a", "source_title": "A", "source_excerpt": "Railway told all users to rotate keys."}
    with TestClient(create_app(settings)) as client:
        default = client.post("/api/videos", json=brief)
        assert client.app.state.runtime.jobs.get(default.json()["id"]).request.video_style == "classic"
        story = client.post("/api/videos", json={**brief, "video_style": "story"})
        assert story.status_code == 201
        assert client.app.state.runtime.jobs.get(story.json()["id"]).request.video_style == "story"
        assert client.post("/api/videos", json={**brief, "video_style": "neon"}).status_code == 422
        page = client.get("/").text
        assert "videoStyle" in page and "Story: big headline" in page and "Classic: one card per scene" in page


@pytest.mark.skipif(not (JOB / "topic.json").is_file(), reason="real reference job absent")
def test_story_layout_covers_every_template_and_uses_only_topic_text(tmp_path):
    from test_hyperframes_evidence_quote import _fixture
    from tubeforge.rendering.shorts import story
    from tubeforge.rendering.shorts.plates import load_manifest
    timeline = _fixture()
    report = story.build_story(timeline, tmp_path / "p", plates_directory=JOB, manifest=load_manifest(JOB))
    page = (tmp_path / "p" / "index.html").read_text()
    assert page.count('class="scene"') == len(timeline.topic.scenes)
    assert [h["scene_index"] for h in report["evidence_quote"]] == [1, 3, 6, 7]
    scene = timeline.topic.scenes[1]
    first = f"{timeline.timings[1].words[scene.reveal_words[0]].start:.3f}"
    assert "assets/hero-1-hl.png" in page and f'inset(0 0% 0 0)",duration:.5,ease:"none"}},{first})' in page  # sweep at the real word time
    for scene in timeline.topic.scenes:  # every caption group is the approved caption, nothing invented
        assert scene.caption.split()[0].casefold() in page.casefold()
    assert "BREACHED" not in page
    # A scene with no captured plate keeps its quote as a labelled quote, never as a screenshot.
    bare = story.build_story(timeline, tmp_path / "bare", plates_directory=None, manifest={"scenes": {}})
    assert bare["evidence_quote"] == []
    assert "assets/hero-" not in (tmp_path / "bare" / "index.html").read_text()


def test_claude_runner_accepts_the_long_excerpt_prompt_that_the_old_60k_limit_rejected():
    from test_ending_and_length import request as make_request
    from tubeforge import host_claude_runner
    from tubeforge.domain.contracts import SourceReference
    from tubeforge.providers.content.prompts import build_content_prompt
    long = make_request(90).model_copy(update={"sources": (
        SourceReference(source_id="s", title="T", url="https://example.com/a", excerpt="word " * 3100),)})
    prompt = build_content_prompt(long, template_version="m6-content-v8", max_chars=host_claude_runner.MAX_PROMPT_CHARS)
    assert 60_000 < len(prompt) <= host_claude_runner.MAX_PROMPT_CHARS


def test_hyperframes_gets_a_writable_home_so_chromium_starts_under_the_worker_uid(tmp_path, monkeypatch):
    """The worker's HOME is '/', unwritable for Chromium's profile; both HyperFrames paths must override it."""
    from test_hyperframes_evidence_quote import _fixture
    from tubeforge.rendering.shorts import hyperframes_compose, story
    seen = []
    def fake_check(project, **kwargs):
        seen.append(kwargs["extra_env"])
        raise RuntimeError("stop after the first check")
    for module in (story, hyperframes_compose):
        monkeypatch.setattr(module.cli, "check", fake_check)
    timeline = _fixture()
    for module in (story, hyperframes_compose):
        with pytest.raises(RuntimeError, match="stop after"):
            module.render_silent(timeline, tmp_path / "out.mp4", draft=True, plates_directory=None, hyperframes_bin="/bin/true")
    assert len(seen) == 2
    for env in seen:
        assert env["HOME"] == env["TMPDIR"] == env["XDG_CONFIG_HOME"] == env["XDG_CACHE_HOME"]
