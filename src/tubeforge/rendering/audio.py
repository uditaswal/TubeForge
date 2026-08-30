"""Small FFprobe/FFmpeg wrappers used only for audio measurement and assembly."""

from __future__ import annotations

import json
import math
import subprocess
import wave
from pathlib import Path

from tubeforge.core.errors import ProviderValidationError, RetryableProviderError


class FFprobe:
    def __init__(self, executable: str = "ffprobe", timeout_seconds: int = 30) -> None:
        self.executable, self.timeout_seconds = executable, timeout_seconds

    def command(self, path: Path) -> list[str]:
        # ``inspect`` selects the audio stream by codec_type. Keep that field in
        # the explicit projection: ffprobe does not emit fields that were not
        # requested, even for an audio-only WAV.
        return [self.executable, "-v", "error", "-show_entries", "format=duration:stream=codec_type,codec_name,sample_rate,channels", "-of", "json", str(path)]

    def inspect(self, path: Path) -> dict[str, object]:
        if not path.is_file() or path.stat().st_size == 0:
            raise ProviderValidationError("audio artifact is missing or empty")
        try:
            result = subprocess.run(self.command(path), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=self.timeout_seconds, check=False, shell=False)
        except subprocess.TimeoutExpired as error:
            raise RetryableProviderError("ffprobe timed out") from error
        except OSError as error:
            raise ProviderValidationError("ffprobe executable is unavailable") from error
        if result.returncode:
            raise ProviderValidationError("ffprobe rejected audio artifact")
        try:
            data = json.loads(result.stdout.decode("utf-8"))
            duration = float(data["format"]["duration"])
            streams = data["streams"]
            audio = next(stream for stream in streams if stream.get("codec_type") == "audio")
            codec_value = audio["codec_name"]
            if not isinstance(codec_value, str):
                raise TypeError("audio codec name is not text")
            codec = codec_value.strip()
            sample_rate = int(audio["sample_rate"])
            channels = int(audio["channels"])
        except (KeyError, StopIteration, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ProviderValidationError("ffprobe returned invalid duration data") from error
        if not math.isfinite(duration) or duration <= 0 or not codec or sample_rate <= 0 or channels <= 0:
            raise ProviderValidationError("ffprobe returned invalid audio stream metadata")
        return {"duration_seconds": duration, "streams": streams}


class FFmpegAudioAssembler:
    def __init__(self, executable: str = "ffmpeg", threads: int = 1, timeout_seconds: int = 300) -> None:
        self.executable, self.threads, self.timeout_seconds = executable, threads, timeout_seconds

    def command(self, inputs: tuple[Path, ...], output: Path, pause_seconds: float) -> list[str]:
        command = [self.executable, "-nostdin", "-y", "-v", "error", "-threads", str(self.threads)]
        labels: list[str] = []
        for index, path in enumerate(inputs):
            command.extend(("-i", str(path)))
            input_index = len(labels)
            labels.append(f"[{input_index}:a]")
            if index < len(inputs) - 1 and pause_seconds:
                command.extend(("-f", "lavfi", "-t", f"{pause_seconds:.6f}", "-i", "anullsrc=r=48000:cl=mono"))
                labels.append(f"[{len(labels)}:a]")
        # Piper models use different native sample rates. Normalize every real
        # phrase and generated pause before concat so FFmpeg does not have to
        # negotiate incompatible stream parameters at the concat boundary.
        filters = [
            f"{label}aresample=48000,aformat=sample_fmts=s16:channel_layouts=mono[n{index}]"
            for index, label in enumerate(labels)
        ]
        normalized = "".join(f"[n{index}]" for index in range(len(labels)))
        filters.append(f"{normalized}concat=n={len(labels)}:v=0:a=1[outa]")
        return [*command, "-filter_complex", ";".join(filters), "-map", "[outa]", "-c:a", "pcm_s16le", str(output)]

    @staticmethod
    def _valid_output(path: Path) -> bool:
        """Validate the complete normalized WAV before atomic promotion."""
        try:
            if not path.is_file() or path.stat().st_size <= 44:
                return False
            with wave.open(str(path), "rb") as stream:
                frames = stream.getnframes()
                if (
                    stream.getcomptype() != "NONE"
                    or stream.getnchannels() != 1
                    or stream.getsampwidth() != 2
                    or stream.getframerate() != 48_000
                    or frames <= 0
                ):
                    return False
                return len(stream.readframes(frames)) == frames * 2
        except (EOFError, OSError, wave.Error):
            return False

    def assemble(self, inputs: tuple[Path, ...], output: Path, *, pause_seconds: float = 0.0) -> None:
        if not inputs or any(not path.is_file() or path.stat().st_size == 0 for path in inputs):
            raise ProviderValidationError("cannot assemble missing audio phrases")
        if not math.isfinite(pause_seconds) or pause_seconds < 0:
            raise ProviderValidationError("audio pause must be finite and nonnegative")
        output.parent.mkdir(parents=True, exist_ok=True)
        # Keep the final extension so FFmpeg can select the output container.
        temporary = output.with_name(f"{output.stem}.tmp{output.suffix}")
        # A killed/failed earlier invocation may have left this path behind.
        # Never allow stale bytes to satisfy the success checks for this run.
        temporary.unlink(missing_ok=True)
        try:
            result = subprocess.run(self.command(inputs, temporary, pause_seconds), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=self.timeout_seconds, check=False, shell=False)
        except subprocess.TimeoutExpired as error:
            temporary.unlink(missing_ok=True)
            raise RetryableProviderError("FFmpeg audio assembly timed out") from error
        except OSError as error:
            temporary.unlink(missing_ok=True)
            raise ProviderValidationError("FFmpeg executable is unavailable") from error
        if result.returncode or not self._valid_output(temporary):
            temporary.unlink(missing_ok=True)
            raise RetryableProviderError("FFmpeg audio assembly failed")
        temporary.replace(output)
