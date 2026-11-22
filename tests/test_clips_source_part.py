"""A video longer than the limit is trimmed or sliced instead of refused; the limits are editable settings."""
from pathlib import Path

import pytest

from tubeforge.clips.engine import ClipRequest, build_engine_config, clip_cache_key
from tubeforge.clips.signals import choose_windows
from tubeforge.core.config import SourceClipConfig
from tubeforge.core.errors import ProviderValidationError
from tubeforge.domain.contracts import ContentRequest, SourceReference
from tubeforge.domain.states import JobState
from tubeforge.pipeline.orchestrator import PipelineOrchestrator


def test_windows_stay_inside_the_chosen_part_even_when_the_best_peaks_are_elsewhere():
    signals = {"heatmap": [{"start_time": 100.0, "end_time": 160.0, "value": 1.0}, {"start_time": 6000.0, "end_time": 6060.0, "value": 0.9}], "comment_timestamps": [120.0, 6030.0]}
    windows = choose_windows(7200.0, signals, count=3, window=(5400.0, 7200.0))
    assert windows and all(5400.0 <= w.start and w.end <= 7200.0 for w in windows)
    assert any(w.start <= 6030.0 <= w.end for w in windows)  # the peak inside the part is used
    assert choose_windows(7200.0, signals, count=3, window=(7300.0, 7400.0)) == []


def test_the_engine_reads_only_the_part_and_ignores_the_whole_videos_length():
    request = ClipRequest(url="https://youtu.be/x", work_dir=Path("/tmp/x"), max_video_duration=5400, source_window=(3600.0, 7200.0))
    config = build_engine_config(request)
    assert config.source_window == (3600.0, 7200.0) and config.max_video_duration >= 86_400
    other = ClipRequest(url="https://youtu.be/x", work_dir=Path("/tmp/x"), max_video_duration=5400, source_window=(0.0, 3600.0))
    assert clip_cache_key(request) != clip_cache_key(other)  # a different part never reuses another part's analysis


def _orchestrator_with(limit_minutes=240):
    runner = PipelineOrchestrator.__new__(PipelineOrchestrator)
    runner.source_clips = SourceClipConfig(enabled=True, max_source_duration_seconds=limit_minutes * 60)
    return runner


def _request(**extra):
    return ContentRequest(topic="A source", angle="clips", target_duration_seconds=30, language="en", audience="general", prompt_version="source-clip-v1", sources=(SourceReference(source_id="source-video", url="https://example.com/video", title="A source"),), review_mode="auto", production_mode="source_clip", source_url="https://example.com/video", clip_count=2, **extra)


class _Job:
    def __init__(self, **extra):
        self.request = _request(**extra)
        self.id = "job"


def test_a_video_longer_than_the_limit_is_trimmed_to_its_first_stretch():
    runner = _orchestrator_with(240)
    assert runner._clip_window(_Job(), 5 * 3600.0, 4 * 3600) == ([0.0, 14400.0], True)
    assert runner._clip_window(_Job(), 3 * 3600.0, 4 * 3600) == (None, False)  # fits: the whole video, no note


def test_a_chosen_start_and_length_pick_the_part_and_are_capped_by_the_limit():
    runner = _orchestrator_with(240)
    window, trimmed = runner._clip_window(_Job(source_start_seconds=3900, source_length_seconds=1800), 5 * 3600.0, 4 * 3600)
    assert window == [3900.0, 5700.0] and trimmed is False
    window, _ = runner._clip_window(_Job(source_start_seconds=3600), 5 * 3600.0, 2 * 3600)
    assert window == [3600.0, 10800.0]  # length defaults to the limit
    assert runner._clip_window(_Job(source_start_seconds=100), None, 3600) == ([100.0, 3700.0], False)  # unknown length: trust the pick


def test_a_start_after_the_end_of_the_video_is_refused_with_a_reason():
    with pytest.raises(ProviderValidationError, match="after the end"):
        _orchestrator_with()._clip_window(_Job(source_start_seconds=20_000), 3600.0, 14400)


def test_the_limits_are_settings_with_the_config_as_default(tmp_path, monkeypatch):
    from tubeforge.core import runtime_settings
    runner = _orchestrator_with(240)
    monkeypatch.setattr(runtime_settings, "shared", lambda: runtime_settings.RuntimeSettings(tmp_path / "empty.json"))  # not the machine's own overrides
    assert runner._clip_limits() == (240 * 60, 6_000_000_000)
    assert {"clips.max_source_minutes", "clips.max_download_gb"} <= set(runtime_settings.BY_KEY)
    from tubeforge.core.config import AppConfig, DatabaseConfig, Settings
    settings = Settings(app=AppConfig(name="t", environment="test"), database=DatabaseConfig(url=f"sqlite:///{tmp_path / 's.db'}"))
    store = runtime_settings.RuntimeSettings(tmp_path / "settings.json")
    monkeypatch.setattr(runtime_settings, "shared", lambda: store)
    store.update("clips.max_source_minutes", 360, "test", settings)
    assert runner._clip_limits()[0] == 360 * 60


def test_the_clip_request_carries_start_and_length():
    request = _request(source_start_seconds=60, source_length_seconds=600)
    assert (request.source_start_seconds, request.source_length_seconds) == (60, 600)
    assert "source_start_seconds" not in _request().model_dump()  # omitted when unset, so existing jobs are unchanged


def test_the_operators_guidance_reaches_the_ai_and_separates_cached_analyses(tmp_path):
    from tubeforge.clips.engine import ClipRequest, clip_cache_key
    from tubeforge.pipeline.clip_runs import EngineClipRunner
    plain = ClipRequest(url="https://youtu.be/x", work_dir=tmp_path)
    steered = ClipRequest(url="https://youtu.be/x", work_dir=tmp_path, instructions="find scenes about caching")
    assert clip_cache_key(plain) != clip_cache_key(steered)  # a different request never reuses the other's analysis
    plan = {"source_url": "https://youtu.be/x", "clip_count": 2, "captions": True, "instructions": "find scenes about caching"}
    assert EngineClipRunner.request(tmp_path, plan).instructions == "find scenes about caching"


def test_the_instructions_are_stored_as_the_jobs_notes_and_passed_in_the_plan(tmp_path):
    runner = _orchestrator_with()
    runner.artifact_root = tmp_path
    runner._load_json_artifact = lambda *args: {"duration_seconds": 600.0}
    assert runner._clip_params(_Job(notes=("find scenes about caching",)))["instructions"] == "find scenes about caching"
    assert runner._clip_params(_Job())["instructions"] is None
