"""Engagement signals for a YouTube video, used to decide *where* to spend Whisper time.

Transcribing a 60-minute stream on a small CPU is the slow, memory-hungry step. Viewers
already told YouTube where the good parts are, so we read that first:

* the "Most replayed" heatmap (100 points over the video; absent on many videos),
* timestamps people write in comments ("31:20 is insane"), weighted by likes,
* chapters,
* the auto-captions: a free, timed, full-length transcript whose pace and excitement (exclamations,
  laughter, "oh my god") mark the loud moments. A weak signal on its own, but it separates the
  candidates when comments or the heatmap are thin.

``choose_windows`` turns them into a few time windows; only those get transcribed.
When the evidence is thin, remaining slots are spread across the video so coverage never
collapses to nothing.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from . import decisions

logger = logging.getLogger(__name__)

_TIMESTAMP = re.compile(r"(?<![\d:])(?:(\d{1,2}):)?(\d{1,2}):(\d{2})(?![\d:])")


@dataclass(frozen=True)
class Window:
    start: float
    end: float
    score: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"start": self.start, "end": self.end, "score": self.score, "reason": self.reason}


def parse_comment_timestamps(text: str, duration: float) -> list[float]:
    """Seconds mentioned as ``m:ss`` / ``h:mm:ss`` in a comment, within the video."""
    found = []
    for hours, minutes, seconds in _TIMESTAMP.findall(text or ""):
        if int(seconds) > 59:
            continue
        total = int(hours or 0) * 3600 + int(minutes) * 60 + int(seconds)
        if 0 <= total <= duration:
            found.append(float(total))
    return found


_EXCITED = re.compile(
    r"\b(oh my god|omg|what the|holy|no way|bro|dude|yo)\b|[!?]{1}|\[(laughter|applause|music|screaming)\]",
    re.IGNORECASE,
)


def caption_excitement(cues: list[dict[str, Any]], bucket: float) -> dict[int, float]:
    """Excitement per bucket from timed caption cues ``{"start": s, "text": str}``.

    Words per second (fast talk) plus excited markers. Silence scores 0, so quiet stretches never win.
    """
    words: dict[int, int] = {}
    excited: dict[int, int] = {}
    for cue in cues:
        text = (cue.get("text") or "").strip()
        if not text:
            continue
        index = int(float(cue.get("start", 0)) // bucket)
        words[index] = words.get(index, 0) + len(text.split())
        excited[index] = excited.get(index, 0) + len(_EXCITED.findall(text))
    scores = {}
    for index, count in words.items():
        pace = count / bucket  # words per second
        scores[index] = pace + 0.6 * excited.get(index, 0)
    return scores


def parse_json3_captions(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Cues from a YouTube ``json3`` caption document (milliseconds -> seconds)."""
    cues = []
    for event in data.get("events") or []:
        segs = event.get("segs") or []
        text = "".join(seg.get("utf8", "") for seg in segs).replace("\n", " ").strip()
        if text:
            cues.append({"start": float(event.get("tStartMs", 0)) / 1000.0, "text": text})
    return cues


def _fetch_caption_cues(info: dict[str, Any]) -> list[dict[str, Any]]:
    """Auto-caption cues, or ``[]``: YouTube often answers caption URLs with HTTP 429."""
    import urllib.request

    tracks = info.get("automatic_captions") or {}
    language = next((k for k in tracks if k == "en" or k.startswith("en")), None)
    entry = next((f for f in tracks.get(language or "", []) if f.get("ext") == "json3"), None)
    if not entry:
        decisions.record("signals", "captions-missing", "this video has no English auto-captions to read the pace of speech from")
        return []
    try:
        request = urllib.request.Request(entry["url"], headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=30) as response:
            return parse_json3_captions(json.load(response))
    except Exception as error:
        logger.info("Auto-captions unavailable (%s); using comments, heatmap and chapters only", error)
        decisions.record("signals", "captions-missing", "the auto-captions could not be downloaded (often a rate limit)", error=str(error)[:160])
        return []


