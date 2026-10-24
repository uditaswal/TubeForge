"""Render a local test video from a previously reviewed reference Short topic.

This is test-fixture evidence, never a production approval or publishing action.
Use a fresh output directory so prior media and review evidence stay intact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from tubeforge.core.config import load_settings
from tubeforge.pipeline import reference_short
from tubeforge.pipeline.plates import prepare_plates
from tubeforge.core.config import PixabayConfig
from tubeforge.providers.media.pixabay import PixabayClient
from tubeforge.rendering.shorts.prepare import prepare
from tubeforge.rendering.shorts.schema import ShortsTopic


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_job", type=Path, help="existing locally reviewed job folder")
    parser.add_argument("output", type=Path, help="fresh test artifact folder")
    parser.add_argument("--config", type=Path, default=Path("config/production.yaml"))
    parser.add_argument("--visual-plan", type=Path, help="local test-only scene-index-to-stock-visual JSON")
    parser.add_argument("--stock-cache", type=Path, help="existing local Pixabay cache; network is disabled")
    args = parser.parse_args()
    source = args.source_job.resolve(strict=True)
    output = args.output.resolve()
    if output.exists():
        raise SystemExit(f"output must be a fresh folder: {output}")
    settings = load_settings(args.config)
    config = settings.pipeline.reference_short
    if config.alignment_model_path is None:
        raise SystemExit("reference alignment model is not configured")
    source_topic_path = source / "reference" / "topic.json"
    topic = ShortsTopic.model_validate_json(source_topic_path.read_text())
    source_topic_sha256 = hashlib.sha256(source_topic_path.read_bytes()).hexdigest()
    if args.visual_plan:
        if not args.stock_cache:
            raise SystemExit("--visual-plan requires --stock-cache")
        plan = json.loads(args.visual_plan.read_text())
        data = topic.model_dump(mode="json")
        for raw_index, visual in plan.items():
            index = int(raw_index)
            if not 0 <= index < len(data["scenes"]) or data["scenes"][index].get("visual"):
                raise SystemExit("visual plan must target an unassigned scene index")
            data["scenes"][index]["visual"] = visual
        topic = ShortsTopic.model_validate(data)
    output.mkdir(parents=True)
    for name in ("content_package.json", "effective_content_request.json", "metadata.json"):
        path = source / name
        if path.is_file():
            shutil.copyfile(path, output / name)
    reference = output / "reference"
    if args.visual_plan:
        (output / "visual-plan.json").write_text(json.dumps(plan, indent=2) + "\n")
        pixabay = PixabayClient(PixabayConfig(cache_root=args.stock_cache.resolve()), api_key="")
        prepare_plates(topic, reference, pixabay=pixabay, capture=None)
    timeline = prepare(topic, reference, config=args.config.resolve(),
                       alignment_model=reference_short.resolve(config.alignment_model_path),
                       voice=config.voice)
    report = reference_short.render(timeline, reference, output / "final.mp4", config,
                                    draft=False, cancelled=lambda: False)
    (output / "smoke-result.json").write_text(json.dumps({
        "scope": "local test from a previously reviewed topic; no production approval",
        "source_job": str(source), "source_topic_sha256": source_topic_sha256,
        "render_topic_sha256": report["topic_sha256"],
        "visual_plan_is_test_only": bool(args.visual_plan),
        "final_sha256": report["video_sha256"], "qa_passed": report["passed"],
        "narration_health": report["narration_health"],
        "encoded_audio_health": report["audio_health"],
    }, indent=2) + "\n")
    print(output / "final.mp4")


if __name__ == "__main__":
    main()
