from __future__ import annotations

import math
import re
import struct
import subprocess
import sys
import wave
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from tubeforge.core.config import ShortsFinalRenderConfig
from tubeforge.pipeline.alignment import LocalWhisperDTWAligner, LocalWordAligner, WordTiming, _clause_spans, alignment_model_sha256, map_spoken_words, verify_word_alignment
from tubeforge.core.errors import ProviderCancellation, ProviderValidationError, RetryableProviderError
from tubeforge.pipeline.captions import TimedPhrase, render_highlighted_ass
from tubeforge.pipeline.narration import NarrationPhrase
from tubeforge.pipeline.orchestrator import _ass_dialogue_text
from tubeforge.rendering.preview import PreviewRenderer, TimelineSegment, pace_segments


def _speech_wave(path: Path) -> None:
    sample_rate = 16_000
    samples = []
    for frame in range(sample_rate):
        seconds = frame / sample_rate
        value = 0 if seconds < 0.1 or seconds > 0.9 else round(7_000 * math.sin(2 * math.pi * 220 * seconds))
        samples.append(value)
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(sample_rate)
        stream.writeframes(b"".join(struct.pack("<h", value) for value in samples))


def test_local_word_alignment_uses_waveform_and_verifies_final_audio(tmp_path: Path) -> None:
    audio = tmp_path / "phrase.wav"
    _speech_wave(audio)
    words = LocalWordAligner().align(audio_path=audio, text="A strong opening hook", phrase_id="phrase-1", section_id="section-1", phrase_start_seconds=0, phrase_end_seconds=1, ordinal_start=0)

    assert [word.word for word in words] == ["A", "strong", "opening", "hook"]
    assert 0.05 <= words[0].start_seconds <= 0.15
    assert 0.85 <= words[-1].end_seconds <= 1.0
    assert verify_word_alignment(words, final_duration=words[-1].end_seconds, tolerance=0.02)["verified"]


def test_audio_grounded_mapping_keeps_approved_display_tokens_and_many_to_one_time() -> None:
    words = map_spoken_words(
        approved_text="unstaged working-tree changes",
        recognized=(("unstaged", 0.1, 0.5, 0.95), ("working", 0.55, 0.8, 0.9), ("tree", 0.8, 1.05, 0.9), ("changes", 1.1, 1.5, 0.9)),
        phrase_id="phrase-1", section_id="section-1", phrase_start_seconds=2.0,
        phrase_end_seconds=3.6, ordinal_start=7,
    )
    assert [(word.word, word.ordinal) for word in words] == [("unstaged", 7), ("working-tree", 8), ("changes", 9)]
    assert (words[1].start_seconds, words[1].end_seconds) == pytest.approx((2.55, 3.05))


@pytest.mark.parametrize("speech", [
    (("save", 0.0, 0.3, 0.95),),
    (("safe", 0.0, 0.3, 0.1),),
    (("safe", 0.0, 0.3, 0.95), ("extra", 0.3, 0.5, 0.95)),
])
def test_audio_grounded_mapping_blocks_substitutions_low_confidence_and_extra_words(speech) -> None:
    with pytest.raises(ProviderValidationError):
        map_spoken_words(
            approved_text="safe", recognized=speech,
            phrase_id="phrase-1", section_id="section-1", phrase_start_seconds=0.0,
            phrase_end_seconds=1.0, ordinal_start=0,
        )


def test_transcript_clause_split_uses_measured_pause_and_keeps_approved_text() -> None:
    numpy = pytest.importorskip("numpy")
    audio = numpy.full(4 * 16_000, 0.05, dtype=numpy.float32)
    audio[round(1.9 * 16_000) : round(2.15 * 16_000)] = 0
    spans = _clause_spans(audio, "Compare both states, then inspect the result.")
    assert len(spans) == 2
    assert spans[0][2] == "Compare both states,"
    assert spans[1][2] == "then inspect the result."
    assert spans[0][1] == spans[1][0] == pytest.approx(2.02, abs=0.03)
    audio[:] = 0.05
    assert _clause_spans(audio, "Compare both states, then inspect the result.") == ((0.0, 4.0, "Compare both states, then inspect the result."),)


