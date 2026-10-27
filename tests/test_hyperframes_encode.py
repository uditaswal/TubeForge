"""HyperFrames mux keeps the established reference video QA contract."""
from pathlib import Path

import pytest

from tubeforge.pipeline.reference_short import load_timeline
from tubeforge.rendering.shorts.hyperframes_encode import encode
from tubeforge.rendering.shorts.schema import ShortsTopic

JOB = Path(__file__).resolve().parents[2] / "Youtube_Video_Producer" / "data" / "artifacts" / "e53f4e8387424f65b6a6b50fbb166efa"


@pytest.mark.skipif(not (JOB / "preview.mp4").is_file(), reason="reviewed real-job fixture absent")
def test_real_mastered_mix_mux_and_existing_qa(tmp_path):
    reference = JOB / "reference"
    topic = ShortsTopic.model_validate_json((reference / "topic.json").read_text())
    timeline = load_timeline(topic, reference)
    output = tmp_path / "preview.mp4"
    report = encode(timeline, JOB / "preview.mp4", reference / "mix" / "mix.wav", output,
                    draft=True, budget_rtf=20)
    assert report["passed"] is True
    assert report["scene_count"] == len(timeline.topic.scenes)
    assert report["frames"] == round(timeline.duration * 30)
    assert report["full_decode"] is True
    assert report["audio_health"] and report["temporal_qa"]
    assert output.is_file() and output.with_suffix(".qa.json").is_file()
