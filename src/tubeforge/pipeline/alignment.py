"""Local waveform-aware word alignment for generated narration."""

from __future__ import annotations

import math
import re
import struct
import wave
from dataclasses import dataclass
from pathlib import Path

from tubeforge.core.errors import ProviderValidationError


_WORD = re.compile(r"[^\W_]+(?:[’'-][^\W_]+)*", re.UNICODE)


@dataclass(frozen=True, slots=True)
class WordTiming:
    word: str
    phrase_id: str
    section_id: str
    ordinal: int
    start_seconds: float
    end_seconds: float


class LocalWordAligner:
    """Align words to the voiced span of a local PCM WAV.

    TubeForge synthesizes narration phrase-by-phrase. That gives us exact
    phrase boundaries without a network service. Inside each phrase, this
    aligner detects the voiced waveform span and distributes words using a
    pronunciation-length weight. The result is deterministic, local, and tied
    to the exact audio bytes that are assembled into the final narration.
    """

    def align(
        self,
        *,
        audio_path: Path,
        text: str,
        phrase_id: str,
        section_id: str,
        phrase_start_seconds: float,
        phrase_end_seconds: float,
        ordinal_start: int,
    ) -> tuple[WordTiming, ...]:
        words = tuple(_WORD.findall(text))
        if not words:
            raise ProviderValidationError("word alignment requires spoken words")
        if phrase_end_seconds <= phrase_start_seconds:
            raise ProviderValidationError("word alignment requires a positive phrase duration")
        local_start, local_end = self._voiced_span(audio_path)
        audio_duration = max(local_end, 0.001)
        phrase_duration = phrase_end_seconds - phrase_start_seconds
        scale = phrase_duration / audio_duration
        voiced_start = phrase_start_seconds + local_start * scale
        voiced_end = min(phrase_end_seconds, phrase_start_seconds + local_end * scale)
        if voiced_end <= voiced_start:
            voiced_start, voiced_end = phrase_start_seconds, phrase_end_seconds
        weights = tuple(max(1.0, len(re.sub(r"\W", "", word)) ** 0.65) for word in words)
        total = sum(weights)
        cursor = voiced_start
        output: list[WordTiming] = []
        for index, (word, weight) in enumerate(zip(words, weights, strict=True)):
            end = voiced_end if index == len(words) - 1 else cursor + (voiced_end - voiced_start) * weight / total
            output.append(WordTiming(word, phrase_id, section_id, ordinal_start + index, cursor, end))
            cursor = end
        return tuple(output)

    @staticmethod
    def _voiced_span(path: Path) -> tuple[float, float]:
        try:
            with wave.open(str(path), "rb") as stream:
                channels = stream.getnchannels()
                sample_width = stream.getsampwidth()
                sample_rate = stream.getframerate()
                frame_count = stream.getnframes()
                payload = stream.readframes(frame_count)
        except (OSError, wave.Error, EOFError) as error:
            raise ProviderValidationError("local word aligner requires valid PCM WAV phrase audio") from error
        if channels < 1 or sample_rate < 1 or frame_count < 1 or sample_width not in {1, 2, 4}:
            raise ProviderValidationError("local word aligner received unsupported WAV audio")
        duration = frame_count / sample_rate
        samples = LocalWordAligner._samples(payload, sample_width)
        if not samples:
            return 0.0, duration
        window_frames = max(1, sample_rate // 50)
        window_samples = window_frames * channels
        energies = []
        for offset in range(0, len(samples), window_samples):
            chunk = samples[offset : offset + window_samples]
            energies.append(math.sqrt(sum(value * value for value in chunk) / max(1, len(chunk))))
        peak = max(energies, default=0.0)
        threshold = max(64.0, peak * 0.08)
        active = [index for index, energy in enumerate(energies) if energy >= threshold]
        if not active or peak == 0:
            return 0.0, duration
        start = active[0] * window_frames / sample_rate
        end = min(duration, (active[-1] + 1) * window_frames / sample_rate)
        return start, max(start + 0.001, end)

    @staticmethod
    def _samples(payload: bytes, width: int) -> tuple[int, ...]:
        if width == 1:
            return tuple(value - 128 for value in payload)
        code = "h" if width == 2 else "i"
        usable = len(payload) - len(payload) % width
        return tuple(value[0] for value in struct.iter_unpack(f"<{code}", payload[:usable]))


def verify_word_alignment(words: tuple[WordTiming, ...], *, final_duration: float, tolerance: float) -> dict[str, object]:
    if not words:
        raise ProviderValidationError("word alignment is empty")
    previous = 0.0
    for word in words:
        if word.start_seconds < previous - tolerance or word.end_seconds <= word.start_seconds:
            raise ProviderValidationError("word alignment is non-monotonic")
        if word.end_seconds > final_duration + tolerance:
            raise ProviderValidationError("word alignment exceeds final narration")
        previous = word.end_seconds
    if words[0].start_seconds > 3.0:
        raise ProviderValidationError("Shorts hook does not begin within the first three seconds")
    if abs(words[-1].end_seconds - final_duration) > tolerance:
        raise ProviderValidationError("word alignment does not end with final narration")
    return {
        "word_count": len(words),
        "first_word_seconds": words[0].start_seconds,
        "last_word_seconds": words[-1].end_seconds,
        "final_audio_duration_seconds": final_duration,
        "verified": True,
    }