def test_audio_grounded_model_pin_covers_all_four_resources(tmp_path: Path) -> None:
    from tubeforge.core.errors import ProviderValidationError

    with pytest.raises(ProviderValidationError, match="missing config.json"):
        alignment_model_sha256(tmp_path)
    for name in ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt"):
        (tmp_path / name).write_bytes(name.encode())
    before = alignment_model_sha256(tmp_path)
    (tmp_path / "tokenizer.json").write_bytes(b"changed")
    assert alignment_model_sha256(tmp_path) != before
    with pytest.raises(ProviderValidationError, match="differ from the pinned"):
        LocalWhisperDTWAligner(model_path=tmp_path, model_sha256=before)


def test_audio_grounded_alignment_observes_cancellation_before_and_after_decode(monkeypatch: pytest.MonkeyPatch) -> None:
    aligner = LocalWhisperDTWAligner.__new__(LocalWhisperDTWAligner)
    aligner.ffmpeg_executable = "ffmpeg"
    def no_decode(*args, **kwargs):
        pytest.fail("cancelled alignment must not decode audio")
    monkeypatch.setattr("tubeforge.pipeline.alignment.subprocess.run", no_decode)
    kwargs = dict(audio_path=Path("unused.wav"), text="Check status", phrase_id="p", section_id="s", phrase_start_seconds=0.0, phrase_end_seconds=1.0, ordinal_start=0)
    with pytest.raises(ProviderCancellation, match="before audio-grounded alignment decode"):
        aligner.align(**kwargs, cancellation_requested=lambda: True)

    monkeypatch.setattr("tubeforge.pipeline.alignment.subprocess.run", lambda *args, **kwargs: SimpleNamespace(stdout=b"\0" * 64000))
    calls = 0
    def cancel_after_decode() -> bool:
        nonlocal calls
        calls += 1
        return calls > 1
    with pytest.raises(ProviderCancellation, match="after audio-grounded alignment decode"):
        aligner.align(**kwargs, cancellation_requested=cancel_after_decode)
    assert calls == 2


def test_audio_grounded_alignment_stops_between_clauses(monkeypatch: pytest.MonkeyPatch) -> None:
    numpy = pytest.importorskip("numpy")
    audio = numpy.full(4 * 16_000, 0.05, dtype=numpy.float32)
    audio[round(1.9 * 16_000) : round(2.15 * 16_000)] = 0
    monkeypatch.setattr("tubeforge.pipeline.alignment.subprocess.run", lambda *args, **kwargs: SimpleNamespace(stdout=audio.tobytes()))
    parent = ModuleType("faster_whisper")
    parent.__path__ = []  # type: ignore[attr-defined]
    child = ModuleType("faster_whisper.audio")
    child.pad_or_trim = lambda features: features  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "faster_whisper", parent)
    monkeypatch.setitem(sys.modules, "faster_whisper.audio", child)

    class Model:
        calls = 0
        def feature_extractor(self, chunk):
            return numpy.zeros((80, 300), dtype=numpy.float32)
        def encode(self, features):
            return features
        def find_alignment(self, tokenizer, tokens, encoded, frames):
            self.calls += 1
            return [[{"word": "Compare", "start": 0.1, "end": 0.3, "probability": 1.0}]]

    aligner = LocalWhisperDTWAligner.__new__(LocalWhisperDTWAligner)
    aligner.ffmpeg_executable = "ffmpeg"
    aligner.model = Model()
    aligner.tokenizer = SimpleNamespace(encode=lambda text: [1])
    with pytest.raises(ProviderCancellation, match="after audio-grounded alignment clause"):
        aligner.align(audio_path=Path("unused.wav"), text="Compare both states, then inspect the result.", phrase_id="p", section_id="s", phrase_start_seconds=0.0, phrase_end_seconds=4.0, ordinal_start=0, cancellation_requested=lambda: aligner.model.calls > 0)
    assert aligner.model.calls == 1


