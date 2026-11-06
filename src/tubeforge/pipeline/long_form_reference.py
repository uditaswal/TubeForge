"""Deterministic identities for captured references, without fetching/writing."""
from __future__ import annotations

import hashlib
import json

from tubeforge.domain.reference_video import ReferenceIntakeRequest, ReferenceSnapshot


def reference_content_identity(snapshot: ReferenceSnapshot) -> str:
    """Exclude capture time only; changed content/extractor/language invalidates."""
    material = snapshot.model_dump(mode='json', exclude={'captured_at'})
    return hashlib.sha256(json.dumps(material, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def reference_cache_key(request: ReferenceIntakeRequest, snapshot: ReferenceSnapshot) -> str:
    if request.reference_url != snapshot.reference_url:
        raise ValueError('cannot cache a snapshot for a different reference')
    material = {'request': request.model_dump(mode='json'), 'reference_content_sha256': reference_content_identity(snapshot)}
    return hashlib.sha256(json.dumps(material, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
