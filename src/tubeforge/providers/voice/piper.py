"""Narrow Piper subprocess adapter. No shell invocation or Piper types escape it."""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import wave
from pathlib import Path

from tubeforge.core.config import PiperProviderConfig, REPOSITORY_ROOT
from tubeforge.core.errors import ProviderValidationError, RetryableProviderError
from tubeforge.domain.contracts import VoiceRequest, VoiceResult
from tubeforge.pipeline.narration import normalize_narration_text


class PiperVoiceProvider:
    """Generate a cached WAV phrase using Piper's documented stdin/output-file CLI."""

    provider_name = "piper"

    def __init__(self, settings: PiperProviderConfig) -> None:
        self.settings = settings
        self.calls = 0

    def cache_key(self, request: VoiceRequest) -> str:
        model = self._path(self.settings.model_path) if self.settings.model_path else None
        identity = _checksum(model) if model and model.is_file() else "unavailable"
        value = {"text": normalize_narration_text(request.text), "provider": self.provider_name,
                 "voice": self.settings.voice_id, "model_checksum": identity, "speaker": self.settings.speaker,
                 "sample_rate": self.settings.sample_rate, "settings": request.settings,
                 "adapter_version": self.settings.adapter_version}
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def command(self, request: VoiceRequest, output_path: Path) -> list[str]:
        model = self._required_model()
        command = [self._executable(), "--model", str(model), "--output_file", str(output_path)]
        if self.settings.config_path is not None:
            command.extend(("--config", str(self._path(self.settings.config_path))))
        if self.settings.speaker is not None:
            command.extend(("--speaker", str(self.settings.speaker)))
        if self.settings.threads != 1:
            command.extend(("--threads", str(self.settings.threads)))
        return command

    def synthesize(self, request: VoiceRequest) -> VoiceResult:
        text = normalize_narration_text(request.text)
        if not text:
            raise ProviderValidationError("Piper narration text is empty")
        key = self.cache_key(request)
        destination = Path(request.output_path) if request.output_path else self._path(self.settings.cache_root) / self.settings.voice_id / f"{key}.wav"
        if self._valid_wave(destination):
            return self._result(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        self._required_model()
        with tempfile.NamedTemporaryFile(prefix="piper-", suffix=".wav", dir=destination.parent, delete=False) as temporary:
            temp_path = Path(temporary.name)
        try:
            self.calls += 1
            completed = subprocess.run(self.command(request, temp_path), input=text.encode("utf-8"), stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, timeout=self.settings.timeout_seconds, check=False, shell=False)
        except subprocess.TimeoutExpired as error:
            temp_path.unlink(missing_ok=True)
            raise RetryableProviderError("Piper synthesis timed out") from error
        except OSError as error:
            temp_path.unlink(missing_ok=True)
            raise RetryableProviderError("Piper process could not start") from error
        if completed.returncode != 0:
            temp_path.unlink(missing_ok=True)
            raise RetryableProviderError("Piper synthesis process failed")
        if not self._valid_wave(temp_path):
            temp_path.unlink(missing_ok=True)
            raise ProviderValidationError("Piper produced invalid audio")
        if temp_path.stat().st_size > self.settings.max_output_bytes:
            temp_path.unlink(missing_ok=True)
            raise ProviderValidationError("Piper output exceeds configured size limit")
        temp_path.replace(destination)
        return self._result(destination)

    def _required_model(self) -> Path:
        if self.settings.model_path is None:
            raise ProviderValidationError("Piper model path is not configured")
        path = self._path(self.settings.model_path)
        if not path.is_file():
            raise ProviderValidationError("Piper model file is unavailable")
        return path

    def _valid_wave(self, path: Path) -> bool:
        try:
            if (
                not path.is_file()
                or path.stat().st_size <= 44
                or path.stat().st_size > self.settings.max_output_bytes
            ):
                return False
            with wave.open(str(path), "rb") as stream:
                frames = stream.getnframes()
                channels = stream.getnchannels()
                sample_width = stream.getsampwidth()
                sample_rate = stream.getframerate()
                if (
                    frames <= 0
                    or channels <= 0
                    or sample_width <= 0
                    or sample_rate <= 0
                    or stream.getcomptype() != "NONE"
                    or (self.settings.sample_rate is not None and sample_rate != self.settings.sample_rate)
                ):
                    return False
                # wave.getnframes() trusts the header. Read the declared payload
                # so a truncated cache entry cannot report a plausible duration.
                return len(stream.readframes(frames)) == frames * channels * sample_width
        except (wave.Error, OSError, EOFError):
            return False

    def _result(self, path: Path) -> VoiceResult:
        with wave.open(str(path), "rb") as stream:
            duration = stream.getnframes() / stream.getframerate()
        return VoiceResult(artifact_path=str(path), duration_seconds=duration, checksum_sha256=_checksum(path), provider_name=self.provider_name)

    @staticmethod
    def _path(value: Path | str | None) -> Path:
        assert value is not None
        path = Path(value)
        return path if path.is_absolute() else REPOSITORY_ROOT / path

    def _executable(self) -> str:
        executable = Path(self.settings.executable)
        return str(executable) if executable.parent == Path(".") else str(self._path(executable))


def _checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
