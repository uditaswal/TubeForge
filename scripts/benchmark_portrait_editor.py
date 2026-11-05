"""Render labelled synthetic vertical editor fixtures; no providers or approvals.

Run from the repository: PYTHONPATH=src python scripts/benchmark_portrait_editor.py
"""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import time

from tubeforge.rendering.shorts.editor import EditorScene, EditorRenderer, VERSION

FIXTURES = {
    "multiline": EditorScene(
        ("cache = {}", "", "def read(key):", "    if key in cache:",
         "        return cache[key]", "    return fetch(key)"),
        typing_seconds=4, hold_seconds=2),
    "command": EditorScene(("python --version",), language="bash", filename="terminal",
        start=0, typing_seconds=2, line_windows=((.25, 1.25),)),
    "width": EditorScene(("identifier_at_maximum_width_12", "print('done')"),
        start=0, typing_seconds=3, line_windows=((.25, 1.25), (2, 2.75))),
}


def render(scene: EditorScene, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    renderer = EditorRenderer(scene)
    started = time.monotonic()
    destination = output / "editor-portrait.mp4"
    temporary = output / "editor-portrait.tmp.mp4"
    process = subprocess.Popen([
        "ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", "1080x1920", "-r", "30", "-i", "pipe:0", "-an", "-c:v", "libx264",
        "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p", str(temporary)],
        stdin=subprocess.PIPE)
    try:
        for number in range(round(scene.duration * 30)):
            process.stdin.write(renderer.frame(number / 30).tobytes())
        process.stdin.close()
        if process.wait():
            raise RuntimeError("encode failed")
        subprocess.run(["ffmpeg", "-v", "error", "-i", str(temporary), "-f", "null", "-"], check=True)
        temporary.replace(destination)
    except BaseException:
        if process.poll() is None:
            process.kill()
        process.wait()
        temporary.unlink(missing_ok=True)
        raise
    for name, seconds in (("opening", 0), ("typing", scene.start + scene.typing_seconds/2),
                          ("hold", scene.start + scene.typing_seconds + .2)):
        renderer.frame(seconds).save(output / f"{name}.png")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(destination), "-vf",
                    "fps=2,scale=270:480,tile=4x4", "-frames:v", "1", str(output / "contact.png")], check=True)
    result = dict(version=VERSION, seconds=scene.duration, frames=round(scene.duration*30),
                  wall_seconds=time.monotonic()-started,
                  sha256=hashlib.sha256(destination.read_bytes()).hexdigest(),
                  line_windows=scene.line_windows,
                  timing_provenance="synthetic fixture; not measured speech",
                  scope="silent synthetic portrait scene; not production acceptance")
    (output / "benchmark.json").write_text(json.dumps(result, indent=2))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", choices=[*FIXTURES, "all"], default="all")
    parser.add_argument("--output", type=Path, default=Path("artifacts/review/reference-motion-v2"))
    args = parser.parse_args()
    for name, scene in FIXTURES.items():
        if args.fixture in (name, "all"):
            print(name, json.dumps(render(scene, args.output / name)))


if __name__ == "__main__":
    main()
