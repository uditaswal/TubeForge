"""Local, topic-driven terminal Short benchmark.

Inspired by the supplied Claude reference's terminal/short-caption separation.
This implementation uses the reviewed ContentPackage as its only narration
source, audio-based Whisper alignment, checked FFmpeg and bounded frame memory.
No publishing, remote inference, shell execution, or automatic installs.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import importlib.metadata
import json
import math
import re
import subprocess
from functools import lru_cache
from pathlib import Path

import numpy as np
import soundfile as sf
from PIL import Image, ImageDraw, ImageFont

W, H, FPS, SR = 1080, 1920, 30, 48000
BG, PANEL, WHITE = '#080f20', '#101c30', '#f3f7fd'
MUTED, CYAN, GREEN, AMBER, RED = '#94a6bc', '#5cdef4', '#74efbd', '#ffcf70', '#ff8494'
SANS = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
MONO = '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(args):
    return subprocess.run(args, check=True, capture_output=True, text=True)


def resample(a, old, new):
    return np.interp(np.arange(round(len(a) * new / old)) * old / new, np.arange(len(a)), a).astype(np.float32)


@lru_cache(maxsize=100)
def font(size, mono=False):
    return ImageFont.truetype(MONO if mono else SANS, size)


def text(draw, xy, value, size, color=WHITE, *, anchor='mm', mono=False, max_width=840):
    f = font(size, mono)
    if f.getlength(value) > max_width:
        raise ValueError(f'Text exceeds safe width ({size}px): {value}')
    bounds = draw.textbbox(xy, value, font=f, anchor=anchor)
    if value.strip() and not (60 <= bounds[0] and bounds[2] <= 930 and 210 <= bounds[1] and bounds[3] <= 1490):
        raise ValueError(f'Text outside portrait safe area: {value!r}: {bounds}')
    draw.text(xy, value, font=f, fill=color, anchor=anchor)


def topic_data(path):
    topic = json.loads(path.read_text())
    package_path = path.parent / topic['package']
    package = json.loads(package_path.read_text())
    assert len(topic['scenes']) == len(package['script_sections']) == 6
    identity = hashlib.sha256(path.read_bytes() + package_path.read_bytes()).hexdigest()
    return topic, package, identity


def prepare(args):
    from kokoro_onnx import Kokoro
    from faster_whisper import WhisperModel
    from faster_whisper.audio import pad_or_trim
    from faster_whisper.tokenizer import Tokenizer
    from faster_whisper.transcribe import merge_punctuations

    topic, package, identity = topic_data(args.topic)
    root = args.output
    root.mkdir(parents=True, exist_ok=True)
    kokoro = Kokoro(str(args.models / 'kokoro-v1.0.int8.onnx'), str(args.models / 'voices-v1.0.bin'))
    aligner = WhisperModel('base.en', device='cpu', compute_type='int8', cpu_threads=4,
                           download_root=str(args.align_models), local_files_only=True)
    tokenizer = Tokenizer(aligner.hf_tokenizer, aligner.model.is_multilingual, task='transcribe', language='en')
    timeline, voices, cursor = [], [], 0.0
    for index, (scene, section) in enumerate(zip(topic['scenes'], package['script_sections'], strict=True)):
        spoken = section['narration']
        key = hashlib.sha256(json.dumps([spoken, topic['voice'], topic['speed'], digest(args.models / 'kokoro-v1.0.int8.onnx')]).encode()).hexdigest()[:16]
        wav = root / f'voice-{index}-{key}.wav'
        if not wav.exists():
            samples, sr = kokoro.create(spoken, voice=topic['voice'], speed=topic['speed'], lang='en-us')
            samples = np.asarray(samples, dtype=np.float32)
            active = np.where(np.abs(samples) > 0.004)[0]
            if not len(active):
                raise ValueError('Silent voice output')
            samples = samples[max(0, active[0] - int(.04 * sr)):min(len(samples), active[-1] + int(.13 * sr))]
            sf.write(wav, samples, sr, subtype='PCM_16')
        samples, sr = sf.read(wav, dtype='float32')
        duration = len(samples) / sr
        audio16 = resample(samples, sr, 16000)
        features = aligner.feature_extractor(audio16)
        frames = min(features.shape[-1] - 1, round(len(audio16) / 160))
        encoded = aligner.encode(pad_or_trim(features[:, :frames]))
        words = aligner.find_alignment(tokenizer, [tokenizer.encode(spoken)], encoded, [frames])[0]
        merge_punctuations(words, "\"'“¿([{-", "\"'.。,，!！?？:：”)]}、")
        words = [{'word': w['word'].strip(), 'start': round(float(w['start']), 3),
                  'end': round(float(w['end']), 3), 'probability': round(float(w['probability']), 4)}
                 for w in words if w['word'].strip()]
        # DTW can collapse a short article to one boundary. Keep it in the
        # neighboring measured caption group, rather than inventing a duration
        # or dropping spoken text. Such groups highlight together.
        joined = []
        for w in words:
            if joined and joined[-1]['end'] <= joined[-1]['start']:
                previous = joined.pop()
                w = {**w, 'word': previous['word'] + ' ' + w['word'],
                     'start': previous['start'], 'joined_zero_duration': True}
            joined.append(w)
        if joined and joined[-1]['end'] <= joined[-1]['start'] and len(joined) > 1:
            last = joined.pop()
            joined[-1]['word'] += ' ' + last['word']
            joined[-1]['joined_zero_duration'] = True
        words = joined
        if not words or any(w['end'] <= w['start'] for w in words):
            raise ValueError(f'Invalid audio alignment in scene {index}: {words}')
        if words[-1]['end'] > duration + .1:
            raise ValueError('Word timing exceeds voice file')
        lead, tail = (.04 if index == 0 else .10), (.32 if index == 5 else .18)
        for word in words:
            word['start'] += cursor + lead
            word['end'] += cursor + lead
        item = {**scene, 'narration': spoken, 'start': cursor, 'voice_start': cursor + lead,
                'duration': lead + duration + tail, 'voice_duration': duration,
                'voice_file': wav.name, 'voice_sha256': digest(wav), 'words': words}
        timeline.append(item)
        voices.append((cursor + lead, resample(samples, sr, SR)))
        cursor += item['duration']
        print(f'scene {index + 1}: {item["duration"]:.2f}s, {len(words)} aligned words', flush=True)
    if not 30 <= cursor <= 55:
        raise ValueError(f'Runtime outside benchmark bounds: {cursor}')
    result = {'source_identity': identity, 'title': topic['title'], 'duration': cursor,
              'cta': topic.get('cta'),
              'alignment': 'Whisper base.en cross-attention DTW on supplied transcript', 'scenes': timeline}
    voice = np.zeros(math.ceil(cursor * SR), np.float32)
    for offset, samples in voices:
        start = round(offset * SR)
        voice[start:start + len(samples)] += samples
    sf.write(root / 'narration.wav', voice, SR, subtype='PCM_24')
    refine_alignment(aligner, voice, result, root)
    (root / 'timeline.json').write_text(json.dumps(result, indent=2) + '\n')
    mix_audio(root, result, voice, topic['music'])
    print(f'Ready: {cursor:.3f}s; exact source {identity}', flush=True)


def refine_alignment(aligner, voice, timeline, root):
    """Cross-check supplied-transcript timing against a full-audio ASR pass.

    Only exact contiguous word matches can refine a timestamp. Spoken text is
    never replaced by recognition output. This resolves collapsed articles and
    sentence-boundary timing without character-length interpolation.
    """
    segments, _ = aligner.transcribe(resample(voice, SR, 16000), language='en', word_timestamps=True, beam_size=5)
    decoded = [{'start': s.start, 'end': s.end, 'text': s.text,
                'words': [{'word': w.word, 'start': w.start, 'end': w.end, 'probability': w.probability} for w in s.words]}
               for s in segments]
    (root / 'narration-asr.json').write_text(json.dumps(decoded, indent=2))
    groups = [w for s in timeline['scenes'] for w in s['words']]
    original, owners, recognized, targets = [], [], [], []
    for i, w in enumerate(groups):
        for token in re.findall(r'[a-z0-9]+', w['word'].lower()):
            original.append(token); owners.append(i)
    for s in decoded:
        for w in s['words']:
            for token in re.findall(r'[a-z0-9]+', w['word'].lower()):
                recognized.append(token); targets.append(w)
    matching = {}
    for block in difflib.SequenceMatcher(a=original, b=recognized, autojunk=False).get_matching_blocks():
        matching.update({block.a + k: block.b + k for k in range(block.size)})
    changes = []
    for i, group in enumerate(groups):
        indices = [j for j, owner in enumerate(owners) if owner == i]
        mapped = [matching[j] for j in indices if j in matching]
        if len(mapped) != len(indices) or mapped != list(range(mapped[0], mapped[-1] + 1)):
            continue
        start, end = targets[mapped[0]]['start'], targets[mapped[-1]]['end']
        # Refine only a late onset whose end agrees. Never compress an otherwise
        # measured word to an ASR token's occasionally near-zero duration.
        late_by = group['start'] - start
        if .08 < late_by <= .6 and abs(end - group['end']) <= .10 and end > start:
            before, after = groups[i - 1]['end'] if i else 0, groups[i + 1]['start'] if i + 1 < len(groups) else timeline['duration']
            if start < before - .025 or group['end'] > after + .025:
                continue
            changes.append({'word': group['word'], 'original': [group['start'], group['end']], 'refined': [start, group['end']]})
            group.update(start=start, refinement='exact contiguous ASR match; measured end retained')
    split_groups = []
    replacements = {}
    for i, group in enumerate(groups):
        if not (group.get('joined_zero_duration') or '—' in group['word']):
            continue
        parts = [part for part in re.split(r'(?<=—)|\s+', group['word']) if part]
        indices = [j for j, owner in enumerate(owners) if owner == i]
        mapped = [matching[j] for j in indices if j in matching]
        if len(parts) != len(indices) or len(mapped) != len(indices):
            continue
        candidates = [targets[j] for j in mapped]
        if (mapped != list(range(mapped[0], mapped[-1] + 1)) or
                any(w['end'] <= w['start'] for w in candidates) or
                candidates[0]['start'] < group['start'] - .05 or
                candidates[-1]['end'] > group['end'] + .05):
            continue
        replacements[id(group)] = [
            {'word': part, 'start': w['start'], 'end': w['end'],
             'probability': round(float(w['probability']), 4), 'refinement': 'exact matched ASR word'}
            for part, w in zip(parts, candidates, strict=True)]
        split_groups.append(group['word'])
    for scene in timeline['scenes']:
        scene['words'] = [part for group in scene['words'] for part in replacements.get(id(group), [group])]
    timeline['alignment_refinements'] = changes
    timeline['alignment_splits'] = split_groups
    timeline['alignment'] += '; sentence boundaries cross-checked with exact ASR word matches'
    print(f'Audio cross-check refined {len(changes)} caption groups', flush=True)


def synth_music(count, config):
    """Original pad, bass and eighth-note plucks; no sampled recording."""
    if not config['enabled']:
        return np.zeros(count, np.float32)
    bpm, level, duck = float(config['bpm']), float(config['level']), float(config['duck'])
    progression = config['progression']
    if not (60 <= bpm <= 180 and 0 < level <= .2 and 0 <= duck <= .85 and progression):
        raise ValueError('Invalid music configuration')
    if any(not (0 <= root <= 127 and len(notes) == 3 and all(0 <= note <= 127 for note in notes))
           for root, notes in progression):
        raise ValueError('Invalid music progression')
    music = np.zeros(count, np.float32)
    beat, bar = 60 / bpm, 4 * 60 / bpm
    def hz(midi):
        return 440 * 2 ** ((midi - 69) / 12)
    for index, start_seconds in enumerate(np.arange(0, count / SR, bar)):
        start = round(start_seconds * SR)
        n = min(round(bar * SR), count - start)
        t = np.arange(n, dtype=np.float32) / SR
        root, notes = progression[index % len(progression)]
        envelope = np.minimum(t / .4, 1) * np.clip((bar - t) / .5, 0, 1)
        pad = sum(np.sin(2 * np.pi * hz(note + 12) * t) +
                  .4 * np.sin(2 * np.pi * hz(note + 12) * 2.003 * t) for note in notes) / 3
        bass = np.sin(2 * np.pi * hz(root - 12) * t) * .9
        music[start:start + n] += ((pad + bass) * .25 * envelope).astype(np.float32)
        for eighth in range(8):
            pluck_start = start + round(eighth * beat * SR / 2)
            pluck_n = min(round(.35 * SR), count - pluck_start)
            if pluck_n <= 0:
                continue
            x = np.arange(pluck_n, dtype=np.float32) / SR
            pluck = np.sin(2 * np.pi * hz(notes[eighth % 3] + 12) * x) * np.exp(-9 * x) * .28
            music[pluck_start:pluck_start + pluck_n] += pluck.astype(np.float32)
    seconds = np.arange(count, dtype=np.float32) / SR
    music *= np.minimum(seconds / 1.0, 1) * np.minimum((count / SR - seconds) / 1.2, 1)
    return music * (level / max(float(np.max(np.abs(music))), 1e-6))


def mix_audio(root, timeline, voice, music_config):
    # Original synthesized accompaniment and action accents, with speech ducking.
    n = len(voice)
    bed, fx = synth_music(n, music_config), np.zeros(n, np.float32)
    rng = np.random.default_rng(20261012)
    for i, scene in enumerate(timeline['scenes']):
        if i:
            start = max(0, round((scene['start'] - .035) * SR)); count = min(round(.18 * SR), n - start)
            env = np.sin(np.linspace(0, np.pi, count)) ** 2
            noise = np.convolve(rng.normal(0, 1, count), np.ones(24) / 24, mode='same')
            fx[start:start + count] += (noise * env * .035).astype(np.float32)
        for _, _, at, count, cps in command_schedule(scene):
            for j in range(count):
                start = round((scene['start'] + at + j / cps) * SR)
                length = min(round(.009 * SR), n - start)
                if length > 0:
                    fx[start:start + length] += (rng.normal(0, 1, length) * np.exp(-np.linspace(0, 8, length)) * .019).astype(np.float32)
    # Block RMS avoids the quadratic full-rate convolution in the reference.
    block = 480
    levels = np.array([np.sqrt(np.mean(voice[i:i + block] ** 2)) for i in range(0, n, block)])
    smooth = np.convolve(levels, np.ones(15) / 15, mode='same')
    voice_gain = .83 / max(float(np.max(np.abs(voice))), .001)
    duck = np.interp(np.arange(n) / block, np.arange(len(smooth)),
                     1 - float(music_config['duck']) * np.clip(smooth / .08, 0, 1))
    ducked_bed = bed * duck
    sf.write(root / 'music-bed.wav', bed, SR, subtype='PCM_24')
    sf.write(root / 'music-ducked.wav', ducked_bed, SR, subtype='PCM_24')
    sf.write(root / 'effects.wav', fx, SR, subtype='PCM_24')
    mix = voice * voice_gain + ducked_bed + fx
    sf.write(root / 'mix-raw.wav', mix, SR, subtype='PCM_24')
    dependencies = {}
    for name in ('numpy', 'soundfile', 'kokoro-onnx'):
        metadata = importlib.metadata.metadata(name)
        dependencies[name] = {'version': importlib.metadata.version(name),
                              'license_expression': metadata.get('License-Expression'),
                              'license': metadata.get('License')}
    (root / 'music-provenance.json').write_text(json.dumps({
        'origin': 'Original synthesized pad, bass and eighth-note plucks in produce.py; no sampled track',
        'configuration': music_config, 'music_bed_sha256': digest(root / 'music-bed.wav'),
        'music_ducked_sha256': digest(root / 'music-ducked.wav'),
        'effects_sha256': digest(root / 'effects.wav'), 'dependencies': dependencies,
        'voice_model': 'Locally provisioned Kokoro v1.0 INT8; verify model and voice terms before publication',
        'font': 'System DejaVu Sans and Mono; verify font terms before distribution',
    }, indent=2) + '\n')
    first = run(['ffmpeg', '-hide_banner', '-i', str(root / 'mix-raw.wav'), '-af',
                 'loudnorm=I=-14:TP=-1.5:LRA=9:print_format=json', '-f', 'null', '-'])
    match = re.findall(r'\{\s*"input_i".*?\}', first.stderr, re.S)
    measured = json.loads(match[-1])
    (root / 'mix-loudness-pass1.json').write_text(json.dumps(measured, indent=2))
    filt = 'loudnorm=I=-14:TP=-1.5:LRA=9:linear=true:' + ':'.join(
        f'{key}={measured[value]}' for key, value in [('measured_I','input_i'), ('measured_TP','input_tp'),
        ('measured_LRA','input_lra'), ('measured_thresh','input_thresh'), ('offset','target_offset')])
    run(['ffmpeg', '-y', '-v', 'error', '-i', str(root / 'mix-raw.wav'), '-af', filt, '-ar', str(SR), str(root / 'mix.wav')])


def command_schedule(scene):
    result, at = [], .36
    for row, command in enumerate(scene.get('commands', [])):
        cps = 27.0
        result.append((row, command, at, len(command), cps))
        at += len(command) / cps + .12
    return result


def caption_chunks(words):
    chunks, current = [], []
    for word in words:
        value = word['word'].upper()
        candidate = ' '.join([w['word'].upper() for w in current] + [value])
        if current and (sum(len(w['word'].split()) for w in current) + len(word['word'].split()) > 3 or font(84).getlength(candidate) > 760 or
                        re.search(r'[.!?,;:]$', current[-1]['word']) or
                        word['start'] - current[-1]['end'] > .18):
            chunks.append(current); current = []
        current.append(word)
    if current:
        chunks.append(current)
    return chunks


class Renderer:
    def __init__(self, timeline):
        self.timeline = timeline
        yy, xx = np.mgrid[0:H, 0:W]
        glow = np.exp(-((xx - 140) ** 2 + (yy - 900) ** 2) / (2 * 610 ** 2))
        violet = np.exp(-((xx - 930) ** 2 + (yy - 1500) ** 2) / (2 * 750 ** 2))
        colors = np.stack([8 + glow * 3 + violet * 12, 15 + glow * 14, 31 + glow * 22 + violet * 20], axis=-1).astype(np.uint8)
        self.background = Image.fromarray(colors)
        self.chunks = [caption_chunks(s['words']) for s in timeline['scenes']]

    def frame(self, t):
        scenes = self.timeline['scenes']
        index = max(i for i, s in enumerate(scenes) if t >= s['start'])
        scene = scenes[index]; local = t - scene['start']; kind = scene['kind']
        im = self.background.copy(); d = ImageDraw.Draw(im)
        # Important information stays in x=60..930, y=210..1490.
        d.line((74, 232, 926, 232), fill='#25364d', width=7)
        d.line((74, 232, 74 + 852 * min(t / self.timeline['duration'], 1), 232), fill=CYAN, width=7)
        text(d, (500, 292), scene['label'], 28, CYAN)
        if kind == 'hook':
            text(d, (500, 540), 'STOP', 128)
            text(d, (500, 668), 'MEMORIZING.', 90, RED)
            text(d, (500, 830), 'START RUNNING.', 72, CYAN)
            for j, label in enumerate(['run', 'ps', 'logs', 'stop', 'rm']):
                x = 85 + j * 171
                active = local > .40 + j * .35
                d.rounded_rectangle((x, 990, x + 146, 1080), 18, fill=('#183c46' if active else PANEL), outline=(CYAN if active else '#26354b'), width=2)
                text(d, (x + 73, 1035), label, 35, WHITE if active else MUTED, mono=True, max_width=140)
            text(d, (500, 1165), 'ONE PRACTICE CONTAINER', 30, MUTED)
        else:
            text(d, (500, 380), scene['heading'], 76)
            text(d, (500, 456), scene['subheading'], 28, MUTED)
            follow_word = next((w for w in scene['words'] if w['word'].lower().startswith('follow')), None)
            cta_active = kind == 'rm' and follow_word and t >= follow_word['start'] - .12
            if cta_active:
                self.cta_card(d, t - follow_word['start'] + .12)
            else:
                self.terminal(d, scene, local)
                state_color = GREEN if scene['state'] == 'RUNNING' else AMBER if scene['state'] == 'STOPPED' else MUTED
                complete = max(at + count / cps for _, _, at, count, cps in command_schedule(scene)) + .22
                state = scene['state'] if local >= complete else ('RUNNING' if kind == 'stop' else 'STOPPED' if kind == 'rm' else 'STARTING' if kind == 'run' else 'RUNNING')
                d.rounded_rectangle((150, 1160, 850, 1248), 25, fill=PANEL, outline=state_color, width=2)
                text(d, (500, 1204), 'demo  /  ' + state, 36, state_color)
        self.captions(d, index, t)
        return im

    def cta_card(self, d, elapsed):
        config = self.timeline.get('cta')
        if not config or len(config.get('chips', [])) != 3:
            raise ValueError('Closing CTA requires three chips and a headline')
        d.rounded_rectangle((85, 565, 925, 1125), 26, fill='#0a121e', outline='#304058', width=2)
        for index, label in enumerate(config['chips']):
            if elapsed < .1 + index * .28:
                continue
            x = 124 + index * 244
            d.rounded_rectangle((x, 670, x + 210, 754), 17, fill='#183c46', outline=CYAN, width=2)
            text(d, (x + 105, 712), label, 31, WHITE, max_width=188)
        if elapsed >= .05:
            text(d, (500, 905), config['headline'], 64, CYAN, max_width=790)
        if elapsed >= .3:
            text(d, (500, 1005), config['subline'], 38, WHITE, max_width=790)

    def terminal(self, d, scene, local):
        kind = scene['kind']
        d.rounded_rectangle((72, 530, 930, 1112), 26, fill='#0a121e', outline='#304058', width=2)
        d.line((74, 601, 928, 601), fill='#26354b', width=2)
        for j, color in enumerate((RED, AMBER, GREEN)):
            d.ellipse((100 + j * 30, 554, 114 + j * 30, 568), fill=color)
        text(d, (500, 566), 'terminal', 23, MUTED)
        schedule = command_schedule(scene)
        for row, command, at, count, cps in schedule:
            if local < at:
                continue
            shown = min(count, int((local - at) * cps))
            prompt = '$ ' if row == 0 else '  '
            x, y = 104, 670 + row * 76
            text(d, (x, y), prompt, 48, GREEN, anchor='lm', mono=True)
            x += font(48, True).getlength(prompt)
            value = command[:shown]
            text(d, (x, y), value, 48, WHITE, anchor='lm', mono=True, max_width=760)
            cursor_x = x + font(48, True).getlength(value)
            if shown < count or (row == len(schedule) - 1 and int(local * 2) % 2 == 0):
                d.rectangle((cursor_x + 2, y - 23, cursor_x + 15, y + 24), fill=CYAN)
        complete = max(at + count / cps for _, _, at, count, cps in schedule) + .22
        if local < complete:
            return
        if kind == 'run':
            text(d, (108, 852), 'container created', 29, MUTED, anchor='lm')
            text(d, (108, 914), 'f46605094078…', 43, CYAN, anchor='lm', mono=True)
            detached = next((w['start'] - scene['start'] for w in scene['words'] if 'detached' in w['word'].lower()), 4.5)
            if local >= detached - .15:
                text(d, (108, 1020), '-d  =  in the background', 36, GREEN, anchor='lm', mono=True)
            else:
                text(d, (108, 1020), '--name  =  demo', 38, CYAN, anchor='lm', mono=True)
        elif kind == 'ps':
            text(d, (108, 764), 'OUTPUT · CONDENSED', 23, MUTED, anchor='lm')
            for y, label, value in [(842, 'NAME', 'demo'), (922, 'IMAGE', 'nginx:alpine'), (1002, 'STATE', 'running')]:
                cues = {'NAME': ['name.'], 'IMAGE': ['image,'], 'STATE': ['status,']}
                active = any(w['word'].lower() in cues[label] and w['start'] - scene['start'] - .12 <= local < w['end'] - scene['start'] + .20 for w in scene['words'])
                if active:
                    d.rounded_rectangle((94, y - 38, 901, y + 38), 12, fill='#193e48', outline=CYAN, width=2)
                text(d, (108, y), label, 25, MUTED, anchor='lm')
                text(d, (350, y), value, 43, GREEN if label == 'STATE' else WHITE, anchor='lm', mono=True, max_width=560)
        elif kind == 'logs':
            text(d, (108, 768), 'LOG EXCERPT · PREFIX OMITTED', 22, MUTED, anchor='lm')
            text(d, (108, 850), 'Configuration complete;', 43, GREEN, anchor='lm', mono=True)
            text(d, (108, 920), 'ready for start up', 43, GREEN, anchor='lm', mono=True)
            text(d, (108, 1030), 'Recorded app output', 31, MUTED, anchor='lm')
        elif kind == 'stop':
            text(d, (108, 778), 'demo', 45, MUTED, anchor='lm', mono=True)
            text(d, (500, 910), 'RUNNING → STOPPED', 46, AMBER)
            text(d, (500, 1007), 'Still exists. Not running.', 34, MUTED)
        else:
            text(d, (108, 778), 'demo', 45, MUTED, anchor='lm', mono=True)
            text(d, (500, 905), 'CONTAINER REMOVED', 43, GREEN)
            text(d, (500, 1008), 'The image stays.', 36, MUTED)

    def captions(self, d, index, t):
        for chunk in self.chunks[index]:
            if chunk[0]['start'] - .025 <= t < chunk[-1]['end'] + .055:
                values = [w['word'].upper() for w in chunk]
                size = 84
                value = ' '.join(values)
                width = font(size).getlength(value)
                if width > 760:
                    raise ValueError('Caption cannot fit safe area')
                x = 490 - width / 2
                d.rounded_rectangle((x - 22, 1321, x + width + 22, 1441), 20, fill='#080e19')
                for w, word in zip(chunk, values, strict=True):
                    color = AMBER if w['start'] - .015 <= t < w['end'] + .015 else WHITE
                    text(d, (x, 1380), word, size, color, anchor='lm', max_width=760)
                    x += font(size).getlength(word + ' ')
                break


def load_timeline(args):
    _, _, identity = topic_data(args.topic)
    value = json.loads((args.output / 'timeline.json').read_text())
    if value['source_identity'] != identity:
        raise ValueError('Source changed; prepare the exact revision again')
    for s in value['scenes']:
        if digest(args.output / s['voice_file']) != s['voice_sha256']:
            raise ValueError('Narration audio changed')
    return value


def stills(args):
    timeline = load_timeline(args); renderer = Renderer(timeline)
    selected = []
    for i, scene in enumerate(timeline['scenes']):
        for offset in (min(1.8, scene['duration'] / 3), scene['duration'] - .7):
            t = scene['start'] + offset
            im = renderer.frame(t)
            im.save(args.output / f'scene-{i + 1}-{t:.2f}.png')
            thumb = im.resize((270, 480))
            ImageDraw.Draw(thumb).text((8, 8), f'{t:.2f}s', fill='white')
            selected.append(thumb)
    sheet = Image.new('RGB', (1080, 1440))
    for i, im in enumerate(selected):
        sheet.paste(im, ((i % 4) * 270, (i // 4) * 480))
    sheet.save(args.output / 'contact-sheet.jpg', quality=94)
    print('Saved 12 inspected-time candidates and contact sheet')


def render(args):
    timeline = load_timeline(args); renderer = Renderer(timeline)
    temporary, destination = args.output / 'docker-short.partial.mp4', args.output / 'docker-short.mp4'
    frames = math.ceil(timeline['duration'] * FPS)
    command = ['ffmpeg', '-y', '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}',
               '-r', str(FPS), '-i', '-', '-i', str(args.output / 'mix.wav'), '-map', '0:v', '-map', '1:a',
               '-c:v', 'libx264', '-threads', '2', '-preset', 'fast', '-crf', '18', '-pix_fmt', 'yuv420p',
               '-c:a', 'aac', '-b:a', '192k', '-ar', str(SR), '-shortest', '-movflags', '+faststart', str(temporary)]
    with (args.output / 'encode.log').open('w') as log:
        p = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=log)
        try:
            for f in range(frames):
                p.stdin.write(renderer.frame(f / FPS).tobytes())
                if f % 150 == 0:
                    print(f'frame {f}/{frames}', flush=True)
            p.stdin.close()
            if p.wait() != 0:
                raise RuntimeError('FFmpeg failed; inspect encode.log')
        except BaseException:
            p.kill(); p.wait(); raise
    probe = json.loads(run(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(temporary)]).stdout)
    video = next(s for s in probe['streams'] if s['codec_type'] == 'video')
    assert (video['width'], video['height']) == (W, H) and video['r_frame_rate'] == '30/1'
    assert abs(float(probe['format']['duration']) - timeline['duration']) < .1
    temporary.replace(destination)
    (args.output / 'render-manifest.json').write_text(json.dumps({'source_identity': timeline['source_identity'],
        'output_sha256': digest(destination), 'timeline_sha256': digest(args.output / 'timeline.json'),
        'audio_sha256': digest(args.output / 'mix.wav'), 'probe': probe}, indent=2))
    print(destination)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['prepare', 'stills', 'render'])
    parser.add_argument('--topic', type=Path, default=Path(__file__).with_name('topic.json'))
    parser.add_argument('--output', type=Path, default=Path('artifacts/benchmark/docker-short/final'))
    parser.add_argument('--models', type=Path, default=Path('models'))
    parser.add_argument('--align-models', type=Path, default=Path('data/benchmark/models'))
    args = parser.parse_args()
    {'prepare': prepare, 'stills': stills, 'render': render}[args.mode](args)


if __name__ == '__main__':
    main()
