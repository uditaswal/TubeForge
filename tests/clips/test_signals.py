from tubeforge.clips.media.transcription import merge_whisper_windows
from tubeforge.clips.signals import Window, choose_windows, merge_windows, parse_comment_timestamps


def test_parse_comment_timestamps_bounds_and_formats():
    text = "31:20 is insane, also 1:02:03 and 99:99 and v1.2:3 plus 12:5"
    assert parse_comment_timestamps(text, duration=7200) == [1880.0, 3723.0]
    assert parse_comment_timestamps("31:20", duration=600) == []  # past the end


def test_heatmap_beats_weak_comments_and_windows_lead_the_peak():
    signals = {
        "heatmap": [{"start_time": i * 36.0, "end_time": (i + 1) * 36.0, "value": 1.0 if i == 50 else 0.1} for i in range(100)],
        "comments": [{"text": "10:00", "like_count": 0}],
    }
    windows = choose_windows(3600, signals, count=2, before=60, after=90)
    best = max(windows, key=lambda w: w.score)
    assert best.start < 1818 < best.end and "most-replayed" in best.reason
    assert (best.end - best.start) <= 150 + 30  # one bucket of slack


def test_comment_timestamps_pick_the_test_video_pattern():
    # What the real top comments of the 60-minute test stream looked like (minutes 31, 25, 11).
    comments = [{"text": f"{m}:10 😂", "like_count": 40} for m in (31, 31, 31, 25, 25, 11)]
    windows = choose_windows(3588, {"comments": comments}, count=3, before=60, after=90)
    starts = [round(w.start / 60) for w in windows]
    assert any(abs(s - 30) <= 1 for s in starts) and any(abs(s - 24) <= 1 for s in starts)
    assert all("comments" in w.reason for w in windows if w.score > 0)


def test_no_evidence_spreads_windows_across_the_video():
    windows = choose_windows(3600, {}, count=4)
    assert len(windows) == 4 and all(w.reason == "spread" for w in windows)
    assert windows[0].start < 900 and windows[-1].end > 2700 and windows[-1].end <= 3600


def test_windows_merge_and_stay_inside_the_video():
    merged = merge_windows([Window(0, 100, 1, "a"), Window(103, 200, 2, "b"), Window(500, 600, 1, "c")])
    assert [(w.start, w.end) for w in merged] == [(0, 200), (500, 600)]
    assert merged[0].score == 2 and merged[0].reason == "a+b"
    assert all(0 <= w.start and w.end <= 90 for w in choose_windows(90, {}, count=3))


def test_merge_whisper_windows_orders_and_drops_overlap_duplicates():
    a = {"segments": [{"text": "one", "start": 10.0, "end": 12.0, "words": []}, {"text": "two", "start": 12.0, "end": 14.0, "words": []}], "language": "en"}
    b = {"segments": [{"text": "two again", "start": 13.0, "end": 14.5, "words": []}, {"text": "three", "start": 20.0, "end": 22.0, "words": []}], "language": "en"}
    merged = merge_whisper_windows([b, a])
    assert [s["text"] for s in merged["segments"]] == ["one", "two", "three"]
    assert merged["language"] == "en"


def test_captions_mark_the_loud_moment_and_silence_never_wins():
    from tubeforge.clips.signals import caption_excitement, parse_json3_captions

    doc = {"events": [
        {"tStartMs": 10_000, "segs": [{"utf8": "so anyway we walk in"}]},
        {"tStartMs": 40_000, "segs": [{"utf8": "OH MY GOD "}, {"utf8": "what the hell was that!"}]},
        {"tStartMs": 42_000, "segs": [{"utf8": "[Laughter]"}]},
        {"tStartMs": 90_000, "segs": [{"utf8": "\n"}]},
    ]}
    cues = parse_json3_captions(doc)
    assert [c["start"] for c in cues] == [10.0, 40.0, 42.0]
    scores = caption_excitement(cues, bucket=30.0)
    assert max(scores, key=scores.get) == 1 and 3 not in scores  # the 30-60 s bucket; the empty cue is dropped


def test_captions_alone_can_pick_windows_when_nothing_else_exists():
    cues = [{"start": 600.0 + i, "text": "no way!! oh my god"} for i in range(20)]
    windows = choose_windows(3600, {"caption_cues": cues}, count=1)
    assert windows[0].start < 640 < windows[0].end and "captions" in windows[0].reason
