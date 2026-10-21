"""Local CPU-friendly Kokoro ONNX adapter; imports the optional runtime lazily."""

from __future__ import annotations

import hashlib
import json
import wave
from pathlib import Path

from tubeforge.core.config import KokoroProviderConfig, REPOSITORY_ROOT
from tubeforge.core.errors import ProviderValidationError, RetryableProviderError
from tubeforge.domain.contracts import VoiceRequest, VoiceResult
from tubeforge.pipeline.narration import normalize_narration_text


class KokoroVoiceProvider:
    """Create natural local English narration with one of a bounded voice set."""

    provider_name = "kokoro"

    def __init__(self, settings: KokoroProviderConfig) -> None:
        self.settings = settings
        self.calls = 0
        self._pipeline = None
        self._pipeline_identity = None

    def synthesize(self, request: VoiceRequest) -> VoiceResult:
        text = normalize_narration_text(request.text)
        if not text:
            raise ProviderValidationError("Kokoro narration text is empty")
        if request.voice_id not in self.settings.voices:
            raise ProviderValidationError(f"unsupported Kokoro voice: {request.voice_id}")
        model, voices = self._required_models()
        def digest(path):
            with path.open("rb") as stream:
                return hashlib.file_digest(stream, "sha256").hexdigest()
        model_identity = (digest(model), digest(voices))
        key = hashlib.sha256(json.dumps({"text": text, "voice": request.voice_id, "provider": self.provider_name,
                                        "version": self.settings.adapter_version, "model": model_identity,
                                        "speed": 1.0, "language": "en-us"}, sort_keys=True).encode()).hexdigest()
        destination = Path(request.output_path) if request.output_path else self._path(self.settings.cache_root) / request.voice_id / f"{key}.wav"
        if self._valid_wave(destination):
            return self._result(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            from kokoro_onnx import Kokoro
        except ImportError as error:
            raise RetryableProviderError("Kokoro ONNX runtime is not installed") from error
        try:
            self.calls += 1
            if self._pipeline_identity != model_identity:
                self._pipeline = Kokoro(str(model), str(voices))
                self._pipeline_identity = model_identity
            samples, sample_rate = self._pipeline.create(text, voice=request.voice_id, speed=1.0, lang="en-us")
            if sample_rate != self.settings.sample_rate:
                raise ProviderValidationError(f"Kokoro returned unexpected sample rate: {sample_rate}")
            chunks = [float(value) for value in samples]
            if not chunks:
                raise ProviderValidationError("Kokoro produced no audio")
            temporary = destination.with_suffix(".tmp.wav")
            self._write_wave(temporary, chunks)
            if not self._valid_wave(temporary):
                temporary.unlink(missing_ok=True)
                raise ProviderValidationError("Kokoro produced invalid audio")
            temporary.replace(destination)
        except ProviderValidationError:
            raise
        except Exception as error:  # optional model download/runtime failures are retryable
            raise RetryableProviderError("Kokoro synthesis failed") from error
        return self._result(destination)

    def _write_wave(self, path: Path, samples: list[float]) -> None:
        import array

        pcm = array.array("h", (max(-32768, min(32767, round(sample * 32767))) for sample in samples))
        with wave.open(str(path), "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(self.settings.sample_rate)
            stream.writeframes(pcm.tobytes())

    def _required_models(self) -> tuple[Path, Path]:
        if self.settings.model_path is None or self.settings.voices_path is None:
            raise RetryableProviderError("Kokoro model files are not configured")
        model, voices = self._path(self.settings.model_path), self._path(self.settings.voices_path)
        if not model.is_file() or not voices.is_file():
            raise RetryableProviderError("Kokoro model files are unavailable")
        return model, voices

    def _valid_wave(self, path: Path) -> bool:
        try:
            if not path.is_file() or path.stat().st_size <= 44 or path.stat().st_size > self.settings.max_output_bytes:
                return False
            with wave.open(str(path), "rb") as stream:
                return stream.getnframes() > 0 and stream.getnchannels() == 1 and stream.getsampwidth() == 2 and stream.getframerate() == self.settings.sample_rate and stream.getcomptype() == "NONE"
        except (wave.Error, OSError, EOFError):
            return False

    def _result(self, path: Path) -> VoiceResult:
        with wave.open(str(path), "rb") as stream:
            duration = stream.getnframes() / stream.getframerate()
        return VoiceResult(artifact_path=str(path), duration_seconds=duration, checksum_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), provider_name=self.provider_name)

    @staticmethod
    def _path(value: Path) -> Path:
        return value if value.is_absolute() else REPOSITORY_ROOT / value
