"""Operator-editable runtime settings, shared by the web server and the worker.

Values live in ``data/config/runtime-settings.json`` (the ``data`` folder is bind-mounted into every
container), so a change made on the dashboard Settings page applies to the next job without a restart.
Only the settings registered below can be changed, each with a type and a range; everything else stays
in ``config/*.yaml``. The two-attempt allowance per source packet is deliberately not here: it is part of
the safety contract in AGENTS.md.
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

DEFAULT_PATH = Path(os.environ.get("TUBEFORGE_RUNTIME_SETTINGS", "data/config/runtime-settings.json"))
AUDIT_LIMIT = 200


@dataclass(frozen=True)
class Definition:
    key: str
    group: str
    label: str
    help: str
    kind: str                       # "int" | "bool"
    default: Callable[[Any], Any]   # config default, from the loaded Settings
    minimum: int | None = None
    maximum: int | None = None


def _claude_ceiling() -> int:
    """The Claude runner refuses prompts above its own ceiling, so a larger value here would only fail later."""
    return int(os.environ.get("TUBEFORGE_CLAUDE_MAX_PROMPT_CHARS", "90000"))


DEFINITIONS: tuple[Definition, ...] = (
    Definition("prompt.max_chars_claude", "Script prompt size", "Largest Claude script prompt (characters)",
               "The assembled writer prompt may not exceed this. The Claude runner has its own ceiling (90000 unless the "
               "TUBEFORGE_CLAUDE_MAX_PROMPT_CHARS environment variable says otherwise), so values above it are clamped.",
               "int", lambda s: s.pipeline.claude.max_prompt_chars, 20_000, 200_000),
    Definition("prompt.max_chars_codex", "Script prompt size", "Largest Codex script prompt (characters)",
               "Same limit for the Codex writer.", "int", lambda s: s.pipeline.codex.max_prompt_chars, 20_000, 200_000),
    Definition("prompt.auto_trim_sources", "Script prompt size", "Trim long source excerpts to fit",
               "When the prompt would be too large, shorten the longest source excerpts (at a sentence end) while the request "
               "is built, so it is checked before anything is queued. Off means a too-large brief is refused instead.",
               "bool", lambda s: True),
    Definition("prompt.min_chars_per_source", "Script prompt size", "Smallest excerpt kept per source (characters)",
               "Trimming never goes below this. If the sources still do not fit, the brief is refused with the numbers.",
               "int", lambda s: 1_500, 500, 10_000),
    Definition("prompt.margin_chars", "Script prompt size", "Safety margin (characters)",
               "Room left under the limit for the repair and editor passes.", "int", lambda s: 2_500, 0, 20_000),
    Definition("script.require_verified_sources", "Your own scripts", "Require verified sources and independent research",
               "On (the default): a notes-only brief is first researched on the web, every factual claim must trace to a source, and a script is "
               "refused when the evidence is thin. Off: your notes, script or reference transcript are accepted as the evidence, no web research "
               "runs, source-card checks are skipped and the writer is told not to refuse for missing sources. Fewer failures and less spend, but "
               "nothing checks the facts: you vouch for them. Applies to the next job.",
               "bool", lambda s: True),
    Definition("script.exact_by_default", "Your own scripts", "Use every script I provide word for word",
               "When on, any script you give (Studio box, batch `script`/`narration`) is used exactly: the writer only plans the "
               "visuals around it, your wording is forced back in, and the hook/craft/number checks are skipped. Off means a script is "
               "fitted and checked like AI-written text unless the short sets exact itself. The script is re-cut into scenes and the video length follows it. You vouch for the facts.",
               "bool", lambda s: False),
    Definition("generation.auto_retry_rejected", "Retries", "Retry a rejected script automatically",
               "When the writer's script fails validation and the source packet still has an attempt left, queue the next "
               "attempt by itself instead of stopping. It never exceeds the two-attempt allowance.",
               "bool", lambda s: True),
    Definition("reference.use_transcript_as_script", "Reference videos", "Use the reference transcript word for word by default",
               "When on, preparing a Short from a reference starts with \"use the transcript exactly as the script\" selected. Off starts with "
               "fresh AI narration. Either way you can change it for each Short before queueing.",
               "bool", lambda s: False),
    Definition("clips.max_source_minutes", "Clips", "Longest video a clip job reads (minutes)",
               "A longer video is not refused: the job reads the first stretch of this length (or the part you pick on the Clips page) "
               "and says so on the job card. Raise it for long shows; the engine only transcribes the busiest parts, but a long video is a big download.",
               "int", lambda s: s.pipeline.source_clips.max_source_duration_seconds // 60, 10, 720),
    Definition("clips.claude_calls_per_day", "Clips", "Claude calls per day for clip selection",
               "A separate daily allowance for clip jobs, inside the shared 40-call limit. One clip job usually needs two to six calls. "
               "The Claude runner reads this on every request, so a change applies immediately.",
               "int", lambda s: 12, 1, 40),
    Definition("clips.max_download_gb", "Clips", "Largest download for one clip job (GB)",
               "The video is stopped if its download would pass this size. A 4-hour 1080p video is about 6 GB.",
               "int", lambda s: -(-s.pipeline.source_clips.max_download_bytes // 1_000_000_000), 1, 30),
    Definition("clips.direct_sections", "Clips", "Download only the parts the clips need",
               "On: the audio is downloaded first, the AI picks the moments, and only those sections of the video are fetched (minutes instead "
               "of the 30-45 it takes to download a 5 GB show). Off: the whole video is downloaded first. If a section download fails the "
               "job falls back to the whole video by itself.", "bool", lambda s: True),
    Definition("clips.download_connections", "Clips", "Download pieces at the same time",
               "How many pieces of a video are fetched in parallel. Measured on this connection (about 2.4 MB/s) 1 and 4 took the same time, "
               "so the default is 1; raise it only on a faster connection.",
               "int", lambda s: 1, 1, 8),
    Definition("clips.max_clip_seconds", "Clips", "Longest clip (seconds)",
               "No clip is cut longer than this. The Clips page asks for a length per job; the shorter of the two applies.",
               "int", lambda s: int(s.pipeline.source_clips.max_clip_seconds), 10, 900),
    Definition("clips.engaging_only", "Clips", "Transcribe only the parts viewers engaged with",
               "On: only the busiest parts of a long video (peaks in replays, comments, chapters) are transcribed, which is far faster. "
               "Off: the whole video is transcribed, which can take hours on this machine.",
               "bool", lambda s: bool(s.pipeline.source_clips.engaging_only)),
    Definition("clips.signal_windows", "Clips", "Busy parts to transcribe",
               "How many busy parts of a long video are transcribed. More parts find more moments but take longer and use more AI calls.",
               "int", lambda s: 8, 1, 20),
    Definition("clips.signal_window_before", "Clips", "Seconds kept before a busy moment",
               "Setup shown before the peak, so a clip does not start mid-sentence.", "int", lambda s: 60, 10, 300),
    Definition("clips.signal_window_after", "Clips", "Seconds kept after a busy moment",
               "Reaction and payoff kept after the peak.", "int", lambda s: 90, 10, 300),
    Definition("clips.whisper_threads", "Clips", "CPU threads for transcription",
               "More threads transcribe faster but leave less for the website and other jobs. This machine has 4.", "int", lambda s: 4, 1, 8),
    Definition("clips.max_height", "Clips", "Highest video quality to download (pixels tall)",
               "1080 gives the sharpest clips; 720 downloads about half the data and finishes sooner but looks softer when cropped to vertical.",
               "int", lambda s: 1080, 360, 2160),
    Definition("clips.cache_days", "Clips", "Days to keep downloaded videos",
               "Downloads are kept so a retry or a second job on the same video does not download it again. Each can be several GB.",
               "int", lambda s: 7, 1, 60),
    Definition("clips.analysis_window_max_chars", "Clips", "Transcript per AI call (characters)",
               "Neighbouring parts of a long video share one AI call while they fit this size. Larger means fewer calls; the runner refuses a whole request above 48,000.",
               "int", lambda s: 24_000, 4_000, 40_000),
    Definition("clips.inspect_timeout_seconds", "Clips", "Time allowed to look up a video (seconds)",
               "How long the first check of a link may take before the job fails. Raise it on a slow connection.",
               "int", lambda s: int(s.pipeline.source_clips.timeout_seconds), 5, 600),
    Definition("worker.retry_base_seconds", "Retries", "First wait before a retry (seconds)",
               "After a temporary failure the worker waits this long, then twice as long each time, up to the cap below.",
               "int", lambda s: s.worker.retry_base_seconds, 1, 3600),
    Definition("worker.retry_max_seconds", "Retries", "Longest wait between retries (seconds)",
               "The cap on the retry wait.", "int", lambda s: s.worker.retry_max_seconds, 1, 86_400),
    Definition("worker.max_attempts", "Retries", "Worker retries for temporary failures",
               "How many times the worker re-runs a stage after a temporary failure (runner down, timeout, "
               "reservation expired) before the job fails.", "int", lambda s: s.worker.max_attempts, 1, 20),
)
BY_KEY = {definition.key: definition for definition in DEFINITIONS}


class SettingError(ValueError):
    """A setting name or value that is not allowed."""


def _coerce(definition: Definition, value: Any) -> Any:
    if definition.kind == "bool":
        if isinstance(value, bool):
            return value
        raise SettingError(f"{definition.label} must be true or false")
    if isinstance(value, bool) or not isinstance(value, int):
        raise SettingError(f"{definition.label} must be a whole number")
    if definition.minimum is not None and value < definition.minimum or definition.maximum is not None and value > definition.maximum:
        raise SettingError(f"{definition.label} must be between {definition.minimum} and {definition.maximum}")
    return value


class RuntimeSettings:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else DEFAULT_PATH
        self._lock = threading.Lock()
        self._cache: tuple[float, dict] | None = None

    # -- reading ---------------------------------------------------------------------------------
    def _load(self) -> dict:
        try:
            stamp = self.path.stat().st_mtime_ns
        except OSError:
            return {"values": {}, "meta": {}, "audit": []}
        if self._cache and self._cache[0] == stamp:
            return self._cache[1]
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"values": {}, "meta": {}, "audit": []}  # an unreadable file never blocks a job; defaults apply
        data.setdefault("values", {}), data.setdefault("meta", {}), data.setdefault("audit", [])
        self._cache = (stamp, data)
        return data

    def value(self, key: str, default: Any) -> Any:
        """The operator's override when it is valid, otherwise ``default``."""
        definition = BY_KEY.get(key)
        stored = self._load()["values"].get(key)
        if definition is None or stored is None:
            return default
        try:
            return _coerce(definition, stored)
        except SettingError:
            return default

    def snapshot(self, settings: Any) -> list[dict]:
        data = self._load()
        rows = []
        for definition in DEFINITIONS:
            default = definition.default(settings)
            overridden = definition.key in data["values"]
            meta = data["meta"].get(definition.key, {})
            rows.append({
                "key": definition.key, "group": definition.group, "label": definition.label, "help": definition.help,
                "kind": definition.kind, "minimum": definition.minimum, "maximum": definition.maximum,
                "default": default, "value": self.value(definition.key, default), "overridden": overridden,
                "updated_at": meta.get("updated_at"), "updated_by": meta.get("updated_by"),
            })
        return rows

    def audit(self, limit: int = 20) -> list[dict]:
        return list(reversed(self._load()["audit"][-limit:]))

    # -- writing ---------------------------------------------------------------------------------
    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")
        os.replace(temporary, self.path)  # atomic: the worker never reads half a file
        self._cache = None

    def update(self, key: str, value: Any, actor: str, settings: Any) -> dict:
        definition = BY_KEY.get(key)
        if definition is None:
            raise SettingError(f"unknown setting: {key}")
        value = _coerce(definition, value)
        with self._lock:
            data = self._load()
            data = {"values": dict(data["values"]), "meta": dict(data["meta"]), "audit": list(data["audit"])}
            old = data["values"].get(key, definition.default(settings))
            now = datetime.now(UTC).isoformat(timespec="seconds")
            data["values"][key] = value
            data["meta"][key] = {"updated_at": now, "updated_by": actor}
            data["audit"] = (data["audit"] + [{"at": now, "by": actor, "key": key, "old": old, "new": value}])[-AUDIT_LIMIT:]
            self._write(data)
        return next(row for row in self.snapshot(settings) if row["key"] == key)

    def reset(self, key: str, actor: str, settings: Any) -> dict:
        definition = BY_KEY.get(key)
        if definition is None:
            raise SettingError(f"unknown setting: {key}")
        with self._lock:
            data = self._load()
            data = {"values": dict(data["values"]), "meta": dict(data["meta"]), "audit": list(data["audit"])}
            if key in data["values"]:
                now = datetime.now(UTC).isoformat(timespec="seconds")
                old = data["values"].pop(key)
                data["meta"].pop(key, None)
                data["audit"] = (data["audit"] + [{"at": now, "by": actor, "key": key, "old": old, "new": "default"}])[-AUDIT_LIMIT:]
                self._write(data)
        return next(row for row in self.snapshot(settings) if row["key"] == key)


_shared = RuntimeSettings()


def shared() -> RuntimeSettings:
    """The process-wide store (path from TUBEFORGE_RUNTIME_SETTINGS or data/config/runtime-settings.json)."""
    return _shared


def effective_max_prompt_chars(owner: str, configured: int, store: RuntimeSettings | None = None) -> int:
    """The prompt ceiling for a script owner: the operator's override, never above the Claude runner's own ceiling."""
    key = "prompt.max_chars_claude" if owner == "claude" else "prompt.max_chars_codex"
    value = (store or _shared).value(key, configured)
    return min(value, _claude_ceiling()) if owner == "claude" else value
