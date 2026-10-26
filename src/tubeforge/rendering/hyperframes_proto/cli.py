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
from pathlib import Path


class HyperFramesError(RuntimeError):
    pass


def _env(extra_env: dict[str, str] | None) -> dict[str, str]:
    env = dict(os.environ)
    env.update(extra_env or {})
    return env


def _run(args: list[str], *, cwd: Path, timeout: float, extra_env: dict[str, str] | None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(args, cwd=str(cwd), capture_output=True, text=True, timeout=timeout,
                              env=_env(extra_env), check=False)
    except FileNotFoundError as error:
        raise HyperFramesError(f"hyperframes binary not found: {args[0]}") from error
    except subprocess.TimeoutExpired as error:
        raise HyperFramesError(f"hyperframes {args[1] if len(args) > 1 else ''} timed out after {timeout:.0f}s") from error


def check(project_dir: Path, *, hyperframes_bin: str = "hyperframes", timeout: float = 120,
         extra_env: dict[str, str] | None = None) -> dict:
    """Run ``hyperframes check --json``; raise with its own findings on any error."""
    result = _run([hyperframes_bin, "check", "--json"], cwd=project_dir, timeout=timeout, extra_env=extra_env)
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
          timeout: float = 600, workers: int = 1, extra_env: dict[str, str] | None = None) -> None:
    """Render the project's ``index.html`` to a silent MP4 at ``output``."""
    args = [hyperframes_bin, "render", "--quality", quality, "--workers", str(workers),
            "--output", str(output.resolve())]
    result = _run(args, cwd=project_dir, timeout=timeout, extra_env=extra_env)
    if result.returncode != 0 or not output.is_file():
        raise HyperFramesError(f"hyperframes render failed (exit {result.returncode}): {result.stderr[-4000:] or result.stdout[-4000:]}")
