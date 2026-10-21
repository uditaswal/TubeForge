"""Declarative hook/close visuals resolved against spoken-word alignment."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from tubeforge.domain.contracts import CardMotionKind
from tubeforge.pipeline.alignment import WordTiming
from tubeforge.rendering.animated_terminal import BOLD_FONT, FONT


ANIMATED_CARD_VERSION = "animated-card-v3"


@dataclass(frozen=True, slots=True)
class AnimatedCardScene:
    scene_id: str
    section_id: str
    kind: CardMotionKind
    heading: str
    elements: tuple[str, str, str]
    source_ids: tuple[str, ...]
    scene_start_seconds: float
    duration_seconds: float
    first_word_index: int
    second_word_index: int
    third_word_index: int
    step_number: int
    step_count: int


def resolve_card_cues(scene: AnimatedCardScene, words: tuple[WordTiming, ...]) -> tuple[float, float, float]:
    spoken = tuple(word for word in words if word.section_id == scene.section_id)
    indices = (scene.first_word_index, scene.second_word_index, scene.third_word_index)
    if not spoken or not (0 <= indices[0] < indices[1] < indices[2] < len(spoken)):
        raise ValueError("card reveal word indices are out of order or stale")
    values = tuple(spoken[index].start_seconds - scene.scene_start_seconds for index in indices)
    if not (0 <= values[0] < values[1] < values[2] < scene.duration_seconds):
        raise ValueError("card reveal anchors cannot resolve inside this clip")
    return values


def _validate(scene: AnimatedCardScene) -> None:
    if not scene.scene_id or not scene.section_id or not 1 <= scene.step_number <= scene.step_count <= 8:
        raise ValueError("animated card scene identity or step is invalid")
    if not (3 <= scene.duration_seconds <= 12 and math.isfinite(scene.scene_start_seconds) and scene.scene_start_seconds >= 0):
        raise ValueError("animated card scene duration or start is invalid")
    if scene.kind not in {CardMotionKind.HOOK, CardMotionKind.CLOSE}:
        raise ValueError("animated card kind is invalid")
    if not scene.heading.strip() or len(scene.heading) > 30 or "\n" in scene.heading:
        raise ValueError("animated card heading is missing or too wide")
    if len(scene.elements) != 3 or any(not item.strip() or len(item) > 32 or "\n" in item for item in scene.elements):
        raise ValueError("animated card elements are missing or too wide")


def _heading_text(value: str) -> str:
    if len(value) <= 16:
        return value
    words = value.split()
    candidates = [
        (" ".join(words[:index]), " ".join(words[index:]))
        for index in range(1, len(words))
    ]
    valid = [(left, right) for left, right in candidates if max(len(left), len(right)) <= 18]
    if not valid:
        raise ValueError("animated card heading cannot fit the portrait layout")
    left, right = min(valid, key=lambda pair: abs(len(pair[0]) - len(pair[1])))
    return left + "\n" + right


def prepare_card_visual_command(
    scene: AnimatedCardScene,
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
    """Prepare an inert video-only FFmpeg command for the bounded render loop."""
    if width > height:
        from tubeforge.rendering.animated_landscape import prepare_landscape
        return prepare_landscape(
            scene, resolve_card_cues(scene, words), output, scratch, layout=scene.kind.value,
            ffmpeg=ffmpeg, threads=threads, crf=crf, width=width, height=height,
            fps=fps, tail_pad_frames=tail_pad_frames,
        )
    _validate(scene)
    cues = resolve_card_cues(scene, words)
    if not FONT.is_file() or not BOLD_FONT.is_file():
        raise ValueError("animated card fonts are unavailable")
    scratch.mkdir(parents=True, exist_ok=True)

    def label(name: str, value: str, x: str | int, y: int, size: int, color: str, *, enable: str | None = None) -> str:
        path = scratch / name
        path.write_text(value, encoding="utf-8")
        result = f"drawtext=fontfile={BOLD_FONT}:textfile={path}:reload=0:fontcolor={color}:fontsize={size}:x={x}:y={y}"
        return result + (f":enable='gte(t,{enable})'" if enable else "")

    filters = [
        label("step.txt", f"STEP {scene.step_number} / {scene.step_count}", "(w-text_w)/2", 275, 28, "0x57dfff"),
        label("heading.txt", _heading_text(scene.heading), "(w-text_w)/2", 350, 78, "white"),
    ]
    for index in range(scene.step_count):
        bar_width = int((860 - (scene.step_count - 1) * 10) / scene.step_count)
        color = "0x57dfff" if index < scene.step_number else "0x26354b"
        filters.append(f"drawbox=x={70 + index * (bar_width + 10)}:y=220:w={bar_width}:h=7:color={color}:t=fill")

    if scene.kind is CardMotionKind.HOOK:
        for index, (x, color) in enumerate(((75, "0x183d63"), (565, "0x4a2945"))):
            at = f"{cues[index]:.3f}"
            filters.append(f"drawbox=x={x}:y=680:w=440:h=240:color={color}:t=fill:enable='gte(t,{at})'")
            filters.append(label(f"item-{index}.txt", scene.elements[index], f"{x}+(440-text_w)/2", 780, 42, "white", enable=at))
        at = f"{cues[2]:.3f}"
        filters.extend((
            label("arrow.txt", "↓", "(w-text_w)/2", 938, 90, "0x57dfff", enable=at),
            f"drawbox=x=145:y=1050:w=790:h=185:color=0x1c684e:t=fill:enable='gte(t,{at})'",
            label("item-2.txt", scene.elements[2], "(w-text_w)/2", 1120, 48, "white", enable=at),
        ))
    else:
        for index, (y, color) in enumerate(((630, "0x164367"), (850, "0x6a5020"), (1070, "0x1c684e"))):
            at = f"{cues[index]:.3f}"
            filters.append(f"drawbox=x=125:y={y}:w=830:h=165:color={color}:t=fill:enable='gte(t,{at})'")
            filters.append(label(f"item-{index}.txt", scene.elements[index], "(w-text_w)/2", y+55, 50, "white", enable=at))

    if tail_pad_frames < 0:
        raise ValueError("tail padding cannot be negative")
    filters.extend((f"scale={width}:{height}:flags=lanczos", "format=yuv420p[v]"))
    graph = ",".join(filters)
    frames = round(scene.duration_seconds * fps) + tail_pad_frames
    render_duration = frames / fps
    return [
        ffmpeg, "-nostdin", "-y", "-v", "error", "-threads", str(threads), "-filter_complex_threads", str(threads),
        "-f", "lavfi", "-i", f"gradients=s=1080x1920:r=30:c0=0x081021:c1=0x251747:x0=0:y0=0:x1=1080:y1=1920:d={render_duration:.6f}",
        "-filter_complex", f"[0:v]{graph}", "-map", "[v]", "-an", "-c:v", "libx264", "-crf", str(crf),
        "-preset", "veryfast", "-threads", str(threads), "-r", str(fps), "-frames:v", str(frames), "-movflags", "+faststart", str(output),
    ]
