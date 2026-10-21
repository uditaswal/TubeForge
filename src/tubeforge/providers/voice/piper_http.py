"""Worker client for TubeForge's private, long-lived local Piper service."""

from __future__ import annotations

import hashlib
import json
import tempfile
import urllib.error
import urllib.request
import wave
from pathlib import Path

from tubeforge.core.config import PiperProviderConfig, REPOSITORY_ROOT
from tubeforge.core.errors import ProviderValidationError, RetryableProviderError
from tubeforge.domain.contracts import VoiceRequest, VoiceResult
from tubeforge.pipeline.narration import normalize_narration_text


class PiperHttpVoiceProvider:
    """Cache phrase WAVs locally and ask the internal Piper service on misses."""

    provider_name = "piper-http"

    def __init__(self, settings: PiperProviderConfig) -> None:
        self.settings = settings
        self.calls = 0
        model = self._path(settings.model_path) if settings.model_path else None
        self._model_sha256 = _checksum(model) if model and model.is_file() else "unavailable"

    def cache_key(self, request: VoiceRequest) -> str:
        material = {
            "text": normalize_narration_text(request.text),
            "provider": self.provider_name,
            "voice": self.settings.voice_id,
            "model_checksum": self._model_sha256,
            "speaker": self.settings.speaker,
            "sample_rate": self.settings.sample_rate,
            "settings": request.settings,
            "adapter_version": self.settings.adapter_version,
        }
        return hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def synthesize(self, request: VoiceRequest) -> VoiceResult:
        text = normalize_narration_text(request.text)
        if not text:
            raise ProviderValidationError("Piper narration text is empty")
        key = self.cache_key(request)
        destination = Path(request.output_path) if request.output_path else self._path(self.settings.cache_root) / self.settings.voice_id / f"{key}.wav"
        if self._valid_wave(destination):
            return self._result(destination)
        if not self.settings.server_url:
            raise ProviderValidationError("Piper local service URL is not configured")
        if self.settings.model_path is None or not self._path(self.settings.model_path).is_file():
            raise ProviderValidationError("Piper model file is unavailable to the worker")

        payload = json.dumps({"text": text, "speaker_id": self.settings.speaker}, separators=(",", ":")).encode()
        http_request = urllib.request.Request(
            self.settings.server_url + "/synthesize",
            data=payload,
            headers={"Content-Type": "application/json", "Accept": "audio/wav"},
            method="POST",
        )
        self.calls += 1
        try:
            with urllib.request.urlopen(http_request, timeout=self.settings.timeout_seconds) as response:
                if response.status != 200 or response.headers.get_content_type() != "audio/wav":
                    raise RetryableProviderError("Piper local service returned an unexpected response")
                if response.headers.get("X-Piper-Voice") != self.settings.voice_id:
                    raise ProviderValidationError("Piper service voice does not match the configured voice")
                if response.headers.get("X-Piper-Model-SHA256") != self._model_sha256:
                    raise ProviderValidationError("Piper service model does not match the configured model")
                audio = response.read(self.settings.max_output_bytes + 1)
        except urllib.error.HTTPError as error:
            if error.code >= 500 or error.code in {408, 425, 429}:
                raise RetryableProviderError("Piper local service is temporarily unavailable") from error
            raise ProviderValidationError("Piper local service rejected the synthesis request") from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise RetryableProviderError("Piper local service could not be reached") from error
        if len(audio) > self.settings.max_output_bytes:
            raise ProviderValidationError("Piper output exceeds configured size limit")

        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix="piper-http-", suffix=".wav", dir=destination.parent, delete=False) as temporary:
            temp_path = Path(temporary.name)
            temporary.write(audio)
        try:
            if not self._valid_wave(temp_path):
                raise ProviderValidationError("Piper local service produced invalid audio")
            temp_path.replace(destination)
        finally:
            temp_path.unlink(missing_ok=True)
        return self._result(destination)

    def _valid_wave(self, path: Path) -> bool:
        try:
            if not path.is_file() or path.stat().st_size <= 44 or path.stat().st_size > self.settings.max_output_bytes:
                return False
            with wave.open(str(path), "rb") as stream:
                frames, channels, width, rate = stream.getnframes(), stream.getnchannels(), stream.getsampwidth(), stream.getframerate()
                if frames <= 0 or channels <= 0 or width <= 0 or rate <= 0 or stream.getcomptype() != "NONE":
                    return False
                if self.settings.sample_rate is not None and rate != self.settings.sample_rate:
                    return False
                return len(stream.readframes(frames)) == frames * channels * width
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


def _checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1_048_576), b""):
            digest.update(block)
    return digest.hexdigest()
