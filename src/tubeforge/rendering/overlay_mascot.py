"""Put the Chip mascot on top of any finished video (one ffmpeg overlay; audio is copied).

python -m tubeforge.rendering.overlay_mascot input.mp4 output.mp4 [--position bottom-right] [--size 0.16] [--margin 0.04]
``--size`` is the mascot width as a fraction of the video width. Positions: top-left, top-right, bottom-left, bottom-right.
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from tubeforge.rendering.shorts.mascot import SPRITE

POSITIONS = {
    "top-left": "x={m}:y={m}",
    "top-right": "x=main_w-overlay_w-{m}:y={m}",
    "bottom-left": "x={m}:y=main_h-overlay_h-{m}",
    "bottom-right": "x=main_w-overlay_w-{m}:y=main_h-overlay_h-{m}",
}


def command(source: Path, destination: Path, *, position: str = "bottom-right", size: float = 0.16, margin: float = 0.04,
            ffmpeg: str = "ffmpeg", sprite: Path = SPRITE) -> list[str]:
    if position not in POSITIONS:
        raise ValueError(f"position must be one of {sorted(POSITIONS)}")
    if not 0.04 <= size <= 0.5 or not 0 <= margin <= 0.2:
        raise ValueError("size must be 0.04-0.5 and margin 0-0.2 of the video width")
    place = POSITIONS[position].format(m=f"(main_w*{margin})")
    graph = f"[1:v][0:v]scale2ref=w=main_w*{size}:h=ow/mdar[mascot][base];[base][mascot]overlay={place}:format=auto,format=yuv420p[out]"
    return [ffmpeg, "-nostdin", "-y", "-v", "error", "-i", str(source), "-i", str(sprite), "-filter_complex", graph,
            "-map", "[out]", "-map", "0:a?", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-c:a", "copy", "-movflags", "+faststart", str(destination)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--position", default="bottom-right", choices=sorted(POSITIONS))
    parser.add_argument("--size", type=float, default=0.16)
    parser.add_argument("--margin", type=float, default=0.04)
    args = parser.parse_args()
    subprocess.run(command(args.source, args.destination, position=args.position, size=args.size, margin=args.margin), check=True, timeout=1800)
    print(args.destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
