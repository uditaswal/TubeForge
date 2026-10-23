"""Render a local test video from a previously reviewed reference Short topic.

This is test-fixture evidence, never a production approval or publishing action.
Use a fresh output directory so prior media and review evidence stay intact.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from tubeforge.core.config import load_settings
from tubeforge.pipeline import reference_short
from tubeforge.rendering.shorts.prepare import prepare
from tubeforge.rendering.shorts.schema import ShortsTopic


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_job", type=Path, help="existing locally reviewed job folder")
    parser.add_argument("output", type=Path, help="fresh test artifact folder")
    parser.add_argument("--config", type=Path, default=Path("config/production.yaml"))
    args = parser.parse_args()
    source = args.source_job.resolve(strict=True)
    output = args.output.resolve()
    if output.exists():
        raise SystemExit(f"output must be a fresh folder: {output}")
    settings = load_settings(args.config)
    config = settings.pipeline.reference_short
    if config.alignment_model_path is None:
        raise SystemExit("reference alignment model is not configured")
    topic = ShortsTopic.model_validate_json((source / "reference" / "topic.json").read_text())
    output.mkdir(parents=True)
    for name in ("content_package.json", "effective_content_request.json", "metadata.json"):
        path = source / name
        if path.is_file():
            shutil.copyfile(path, output / name)
    reference = output / "reference"
    timeline = prepare(topic, reference, config=args.config.resolve(),
                       alignment_model=reference_short.resolve(config.alignment_model_path),
                       voice=config.voice)
    report = reference_short.render(timeline, reference, output / "final.mp4", config,
                                    draft=False, cancelled=lambda: False)
    (output / "smoke-result.json").write_text(json.dumps({
        "scope": "local test from a previously reviewed topic; no production approval",
        "source_job": str(source), "source_topic_sha256": report["topic_sha256"],
        "final_sha256": report["video_sha256"], "qa_passed": report["passed"],
        "narration_health": report["narration_health"],
        "encoded_audio_health": report["audio_health"],
    }, indent=2) + "\n")
    print(output / "final.mp4")


if __name__ == "__main__":
    main()
