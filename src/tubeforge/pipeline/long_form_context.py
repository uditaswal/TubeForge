"""Exact source context for long-form writers, bounded without truncation."""
from __future__ import annotations

import hashlib
import json

from tubeforge.domain.long_form import LongFormPlanningContract
from tubeforge.pipeline.scene_contracts import validate_request_source_packet
from tubeforge.providers.content.prompts import validate_untrusted_request


def build_source_context(planning: LongFormPlanningContract, source_packet_bytes: bytes,
                         *, maximum_bytes: int = 24000) -> bytes:
    """Serialize only the plan's cited sources, preserving every excerpt byte.

    This is context, not a finished writer prompt or an approved evidence claim.
    Selecting IDs is explicit in the plan; unknown IDs or missing excerpts fail.
    """
    if maximum_bytes <= 0:
        raise ValueError('source context byte budget must be positive')
    if hashlib.sha256(source_packet_bytes).hexdigest() != planning.source_packet_sha256:
        raise ValueError('source context packet identity is stale')
    validate_request_source_packet(planning.request, source_packet_bytes)
    validate_untrusted_request(planning.request)
    by_id = {s.source_id:s for s in planning.request.sources}
    sources = []
    for source_id in planning.cited_source_ids:
        source = by_id[source_id]
        if source.excerpt is None or not source.excerpt.strip():
            raise ValueError('source context requires evidence excerpts for every selected source')
        sources.append(dict(source_id=source_id,url=str(source.url),title=source.title,excerpt=source.excerpt))
    payload = json.dumps(dict(schema_version='long-form-source-context-v1',untrusted=True,
                             source_packet_sha256=planning.source_packet_sha256,sources=sources),
                         ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
    if len(payload) > maximum_bytes:
        raise ValueError(f'source context exceeds its UTF-8 byte budget ({len(payload)} > {maximum_bytes}); revise the source packet')
    return payload
