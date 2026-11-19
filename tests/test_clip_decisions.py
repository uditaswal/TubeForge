from tubeforge.clips import decisions
from tubeforge.clips.signals import choose_windows


def test_records_nothing_without_a_run(tmp_path):
    decisions.end()
    decisions.record("signals", "read")
    assert decisions.read(tmp_path) == []


def test_records_in_order_and_tags_the_clip(tmp_path):
    decisions.begin(tmp_path)
    try:
        decisions.record("signals", "read", "none", heatmap=0)
        decisions.set_clip(2)
        decisions.record("captions", "skipped", "no timed words")
        decisions.set_clip(None)
        decisions.record("render", "done")
    finally:
        decisions.end()
    entries = decisions.read(tmp_path)
    assert [e["outcome"] for e in entries] == ["read", "skipped", "done"]
    assert entries[0]["facts"] == {"heatmap": 0}
    assert entries[1]["clip"] == 2 and "clip" not in entries[2]


def test_a_resumed_run_appends_and_bad_lines_are_skipped(tmp_path):
    decisions.begin(tmp_path)
    decisions.record("a", "one")
    decisions.end()
    (tmp_path / decisions.DECISIONS_FILE).open("a").write("not json\n")
    decisions.begin(tmp_path)
    decisions.record("a", "two")
    decisions.end()
    assert [e["outcome"] for e in decisions.read(tmp_path)] == ["one", "two"]


def test_unwritable_folder_never_raises(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    decisions.begin(blocker / "inside")
    try:
        decisions.record("a", "b")
    finally:
        decisions.end()


def test_signals_without_a_heatmap_say_so_in_the_windows(tmp_path):
    decisions.begin(tmp_path)
    try:
        windows = choose_windows(3600, {"caption_cues": [{"start": 100, "text": "oh my god!"}]}, count=2)
    finally:
        decisions.end()
    assert windows and all(w.end > w.start for w in windows)
