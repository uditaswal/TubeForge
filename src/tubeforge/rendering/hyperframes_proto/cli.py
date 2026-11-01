"""Subprocess wrapper around the real ``hyperframes`` CLI (prototype; see package docstring).

Mirrors the pattern OpenMontage's own wrapper uses (``tools/video/hyperframes_compose.py``,
reviewed in the video-quality review): a bounded-timeout subprocess call, a frame-cache
directory pointed off any tmpfs ``/tmp`` (phase 0's benchmark found this host's own `/tmp` is
a 1.9 GB tmpfs HyperFrames defaults into), and errors surfaced with the tool's own stderr/JSON
rather than swallowed.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path


class HyperFramesError(RuntimeError):
    pass


@contextmanager
def short_scratch(root: Path) -> Iterator[Path]:
    """A short symlink to ``root`` to use as TMPDIR/HOME for Chromium.

    Chromium creates a unix socket inside its profile directory, and a socket path is limited to ~107
    characters. A worker scratch directory under ``/app/data/artifacts/<32-char job id>/...`` plus
    Chromium's profile folder is ~138, so the browser exits at once ("Target closed")."""
    link = Path(tempfile.gettempdir()) / f"hf-{uuid.uuid4().hex[:8]}"
    link.symlink_to(root, target_is_directory=True)
    try:
        yield link
    finally:
        link.unlink(missing_ok=True)


def _env(extra_env: dict[str, str] | None) -> dict[str, str]:
    env = dict(os.environ)
    env.update(extra_env or {})
    return env


def _run(args: list[str], *, cwd: Path, timeout: float, extra_env: dict[str, str] | None,
         cancelled: Callable[[], bool] = lambda: False) -> subprocess.CompletedProcess:
    with tempfile.TemporaryFile(mode="w+t") as stdout, tempfile.TemporaryFile(mode="w+t") as stderr:
        try:
            process = subprocess.Popen(args, cwd=str(cwd), stdout=stdout, stderr=stderr,
                                       text=True, env=_env(extra_env), start_new_session=True)
        except FileNotFoundError as error:
            raise HyperFramesError(f"hyperframes binary not found: {args[0]}") from error
        deadline = time.monotonic() + timeout
        try:
            while process.poll() is None:
                if cancelled():
                    from tubeforge.rendering.shorts.encode import RenderCancelled
                    raise RenderCancelled("HyperFrames render cancelled or worker ownership lost")
                if time.monotonic() > deadline:
                    raise HyperFramesError(f"hyperframes {args[1] if len(args) > 1 else ''} timed out after {timeout:.0f}s")
                time.sleep(.1)
            stdout.seek(0)
            stderr.seek(0)
            return subprocess.CompletedProcess(args, process.returncode, stdout.read(), stderr.read())
        finally:
            if process.poll() is None:
                import signal
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()


def check(project_dir: Path, *, hyperframes_bin: str = "hyperframes", timeout: float = 120,
         extra_env: dict[str, str] | None = None, cancelled: Callable[[], bool] = lambda: False) -> dict:
    """Run ``hyperframes check --json``; raise with its own findings on any error."""
    result = _run([hyperframes_bin, "check", "--json"], cwd=project_dir, timeout=timeout,
                  extra_env=extra_env, cancelled=cancelled)
    try:
        report = json.loads(result.stdout)
    except ValueError as error:
        raise HyperFramesError(f"hyperframes check produced no JSON (exit {result.returncode}): "
                               f"{result.stderr[-2000:]}") from error
    if not report.get("ok", False):
        findings = [f["message"] for group in ("lint", "runtime", "layout", "craft")
                   for f in (report.get(group) or {}).get("findings", []) if f.get("severity") == "error"]
        raise HyperFramesError("hyperframes check failed: " + "; ".join(findings or [str(report)]))
    return report


def render(project_dir: Path, output: Path, *, quality: str = "draft", hyperframes_bin: str = "hyperframes",
          timeout: float = 600, workers: int = 1, extra_env: dict[str, str] | None = None,
          cancelled: Callable[[], bool] = lambda: False) -> None:
    """Render the project's ``index.html`` to a silent MP4 at ``output``."""
    args = [hyperframes_bin, "render", "--quality", quality, "--workers", str(workers),
            "--output", str(output.resolve())]
    result = _run(args, cwd=project_dir, timeout=timeout, extra_env=extra_env, cancelled=cancelled)
    if result.returncode != 0 or not output.is_file():
        raise HyperFramesError(f"hyperframes render failed (exit {result.returncode}): {result.stderr[-4000:] or result.stdout[-4000:]}")
