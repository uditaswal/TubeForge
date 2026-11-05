"""Local evidence and advisory channel checks. Never authorizes publication."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from tubeforge.providers.content.craft import originality_problems

POLICY_URL = 'https://support.google.com/youtube/answer/14328491'
DISCLOSURE_TEXT = 'This video uses an AI-assisted script and synthetic narration. Sources are listed below.'


def disclosure_record(package, audio, *, job_id, final_checksum):
    """Reuse the audio licence trail and M-S2 check; missing evidence fails closed."""
    sources = (package.get('request') or {}).get('sources') or []
    scenes = (package.get('reference_short') or {}).get('scenes') or []
    missing = []
    if not sources or any(not s.get('url') or not s.get('excerpt') for s in sources):
        missing.append('source URLs and excerpts')
    if not scenes or any(not s.get('vo') or (not s.get('source_ids') and s.get('template') not in {'loop', 'cta'}) for s in scenes):
        missing.append('source-grounded scenes')
    licenses = audio.get('audio_licenses') or []
    if not isinstance(licenses, list) or any(not isinstance(entry, dict) for entry in licenses):
        licenses = []
    if not any(entry.get('asset') == 'music' and entry.get('mode') in {'synthesized', 'silence', 'track'} for entry in licenses):
        missing.append('music mode or licence')
    if not licenses:
        missing.append('audio licence trail')
    # A catalog pointer alone is not the full licence. Do not invent its terms.
    for entry in licenses:
        if entry.get('mode') == 'track' and not (entry.get('license_name') and entry.get('license_url')):
            missing.append('catalog music licence terms')
        if str(entry.get('asset', '')).startswith('sfx:') and not (entry.get('license') and entry.get('source')):
            missing.append('SFX licence terms')
    ns = SimpleNamespace
    problems = originality_problems(ns(request=ns(sources=[ns(source_id=s.get('source_id'), excerpt=s.get('excerpt', '')) for s in sources]),
        reference_short=ns(scenes=[ns(vo=s.get('vo', ''), source_ids=s.get('source_ids', [])) for s in scenes])))
    known = {s.get('source_id') for s in sources}
    if any(set(s.get('source_ids', [])) - known for s in scenes):
        missing.append('valid scene source references')
    material = {'sources': sources, 'scenes': scenes, 'audio_licenses': licenses, 'final_checksum': final_checksum}
    return {'schema_version': 'channel-disclosure-v1', 'job_id': job_id, 'final_checksum': final_checksum,
            'evidence_identity': hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest(),
            'synthetic_components': ['AI-assisted script', 'synthetic narration'],
            'description_text': DISCLOSURE_TEXT, 'platform_disclosure_required': None,
            'policy_url': POLICY_URL, 'policy_checked_on': '2026-11-04',
            'sources': [{'source_id': s.get('source_id'), 'url': s.get('url'), 'title': s.get('title')} for s in sources],
            'audio_licenses': [{k: v for k, v in entry.items() if k != 'source_path'} for entry in licenses],
            'originality': {'method': 'M-S2 seven-word shingle check', 'problems': problems,
                            'status': 'unavailable' if missing else 'fail' if problems else 'pass'},
            'missing': sorted(set(missing)), 'eligible': not missing and not problems}


def read_audio(final_path, music_catalog=None):
    path = Path(final_path).parent / 'reference' / 'mix' / 'audio-provenance.json'
    try:
        if path.stat().st_size > 2_000_000 or path.is_symlink():
            return {}
        audio = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(audio, dict) or not isinstance(audio.get('audio_licenses', []), list) or any(not isinstance(entry, dict) for entry in audio.get('audio_licenses', [])):
            return {}
        if music_catalog:
            rights = {r.checksum_sha256: r.model_dump(mode='json', exclude={'path'}) for r in music_catalog.list()}
            for entry in audio.get('audio_licenses', []):
                if entry.get('mode') == 'track' and entry.get('source_sha256') in rights:
                    entry.update(rights[entry['source_sha256']])
        return audio
    except (OSError, ValueError):
        return {}
