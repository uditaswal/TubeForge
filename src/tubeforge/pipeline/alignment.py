"""Local waveform-aware word alignment for generated narration."""

from __future__ import annotations

import math
import hashlib
import re
import struct
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from tubeforge.core.errors import ProviderCancellation, ProviderValidationError, RepairableAlignmentResult, RetryableProviderError


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


def map_spoken_words(
    *,
    approved_text: str,
    recognized: tuple[tuple[str, float, float, float], ...],
    phrase_id: str,
    section_id: str,
    phrase_start_seconds: float,
    phrase_end_seconds: float,
    ordinal_start: int,
    minimum_probability: float = 0.4,
) -> tuple[WordTiming, ...]:
    """Map recognized speech to approved display words without rewriting either.

    A display token such as ``working-tree`` may span two contiguous spoken
    tokens. Other substitutions, omissions, and ambiguous pronunciations
    fail closed; the approved script must supply an explicit reviewed mapping
    before such speech can receive production timestamps.
    """
    approved = tuple(_WORD.findall(approved_text))
    if not approved or not recognized:
        raise ProviderValidationError("audio-grounded alignment has no words")
    cursor = 0
    result: list[WordTiming] = []
    previous_end = phrase_start_seconds
    for offset, display in enumerate(approved):
        target = re.sub(r"[^\w]", "", display.casefold(), flags=re.UNICODE)
        if not target:
            raise ProviderValidationError("approved display token is empty")
        start: float | None = None
        assembled = ""
        end = previous_end
        while assembled != target:
            if cursor >= len(recognized):
                raise ProviderValidationError("recognized speech omits an approved word")
            spoken, local_start, local_end, probability = recognized[cursor]
            token = re.sub(r"[^\w]", "", spoken.casefold(), flags=re.UNICODE)
            if not token or probability < minimum_probability or local_end <= local_start:
                raise ProviderValidationError("recognized speech has an ambiguous word")
            if start is None:
                start = phrase_start_seconds + local_start
            end = phrase_start_seconds + local_end
            assembled += token
            if not target.startswith(assembled):
                raise ProviderValidationError("recognized speech differs from approved narration")
            cursor += 1
        if start is None or start < previous_end - 0.025 or end > phrase_end_seconds + 0.025:
            raise ProviderValidationError("recognized word timing is outside its approved phrase")
        result.append(WordTiming(display, phrase_id, section_id, ordinal_start + offset, max(start, previous_end), end))
        previous_end = end
    if cursor != len(recognized):
        raise ProviderValidationError("recognized speech contains words outside approved narration")
    return tuple(result)


def _regularize_overlap(spoken, phrase_seconds: float, minimum: float = 0.02):
    """Make the overlap-decoded words monotonic, at least ``minimum`` long and inside the phrase.

    The overlapped clause windows can report the same boundary word twice or push the last word a few
    hundredths past the audio; those are decoder artefacts, not different speech, so only the times move.
    """
    words = [list(item) for item in spoken]
    previous = 0.0
    for item in words:
        item[1] = max(item[1], previous)
        item[2] = max(item[2], item[1] + minimum)
        previous = item[2]
    limit = phrase_seconds
    for item in reversed(words):
        item[2] = min(item[2], limit)
        item[1] = min(item[1], item[2] - minimum)
        limit = item[1]
    if words and words[0][1] < 0:
        raise ProviderValidationError("audio-grounded alignment has no room for the recognized words")
    return [tuple(item) for item in words]


