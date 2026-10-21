"""Source-bound teaching layouts with word-anchored, non-executable reveals."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from tubeforge.pipeline.alignment import WordTiming
from tubeforge.pipeline.scene_contracts import SceneLayout
from tubeforge.rendering.animated_terminal import BOLD_FONT, FONT


ANIMATED_TEACHING_VERSION = "animated-teaching-v3"
ANIMATED_TEACHING_PANELS_FIRST_VERSION = "comparison-panels-first-v1"
TEACHING_LAYOUTS = frozenset({SceneLayout.FLOW_DIAGRAM, SceneLayout.COMPARISON, SceneLayout.TIMELINE, SceneLayout.SOURCE_CARD})


@dataclass(frozen=True, slots=True)
class AnimatedTeachingScene:
    scene_id: str
    section_id: str
    layout: SceneLayout
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
    comparison_panels_first: bool = False


def resolve_teaching_cues(scene: AnimatedTeachingScene, words: tuple[WordTiming, ...]) -> tuple[float, float, float]:
    spoken = tuple(word for word in words if word.section_id == scene.section_id)
    indices = (scene.first_word_index, scene.second_word_index, scene.third_word_index)
    if not spoken or not (0 <= indices[0] < indices[1] < indices[2] < len(spoken)):
        raise ValueError("teaching reveal word indices are out of order or stale")
    values = tuple(spoken[index].start_seconds - scene.scene_start_seconds for index in indices)
    if not (0 <= values[0] < values[1] < values[2] < scene.duration_seconds):
        raise ValueError("teaching reveal anchors cannot resolve inside this clip")
    return values


def _wrap(value: str, *, max_chars: int, max_lines: int) -> str:
    words = value.split()
    if not words or any(len(word) > max_chars for word in words):
        raise ValueError("teaching display token does not fit the portrait layout")
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else current + " " + word
        if len(candidate) <= max_chars:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        raise ValueError("teaching display text needs editorial shortening")
    return "\n".join(lines)


def _validate(scene: AnimatedTeachingScene) -> None:
    if not scene.scene_id or not scene.section_id or scene.layout not in TEACHING_LAYOUTS:
        raise ValueError("teaching scene identity or layout is invalid")
    if not (1 <= scene.step_number <= scene.step_count <= 8):
        raise ValueError("teaching step count is invalid")
    if not (3 <= scene.duration_seconds <= 12 and math.isfinite(scene.scene_start_seconds) and scene.scene_start_seconds >= 0):
        raise ValueError("teaching scene timing is invalid")
    if not scene.heading.strip() or len(scene.heading) > 80 or "\n" in scene.heading:
        raise ValueError("teaching heading is missing or invalid")
    _wrap(scene.heading, max_chars=20, max_lines=3)
    if len(scene.elements) != 3 or any(not item.strip() or len(item) > 80 or "\n" in item for item in scene.elements):
        raise ValueError("teaching elements are missing or invalid")
    for item in scene.elements:
        _wrap(item, max_chars=26, max_lines=3)
    if scene.layout is SceneLayout.SOURCE_CARD and not scene.source_ids:
        raise ValueError("source-card scene requires a cited source")
    if scene.comparison_panels_first and scene.layout is not SceneLayout.COMPARISON:
        raise ValueError("comparison panel reveal order requires a comparison scene")


def prepare_teaching_visual_command(
    scene: AnimatedTeachingScene,
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
    """Prepare a video-only FFmpeg command; displayed data never enters a shell."""
    if width > height:
        from tubeforge.rendering.animated_landscape import prepare_landscape
        return prepare_landscape(
            scene, resolve_teaching_cues(scene, words), output, scratch, layout=scene.layout.value,
            ffmpeg=ffmpeg, threads=threads, crf=crf, width=width, height=height,
            fps=fps, tail_pad_frames=tail_pad_frames,
        )
    _validate(scene)
    cues = resolve_teaching_cues(scene, words)
    if not FONT.is_file() or not BOLD_FONT.is_file():
        raise ValueError("teaching fonts are unavailable")
    scratch.mkdir(parents=True, exist_ok=True)

    def label(name: str, value: str, x: str | int, y: int, size: int, color: str, *, at: float | None = None, bold: bool = True) -> str:
        path = scratch / name
        path.write_text(value, encoding="utf-8")
        font = BOLD_FONT if bold else FONT
        result = f"drawtext=fontfile={font}:textfile={path}:reload=0:fontcolor={color}:fontsize={size}:x={x}:y={y}"
        return result + (f":enable='gte(t,{at:.3f})'" if at is not None else "")

    def box(x: int, y: int, w: int, h: int, color: str, at: float) -> str:
        return f"drawbox=x={x}:y={y}:w={w}:h={h}:color={color}:t=fill:enable='gte(t,{at:.3f})'"

    heading = _wrap(scene.heading, max_chars=20, max_lines=3)
    filters = [
        label("step.txt", f"STEP {scene.step_number} / {scene.step_count}", "(w-text_w)/2", 275, 28, "0x57dfff"),
        label("heading.txt", heading, "(w-text_w)/2", 330, 68 if "\n" not in heading else 60, "white"),
    ]
    for index in range(scene.step_count):
        bar_width = int((860 - (scene.step_count - 1) * 10) / scene.step_count)
        color = "0x57dfff" if index < scene.step_number else "0x26354b"
        filters.append(f"drawbox=x={70 + index * (bar_width + 10)}:y=220:w={bar_width}:h=7:color={color}:t=fill")

    items = tuple(_wrap(item, max_chars=26, max_lines=3) for item in scene.elements)
    if scene.layout is SceneLayout.FLOW_DIAGRAM:
        filters.extend((
            box(235, 585, 610, 175, "0x183d63", cues[0]),
            label("item-0.txt", items[0], "(w-text_w)/2", 645, 52, "white", at=cues[0]),
            box(90, 960, 420, 180, "0x1c684e", cues[1]),
            label("item-1.txt", items[1], "90+(420-text_w)/2", 1020, 54, "white", at=cues[1]),
            box(570, 960, 420, 180, "0x1c684e", cues[2]),
            label("item-2.txt", items[2], "570+(420-text_w)/2", 1020, 54, "white", at=cues[2]),
            label("arrow-1.txt", "↙", 305, 790, 110, "0x57dfff", at=cues[1]),
            label("arrow-2.txt", "↘", 680, 790, 110, "0x57dfff", at=cues[2]),
        ))
    elif scene.layout is SceneLayout.COMPARISON:
        left_text = _wrap(scene.elements[0], max_chars=12, max_lines=3)
        right_index = 1 if scene.comparison_panels_first else 2
        detail_index = 2 if scene.comparison_panels_first else 1
        right_text = _wrap(scene.elements[right_index], max_chars=12, max_lines=3)
        filters.extend((
            box(70, 650, 440, 300, "0x183d63", cues[0]),
            label("item-0.txt", left_text, "70+(440-text_w)/2", 715, 44, "white", at=cues[0]),
            box(100, 1000, 880, 190, "0x304060", cues[detail_index]),
            label("detail.txt", items[detail_index], "(w-text_w)/2", 1045, 42, "white", at=cues[detail_index]),
            box(570, 650, 440, 300, "0x1c684e", cues[right_index]),
            label("right.txt", right_text, "570+(440-text_w)/2", 715, 44, "white", at=cues[right_index]),
        ))
    elif scene.layout is SceneLayout.TIMELINE:
        for index, (y, color) in enumerate(((620, "0x183d63"), (850, "0x304060"), (1080, "0x1c684e"))):
            filters.append(box(145, y, 790, 155, color, cues[index]))
            filters.append(label(f"item-{index}.txt", items[index], "(w-text_w)/2", y+50, 46, "white", at=cues[index]))
            if index:
                filters.append(label(f"arrow-{index}.txt", "↓", "(w-text_w)/2", y-68, 62, "0x57dfff", at=cues[index]))
    else:
        filters.extend((
            box(70, 550, 940, 690, "0x0b1728", cues[0]),
            box(70, 550, 940, 70, "0x183d63", cues[0]),
            label("document.txt", "SOURCE SNAPSHOT", "(w-text_w)/2", 565, 28, "0x57dfff", at=cues[0]),
            label("item-0.txt", items[0], "(w-text_w)/2", 690, 46, "white", at=cues[0]),
            box(110, 835, 860, 130, "0x173f54", cues[1]),
            label("item-1.txt", items[1], "(w-text_w)/2", 875, 43, "white", at=cues[1]),
            box(110, 1010, 860, 130, "0x493f24", cues[2]),
            label("item-2.txt", items[2], "(w-text_w)/2", 1050, 43, "white", at=cues[2]),
            label("source-id.txt", "SOURCE: " + scene.source_ids[0], "(w-text_w)/2", 1180, 24, "0x90a8c7", at=cues[0], bold=False),
        ))

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
