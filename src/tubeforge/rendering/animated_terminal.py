"""Bounded, declarative terminal-scene motion proof for portrait videos.

The content and word-index cues belong to a validated scene contract. This
module only resolves those cues against measured alignment and draws them;
it never executes a displayed command or treats it as an FFmpeg expression.
"""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from tubeforge.pipeline.alignment import WordTiming


ANIMATED_TERMINAL_VERSION = "animated-terminal-v1"
ANIMATED_TERMINAL_LONG_VERSION = "animated-terminal-long-v1"
ANIMATED_TERMINAL_THIRD_VERSION = "animated-terminal-third-v1"
ANIMATED_TERMINAL_HEADING_VERSION = "animated-terminal-heading-v1"
FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
BOLD_FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
MONO_FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")


@dataclass(frozen=True, slots=True)
class AnimatedTerminalScene:
    scene_id: str
    heading: str
    command: str
    output_label: str
    output_line: str
    secondary_line: str
    source_ids: tuple[str, ...]
    section_id: str
    scene_start_seconds: float
    duration_seconds: float
    command_start_word_index: int
    command_end_word_index: int
    output_word_index: int
    secondary_word_index: int
    step_number: int
    step_count: int
    third_line: str | None = None
    third_word_index: int | None = None


def _sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1_048_576), b""):
            value.update(chunk)
    return value.hexdigest()


def resolve_cues(scene: AnimatedTerminalScene, words: tuple[WordTiming, ...]) -> dict[str, float]:
    """Resolve local spoken-word positions, failing on stale/ambiguous input."""
    spoken = tuple(word for word in words if word.section_id == scene.section_id)
    if not spoken or any(word.end_seconds <= word.start_seconds for word in spoken):
        raise ValueError("scene requires measured, positive word alignment")
    indices = (scene.command_start_word_index, scene.command_end_word_index, scene.output_word_index, scene.secondary_word_index)
    if not (0 <= indices[0] <= indices[1] < indices[2] < indices[3] < len(spoken)):
        raise ValueError("scene reveal word indices are out of order or stale")
    values = {
        "type_start": spoken[indices[0]].start_seconds - scene.scene_start_seconds,
        "type_end": spoken[indices[1]].end_seconds - scene.scene_start_seconds,
        "output_start": spoken[indices[2]].start_seconds - scene.scene_start_seconds,
        "secondary_start": spoken[indices[3]].start_seconds - scene.scene_start_seconds,
    }
    if not (0 <= values["type_start"] < values["type_end"] < values["output_start"] < values["secondary_start"] < scene.duration_seconds):
        raise ValueError("scene reveal anchors cannot resolve inside this clip")
    if scene.third_word_index is not None:
        if not indices[3] < scene.third_word_index < len(spoken):
            raise ValueError("terminal third reveal word index is out of order or stale")
        values["third_start"] = spoken[scene.third_word_index].start_seconds - scene.scene_start_seconds
        if not values["secondary_start"] < values["third_start"] < scene.duration_seconds:
            raise ValueError("terminal third reveal anchor cannot resolve inside this clip")
    return values


def _validate_scene(scene: AnimatedTerminalScene) -> None:
    if not (scene.scene_id and scene.section_id and scene.source_ids):
        raise ValueError("animated terminal requires scene, section and cited source")
    if not (1 <= scene.step_number <= scene.step_count <= 8):
        raise ValueError("animated terminal step count is invalid")
    if not (3 <= scene.duration_seconds <= 10.5 and math.isfinite(scene.scene_start_seconds)):
        raise ValueError("animated terminal proof must last 3–10.5 seconds")
    for name, limit in (("heading", 24), ("command", 80), ("output_label", 30), ("output_line", 36), ("secondary_line", 36)):
        value = getattr(scene, name)
        if not value or not value.strip() or len(value) > limit or "\n" in value:
            raise ValueError(f"animated terminal {name} is missing or too wide")
    _display_command(scene.command)
    _display_heading(scene.heading)
    if (scene.third_line is None) != (scene.third_word_index is None):
        raise ValueError("terminal third text and word cue must be supplied together")
    if scene.third_line is not None and (not scene.third_line.strip() or len(scene.third_line) > 36 or "\n" in scene.third_line):
        raise ValueError("terminal third line is missing or too wide")