def alignment_model_sha256(model_path: Path) -> str:
    """Hash the exact local model, configuration, vocabulary and tokenizer."""
    digest = hashlib.sha256()
    for name in ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt"):
        path = model_path / name
        if not path.is_file():
            raise ProviderValidationError(f"audio-grounded alignment model is missing {name}")
        digest.update(name.encode("ascii") + b"\0")
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _clause_spans(audio: object, text: str) -> tuple[tuple[float, float, str], ...]:
    """Split at approved punctuation only when the waveform has a matching pause."""
    import numpy as np

    duration = len(audio) / 16_000  # type: ignore[arg-type]
    clauses = tuple(part.strip() for part in re.split(r"(?<=[,;:])\s+", text) if part.strip())
    if len(clauses) < 2:
        return ((0.0, duration, text),)
    windows = [audio[index : index + 320] for index in range(0, len(audio), 320)]  # type: ignore[arg-type]
    energy = [float(np.sqrt(np.mean(window * window))) for window in windows if len(window)]
    threshold = max(0.002, max(energy, default=0.0) * 0.025)
    quiet: list[tuple[int, int]] = []
    start: int | None = None
    for index, value in enumerate([*energy, threshold + 1]):
        if value < threshold and start is None:
            start = index
        elif value >= threshold and start is not None:
            if index - start >= 6 and start * 0.02 >= 0.15 and index * 0.02 <= duration - 0.15:
                quiet.append((start, index))
            start = None
    weights = [max(1, len(_WORD.findall(clause))) for clause in clauses]
    total = sum(weights)
    boundaries: list[float] = []
    used: set[int] = set()
    for position in range(1, len(clauses)):
        expected = duration * sum(weights[:position]) / total
        candidates = [(abs((lo + hi) * 0.01 - expected), index, (lo + hi) * 0.01) for index, (lo, hi) in enumerate(quiet) if index not in used]
        if not candidates:
            return ((0.0, duration, text),)
        distance, index, boundary = min(candidates)
        if distance > 0.7 or (boundaries and boundary <= boundaries[-1]):
            return ((0.0, duration, text),)
        boundaries.append(boundary)
        used.add(index)
    edges = (0.0, *boundaries, duration)
    return tuple((edges[index], edges[index + 1], clause) for index, clause in enumerate(clauses))


