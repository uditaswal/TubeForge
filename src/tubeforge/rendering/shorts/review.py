"""Review evidence from the same scene compositor used for video frames."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image

from .layout import SceneRenderer
from .schema import ShortsTopic


def write_layout_review(topic: ShortsTopic, output: Path) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    renderer = SceneRenderer(topic)
    report = renderer.validate()
    report["topic_sha256"] = hashlib.sha256(topic.model_dump_json().encode()).hexdigest()
    report["scope"] = "Fully revealed layout and all caption chunks; not audiovisual acceptance or operator approval"
    (output / "layout-qa.json").write_text(json.dumps(report, indent=2) + "\n")
    columns = 4
    sheet = Image.new("RGB", (270 * columns, 480 * ((len(topic.scenes) + columns - 1) // columns)), "#080f1f")
    for i, scene in enumerate(topic.scenes):
        frame = renderer.frame(i, chunk=0, rails=True)
        frame.save(output / f"{i + 1:02d}-{scene.template}.png")
        sheet.paste(frame.resize((270, 480), Image.Resampling.LANCZOS), (270 * (i % columns), 480 * (i // columns)))
    target = output / "contact-sheet.png"
    sheet.save(target)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("topic", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    topic = ShortsTopic.model_validate_json(args.topic.read_text())
    print(write_layout_review(topic, args.output))


if __name__ == "__main__":
    main()