def test_audio_grounded_decode_timeout_retries_but_invalid_audio_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    aligner = LocalWhisperDTWAligner.__new__(LocalWhisperDTWAligner)
    aligner.ffmpeg_executable = "ffmpeg"
    kwargs = dict(audio_path=Path("unused.wav"), text="Check status", phrase_id="p", section_id="s", phrase_start_seconds=0.0, phrase_end_seconds=1.0, ordinal_start=0)
    def timed_out(*args, **kwargs):
        raise subprocess.TimeoutExpired("ffmpeg", 60)
    monkeypatch.setattr("tubeforge.pipeline.alignment.subprocess.run", timed_out)
    with pytest.raises(RetryableProviderError, match="decode timed out"):
        aligner.align(**kwargs)
    def invalid_audio(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "ffmpeg")
    monkeypatch.setattr("tubeforge.pipeline.alignment.subprocess.run", invalid_audio)
    with pytest.raises(ProviderValidationError, match="could not decode approved narration"):
        aligner.align(**kwargs)


def test_audio_grounded_model_runtime_fault_is_retryable(monkeypatch: pytest.MonkeyPatch) -> None:
    numpy = pytest.importorskip("numpy")
    audio = numpy.full(16_000, 0.05, dtype=numpy.float32)
    monkeypatch.setattr("tubeforge.pipeline.alignment.subprocess.run", lambda *args, **kwargs: SimpleNamespace(stdout=audio.tobytes()))
    parent = ModuleType("faster_whisper")
    parent.__path__ = []  # type: ignore[attr-defined]
    child = ModuleType("faster_whisper.audio")
    child.pad_or_trim = lambda features: features  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "faster_whisper", parent)
    monkeypatch.setitem(sys.modules, "faster_whisper.audio", child)

    class FailingModel:
        def feature_extractor(self, chunk):
            raise RuntimeError("temporary model resource fault")

    aligner = LocalWhisperDTWAligner.__new__(LocalWhisperDTWAligner)
    aligner.ffmpeg_executable = "ffmpeg"
    aligner.model = FailingModel()
    aligner.tokenizer = SimpleNamespace(encode=lambda text: [1])
    with pytest.raises(RetryableProviderError, match="model execution failed"):
        aligner.align(audio_path=Path("unused.wav"), text="Check status", phrase_id="p", section_id="s", phrase_start_seconds=0.0, phrase_end_seconds=1.0, ordinal_start=0)


def test_highlighted_ass_uses_portrait_safe_area_and_active_word_colour(tmp_path: Path) -> None:
    audio = tmp_path / "phrase.wav"
    _speech_wave(audio)
    words = LocalWordAligner().align(audio_path=audio, text="Make every second count", phrase_id="phrase-1", section_id="section-1", phrase_start_seconds=0, phrase_end_seconds=1, ordinal_start=0)
    captions = render_highlighted_ass(words, width=1080, height=1920, font_size=80, margin_vertical=470, margin_horizontal=96, center_x=490)

    assert "PlayResX: 1080" in captions and "PlayResY: 1920" in captions
    assert "Style: Shorts,Arial,80" in captions
    assert ",96,96,470,1" in captions
    assert captions.count(r"\pos(490,1450)") == 4
    assert "&H0000D7FF" in captions
    assert captions.count("Dialogue:") == 4


