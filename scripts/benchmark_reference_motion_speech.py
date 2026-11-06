"""Offline Android/Rust visual comparison using the accepted M3 captured speech.

This creates a distinct, unapproved visual overlay. It preserves narration and
word timing, never invokes a provider, and cannot grant production approval.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import shutil

from tubeforge.pipeline.reference_short import load_timeline
from tubeforge.rendering.shorts.schema import ShortsTopic
from tubeforge.rendering.shorts.timeline import Timeline
from tubeforge.rendering.shorts.plates import Plates, card_indices, load_manifest
from tubeforge.rendering.shorts.encode import encode


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=['android', 'rate-limit'], default='android')
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output.resolve()
    if output == source or source in output.parents:
        raise ValueError('comparison output must be separate from accepted input')
    output.mkdir(parents=True, exist_ok=False)
    reference = source / 'reference'
    topic = ShortsTopic.model_validate_json((reference/'topic.json').read_bytes())
    original = load_timeline(topic, reference)  # verifies original topic/audio hashes
    data = topic.model_dump(mode='json')
    if args.profile == 'android':
        if 'Android' not in topic.scenes[1].vo or 'safer languages' not in topic.scenes[1].vo:
            raise ValueError('Android overlay requires the captured Android/Rust example')
        data['scenes'][1]['visual'] = dict(kind='code', language='rust',
            lines=['let names = ["Ada", "Lin"];', 'let first = names.get(0);'],
            line_reveal_words=[0, 3])
    else:
        scene = data['scenes'][9]
        if scene['vo'].split()[3] != 'rate' or scene['vo'].split()[6] != 'burst':
            raise ValueError('rate-limit overlay requires the captured TWO DIALS scene')
        visual = scene['visual']
        if visual['lines'] != ['"ThrottlingBurstLimit": 100,', '"ThrottlingRateLimit": 2000']:
            raise ValueError('unexpected captured code')
        # Preserve identifiers/numbers while matching the spoken rate-then-burst order.
        # Commas move with JSON member position; this remains a labelled excerpt.
        visual['lines'] = ['"ThrottlingRateLimit": 2000,', '"ThrottlingBurstLimit": 100']
        visual['line_reveal_words'] = [3, 6]
    compared = ShortsTopic.model_validate(data)
    assert [s.vo for s in compared.scenes] == [s.vo for s in topic.scenes]
    manifest = load_manifest(reference)
    plates = Plates(compared, reference, manifest)
    timeline = Timeline(compared, original.timings, card_indices(compared, manifest))
    package = json.loads((source/'content_package.json').read_text())
    package['reference_short'] = compared.model_dump(mode='json')
    (output/'content_package.json').write_text(json.dumps(package, indent=2))
    (output/'topic.json').write_text(compared.model_dump_json(indent=2))
    saved_reference = output/'reference'
    saved_reference.mkdir()
    shutil.copyfile(output/'topic.json', saved_reference/'topic.json')
    shutil.copyfile(reference/'narration.wav', saved_reference/'narration.wav')
    timing_data = json.loads((reference/'timeline.json').read_text())
    timing_data['topic_sha256'] = sha(saved_reference/'topic.json')
    (saved_reference/'timeline.json').write_text(json.dumps(timing_data, indent=2))
    provenance_path = reference/'mix/audio-provenance.json'
    if provenance_path.is_file():
        provenance = json.loads(provenance_path.read_text())
        voice_hash = sha(saved_reference/'narration.wav')
        if provenance.get('narration_sha256') != voice_hash:
            raise ValueError('source narration provenance does not match reused speech')
        provenance['comparison_reuse'] = {
            'source_provenance_sha256': sha(provenance_path),
            'source_video_sha256': sha(source/'final.mp4'),
            'method': 'source final AAC decoded and reencoded; original mix metadata retained'}
        (saved_reference/'mix').mkdir()
        (saved_reference/'mix/audio-provenance.json').write_text(json.dumps(provenance, indent=2))
    # Reuse the complete accepted mix with the identical timeline and no TTS rerun.
    audio = output/'accepted-mix.wav'
    subprocess.run(['ffmpeg','-v','error','-y','-i',str(source/'final.mp4'),'-vn',
                    '-ar','48000','-c:a','pcm_s24le',str(audio)], check=True)
    (output/'comparison_inputs.json').write_text(json.dumps(dict(
        scope='unapproved illustrative visual overlay; accepted narration/timing reused',
        source_topic_sha256=sha(reference/'topic.json'),
        source_timeline_sha256=sha(reference/'timeline.json'),
        source_video_sha256=sha(source/'final.mp4'),
        source_package_sha256=sha(source/'content_package.json'),
        overlay_topic_sha256=sha(output/'topic.json'),
        narration_unchanged=True, timing_unchanged=True), indent=2))
    try:
        report = encode(timeline, audio, output/'final.mp4', plates=plates, budget_rtf=30)
    finally:
        plates.release()
    (output/'comparison_report.json').write_text(json.dumps(report, indent=2))
    (output/'quality_report.json').write_text(json.dumps({'reference_qa': report}, indent=2))
    subprocess.run(['ffmpeg','-v','error','-y','-i',str(output/'final.mp4'),'-vf',
                    f'fps=1/2,scale=270:480,tile=5x{math.ceil(timeline.duration/2/5)}','-frames:v','1',str(output/'contact.png')],check=True)
    print(json.dumps(dict(passed=report['passed'], seconds=timeline.duration,
                         video_sha256=report['video_sha256'], code_timing=report['code_timing'])),flush=True)


if __name__ == '__main__':
    main()
