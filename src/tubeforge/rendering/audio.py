"""Small FFprobe/FFmpeg wrappers used only for audio measurement and assembly."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from tubeforge.core.errors import ProviderValidationError, RetryableProviderError


class FFprobe:
    def __init__(self, executable: str = "ffprobe", timeout_seconds: int = 30) -> None:
        self.executable, self.timeout_seconds = executable, timeout_seconds

    def command(self, path: Path) -> list[str]:
        return [self.executable, "-v", "error", "-show_entries", "format=duration:stream=codec_name,sample_rate,channels", "-of", "json", str(path)]

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
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise ProviderValidationError("ffprobe returned invalid duration data") from error
        if duration <= 0:
            raise ProviderValidationError("audio duration must be positive")
        return {"duration_seconds": duration, "streams": data.get("streams", [])}


class FFmpegAudioAssembler:
    def __init__(self, executable: str = "ffmpeg", threads: int = 1, timeout_seconds: int = 300) -> None:
        self.executable, self.threads, self.timeout_seconds = executable, threads, timeout_seconds

    def command(self, inputs: tuple[Path, ...], output: Path, pause_seconds: float) -> list[str]:
        command = [self.executable, "-nostdin", "-y", "-v", "error", "-threads", str(self.threads)]
        labels: list[str] = []
        for index, path in enumerate(inputs):
            command.extend(("-i", str(path)))
            labels.append(f"[{len(labels)}:a]")
            if index < len(inputs) - 1 and pause_seconds:
                command.extend(("-f", "lavfi", "-t", f"{pause_seconds:.6f}", "-i", "anullsrc=r=48000:cl=mono"))
                labels.append(f"[{len(labels)}:a]")
        return [*command, "-filter_complex", "".join(labels) + f"concat=n={len(labels)}:v=0:a=1[outa]", "-map", "[outa]", "-c:a", "pcm_s16le", str(output)]

    def assemble(self, inputs: tuple[Path, ...], output: Path, *, pause_seconds: float = 0.0) -> None:
        if not inputs or any(not path.is_file() or path.stat().st_size == 0 for path in inputs):
            raise ProviderValidationError("cannot assemble missing audio phrases")
        if pause_seconds < 0:
            raise ProviderValidationError("audio pause must not be negative")
        output.parent.mkdir(parents=True, exist_ok=True)
        # Keep the final extension so FFmpeg can select the output container.
        temporary = output.with_name(f"{output.stem}.tmp{output.suffix}")
        try:
            result = subprocess.run(self.command(inputs, temporary, pause_seconds), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=self.timeout_seconds, check=False, shell=False)
        except subprocess.TimeoutExpired as error:
            raise RetryableProviderError("FFmpeg audio assembly timed out") from error
        except OSError as error:
            raise ProviderValidationError("FFmpeg executable is unavailable") from error
        if result.returncode or not temporary.is_file() or temporary.stat().st_size == 0:
            temporary.unlink(missing_ok=True)
            raise RetryableProviderError("FFmpeg audio assembly failed")
        temporary.replace(output)
