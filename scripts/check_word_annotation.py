"""Compare independent audio-only word marks with one rendered scene's timing.

The candidate origin is explicit because pipeline word times are job-global while
the annotation page plays a scene-local WAV. Never infer that offset from the
first candidate word: a scene may have leading silence or a pre-roll caption.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import wave
from pathlib import Path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _word_rows(value: object, *, name: str) -> list[dict[str, object]]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{name} must be a nonempty word list")
    rows: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError(f"{name} contains a non-object word")
        rows.append(item)
    return rows


def compare(
    annotation_path: Path,
    candidate_path: Path,
    manifest_path: Path,
    audio_path: Path,
    video_path: Path,
    *,
    candidate_origin_seconds: float,
) -> dict[str, object]:
    if not math.isfinite(candidate_origin_seconds) or candidate_origin_seconds < 0:
        raise ValueError("candidate origin must be a finite, nonnegative scene start time")
    annotation = json.loads(annotation_path.read_text())
    if not isinstance(annotation, dict) or annotation.get("kind") != "independent_manual_word_annotation_v1":
        raise ValueError("unsupported independent annotation schema")
    if not isinstance(annotation.get("annotator"), str) or not annotation["annotator"].strip():
        raise ValueError("independent annotation requires an annotator")
    if annotation.get("method") != "audio_only_listening_no_candidate_timestamps":
        raise ValueError("annotation method is not independent audio-only listening")
    if annotation.get("audio_sha256") != _sha256(audio_path):
        raise ValueError("annotation audio hash does not match the selected WAV")
    if annotation.get("candidate_clip_sha256") != _sha256(video_path):
        raise ValueError("annotation clip hash does not match the selected MP4")
    manifest = json.loads(manifest_path.read_text())
    if not isinstance(manifest, dict) or manifest.get("scene_id") != annotation.get("scene_id"):
        raise ValueError("render manifest does not match the annotated scene")
    if manifest.get("video_sha256") != _sha256(video_path) or manifest.get("new_timing_sha256") != _sha256(candidate_path):
        raise ValueError("candidate timing or video hash does not match the render manifest")
    marks = _word_rows(annotation.get("words"), name="annotation")
    candidate = _word_rows(json.loads(candidate_path.read_text()), name="candidate")
    if len(marks) != len(candidate):
        raise ValueError("annotation and candidate word counts differ")
    with wave.open(str(audio_path), "rb") as audio:
        duration = audio.getnframes() / audio.getframerate()
    errors: list[float] = []
    details: list[dict[str, object]] = []
    previous_start = -1.0
    for index, (mark, word) in enumerate(zip(marks, candidate, strict=True)):
        if mark.get("word") != word.get("word") or mark.get("ordinal") != word.get("ordinal"):
            raise ValueError(f"word {index + 1} has a label or ordinal mismatch")
        if word.get("section_id") != annotation.get("scene_id"):
            raise ValueError(f"word {index + 1} belongs to another scene")
        times: list[float] = []
        for field in ("start_seconds", "end_seconds"):
            for row in (mark, word):
                value = row.get(field)
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise ValueError(f"word {index + 1} has an invalid {field}")
                times.append(float(value))
        marked_start, candidate_start, marked_end, candidate_end = times
        candidate_start -= candidate_origin_seconds
        candidate_end -= candidate_origin_seconds
        if marked_start < 0 or marked_end <= marked_start or marked_end > duration + 0.02:
            raise ValueError(f"word {index + 1} has marks outside the WAV")
        if candidate_start < -0.02 or candidate_end <= candidate_start or candidate_end > duration + 0.02:
            raise ValueError(f"word {index + 1} has candidate timing outside the WAV")
        if marked_start < previous_start:
            raise ValueError(f"word {index + 1} is out of annotation order")
        previous_start = marked_start
        start_error = abs(candidate_start - marked_start)
        end_error = abs(candidate_end - marked_end)
        errors.extend((start_error, end_error))
        details.append({"ordinal": mark["ordinal"], "word": mark["word"], "start_error_ms": round(start_error * 1000, 1), "end_error_ms": round(end_error * 1000, 1)})
    errors.sort()
    p95 = errors[math.ceil(0.95 * len(errors)) - 1] * 1000
    maximum = errors[-1] * 1000
    return {
        "kind": "independent_word_timing_audit_v1",
        "status": "pass" if p95 <= 150 and maximum <= 300 else "fail",
        "annotation_sha256": _sha256(annotation_path),
        "candidate_sha256": _sha256(candidate_path),
        "manifest_sha256": _sha256(manifest_path),
        "audio_sha256": annotation["audio_sha256"],
        "video_sha256": annotation["candidate_clip_sha256"],
        "scene_id": annotation["scene_id"],
        "candidate_origin_seconds": candidate_origin_seconds,
        "word_count": len(details),
        "boundary_count": len(errors),
        "median_error_ms": round(statistics.median(errors) * 1000, 1),
        "p95_error_ms": round(p95, 1),
        "maximum_error_ms": round(maximum, 1),
        "thresholds_ms": {"p95": 150, "maximum": 300},
        "word_errors": details,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("annotation", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("audio", type=Path)
    parser.add_argument("video", type=Path)
    parser.add_argument("--candidate-origin-seconds", type=float, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = compare(args.annotation, args.candidate, args.manifest, args.audio, args.video, candidate_origin_seconds=args.candidate_origin_seconds)
    encoded = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(encoded)
    print(encoded, end="")
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
