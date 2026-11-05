"""Deterministic advisory reports over operator plans and actual render evidence."""
from __future__ import annotations

import re
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from itertools import combinations
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChannelLimits(BaseModel):
    model_config = ConfigDict(extra='forbid')
    max_per_day: int = Field(default=3, ge=1, le=100)
    min_spacing_minutes: int = Field(default=180, ge=0, le=10080)
    timezone: str = 'Asia/Kolkata'

    @field_validator('timezone')
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise ValueError('unknown channel safety timezone') from error
        return value


class ChannelSafetyConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    defaults: ChannelLimits = Field(default_factory=ChannelLimits)
    channels: dict[str, ChannelLimits] = Field(default_factory=dict)
    similarity_threshold: float = Field(default=.7, gt=0, le=1)
    repeated_phrase_words: int = Field(default=5, ge=3, le=12)


def words(value):
    return re.findall(r"[a-z0-9']+", str(value).casefold())


def stamp(short):
    try:
        value = datetime.fromisoformat(short.get('publish_at') or '')
        return value if value.utcoffset() is not None else None
    except ValueError:
        return None


def fingerprint(item):
    short, package = item['short'], item.get('script') or {}
    scenes = (package.get('reference_short') or {}).get('scenes') or []
    opening = scenes[0].get('vo', '') if scenes else short.get('hook', '')
    narration = ' '.join(s.get('vo', '') for s in scenes) or short.get('narration') or ''
    hook = words(opening)
    formula = 'question' if '?' in opening else 'conditional' if hook[:1] == ['if'] else 'statement' if hook else None
    return {'id': short['id'], 'channel': short.get('channel'), 'publish_at': short.get('publish_at'),
            'hook_formula': formula, 'opening': opening, 'title_pattern': ' '.join('#' if w.isdigit() else w for w in words(short['title'])),
            'templates': dict(Counter(s.get('template', 'unknown') for s in scenes)),
            'layout_family': item.get('layout_family'), 'music': item.get('music'), 'voice': item.get('voice'),
            'narration': narration, 'window_basis': 'publish_at' if stamp(short) else 'created_at', 'evidence': 'rendered' if item.get('checksum') else 'plan'}


def observed_time(item):
    planned = stamp(item['short'])
    if planned:
        return planned
    try:
        value = datetime.fromisoformat(item.get('created_at') or '')
        return value if value.utcoffset() is not None else None
    except ValueError:
        return None


def repetition_report(items, config, day=None):
    dated = [observed_time(i) for i in items if observed_time(i)]
    anchor = date.fromisoformat(day) if day else max((d.date() for d in dated), default=datetime.now(UTC).date())
    start = anchor - timedelta(days=6)
    recent = [i for i in items if (d := observed_time(i)) and start <= d.date() <= anchor]
    entries = [fingerprint(i) for i in recent]
    warnings = []
    for a, b in combinations(entries, 2):
        if a['channel'] != b['channel']:
            continue
        reasons = []
        for field in ['opening', 'title_pattern']:
            x, y = set(words(a[field])), set(words(b[field]))
            similarity = len(x & y) / len(x | y) if x and y else 0
            if similarity >= config.similarity_threshold:
                reasons.append({'code': field + '_similarity', 'score': round(similarity, 3)})
        n = config.repeated_phrase_words
        def phrases(value):
            tokens = words(value)
            return {' '.join(tokens[i:i+n]) for i in range(len(tokens)-n+1)}
        repeated = sorted(phrases(a['narration']) & phrases(b['narration']))[:20]
        if repeated:
            reasons.append({'code': 'repeated_phrases', 'phrases': repeated})
        shared = [field for field in ['layout_family', 'music', 'voice'] if a[field] and a[field] == b[field]]
        if len(shared) >= 2:
            reasons.append({'code': 'shared_production_choices', 'fields': shared})
        if reasons:
            warnings.append({'severity': 'warn', 'ids': [a['id'], b['id']], 'channel': a['channel'], 'reasons': reasons})
    for item in entries:
        item.pop('narration')
    return {'schema_version': 'repetition-v1', 'window_start': start.isoformat(), 'window_end': anchor.isoformat(),
            'threshold': config.similarity_threshold, 'entries': entries, 'warnings': warnings,
            'unassessed_ids': [i['short']['id'] for i in items if observed_time(i) is None],
            'meaning': 'heuristic review signals, not a platform-policy or monetization verdict'}


def cadence_report(shorts, config):
    groups = {}
    warnings = []
    for short in shorts:
        channel = short.get('channel')
        limits = config.channels.get(channel, config.defaults)
        value = stamp(short)
        if value is None:
            warnings.append({'code': 'publish_time_missing', 'severity': 'warn', 'ids': [short['id']], 'channel': channel})
            continue
        local_day = value.astimezone(ZoneInfo(limits.timezone)).date().isoformat()
        groups.setdefault((channel, local_day), []).append((value, short))
    for (channel, local_day), entries in groups.items():
        limits = config.channels.get(channel, config.defaults)
        if len(entries) > limits.max_per_day:
            warnings.append({'code': 'daily_limit', 'severity': 'warn', 'ids': sorted(s['id'] for _, s in entries),
                             'channel': channel, 'day': local_day, 'count': len(entries), 'limit': limits.max_per_day})
    channels = {s.get('channel') for s in shorts}
    for channel in sorted(channels, key=lambda value: value or ''):
        entries = sorted(((stamp(s), s['id']) for s in shorts if s.get('channel') == channel and stamp(s)), key=lambda e: (e[0], e[1]))
        limits = config.channels.get(channel, config.defaults)
        for (left, a), (right, b) in zip(entries, entries[1:]):
            minutes = (right.astimezone(UTC) - left.astimezone(UTC)).total_seconds()/60
            if minutes < limits.min_spacing_minutes:
                warnings.append({'code': 'minimum_spacing', 'severity': 'warn', 'ids': [a, b], 'channel': channel,
                                 'minutes': minutes, 'minimum_minutes': limits.min_spacing_minutes})
    return {'schema_version': 'cadence-v1', 'mode': 'warn', 'warnings': warnings,
            'meaning': 'operator-entered publish metadata only; nothing scheduled or published'}
