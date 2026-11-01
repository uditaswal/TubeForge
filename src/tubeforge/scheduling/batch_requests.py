"""Shared normal Studio request expansion for manual and automatic batch intake."""
import json


def build_batch_request(short, settings):
    from tubeforge.api.app import VideoBriefRequest, _video_request, _reject_retired_format
    presets = settings.pipeline.video_generation.presets
    preset = next((name for name, value in presets.items() if value.aspect_ratio == '9:16' and value.minimum_duration_seconds <= short.length_s <= value.maximum_duration_seconds), None)
    if preset is None:
        raise ValueError("no configured vertical preset supports this short's length")
    brief = dict(title=short.title,
        notes=('Unverified operator batch brief: ' + json.dumps(short.model_dump(mode='json'), ensure_ascii=False),),
        angle=short.concept, duration_seconds=short.length_s, preset=preset,
        review_mode='manual', ending=short.ending, channel_identity=short.channel)
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