def _display_command(value: str) -> str:
    """Wrap a displayed CLI command without changing or executing its bytes."""
    if len(value) <= 38:
        return value
    lines = [""]
    for token in value.split(" "):
        if not token or len(token) > 26:
            raise ValueError("terminal command needs editorial line breaking")
        candidate = token if not lines[-1] else lines[-1] + " " + token
        if len(candidate) <= 26:
            lines[-1] = candidate
        else:
            lines.append(token)
    if len(lines) > 2:
        raise ValueError("terminal command needs editorial line breaking")
    return "\n".join(lines)


def _display_heading(value: str) -> str:
    if len(value) <= 16:
        return value
    words = value.split()
    candidates = [(" ".join(words[:index]), " ".join(words[index:])) for index in range(1, len(words))]
    valid = [(left, right) for left, right in candidates if max(len(left), len(right)) <= 16]
    if not valid:
        raise ValueError("terminal heading needs editorial shortening")
    left, right = min(valid, key=lambda pair: abs(len(pair[0]) - len(pair[1])))
    return left + "\n" + right


def _visual_filters(scene: AnimatedTerminalScene, cues: dict[str, float], scratch: Path) -> list[str]:
    def label(name: str, value: str, x: int | str, y: int, size: int, color: str, *, bold: bool = False, mono: bool = False, enable: str | None = None) -> str:
        path = scratch / name
        path.write_text(value, encoding="utf-8")
        font = MONO_FONT if mono else BOLD_FONT if bold else FONT
        result = f"drawtext=fontfile={font}:textfile={path}:reload=0:fontcolor={color}:fontsize={size}:x={x}:y={y}"
        return result + (f":enable='{enable}'" if enable else "")

    filters = [
        "drawbox=x=72:y=520:w=858:h=570:color=0x09121e:t=fill",
        "drawbox=x=72:y=520:w=858:h=70:color=0x172746:t=fill",
        label("step.txt", f"STEP {scene.step_number} / {scene.step_count}", "(w-text_w)/2", 275, 28, "0x57dfff", bold=True),
        label("heading.txt", _display_heading(scene.heading), "(w-text_w)/2", 350, 78, "white", bold=True),
        label("terminal.txt", "terminal", "(w-text_w)/2", 540, 22, "0x9caec7"),
        label("prompt.txt", "$", 110, 645, 48, "0x5dda85", mono=True),
    ]
    for index in range(scene.step_count):
        width = int((860 - (scene.step_count - 1) * 10) / scene.step_count)
        color = "0x57dfff" if index < scene.step_number else "0x26354b"
        filters.append(f"drawbox=x={70 + index * (width + 10)}:y=220:w={width}:h=7:color={color}:t=fill")
    for index, color in enumerate(("0xff646b", "0xffd167", "0x5dda85")):
        filters.append(f"drawbox=x={105 + index * 29}:y=546:w=15:h=15:color={color}:t=fill")
    interval = (cues["type_end"] - cues["type_start"]) / len(scene.command)
    for index in range(1, len(scene.command) + 1):
        start = cues["type_start"] + (index - 1) * interval
        end = cues["type_start"] + index * interval if index < len(scene.command) else scene.duration_seconds
        filters.append(label(f"command-{index:02}.txt", _display_command(scene.command[:index].rstrip()), 160, 645, 48, "white", mono=True, enable=f"gte(t,{start:.3f})*lt(t,{end:.3f})"))
    filters.extend((
        label("output-label.txt", scene.output_label, 110, 785, 24, "0x90a8c7", enable=f"gte(t,{cues['output_start']:.3f})"),
        label("output-line.txt", scene.output_line, 110, 850, 42, "0x5dda85", mono=True, enable=f"gte(t,{cues['output_start']:.3f})"),
        label("secondary-line.txt", scene.secondary_line, 110, 930, 36, "0xffd167", mono=True, enable=f"gte(t,{cues['secondary_start']:.3f})"),
    ))
    if scene.third_line is not None:
        filters.append(label("third-line.txt", scene.third_line, 110, 1005, 32, "0x57dfff", mono=True, enable=f"gte(t,{cues['third_start']:.3f})"))
    return filters


