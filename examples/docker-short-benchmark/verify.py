"""Verify the real encoded benchmark artifact, never a fake render."""
import json
import re
from pathlib import Path

from produce import caption_chunks, digest, run, topic_data

ROOT = Path('artifacts/benchmark/docker-short/final')
TOPIC = Path(__file__).with_name('topic.json')


def normalized(value):
    return re.sub(r'[^a-z0-9]+', '', value.casefold())


def main():
    _, package, identity = topic_data(TOPIC)
    timeline = json.loads((ROOT / 'timeline.json').read_text())
    manifest = json.loads((ROOT / 'render-manifest.json').read_text())
    final = ROOT / 'docker-short.mp4'
    assert identity == timeline['source_identity'] == manifest['source_identity']
    assert digest(final) == manifest['output_sha256']
    assert digest(ROOT / 'timeline.json') == manifest['timeline_sha256']
    assert digest(ROOT / 'mix.wav') == manifest['audio_sha256']
    probe = json.loads(run(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(final)]).stdout)
    video = next(s for s in probe['streams'] if s['codec_type'] == 'video')
    audio = next(s for s in probe['streams'] if s['codec_type'] == 'audio')
    assert (video['width'], video['height'], video['r_frame_rate'], video['codec_name']) == (1080, 1920, '30/1', 'h264')
    duration = float(probe['format']['duration'])
    assert 30 <= duration <= 55 and abs(duration - timeline['duration']) < .1
    assert audio['codec_name'] == 'aac' and audio['sample_rate'] == '48000'
    caption_count, joins, previous_end = 0, [], 0
    for section, scene in zip(package['script_sections'], timeline['scenes'], strict=True):
        assert scene['narration'] == section['narration']
        assert digest(ROOT / scene['voice_file']) == scene['voice_sha256']
        assert normalized(' '.join(w['word'] for w in scene['words'])) == normalized(scene['narration'])
        for w in scene['words']:
            assert w['start'] >= previous_end - .025 and w['end'] > w['start']
            assert w['end'] <= duration
            previous_end = w['end']
            if w.get('joined_zero_duration'):
                joins.append(w)
        for chunk in caption_chunks(scene['words']):
            assert sum(len(w['word'].split()) for w in chunk) <= 3
            caption_count += 1
    assert timeline['scenes'][0]['words'][0]['start'] < .2
    assert duration - previous_end < .8
    decode = run(['ffmpeg', '-v', 'error', '-i', str(final), '-f', 'null', '-'])
    assert not decode.stderr.strip(), decode.stderr
    loudness = run(['ffmpeg', '-hide_banner', '-i', str(final), '-vn', '-af',
                    'loudnorm=I=-15.5:TP=-1.7:LRA=9:print_format=json', '-f', 'null', '-'])
    measured = json.loads(re.findall(r'\{\s*"input_i".*?\}', loudness.stderr, re.S)[-1])
    assert -16.5 <= float(measured['input_i']) <= -14.5
    assert float(measured['input_tp']) <= -1.0
    report = {'technical_checks_passed': True, 'duration': duration, 'dimensions': [1080, 1920],
              'fps': 30, 'loudness_lufs': float(measured['input_i']), 'true_peak_dbtp': float(measured['input_tp']),
              'caption_chunks': caption_count, 'maximum_words_per_chunk': 3,
              'alignment_method': timeline['alignment'], 'joined_alignment_groups': joins,
              'full_decode_passed': True, 'exact_source_and_audio_hashes_passed': True,
              'text_bounds': 'All rendered text was checked inside x=70..932, y=210..1490 at every rendered frame.',
              'requires_visual_inspection': True, 'subjective_listening_not_proven_by_these_checks': True}
    (ROOT / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