def _bucket_scores(duration: float, signals: dict[str, Any], bucket: float) -> list[tuple[float, float, list[str]]]:
    """Per-bucket ``(center_seconds, score, reasons)`` from every available signal.

    Each signal is normalised to 0..1 so none dominates by units alone; the heatmap is
    the strongest evidence, then comments, then chapter starts.
    """
    count = max(1, int(duration // bucket) + 1)
    scores = [0.0] * count
    reasons: list[set[str]] = [set() for _ in range(count)]

    def add(index: int, value: float, reason: str) -> None:
        if 0 <= index < count and value > 0:
            scores[index] += value
            reasons[index].add(reason)

    heatmap = signals.get("heatmap") or []
    if heatmap:
        peak = max((float(p.get("value", 0)) for p in heatmap), default=0.0) or 1.0
        for point in heatmap:
            mid = (float(point["start_time"]) + float(point["end_time"])) / 2
            add(int(mid // bucket), 3.0 * float(point.get("value", 0)) / peak, "most-replayed")

    comment_weight: dict[int, float] = {}
    for comment in signals.get("comments") or []:
        likes = int(comment.get("like_count") or 0)
        weight = 1.0 + min(likes, 500) ** 0.5 / 5  # one liked comment beats a few plain ones, bounded
        for second in parse_comment_timestamps(comment.get("text", ""), duration):
            index = int(second // bucket)
            comment_weight[index] = comment_weight.get(index, 0.0) + weight
    if comment_weight:
        top = max(comment_weight.values())
        for index, weight in comment_weight.items():
            add(index, 2.0 * weight / top, "comments")

    caption_scores = caption_excitement(signals.get("caption_cues") or [], bucket)
    if caption_scores:
        top = max(caption_scores.values()) or 1.0
        for index, value in caption_scores.items():
            add(index, 1.0 * value / top, "captions")

    for chapter in signals.get("chapters") or []:
        add(int(float(chapter["start_time"]) // bucket), 0.5, "chapter")

    return [((i + 0.5) * bucket, scores[i], sorted(reasons[i])) for i in range(count)]


def choose_windows(
    duration: float,
    signals: dict[str, Any],
    *,
    count: int,
    before: float = 60.0,
    after: float = 90.0,
    bucket: float = 30.0,
    window: Optional[tuple[float, float]] = None,
) -> list[Window]:
    """The ``count`` best windows (merged when they overlap), in time order.

    With ``window=(start, end)`` only that part of the video is considered: windows are clamped to it and the
    even spread fills it rather than the whole video.

    A peak at ``t`` yields ``[t - before, t + after]``: a reaction comes after the
    moment people point at, but the setup comes before it.
    """
    if duration <= 0 or count <= 0:
        return []
    low, high = (0.0, duration) if window is None else (max(0.0, window[0]), min(duration, window[1]))
    if high - low <= 0:
        return []

    ranked = sorted(
        (b for b in _bucket_scores(duration, signals, bucket) if b[1] > 0 and low <= b[0] <= high),
        key=lambda b: -b[1],
    )
    picked: list[Window] = []
    for center, score, reasons in ranked:
        start, end = max(low, center - before), min(high, center + after)
        # Skip a peak whose window mostly repeats one we already have.
        if any(min(end, w.end) - max(start, w.start) > 0.5 * (end - start) for w in picked):
            continue
        picked.append(Window(start, end, score, "+".join(reasons)))
        if len(picked) >= count:
            break

    # Not enough evidence: spread the rest evenly across the uncovered video.
    if len(picked) < count:
        slots = count - len(picked)
        span = before + after
        for i in range(slots):
            center = low + (high - low) * (i + 0.5) / slots
            start, end = max(low, center - span / 2), min(high, center + span / 2)
            if any(min(end, w.end) - max(start, w.start) > 0.5 * (end - start) for w in picked):
                continue
            picked.append(Window(start, end, 0.0, "spread"))

    return merge_windows(sorted(picked, key=lambda w: w.start))


def merge_windows(windows: list[Window], gap: float = 5.0) -> list[Window]:
    """Join windows that overlap or nearly touch, keeping the best score and every reason."""
    merged: list[Window] = []
    for window in sorted(windows, key=lambda w: w.start):
        if merged and window.start <= merged[-1].end + gap:
            last = merged[-1]
            reasons = "+".join(dict.fromkeys((last.reason + "+" + window.reason).split("+")))
            merged[-1] = Window(last.start, max(last.end, window.end), max(last.score, window.score), reasons)
        else:
            merged.append(window)
    return merged


# ---- fetching ----------------------------------------------------------------


def _js_runtime_opts() -> dict[str, Any]:
    """YouTube's n-challenge needs a JS runtime: deno (the Docker image) or node."""
    if shutil.which("deno"):
        return {}
    if shutil.which("node"):
        return {"js_runtimes": {"node": {}}, "remote_components": ["ejs:github"]}
    return {}


def fetch_youtube_signals(url: str, *, max_comments: int = 300) -> dict[str, Any]:
    """Heatmap, chapters and timestamped top comments, with no media download."""
    import yt_dlp

    options: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "getcomments": True,
        "extractor_args": {"youtube": {"max_comments": [f"{max_comments},all,100,0"], "comment_sort": ["top"]}},
        **_js_runtime_opts(),
    }
    from .ytdlp_options import cookie_options
    options.update(cookie_options())
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)
    return {
        "video_id": info.get("id"),
        "title": info.get("title"),
        "duration": float(info.get("duration") or 0),
        "heatmap": info.get("heatmap") or [],
        "chapters": info.get("chapters") or [],
        "caption_cues": _fetch_caption_cues(info),
        "comments": [
            {"text": c.get("text", ""), "like_count": c.get("like_count") or 0}
            for c in (info.get("comments") or [])
            if _TIMESTAMP.search(c.get("text") or "")
        ],
    }


def load_or_fetch_signals(url: str, cache_file: Path) -> Optional[dict[str, Any]]:
    """Signals cached beside the media; ``None`` when they cannot be fetched."""
    try:
        if cache_file.exists():
            return json.loads(cache_file.read_text())
    except (OSError, json.JSONDecodeError):
        pass
    try:
        signals = fetch_youtube_signals(url)
    except Exception as error:  # network, rate limit, extractor change: never fail the task
        logger.warning("Could not fetch engagement signals (%s); falling back to spread windows", error)
        decisions.record("signals", "unavailable", "viewer signals could not be fetched, so parts are spread evenly instead", error=str(error)[:160])
        return None
    try:
        cache_file.write_text(json.dumps(signals))
    except OSError:
        pass
    return signals
