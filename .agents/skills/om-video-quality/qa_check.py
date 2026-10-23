#!/usr/bin/env python3
"""Deterministic pre-delivery checks for one TubeForge job folder (the failures we have already hit once).

Usage: python .agents/skills/om-video-quality/qa_check.py data/artifacts/<job_id> [--json]
Exit status 1 when any FAIL is reported. WARN items need a human look. This reads artifacts only; it renders,
publishes and approves nothing, and passing it is not creative acceptance (still look at the frames).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

CARD_HEADING_LIMIT = 30          # rendering/animated_card.py
TARGET_TOLERANCE = 0.40          # core/config.py target_duration_tolerance_ratio
SHORTS_SECONDS = (25.0, 45.0)    # reference-short-v1 profile
WORDS_PER_SECOND = (1.9, 3.2)    # Kokoro ~2.3, Piper ~2.7
LOUDNESS = {"reference": (-15.0, -13.0, -1.5), "legacy": (-16.5, -12.5, -1.0)}  # min LUFS, max LUFS, max true peak
STOP = frozenset("a an the and or but so of to in on for with by is are was were be it its this that your you we our at as from".split())


def load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def content(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9']+", text.casefold()) if w not in STOP}


def duration(video: Path) -> float | None:
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
                             capture_output=True, text=True, timeout=30, check=True).stdout.strip()
        return float(out)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def check(job: Path) -> list[tuple[str, str, str]]:
    results: list[tuple[str, str, str]] = []
    add = lambda level, name, detail: results.append((level, name, detail))  # noqa: E731
    request = load(job / "effective_content_request.json") or {}
    package = load(job / "content_package.json")
    if not package:
        return [("FAIL", "script", "content_package.json is missing or unreadable")]
    reference = bool(package.get("reference_short"))
    video = next((p for p in (job / "final.mp4", job / "preview.mp4") if p.is_file()), None)
    narration = " ".join(s.get("narration", "") for s in package.get("script_sections", [])) or \
        " ".join(s.get("vo", "") for s in (package.get("reference_short") or {}).get("scenes", []))
    words = len(narration.split())
    seconds = duration(video) if video else None
    target = float(request.get("target_duration_seconds") or 0)
    if seconds is None:
        add("WARN", "duration", "no video or ffprobe available; duration not checked")
    else:
        if reference:
            ok = SHORTS_SECONDS[0] <= seconds <= SHORTS_SECONDS[1]
            add("PASS" if ok else "FAIL", "duration", f"{seconds:.1f}s, Shorts window {SHORTS_SECONDS[0]:.0f}–{SHORTS_SECONDS[1]:.0f}s")
        elif target:
            ok = abs(seconds - target) <= target * TARGET_TOLERANCE
            add("PASS" if ok else "FAIL", "duration", f"{seconds:.1f}s vs target {target:.0f}s (±{TARGET_TOLERANCE:.0%})")
        if words:
            rate = words / seconds
            ok = WORDS_PER_SECOND[0] <= rate <= WORDS_PER_SECOND[1]
            add("PASS" if ok else "WARN", "speaking-rate", f"{words} words / {seconds:.1f}s = {rate:.2f} words/s (expect {WORDS_PER_SECOND[0]}–{WORDS_PER_SECOND[1]})")
    contract = load(job / "scene_contract.json") or {}
    long_headings = [r.get("heading") for r in contract.get("scenes", contract.get("rows", [])) if r.get("card_cues") and len(r.get("heading") or "") > CARD_HEADING_LIMIT]
    add("FAIL" if long_headings else "PASS", "card-headings", f"{len(long_headings)} animated-card heading(s) over {CARD_HEADING_LIMIT} characters")
    qa = load(job / "final.qa.json") or load(job / "preview.qa.json") or {}
    report = load(job / "quality_report.json") or {}
    loud = ((report.get("reference_qa") or {}).get("loudness")) or None
    if loud:
        low, high, peak = LOUDNESS["reference" if reference else "legacy"]
        ok = low <= loud["input_i"] <= high and loud["input_tp"] <= peak
        add("PASS" if ok else "FAIL", "loudness", f"{loud['input_i']:.1f} LUFS, true peak {loud['input_tp']:.1f} dBTP (window {low}..{high}, peak ≤ {peak})")
    elif not qa:
        add("WARN", "loudness", "no quality report found; loudness not checked")
    meta = package.get("metadata") or {}
    titles = meta.get("title_options") or []
    add("PASS" if titles and all(0 < len(t) <= 100 for t in titles) else "FAIL", "titles", f"{len(titles)} options, each 1–100 characters")
    brief = package.get("thumbnail_brief") or {}
    hook = ""
    if reference:
        first = package["reference_short"]["scenes"][0]
        hook = " ".join([first.get("vo", ""), *(first.get("headline") or [])])
        if len(first.get("vo", "").split()) > 14:
            add("WARN", "hook-length", "the hook narration is over 14 words")
    for text in brief.get("text_options", []):
        overlap = content(text) & content(hook)
        words_in = len(text.split())
        bad = words_in > 3 or (hook and content(text) and len(overlap) / len(content(text)) >= .6)
        add("FAIL" if bad else "PASS", "thumbnail-text", f"{text!r}: {words_in} word(s), {'repeats the hook' if hook and overlap and len(overlap) / max(1, len(content(text))) >= .6 else 'distinct from the hook'}")
    thumb = load(job / "publishing" / "thumbnail.json")
    if thumb:
        path = job / "publishing" / thumb["file"]
        size = path.stat().st_size if path.is_file() else 0
        add("PASS" if 0 < size <= 2_000_000 else "FAIL", "thumbnail-file", f"{thumb['file']} {size} bytes (YouTube limit 2,000,000)")
        text = thumb.get("text") or ""
        if hook and text and len(content(text) & content(hook)) / max(1, len(content(text))) >= .6:
            add("WARN", "thumbnail-vs-frame", "the thumbnail headline repeats the hook text shown on screen; pick a later video moment or other words")
    else:
        add("WARN", "thumbnail-file", "no thumbnail composed yet (open the job on the Publishing page)")
    description = (meta.get("description") or "").strip()
    add("PASS" if description and len(description) <= 5000 and "<" not in description and ">" not in description else "FAIL", "description", f"{len(description)} characters, no angle brackets")
    return results


def main(argv: list[str]) -> int:
    paths = [a for a in argv[1:] if not a.startswith("--")]
    if not paths or not Path(paths[0]).is_dir():
        print(__doc__)
        return 2
    results = check(Path(paths[0]))
    if "--json" in argv:
        print(json.dumps([{"level": l, "check": n, "detail": d} for l, n, d in results], indent=1))
    else:
        for level, name, detail in results:
            print(f"{level:4} {name:18} {detail}")
    return 1 if any(level == "FAIL" for level, _, _ in results) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
