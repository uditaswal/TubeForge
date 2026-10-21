"""Landscape compositions for approved, word-anchored three-element scenes."""
from __future__ import annotations

import math
import textwrap
from pathlib import Path

from tubeforge.rendering.animated_terminal import BOLD_FONT


def prepare_landscape(scene, cues, output: Path, scratch: Path, *, layout: str,
                      ffmpeg: str, threads: int, crf: int, width: int,
                      height: int, fps: int, tail_pad_frames: int = 0) -> list[str]:
    """Keep text in files, geometry in code, and approved copy unchanged."""
    if not math.isfinite(scene.duration_seconds) or not 0 < scene.duration_seconds <= 600:
        raise ValueError("landscape scene duration is invalid")
    if len(scene.elements) != 3 or len(cues) != 3 or tail_pad_frames < 0:
        raise ValueError("landscape scene requires three ordered reveals")
    if not scene.scene_id or not scene.section_id or not 1 <= scene.step_number <= scene.step_count:
        raise ValueError("landscape scene identity is invalid")
    if layout not in {"hook", "close", "comparison", "flow_diagram", "timeline", "source_card"}:
        raise ValueError("unsupported landscape layout")
    if layout == "source_card" and not scene.source_ids:
        raise ValueError("source-card scene requires a cited source")
    if not BOLD_FONT.is_file():
        raise ValueError("landscape font is unavailable")
    scratch.mkdir(parents=True, exist_ok=True)
    filters = []

    def label(name, text, x, y, size, *, at=None, wrap=24):
        lines = textwrap.wrap(text, width=wrap, break_long_words=False, break_on_hyphens=False)
        if not lines or len(lines) > 3 or any(len(line) > wrap for line in lines):
            raise ValueError("landscape display text needs editorial shortening")
        path = scratch / name
        path.write_text("\n".join(lines), encoding="utf-8")
        expr = f"drawtext=fontfile={BOLD_FONT}:textfile={path}:expansion=none:fontcolor=white:fontsize={size}:line_spacing=12:x={x}:y={y}"
        if at is not None:
            expr += f":enable='gte(t,{at:.3f})'"
        filters.append(expr)

    def box(x, y, w, h, color, at):
        filters.append(f"drawbox=x={x}:y={y}:w={w}:h={h}:color={color}:t=fill:enable='gte(t,{at:.3f})'")

    label("heading.txt", scene.heading, 110, 140, 66, wrap=44)
    label("step.txt", f"{scene.step_number:02d} / {scene.step_count:02d}", 1640, 75, 28)
    filters.append("drawbox=x=110:y=105:w=160:h=6:color=0x57dfff:t=fill")
    if layout in {"comparison", "hook"}:
        # Matched panels and a separate takeaway; no implied numerical scale.
        right = 1 if layout == "hook" or scene.comparison_panels_first else 2
        detail = 3 - right
        for panel, (i, x) in enumerate(((0, 110), (right, 1000))):
            box(x, 365, 810, 260, ("0x183d63", "0x4a2945")[panel], cues[i])
            label(f"element-{i}.txt", scene.elements[i], x + 45, 425, 46, at=cues[i], wrap=27)
        box(350, 705, 1220, 140, "0x1c684e", cues[detail])
        label(f"element-{detail}.txt", scene.elements[detail], "(w-text_w)/2", 745, 42, at=cues[detail], wrap=42)
    else:
        # Sequential reveals in three equal columns; captions occupy the bottom.
        for i, x in enumerate((110, 710, 1310)):
            box(x, 390, 500, 350, ("0x183d63", "0x4a2945", "0x1c684e")[i], cues[i])
            label(f"element-{i}.txt", scene.elements[i], x + 35, 485, 42, at=cues[i], wrap=17)
            if layout == "timeline":
                box(x, 345, 500, 5, "0x57dfff", cues[i])
        if layout == "source_card":
            label("source.txt", "SOURCE: " + scene.source_ids[0], 110, 800, 24, at=cues[0], wrap=70)
    frames = round(scene.duration_seconds * fps) + tail_pad_frames
    filters.extend((f"scale={width}:{height}:flags=lanczos", "format=yuv420p[v]"))
    return [
        ffmpeg, "-nostdin", "-y", "-v", "error", "-threads", str(threads),
        "-filter_complex_threads", str(threads), "-f", "lavfi", "-i",
        f"gradients=s=1920x1080:r={fps}:c0=0x081021:c1=0x251747:x0=0:y0=0:x1=1920:y1=1080:d={frames/fps:.6f}",
        "-filter_complex", "[0:v]" + ",".join(filters), "-map", "[v]", "-an",
        "-c:v", "libx264", "-crf", str(crf), "-preset", "veryfast", "-threads",
        str(threads), "-r", str(fps), "-frames:v", str(frames), "-movflags",
        "+faststart", str(output),
    ]
