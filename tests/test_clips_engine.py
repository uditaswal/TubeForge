"""ClipEngine.run end to end with fake media: state, resume, atomic clips and cancellation."""
import asyncio
from pathlib import Path

import pytest

from tubeforge.clips import engine as engine_module
from tubeforge.clips.cancellation import TaskCancelled
from tubeforge.clips.engine import ClipEngine, ClipRequest, FileClipStore
from tubeforge.clips.services.video_service import VideoService


def segments(count):
    return [{"start_time": f"00:{i * 20:02d}", "end_time": f"00:{i * 20 + 15:02d}", "virality_score": 80 - i} for i in range(count)]


@pytest.fixture
def fake_media(monkeypatch, tmp_path):
    calls = {"analysis": 0, "render": []}
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")

    async def process_video_complete(**kwargs):
        calls["analysis"] += 1
        await kwargs["checkpoint_callback"]({"segments": segments(3)})
        await kwargs["progress_callback"](40, "Analyzing...", "processing")
        return {"video_path": str(source), "segments_to_render": segments(3), "segments": segments(3), "transcript": "words",
                "analysis_json": "{}", "summary": "s", "key_topics": ["t"]}

    async def create_single_clip(video_path, segment, index, output_dir, **kwargs):
        calls["render"].append(index)
        target = Path(output_dir) / f"raw-{index}.mp4"
        target.write_bytes(b"clip%d" % index)
        target.with_suffix(".source_map.json").write_text("{}")
        return {"path": str(target), "filename": target.name, "start_time": "00:00", "end_time": "00:15", "duration": 15.0, "text": "t"}

    monkeypatch.setattr(VideoService, "process_video_complete", staticmethod(process_video_complete))
    monkeypatch.setattr(VideoService, "create_single_clip", staticmethod(create_single_clip))
    monkeypatch.setattr(engine_module, "load_time_map", lambda path: None)
    monkeypatch.setattr(ClipEngine, "_cleanup_source", staticmethod(lambda path, request: None))
    return calls


def request(tmp_path, count=3):
    return ClipRequest(url="https://www.youtube.com/watch?v=abcdefghijk", work_dir=tmp_path / "work", clip_count=count)


def test_run_promotes_every_clip_and_reports_progress(fake_media, tmp_path):
    store = FileClipStore(tmp_path / "state")
    seen = []
    done = []

    async def progress(percent, message):
        seen.append(percent)

    async def on_clip(index, total, info):
        done.append((index, total, Path(info["path"]).name))

    result = asyncio.run(ClipEngine(store).run(request(tmp_path), progress=progress, on_clip=on_clip))
    names = sorted(p.name for p in (tmp_path / "work" / "clips").iterdir())
    assert names == ["clip-01.mp4", "clip-01.source_map.json", "clip-02.mp4", "clip-02.source_map.json", "clip-03.mp4", "clip-03.source_map.json"]
    assert [Path(c["path"]).name for c in result.clips] == ["clip-01.mp4", "clip-02.mp4", "clip-03.mp4"]
    assert done == [(0, 3, "clip-01.mp4"), (1, 3, "clip-02.mp4"), (2, 3, "clip-03.mp4")]
    assert seen[-1] == 100 and seen == sorted(seen)
    assert not (tmp_path / "work" / "scratch").exists()


def test_clip_count_limits_the_clips(fake_media, tmp_path):
    result = asyncio.run(ClipEngine(FileClipStore(tmp_path / "state")).run(request(tmp_path, count=2)))
    assert len(result.clips) == 2 and fake_media["render"] == [0, 1]


def test_cancel_mid_run_leaves_no_partial_clip_and_a_retry_renders_only_the_rest(fake_media, tmp_path):
    store = FileClipStore(tmp_path / "state")

    async def cancel_after_first_clip():
        return len(fake_media["render"]) >= 2  # the second clip is rendered, then cancellation lands

    with pytest.raises(TaskCancelled):
        asyncio.run(ClipEngine(store).run(request(tmp_path), should_cancel=cancel_after_first_clip))
    clips = tmp_path / "work" / "clips"
    assert sorted(p.name for p in clips.glob("*.mp4")) == ["clip-01.mp4"]
    assert not (tmp_path / "work" / "scratch").exists()

    fake_media["render"].clear()
    result = asyncio.run(ClipEngine(store).run(request(tmp_path)))
    assert fake_media["render"] == [1, 2]  # clip 1 was kept, never duplicated
    assert result.resumed_clips == 1 and len(result.clips) == 3


def test_a_render_failure_keeps_finished_clips_and_raises(fake_media, tmp_path, monkeypatch):
    original = VideoService.create_single_clip

    async def flaky(video_path, segment, index, output_dir, **kwargs):
        return None if index == 1 else await original(video_path, segment, index, output_dir, **kwargs)

    monkeypatch.setattr(VideoService, "create_single_clip", staticmethod(flaky))
    with pytest.raises(ValueError, match="clip 2"):
        asyncio.run(ClipEngine(FileClipStore(tmp_path / "state")).run(request(tmp_path)))
    assert [p.name for p in (tmp_path / "work" / "clips").glob("*.mp4")] == ["clip-01.mp4"]


def test_a_crashed_attempts_scratch_files_are_removed_at_the_next_start(fake_media, tmp_path):
    scratch = tmp_path / "work" / "scratch"
    scratch.mkdir(parents=True)
    (scratch / "half.mp4").write_bytes(b"partial")
    asyncio.run(ClipEngine(FileClipStore(tmp_path / "state")).run(request(tmp_path, count=1)))
    assert not scratch.exists()


def test_a_finished_analysis_is_not_repeated_on_retry(fake_media, tmp_path):
    store = FileClipStore(tmp_path / "state")
    asyncio.run(ClipEngine(store).run(request(tmp_path, count=1)))
    asyncio.run(ClipEngine(store).run(request(tmp_path, count=1)))
    assert fake_media["analysis"] == 1


def test_the_cached_transcript_and_analysis_are_reused_when_the_source_is_gone(fake_media, tmp_path, monkeypatch):
    store = FileClipStore(tmp_path / "state")
    asyncio.run(ClipEngine(store).run(request(tmp_path, count=1)))
    (tmp_path / "source.mp4").unlink()  # the download was cleaned up; the analysis must be redone from the cache
    seen = {}
    original = VideoService.process_video_complete
    source = tmp_path / "source.mp4"

    async def spy(**kwargs):
        seen["transcript"] = kwargs["cached_transcript"]
        seen["analysis"] = kwargs["cached_analysis_json"]
        source.write_bytes(b"source")
        return await original(**kwargs)

    monkeypatch.setattr(VideoService, "process_video_complete", staticmethod(spy))
    asyncio.run(ClipEngine(store).analyze(request(tmp_path, count=1)))
    assert seen == {"transcript": "words", "analysis": "{}"}


def test_request_validation():
    with pytest.raises(ValueError):
        ClipRequest(url="https://youtu.be/x", work_dir=Path("/tmp/x"), clip_count=0)
    with pytest.raises(ValueError):
        ClipRequest(url="https://youtu.be/x", work_dir=Path("/tmp/x"), clip_count=13)