def prepare_terminal_visual_command(
    scene: AnimatedTerminalScene,
    words: tuple[WordTiming, ...],
    output: Path,
    scratch: Path,
    *,
    ffmpeg: str,
    threads: int,
    crf: int,
    width: int,
    height: int,
    fps: int,
    tail_pad_frames: int = 0,
) -> list[str]:
    """Build a video-only command for the bounded production render loop."""
    _validate_scene(scene)
    cues = resolve_cues(scene, words)
    if not all(path.is_file() for path in (FONT, BOLD_FONT, MONO_FONT)):
        raise ValueError("animated terminal fonts are unavailable")
    scratch.mkdir(parents=True, exist_ok=True)
    if tail_pad_frames < 0:
        raise ValueError("tail padding cannot be negative")
    filters = _visual_filters(scene, cues, scratch) + [f"scale={width}:{height}:flags=lanczos", "format=yuv420p[v]"]
    graph = ",".join(filters)
    frames = round(scene.duration_seconds * fps) + tail_pad_frames
    render_duration = frames / fps
    return [
        ffmpeg, "-nostdin", "-y", "-v", "error", "-threads", str(threads), "-filter_complex_threads", str(threads),
        "-f", "lavfi", "-i", f"gradients=s=1080x1920:r=30:c0=0x081021:c1=0x251747:x0=0:y0=0:x1=1080:y1=1920:d={render_duration:.6f}",
        "-filter_complex", f"[0:v]{graph}", "-map", "[v]", "-an", "-c:v", "libx264", "-crf", str(crf),
        "-preset", "veryfast", "-threads", str(threads), "-r", str(fps), "-frames:v", str(frames), "-movflags", "+faststart", str(output),
    ]


def render_animated_terminal(
    scene: AnimatedTerminalScene,
    words: tuple[WordTiming, ...],
    narration: Path,
    captions: Path,
    output: Path,
    *,
    ffmpeg: str = "ffmpeg",
) -> dict[str, object]:
    """Render one contract-derived proof scene; production integration follows."""
    _validate_scene(scene)
    cues = resolve_cues(scene, words)
    if not narration.is_file() or not captions.is_file() or not all(path.is_file() for path in (FONT, BOLD_FONT, MONO_FONT)):
        raise ValueError("animated terminal media or fonts are unavailable")
    output.parent.mkdir(parents=True, exist_ok=True)
    temp_output = output.with_name(output.stem + ".part" + output.suffix)
    temp_output.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory(prefix="animated-terminal-", dir=output.parent) as directory:
        scratch = Path(directory)
        filters = _visual_filters(scene, cues, scratch)
        # The retained ASS file has global narration times. Shift this proof
        # clip into that timeline only for the subtitle filter, then shift back.
        shifted = f"setpts=PTS+{scene.scene_start_seconds:.6f}/TB,subtitles='{captions.resolve()}',setpts=PTS-STARTPTS"
        graph = ",".join(filters + [shifted, "format=yuv420p[v]"])
        command = [
            ffmpeg, "-nostdin", "-y", "-v", "error", "-threads", "2", "-filter_complex_threads", "2",
            "-f", "lavfi", "-i", f"gradients=s=1080x1920:r=30:c0=0x081021:c1=0x251747:x0=0:y0=0:x1=1080:y1=1920:d={scene.duration_seconds:.6f}",
            "-ss", f"{scene.scene_start_seconds:.6f}", "-t", f"{scene.duration_seconds:.6f}", "-i", str(narration),
            "-filter_complex", f"[0:v]{graph}", "-map", "[v]", "-map", "1:a:0",
            "-c:v", "libx264", "-crf", "20", "-preset", "veryfast", "-threads", "2", "-r", "30",
            "-c:a", "aac", "-b:a", "160k", "-t", f"{scene.duration_seconds:.6f}", str(temp_output),
        ]
        try:
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120, check=False)
            if result.returncode or not temp_output.is_file() or temp_output.stat().st_size == 0:
                raise RuntimeError("animated terminal FFmpeg render failed: " + result.stderr.decode(errors="replace")[-1500:])
            temp_output.replace(output)
        finally:
            temp_output.unlink(missing_ok=True)
    return {
        "renderer_version": ANIMATED_TERMINAL_VERSION,
        "scene_id": scene.scene_id,
        "source_ids": list(scene.source_ids),
        "cues": cues,
        "scene_data_sha256": hashlib.sha256(json.dumps(asdict(scene), sort_keys=True).encode()).hexdigest(),
        "narration_sha256": _sha256(narration),
        "captions_sha256": _sha256(captions),
        "output_sha256": _sha256(output),
    }
