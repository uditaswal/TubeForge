"""A download or render can outlast the lease; the guard must be polled while a long stage runs."""
import asyncio
import time
from pathlib import Path

from tubeforge.core.config import SourceClipConfig
from tubeforge.pipeline.clip_runs import EngineClipRunner


class SlowEngine:
    async def analyze(self, request, **kwargs):
        await asyncio.sleep(0.6)  # one blocking stage, longer than several keepalive intervals
        return type("A", (), {"video_path": "v.mp4", "segments": [{}], "summary": None, "key_topics": None})()


def test_the_guard_is_polled_throughout_a_long_stage_and_polling_stops_afterwards(tmp_path: Path, monkeypatch):
    runner = EngineClipRunner(SourceClipConfig(enabled=True), keepalive_seconds=0.1)
    monkeypatch.setattr(runner, "_engine", lambda work_dir: SlowEngine())
    monkeypatch.setattr(EngineClipRunner, "request", staticmethod(lambda work_dir, params: object()))
    polls = []
    runner.analyze("job", tmp_path, {}, lambda: polls.append(time.monotonic()) or False)
    during = len(polls)
    assert during >= 4
    time.sleep(0.4)
    assert len(polls) == during  # the keepalive thread ends with the stage
