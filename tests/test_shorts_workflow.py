from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

from tubeforge.core.config import ShortsFinalRenderConfig
from tubeforge.pipeline.alignment import LocalWordAligner, verify_word_alignment
from tubeforge.pipeline.captions import render_highlighted_ass
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


def test_highlighted_ass_uses_portrait_safe_area_and_active_word_colour(tmp_path: Path) -> None:
    audio = tmp_path / "phrase.wav"
    _speech_wave(audio)
    words = LocalWordAligner().align(audio_path=audio, text="Make every second count", phrase_id="phrase-1", section_id="section-1", phrase_start_seconds=0, phrase_end_seconds=1, ordinal_start=0)
    captions = render_highlighted_ass(words, width=1080, height=1920, font_size=80, margin_vertical=360, margin_horizontal=96)

    assert "PlayResX: 1080" in captions and "PlayResY: 1920" in captions
    assert "Style: Shorts,Arial,80" in captions
    assert ",96,96,360,1" in captions
    assert "&H0000D7FF" in captions
    assert captions.count("Dialogue:") == 4


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
    assert "MarginV=360" in graph and "MarginL=96" in graph
    assert command[command.index("-r") + 1] == "30"
    assert command[command.index("-filter_complex_threads") + 1] == str(profile.threads)
    assert command[command.index("-threads", command.index("-c:v")) + 1] == str(profile.threads)
    assert command.count("-threads") == len(paced) + 2
    assert [PreviewRenderer.motion_variant(index) for index in range(4)] == ["pan-right-fast", "pan-left-gentle", "pan-down-fast", "pan-up-gentle"]


def test_ass_dialogue_text_excludes_metadata_and_preserves_caption_commas() -> None:
    row = r"Dialogue: 0,0:00:00.10,0:00:00.40,Shorts,,96,96,360,,{\c&H0000D7FF&}STOP,{\rShorts} NOW"

    assert _ass_dialogue_text(row) == r"{\c&H0000D7FF&}STOP,{\rShorts} NOW"
