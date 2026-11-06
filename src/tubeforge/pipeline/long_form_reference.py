"""Deterministic identities for captured references, without fetching/writing."""
from __future__ import annotations

import hashlib
import json

from tubeforge.domain.reference_video import ReferenceIntakeRequest, ReferenceSnapshot
from tubeforge.domain.long_form import LongFormPlanningContract


def reference_content_identity(snapshot: ReferenceSnapshot) -> str:
    """Exclude capture time only; changed content/extractor/language invalidates."""
    material = snapshot.model_dump(mode='json', exclude={'captured_at'})
    return hashlib.sha256(json.dumps(material, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def reference_cache_key(request: ReferenceIntakeRequest, snapshot: ReferenceSnapshot) -> str:
    if request.reference_url != snapshot.reference_url:
        raise ValueError('cannot cache a snapshot for a different reference')
    material = {'request': request.model_dump(mode='json'), 'reference_content_sha256': reference_content_identity(snapshot)}
    return hashlib.sha256(json.dumps(material, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def validate_planned_reference(planning: LongFormPlanningContract, snapshot_bytes: bytes, *, intake_request: ReferenceIntakeRequest | None = None) -> ReferenceSnapshot:
    """Validate captured reference data against a server-held planning binding.

    Does not establish factual support, originality, reuse rights or approval.
    Exact capture hash and semantic cache identity are intentionally distinct.
    """
    if planning.reference_snapshot_sha256 is None or hashlib.sha256(snapshot_bytes).hexdigest() != planning.reference_snapshot_sha256:
        raise ValueError('reference snapshot does not match the planning identity')
    snapshot = ReferenceSnapshot.model_validate_json(snapshot_bytes)
    if snapshot.transcript_origin == 'unavailable':
        raise ValueError('reference planning requires a usable transcript')
    if snapshot.language.casefold() != planning.request.language.casefold():
        raise ValueError('reference transcript language differs from canonical brief')
    if intake_request is not None:
        if (snapshot.reference_url != intake_request.reference_url
            or intake_request.channel_identity != planning.request.channel_identity
            or intake_request.target_duration_seconds != planning.request.target_duration_seconds
            or intake_request.language.casefold() != planning.request.language.casefold()):
            raise ValueError('reference intake differs from canonical brief')
        if intake_request.supplied_cues and (snapshot.transcript_origin != 'supplied' or snapshot.cues != intake_request.supplied_cues):
            raise ValueError('captured supplied transcript differs from intake')
    return snapshot