class LocalWhisperDTWAligner:
    """Optional transcript-constrained timing with model and speech bytes pinned."""

    provider = "whisper-base-en-dtw-v1"

    def __init__(self, *, model_path: Path, model_sha256: str, ffmpeg_executable: str = "ffmpeg") -> None:
        if alignment_model_sha256(model_path) != model_sha256:
            raise ProviderValidationError("audio-grounded alignment model bytes differ from the pinned SHA-256")
        try:
            from faster_whisper import WhisperModel
            from faster_whisper.tokenizer import Tokenizer
            import faster_whisper
        except ImportError as error:
            raise ProviderValidationError("faster-whisper alignment dependency is unavailable") from error
        if faster_whisper.__version__ != "1.2.1":
            raise ProviderValidationError("audio-grounded alignment requires faster-whisper 1.2.1")
        self.model = WhisperModel(str(model_path), device="cpu", compute_type="int8", cpu_threads=4, local_files_only=True)
        self.tokenizer = Tokenizer(self.model.hf_tokenizer, self.model.model.is_multilingual, task="transcribe", language="en")
        self.model_sha256 = model_sha256
        self.ffmpeg_executable = ffmpeg_executable

    def align(
        self, *, audio_path: Path, text: str, phrase_id: str, section_id: str,
        phrase_start_seconds: float, phrase_end_seconds: float, ordinal_start: int,
        cancellation_requested: Callable[[], bool] | None = None,
        configuration: str = "primary",
    ) -> tuple[WordTiming, ...]:
        if configuration not in {"primary", "normalized-overlap-v1"}:
            raise ProviderValidationError("unsupported audio-grounded alignment configuration")
        if cancellation_requested is not None and cancellation_requested():
            raise ProviderCancellation("cancelled before audio-grounded alignment decode")
        try:
            decoded = subprocess.run(
                [self.ffmpeg_executable, "-v", "error", "-i", str(audio_path), "-ar", "16000", "-ac", "1", "-f", "f32le", "pipe:1"],
                check=True, capture_output=True, timeout=60,
            ).stdout
        except subprocess.TimeoutExpired as error:
            raise RetryableProviderError("audio-grounded alignment decode timed out") from error
        except (OSError, subprocess.CalledProcessError) as error:
            raise ProviderValidationError("audio-grounded alignment could not decode approved narration") from error
        if cancellation_requested is not None and cancellation_requested():
            raise ProviderCancellation("cancelled after audio-grounded alignment decode")
        try:
            import numpy as np
            from faster_whisper.audio import pad_or_trim
            audio = np.frombuffer(decoded, dtype="<f4").copy()
            if not 0 < len(audio) <= 30 * 16_000:
                raise ProviderValidationError("audio-grounded alignment requires a 0–30 second phrase")
            spoken: list[tuple[str, float, float, float]] = []
            for low, high, clause in _clause_spans(audio, text):
                if cancellation_requested is not None and cancellation_requested():
                    raise ProviderCancellation("cancelled before audio-grounded alignment clause")
                decode_low = max(0.0, low - 0.35) if configuration == "normalized-overlap-v1" else low
                decode_high = min(len(audio) / 16_000, high + 0.35) if configuration == "normalized-overlap-v1" else high
                chunk = audio[round(decode_low * 16_000) : round(decode_high * 16_000)]
                features = self.model.feature_extractor(chunk)
                frames = min(features.shape[-1] - 1, round(len(chunk) / 160))
                if frames < 1:
                    raise ProviderValidationError("audio-grounded alignment found an empty clause")
                encoded = self.model.encode(pad_or_trim(features[:, :frames]))
                alignment_text = clause.replace("’", "'") if configuration == "normalized-overlap-v1" else clause
                measured = self.model.find_alignment(self.tokenizer, [self.tokenizer.encode(alignment_text)], encoded, [frames])[0]
                if cancellation_requested is not None and cancellation_requested():
                    raise ProviderCancellation("cancelled after audio-grounded alignment clause")
                for word in measured:
                    if any(character.isalnum() for character in word["word"]):
                        spoken.append((word["word"].strip(), decode_low + float(word["start"]), decode_low + float(word["end"]), float(word["probability"])))
        except (ProviderValidationError, ProviderCancellation, RetryableProviderError):
            raise
        except RuntimeError as error:
            raise RetryableProviderError("audio-grounded alignment model execution failed") from error
        except Exception as error:
            raise ProviderValidationError("audio-grounded alignment execution failed") from error
        if configuration == "normalized-overlap-v1":
            spoken = _regularize_overlap(spoken, phrase_end_seconds - phrase_start_seconds)
        if configuration == "primary" and any(end <= start for _, start, end, _ in spoken):
            normalized = lambda value: re.sub(r"[^\w]", "", value.casefold(), flags=re.UNICODE)
            approved = tuple(_WORD.findall(text))
            if "".join(normalized(value) for value, *_ in spoken) == "".join(normalized(value) for value in approved):
                raise RepairableAlignmentResult("audio-grounded alignment found a repairable zero-duration word")
        return map_spoken_words(
            approved_text=text, recognized=tuple(spoken), phrase_id=phrase_id, section_id=section_id,
            phrase_start_seconds=phrase_start_seconds, phrase_end_seconds=phrase_end_seconds,
            ordinal_start=ordinal_start, minimum_probability=0.0,
        )


def verify_word_alignment(words: tuple[WordTiming, ...], *, final_duration: float, tolerance: float, require_last_word_end: bool = True) -> dict[str, object]:
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
    if require_last_word_end and abs(words[-1].end_seconds - final_duration) > tolerance:
        raise ProviderValidationError("word alignment does not end with final narration")
    if not require_last_word_end and final_duration - words[-1].end_seconds > 1.0:
        raise ProviderValidationError("audio-grounded alignment leaves excessive uncaptioned narration")
    return {
        "word_count": len(words),
        "first_word_seconds": words[0].start_seconds,
        "last_word_seconds": words[-1].end_seconds,
        "final_audio_duration_seconds": final_duration,
        "verified": True,
    }
