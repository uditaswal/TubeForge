"""Bounded LF2 wire bytes without duplicated immutable input packets."""
from __future__ import annotations
import json
from tubeforge.domain.long_form_writing import LongFormHostRequest


def draft_context(draft):
    value=draft.model_dump(mode='json')
    if value['package'] is not None:value['package'].pop('request',None)
    return value


def encode(message:LongFormHostRequest):
    value=message.model_dump(mode='json')
    if message.draft is not None:value['draft']=draft_context(message.draft)
    payload=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
    if len(payload)>65536:raise ValueError('LF2 request exceeds 65,536 UTF-8 wire bytes')
    return payload
