import os
import time

from tubeforge.core.tempdir import ensure_tempdir


def test_creates_folder_and_removes_only_stale_entries(tmp_path, monkeypatch):
    folder = tmp_path / "scratch"
    folder.mkdir()
    old = folder / "old.bin"; old.write_bytes(b"x")
    old_dir = folder / "old-dir"; old_dir.mkdir(); (old_dir / "f").write_text("x")
    fresh = folder / "fresh.bin"; fresh.write_bytes(b"x")
    past = time.time() - 3 * 86400
    os.utime(old, (past, past)); os.utime(old_dir, (past, past))
    monkeypatch.setenv("TMPDIR", str(folder))
    assert ensure_tempdir() == folder
    assert not old.exists() and not old_dir.exists() and fresh.exists()


def test_creates_missing_folder(tmp_path, monkeypatch):
    target = tmp_path / "a" / "b"
    monkeypatch.setenv("TMPDIR", str(target))
    assert ensure_tempdir() == target and target.is_dir()


def test_without_tmpdir_does_nothing(monkeypatch):
    monkeypatch.delenv("TMPDIR", raising=False)
    assert ensure_tempdir() is None
