"""Where a clip job's time goes, and the two download speed-ups (sections only, parallel fragments)."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from tests.test_clips_api import _client, _login
from tubeforge.clips.engine import ClipRequest, build_engine_config
from tubeforge.clips.stage_clock import StageClock, TIMINGS_FILE, classify, summarize
from tubeforge.clips.ytdlp_options import speed_options
from tubeforge.core import runtime_settings
from tubeforge.core.config import SourceClipConfig
from tubeforge.domain.states import JobState
from tubeforge.pipeline.clip_runs import EngineClipRunner


@pytest.mark.parametrize("message,expected", [
    ("Downloading video...", ("download", "Downloading the video (or its audio)")),
    ("Preparing video...", ("prepare", "Preparing the video")),
    ("Generating transcript...", ("transcription", "Transcribing speech")),
    ("Analyzing content with AI...", ("ai", "AI picks the moments")),
    ("Downloading selected segments...", ("sections", "Downloading the chosen sections")),
    ("Creating clip 2/3...", ("render-2", "Rendering clip 2 of 3")),
    ("Complete!", None), ("", None),
])
def test_engine_messages_map_to_stages(message, expected):
    assert classify(message) == expected


def test_each_new_stage_closes_the_previous_one_and_progress_repeats_are_ignored(tmp_path):
    clock = StageClock(tmp_path / TIMINGS_FILE)
    clock.tick("Downloading video...", now=100)
    clock.tick("Downloading video...", now=130)          # the same stage reporting again
    clock.tick("Generating transcript...", now=160)
    clock.tick("Analyzing content with AI...", now=400)
    clock.tick("Creating clip 1/2...", now=460)
    clock.tick("Creating clip 2/2...", now=630)
    clock.close(now=800)
    rows = summarize(StageClock(tmp_path / TIMINGS_FILE).stages, now=900)  # read back from disk
    assert [(r["key"], r["seconds"], r["running"]) for r in rows["rows"]] == [
        ("download", 60.0, False), ("transcription", 240.0, False), ("ai", 60.0, False), ("render-1", 170.0, False), ("render-2", 170.0, False)]
    assert rows["total_seconds"] == 700.0


def test_a_running_stage_counts_up_to_now():
    rows = summarize([{"key": "download", "label": "Downloading", "started_at": 100.0, "seconds": None}], now=190.0)
    assert rows["rows"][0]["seconds"] == 90.0 and rows["rows"][0]["running"]


class _TalkingEngine:
    """An engine that reports its steps the way the real one does, then optionally fails."""
    def __init__(self, fail=False): self.fail = fail
    async def analyze(self, request, *, progress=None, should_cancel=None):
        for percent, message in ((10, "Downloading video..."), (15, "Preparing video..."), (30, "Generating transcript..."), (50, "Analyzing content with AI...")):
            await progress(percent, message)
        if self.fail:
            raise RuntimeError("boom")
        return SimpleNamespace(video_path="v.mp4", segments=[{}], summary=None, key_topics=None)


@pytest.mark.parametrize("fail", [False, True])
def test_the_runner_records_every_stage_and_closes_the_last_one_even_when_the_stage_fails(tmp_path, monkeypatch, fail):
    runner = EngineClipRunner(SourceClipConfig(enabled=True))
    monkeypatch.setattr(runner, "_engine", lambda work_dir: _TalkingEngine(fail))
    monkeypatch.setattr(EngineClipRunner, "request", staticmethod(lambda work_dir, params: object()))
    if fail:
        with pytest.raises(RuntimeError):
            runner.analyze("job", tmp_path, {}, None)
    else:
        runner.analyze("job", tmp_path, {}, None)
    stages = json.loads((tmp_path / TIMINGS_FILE).read_text())["stages"]
    assert [s["key"] for s in stages] == ["download", "prepare", "transcription", "ai"]
    assert all(s["seconds"] is not None for s in stages)  # none left counting after the part ended


def test_the_clips_page_shows_where_the_time_went(tmp_path):
    app = _client(tmp_path)
    with TestClient(app) as client:
        _login(app, client)
        job_id = client.post("/api/clip-jobs", json={"source_url": "https://www.youtube.com/watch?v=abcdefghijk"}).json()["id"]
        app.state.runtime.jobs.update_state(job_id, JobState.FINAL_READY)
        work = Path(app.state.settings.pipeline.voice.artifact_root) / job_id / "clip-work"
        clock = StageClock(work / TIMINGS_FILE)
        clock.tick("Downloading video...", now=1000); clock.tick("Creating clip 1/1...", now=1090); clock.close(now=1250)
        timings = client.get(f"/api/clip-jobs/{job_id}").json()["timings"]
        assert [(r["label"], r["seconds"]) for r in timings["rows"]] == [("Downloading the video (or its audio)", 90.0), ("Rendering clip 1 of 1", 160.0)]
        assert timings["total_seconds"] == 250.0
        page = client.get("/clips").text
        assert "Where the time went" in page and "function timingsBlock" in page and "openTimings" in page


def test_parallel_fragments_are_requested_and_bounded():
    assert speed_options(SimpleNamespace(youtube_fragment_concurrency=4)) == {"concurrent_fragment_downloads": 4}
    assert speed_options(SimpleNamespace(youtube_fragment_concurrency=99)) == {"concurrent_fragment_downloads": 8}
    assert speed_options(SimpleNamespace(youtube_fragment_concurrency=0)) == {"concurrent_fragment_downloads": 1}
    assert speed_options(SimpleNamespace()) == {"concurrent_fragment_downloads": 1}
    from tubeforge.clips.youtube_proxy import base_proxy_params
    assert base_proxy_params(config=SimpleNamespace(youtube_proxy_url="", youtube_proxy_country="", youtube_pot_provider_url="", youtube_direct_sections=True, youtube_fragment_concurrency=6))["concurrent_fragment_downloads"] == 6


def test_the_two_new_settings_reach_the_engine(tmp_path, monkeypatch):
    from tubeforge.core.config import AppConfig, DatabaseConfig, Settings
    for key in ("clips.direct_sections", "clips.download_connections"):
        assert key in runtime_settings.BY_KEY
    settings = Settings(app=AppConfig(name="t", environment="test"), database=DatabaseConfig(url=f"sqlite:///{tmp_path / 's.db'}"))
    store = runtime_settings.RuntimeSettings(tmp_path / "runtime-settings.json")
    monkeypatch.setattr(runtime_settings, "shared", lambda: store)
    from tubeforge.pipeline.orchestrator import PipelineOrchestrator
    runner = PipelineOrchestrator.__new__(PipelineOrchestrator)
    runner.source_clips, runner.artifact_root, runner._load_json_artifact = SourceClipConfig(enabled=True), tmp_path / "artifacts", lambda *a: {"duration_seconds": 600.0}
    job = SimpleNamespace(id="j", request=SimpleNamespace(source_url="https://youtu.be/x", clip_count=2, captions_enabled=True, target_duration_seconds=60, notes=(), source_start_seconds=None, source_length_seconds=None))
    plan = runner._clip_params(job)
    assert plan["direct_sections"] is True and plan["download_connections"] == 4      # on by default
    config = build_engine_config(EngineClipRunner.request(tmp_path, plan))
    assert config.youtube_direct_sections is True and config.youtube_fragment_concurrency == 4
    store.update("clips.direct_sections", False, "test", settings)
    store.update("clips.download_connections", 2, "test", settings)
    config = build_engine_config(EngineClipRunner.request(tmp_path, runner._clip_params(job)))
    assert config.youtube_direct_sections is False and config.youtube_fragment_concurrency == 2
