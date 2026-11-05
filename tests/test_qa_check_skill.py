"""The om-video-quality skill's deterministic QA script (M-AU6 mix checks).

Not a packaged module — loaded from its real path under .agents/skills/, same file the
operator runs by hand, so these tests exercise exactly what ships.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SKILL_PATH = Path(__file__).resolve().parents[1] / ".agents" / "skills" / "om-video-quality" / "qa_check.py"
_spec = importlib.util.spec_from_file_location("qa_check", SKILL_PATH)
qa_check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(qa_check)


def _reference_job(tmp_path, audio_provenance: dict | None) -> Path:
    job = tmp_path / "job"
    job.mkdir()
    scenes = [
        {"template": "hook", "vo": "A fast open that names no greeting at all.", "headline": ["H"], "chips": []},
        {"template": "loop", "vo": "and loops right back to the start without stopping",
         "headline": ["H"], "chips": []},
    ]
    (job / "content_package.json").write_text(json.dumps({
        "reference_short": {"scenes": scenes}, "metadata": {}, "thumbnail_brief": {},
    }))
    (job / "effective_content_request.json").write_text(json.dumps({}))
    if audio_provenance is not None:
        mix = job / "reference" / "mix"
        mix.mkdir(parents=True)
        (mix / "audio-provenance.json").write_text(json.dumps(audio_provenance))
    return job


def _result(results, name):
    return next(r for r in results if r[1] == name)


def test_clipping_and_long_silence_fail():
    provenance = {
        "narration_health": {"warnings": [
            {"kind": "clipping", "start": 1.0, "end": 1.2, "scene_index": 0},
            {"kind": "silence", "start": 3.0, "end": 5.0, "scene_index": 1},
        ]},
        "music_under_speech": {"mask_margin_db": 12, "windows_masked": 0, "warnings": []},
    }

    def build(tmp_path):
        return _reference_job(tmp_path, provenance)

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        results = qa_check.check(build(Path(tmp)))
    assert _result(results, "audio-clipping")[0] == "FAIL"
    assert _result(results, "audio-silence")[0] == "FAIL"
    assert _result(results, "audio-level-jumps")[0] == "PASS"
    assert _result(results, "music-under-speech")[0] == "PASS"


def test_clean_narration_and_masked_music_give_pass_and_warn():
    provenance = {
        "narration_health": {"warnings": [{"kind": "quiet", "start": 2.0, "end": 2.3, "scene_index": 0}]},
        "music_under_speech": {"mask_margin_db": 12, "windows_masked": 3,
                               "warnings": [{"start": 1.0, "end": 1.4}]},
    }
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        results = qa_check.check(_reference_job(Path(tmp), provenance))
    assert _result(results, "audio-clipping")[0] == "PASS"
    assert _result(results, "audio-silence")[0] == "PASS"
    assert _result(results, "audio-level-jumps")[0] == "WARN"
    assert _result(results, "music-under-speech")[0] == "WARN"


def test_missing_audio_provenance_warns_instead_of_crashing():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        results = qa_check.check(_reference_job(Path(tmp), audio_provenance=None))
    assert _result(results, "audio-health")[0] == "WARN"
    names = {r[1] for r in results}
    assert "music-under-speech" not in names  # no audio-provenance.json at all: nothing to warn about either


def test_sfx_peak_and_licence_trail_pass_when_modest_and_recorded():
    provenance = {
        "sfx_enabled": True,
        "sound_effects": [{"cue": "pop", "template": "big_stat"}, {"cue": "whoosh-short", "template": "flow"}],
        "sound_effect_peak_measured": 0.17,
        "audio_licenses": [{"asset": "music", "mode": "synthesized", "note": "..."},
                           {"asset": "sfx:pop", "source": "Pixabay", "license": "Pixabay Content License"}],
    }
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        results = qa_check.check(_reference_job(Path(tmp), provenance))
    assert _result(results, "sfx-variety")[0] == "PASS"
    assert "0.170" in _result(results, "sfx-variety")[2]
    names = {r[1] for r in results}
    assert "sfx-peak" not in names  # no FAIL emitted below the 0.35 threshold
    assert _result(results, "audio-licence-trail") == ("PASS", "audio-licence-trail", "2 audio asset(s) recorded with source/licence (M-AU4)")


def test_sfx_peak_fails_above_threshold_and_missing_licence_trail_warns():
    provenance = {
        "sfx_enabled": True,
        "sound_effects": [{"cue": "pop", "template": "big_stat"}],
        "sound_effect_peak_measured": 0.5,
    }
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        results = qa_check.check(_reference_job(Path(tmp), provenance))
    assert _result(results, "sfx-peak")[0] == "FAIL"
    assert _result(results, "audio-licence-trail")[0] == "WARN"


def test_native_landscape_uses_measured_encoded_loudness_not_raw_narration(tmp_path):
    job=_reference_job(tmp_path,None)
    (job/'content_package.json').write_text(json.dumps({'metadata':{},'script_sections':[]}))
    path=job/'final_manifest.json'
    path.write_text(json.dumps({'metadata':{'audio_loudness':{'before':{'input_i':-21,'input_tp':0},'encoded':{'input_i':-15.76,'input_tp':-2.18}}}}))
    assert _result(qa_check.check(job),'loudness')[0]=='PASS'
    path.write_text(json.dumps({'probe':{'audio_loudness':{'encoded':{'input_i':-15,'input_tp':-.5}}}}))
    assert _result(qa_check.check(job),'loudness')[0]=='FAIL'
