"""Independent caption-timing acceptance uses hash-bound audio-only marks."""

from __future__ import annotations

import json
import wave
from pathlib import Path

import pytest

from scripts.check_word_annotation import _sha256, compare


def _packet(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path]:
    audio = tmp_path / "speech.wav"
    with wave.open(str(audio), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16_000)
        output.writeframes(b"\0\0" * 32_000)
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"test clip bytes")
    candidate = tmp_path / "candidate.json"
    candidate.write_text(json.dumps([
        {"ordinal": 4, "word": "Check", "section_id": "scene-1", "start_seconds": 20.1, "end_seconds": 20.5},
        {"ordinal": 5, "word": "status", "section_id": "scene-1", "start_seconds": 20.6, "end_seconds": 21.0},
    ]))
    annotation = tmp_path / "marks.json"
    annotation.write_text(json.dumps({
        "kind": "independent_manual_word_annotation_v1",
        "annotator": "test reviewer",
        "method": "audio_only_listening_no_candidate_timestamps",
        "audio_sha256": _sha256(audio),
        "candidate_clip_sha256": _sha256(video),
        "scene_id": "scene-1",
        "words": [
            {"ordinal": 4, "word": "Check", "start_seconds": 0.1, "end_seconds": 0.5},
            {"ordinal": 5, "word": "status", "start_seconds": 0.6, "end_seconds": 1.0},
        ],
    }))
    manifest = tmp_path / "render-manifest.json"
    manifest.write_text(json.dumps({"scene_id": "scene-1", "video_sha256": _sha256(video), "new_timing_sha256": _sha256(candidate)}))
    return annotation, candidate, manifest, audio, video


def test_independent_word_audit_passes_exact_boundaries_and_records_evidence(tmp_path: Path) -> None:
    result = compare(*_packet(tmp_path), candidate_origin_seconds=20.0)
    assert result["status"] == "pass"
    assert result["word_count"] == 2 and result["boundary_count"] == 4
    assert result["maximum_error_ms"] == 0
    assert len(result["annotation_sha256"]) == 64


def test_independent_word_audit_fails_large_drift_and_rejects_changed_media(tmp_path: Path) -> None:
    annotation, candidate, manifest, audio, video = _packet(tmp_path)
    marks = json.loads(annotation.read_text())
    marks["words"][1]["start_seconds"] = 0.9
    annotation.write_text(json.dumps(marks))
    result = compare(annotation, candidate, manifest, audio, video, candidate_origin_seconds=20.0)
    assert result["status"] == "fail" and result["maximum_error_ms"] == pytest.approx(300)
    video.write_bytes(b"changed clip")
    with pytest.raises(ValueError, match="clip hash"):
        compare(annotation, candidate, manifest, audio, video, candidate_origin_seconds=20.0)


def test_independent_word_audit_rejects_mislabeled_or_out_of_bounds_marks(tmp_path: Path) -> None:
    annotation, candidate, manifest, audio, video = _packet(tmp_path)
    marks = json.loads(annotation.read_text())
    marks["words"][0]["word"] = "wrong"
    annotation.write_text(json.dumps(marks))
    with pytest.raises(ValueError, match="label or ordinal"):
        compare(annotation, candidate, manifest, audio, video, candidate_origin_seconds=20.0)
    marks["words"][0]["word"] = "Check"
    marks["words"][1]["end_seconds"] = 3.0
    annotation.write_text(json.dumps(marks))
    with pytest.raises(ValueError, match="outside the WAV"):
        compare(annotation, candidate, manifest, audio, video, candidate_origin_seconds=20.0)


def test_independent_word_audit_requires_candidate_bound_to_render_manifest(tmp_path: Path) -> None:
    annotation, candidate, manifest, audio, video = _packet(tmp_path)
    words = json.loads(candidate.read_text())
    words[0]["start_seconds"] = 20.12
    candidate.write_text(json.dumps(words))
    with pytest.raises(ValueError, match="render manifest"):
        compare(annotation, candidate, manifest, audio, video, candidate_origin_seconds=20.0)
