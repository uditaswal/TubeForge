"""Every new Settings value reaches the code that uses it, and the page lists everything else read-only."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.test_clips_api import _client, _login
from tubeforge.clips.engine import ClipRequest, build_engine_config
from tubeforge.core import runtime_settings
from tubeforge.core.config import AppConfig, DatabaseConfig, Settings, SourceClipConfig
from tubeforge.domain.contracts import ContentRequest, SourceReference
from tubeforge.pipeline.clip_runs import EngineClipRunner
from tubeforge.pipeline.orchestrator import PipelineOrchestrator

CLIP_KEYS = ["clips.max_clip_seconds", "clips.engaging_only", "clips.signal_windows", "clips.signal_window_before", "clips.signal_window_after",
             "clips.whisper_threads", "clips.max_height", "clips.cache_days", "clips.analysis_window_max_chars", "clips.inspect_timeout_seconds",
             "worker.retry_base_seconds", "worker.retry_max_seconds"]


def test_every_new_setting_is_defined_with_a_range_and_help():
    for key in CLIP_KEYS:
        definition = runtime_settings.BY_KEY[key]
        assert definition.help and definition.label
        assert definition.kind == "bool" or definition.minimum < definition.maximum


def _job():
    request = ContentRequest(topic="A", angle="clips", target_duration_seconds=60, language="en", audience="general", prompt_version="source-clip-v1", sources=(SourceReference(source_id="s", url="https://example.com/v", title="A"),), review_mode="auto", production_mode="source_clip", source_url="https://example.com/v", clip_count=2)
    return type("J", (), {"request": request, "id": "job"})()


def test_the_operators_values_reach_the_clip_plan_and_the_engine(tmp_path, monkeypatch):
    settings = Settings(app=AppConfig(name="t", environment="test"), database=DatabaseConfig(url=f"sqlite:///{tmp_path / 's.db'}"))
    store = runtime_settings.RuntimeSettings(tmp_path / "runtime-settings.json")
    monkeypatch.setattr(runtime_settings, "shared", lambda: store)
    for key, value in {"clips.max_clip_seconds": 45, "clips.engaging_only": False, "clips.signal_windows": 5, "clips.signal_window_before": 30,
                       "clips.signal_window_after": 40, "clips.whisper_threads": 2, "clips.max_height": 720, "clips.cache_days": 3,
                       "clips.analysis_window_max_chars": 12_000}.items():
        store.update(key, value, "test", settings)
    runner = PipelineOrchestrator.__new__(PipelineOrchestrator)
    runner.source_clips = SourceClipConfig(enabled=True)
    runner.artifact_root = tmp_path / "artifacts"
    runner._load_json_artifact = lambda *args: {"duration_seconds": 600.0}
    plan = runner._clip_params(_job())
    assert plan["max_clip_seconds"] == 45 and plan["engaging_only"] is False and plan["signal_windows"] == 5
    request = EngineClipRunner.request(tmp_path, plan)
    config = build_engine_config(request)
    assert (config.signal_windows, config.signal_window_before, config.signal_window_after) == (5, 30, 40)
    assert (config.whisper_threads, config.youtube_max_height, config.analysis_window_max_chars) == (2, 720, 12_000)
    assert config.youtube_source_cache_ttl_seconds == 3 * 86_400 and config.analysis_strategy == "full"


def test_the_worker_backoff_follows_the_settings(tmp_path, monkeypatch):
    from tubeforge.core.config import WorkerConfig
    from tubeforge.workers.service import WorkerService
    store = runtime_settings.RuntimeSettings(tmp_path / "runtime-settings.json")
    monkeypatch.setattr(runtime_settings, "shared", lambda: store)
    worker = WorkerService.__new__(WorkerService)
    worker.config = WorkerConfig()
    assert worker._retry_waits() == (30, 900)
    settings = Settings(app=AppConfig(name="t", environment="test"), database=DatabaseConfig(url=f"sqlite:///{tmp_path / 's.db'}"))
    store.update("worker.retry_base_seconds", 5, "test", settings)
    store.update("worker.retry_max_seconds", 60, "test", settings)
    assert worker._retry_waits() == (5, 60)


def test_the_reference_lists_the_rest_read_only_without_secrets_and_with_locks(tmp_path):
    app = _client(tmp_path)
    with TestClient(app) as client:
        _login(app, client)
        data = client.get("/api/runtime-settings/reference").json()
        rows = {row["key"]: row for group in data["groups"] for row in group["rows"]}
        assert rows["pipeline.claude.invocation_limit"]["locked"] and "safety contract" in rows["pipeline.claude.invocation_limit"]["how"]
        assert rows["worker.max_attempts"]["editable_here"] and "without a restart" in rows["worker.max_attempts"]["how"]
        assert rows["worker.lease_seconds"]["how"].startswith("Edit config/production.yaml")
        assert not any(".presets." in key for key in rows)
        assert all(row["value"] in ("set", "not set") for key, row in rows.items() if any(w in key.lower() for w in ("key", "token", "secret", "password", "encryption")))
        assert any("TUBEFORGE_CLAUDE_MAX_CALLS_PER_DAY" in item["names"] for item in data["environment"])
        page = client.get("/settings").text
        assert "Everything else (read-only)" in page and "loadReference" in page