def test_phone_first_final_caption_pixels_stay_inside_portrait_safe_area(tmp_path: Path) -> None:
    phrase = NarrationPhrase(phrase_id="phrase-0123456789abcdef", section_id="section-1", ordinal=0, text="Remember, persist what.")
    words = tuple(
        WordTiming(word, phrase.phrase_id, phrase.section_id, index, index * 0.2, (index + 1) * 0.2)
        for index, word in enumerate(("Remember", "persist", "what"))
    )
    captions = tmp_path / "captions.ass"
    captions.write_text(
        render_highlighted_ass(
            words, width=1080, height=1920, font_size=84,
            margin_vertical=470, margin_horizontal=96, center_x=490,
            phrases=(TimedPhrase(phrase, 0, 0.6),),
        ),
        encoding="utf-8",
    )
    frame = tmp_path / "caption-frame.png"
    ffmpeg = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
            "-i", "color=c=black:s=1080x1920:r=30:d=1",
            "-vf", f"subtitles='{captions}':force_style='FontSize=84,Alignment=2,MarginV=470,MarginL=96,MarginR=96,Outline=2,Shadow=1',select='eq(n,6)'",
            "-vsync", "0", "-frames:v", "1", "-y", str(frame),
        ],
        capture_output=True, text=True, timeout=60,
    )
    assert ffmpeg.returncode == 0, ffmpeg.stderr
    measured = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "info", "-i", str(frame), "-vf", "bbox=min_val=48", "-frames:v", "1", "-f", "null", "-"],
        capture_output=True, text=True, timeout=30,
    )
    assert measured.returncode == 0, measured.stderr
    bounds = re.search(r"x1[:=](\d+) x2[:=](\d+) y1[:=](\d+) y2[:=](\d+)", measured.stderr)
    assert bounds is not None, measured.stderr
    x1, x2, y1, y2 = map(int, bounds.groups())
    assert 60 <= x1 < x2 <= 930
    assert 200 <= y1 < y2 <= 1500
    assert abs((x1 + x2) / 2 - 490) <= 12


def test_highlighted_ass_preserves_commands_and_phrase_boundaries() -> None:
    first = NarrationPhrase(phrase_id="phrase-0000000000000001", section_id="section-1", ordinal=0, text="Enter docker run --name web-a -d nginx:alpine.")
    second = NarrationPhrase(phrase_id="phrase-0000000000000002", section_id="section-1", ordinal=1, text="Docker starts web-a detached.")
    words = tuple(
        WordTiming(word, phrase.phrase_id, phrase.section_id, ordinal, ordinal * 0.3, (ordinal + 1) * 0.3)
        for ordinal, (word, phrase) in enumerate(
            [(word, first) for word in ("Enter", "docker", "run", "name", "web-a", "d", "nginx", "alpine")]
            + [(word, second) for word in ("Docker", "starts", "web-a", "detached")]
        )
    )
    cues = (TimedPhrase(first, 0, 2.4), TimedPhrase(second, 2.4, 3.6))
    captions = render_highlighted_ass(words, width=1080, height=1920, font_size=80, margin_vertical=360, margin_horizontal=96, phrases=cues)

    assert "--NAME" in captions and "-D" in captions and "NGINX:ALPINE." in captions
    assert "D NGINX ALPINE" not in captions
    assert all(not ("DETACHED" in line and "ENTER" in line) for line in captions.splitlines() if line.startswith("Dialogue:"))
    assert captions.count("Dialogue:") == 11


def test_highlighted_ass_wraps_real_portrait_width_edge_cases() -> None:
    phrase = NarrationPhrase(phrase_id="phrase-0000000000000003", section_id="section-1", ordinal=0, text="Separate containers—so what distinguishes web-a from web-b?")
    lexical_words = ("Separate", "containers", "so", "what", "distinguishes", "web-a", "from", "web-b")
    words = tuple(WordTiming(word, phrase.phrase_id, phrase.section_id, index, index * 0.3, (index + 1) * 0.3) for index, word in enumerate(lexical_words))
    captions = render_highlighted_ass(words, width=1080, height=1920, font_size=80, margin_vertical=360, margin_horizontal=96, phrases=(TimedPhrase(phrase, 0, 2.4),))
    for row in (line for line in captions.splitlines() if line.startswith("Dialogue:")):
        visible = re.sub(r"\{[^}]*\}", "", row.split(",", 9)[-1])
        assert all(len(line.strip()) <= 18 for line in visible.split(r"\N"))


