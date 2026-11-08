"""Semantic allowance identity excludes provider and capture-only changes."""
import hashlib
import json
from tubeforge.domain.contracts import generation_request_key_payload
from tubeforge.pipeline.long_form_reference import reference_content_identity


def writing_identity(request,reference):
    material=generation_request_key_payload(request)
    for field in ('script_owner','script_model','script_routing_mode'):material.pop(field,None)
    for source in material['sources']:
        source.pop('retrieved_at',None);source.pop('content_sha256',None)
    return hashlib.sha256(json.dumps(dict(request=material,reference=reference_content_identity(reference)),sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
