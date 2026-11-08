"""Shared normal Studio request expansion for manual and automatic batch intake."""
import hashlib
import json


def rotated_music_track(short, settings):
    """A deterministic, varied music pick for one batch short (M-AU4).

    Every batch-produced short previously left `music_track` unset, so a plan day always
    rendered the same single synthesized bed for every short ("an endless loop"). This picks
    across the synthesized bed plus the configured catalog, keyed by publish day and short id,
    so different shorts on the same day consistently land on different tracks without needing
    cross-request state (each call is independent, so this is a stable hash, not a literal
    incrementing counter — see docs/HANDOFF.md for the acceptance tradeoff).
    """
    from tubeforge.pipeline.music import SYNTHESIZED_MUSIC_NAME
    catalog_names = sorted({track.name for track in settings.pipeline.video_generation.music_catalog})
    rotation = [SYNTHESIZED_MUSIC_NAME, *catalog_names]
    if len(rotation) <= 1:
        return None  # nothing to rotate between; keep today's unset/default behavior
    day = short.publish_at.date().isoformat() if short.publish_at else 'unscheduled'
    digest = hashlib.sha256(f'{day}:{short.id}'.encode()).digest()
    return rotation[int.from_bytes(digest[:4], 'big') % len(rotation)]


def build_batch_request(short, settings):
    from tubeforge.api.app import VideoBriefRequest, _video_request, _reject_retired_format
    presets = settings.pipeline.video_generation.presets
    preset = next((name for name, value in presets.items() if value.aspect_ratio == '9:16' and value.minimum_duration_seconds <= short.length_s <= value.maximum_duration_seconds), None)
    if preset is None:
        raise ValueError("no configured vertical preset supports this short's length")
    brief = dict(title=short.title,
        notes=('Unverified operator batch brief: ' + json.dumps(short.model_dump(mode='json'), ensure_ascii=False),),
        angle=short.concept, duration_seconds=short.length_s, preset=preset,
        review_mode='manual', ending=short.ending, channel_identity=short.channel,
        operator_script=(short.narration or '').strip() or None,
        video_style='story',  # the approved look; Classic is the legacy renderer
        music_track=rotated_music_track(short, settings))
    request = None
    if short.sources:
        # The plan's own sources become the evidence (page text is read at request time), so no web research runs.
        from fastapi import HTTPException
        from tubeforge.domain.contracts import SourceReference
        try:
            from urllib.parse import urlparse
            sources = tuple(SourceReference(source_id=f'plan-source-{index}', url=str(url), title=urlparse(str(url)).hostname or 'source')
                            for index, url in enumerate(short.sources, 1))
            request = _video_request(VideoBriefRequest(**brief, sources=sources), settings)
        except (HTTPException, ValueError):
            request = None  # an unreadable page must not block the day: fall back to the research path below
    if request is None:
        request = _video_request(VideoBriefRequest(**brief), settings)
        request = request.model_copy(update={'sources': tuple(
            source.model_copy(update={'title': 'Unverified operator batch brief'}) if source.source_id == 'operator-notes' else source
            for source in request.sources)})
    _reject_retired_format(request, settings)
    return request