def test_highlighted_ass_reduces_group_size_without_losing_spoken_tokens() -> None:
    phrase = NarrationPhrase(phrase_id="phrase-0000000000000004", section_id="section-1", ordinal=0, text="unstaged working-tree changes.")
    lexical = ("unstaged", "working-tree", "changes")
    words = tuple(WordTiming(word, phrase.phrase_id, phrase.section_id, index, index * 0.3, (index + 1) * 0.3) for index, word in enumerate(lexical))
    captions = render_highlighted_ass(words, width=1080, height=1920, font_size=80, margin_vertical=360, margin_horizontal=96, phrases=(TimedPhrase(phrase, 0, 0.9),))
    dialogue = [row for row in captions.splitlines() if row.startswith("Dialogue:")]
    assert len(dialogue) == 3
    for row in dialogue:
        visible = re.sub(r"\{[^}]*\}", "", row.split(",", 9)[-1])
        assert all(len(line.strip()) <= 18 for line in visible.split(r"\N"))
    assert "WORKING-TREE" in captions and "CHANGES." in captions


def test_highlighted_ass_blocks_oversized_single_identifier() -> None:
    phrase = NarrationPhrase(phrase_id="phrase-0000000000000005", section_id="section-1", ordinal=0, text="superlongtechnicalidentifier")
    words = (WordTiming("superlongtechnicalidentifier", phrase.phrase_id, phrase.section_id, 0, 0, 1),)
    with pytest.raises(ValueError, match="token exceeds"):
        render_highlighted_ass(words, width=1080, height=1920, font_size=80, margin_vertical=360, margin_horizontal=96, phrases=(TimedPhrase(phrase, 0, 1),))


def test_shorts_renderer_is_portrait_30fps_and_caps_visual_holds(tmp_path: Path) -> None:
    asset = tmp_path / "asset.png"; asset.write_bytes(b"asset")
    narration = tmp_path / "narration.wav"; narration.write_bytes(b"audio")
    captions = tmp_path / "captions.ass"; captions.write_text("[Script Info]\n", encoding="utf-8")
    segment = TimelineSegment("scene", "section", 0, 7, asset, "a" * 64, "image")
    profile = ShortsFinalRenderConfig()
    paced = pace_segments((segment,), profile.scene_max_duration_seconds)
    command = PreviewRenderer(profile).command((segment,), narration, captions, tmp_path / "short.mp4")
    graph = command[command.index("-filter_complex") + 1]

    assert (profile.width, profile.height, profile.fps) == (1080, 1920, 30)
    assert len(paced) == 3 and max(item.duration_seconds for item in paced) <= 3
    assert "concat=n=3" in graph
    assert "*on/" in graph and "*(1-on/" in graph
    # ASS captions carry their own styles; the renderer must preserve them.
    assert "force_style=''" in graph
    assert command[command.index("-r") + 1] == "30"
    assert command[command.index("-filter_complex_threads") + 1] == str(profile.threads)
    assert command[command.index("-threads", command.index("-c:v")) + 1] == str(profile.threads)
    assert command.count("-threads") == len(paced) + 2
    assert [PreviewRenderer.motion_variant(index) for index in range(4)] == ["pan-right-fast", "pan-left-gentle", "pan-down-fast", "pan-up-gentle"]


def test_ass_dialogue_text_excludes_metadata_and_preserves_caption_commas() -> None:
    row = r"Dialogue: 0,0:00:00.10,0:00:00.40,Shorts,,96,96,360,,{\c&H0000D7FF&}STOP,{\rShorts} NOW"

    assert _ass_dialogue_text(row) == r"{\c&H0000D7FF&}STOP,{\rShorts} NOW"
