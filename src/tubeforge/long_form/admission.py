"""Measured LF2 text admission; never a provider/subscription token guarantee."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile

from tubeforge.domain.long_form_writing import PROFILE
from tubeforge.long_form.wire import encode
from tubeforge.long_form.prompts import build_prompt,output_schema
from tubeforge.providers.content.youtube_skills import preflight

VOCAB_URL='https://openaipublic.blob.core.windows.net/encodings/o200k_base.tiktoken'
ENCODING='o200k_base'


def local_tokenizer():
    # Explicit setup primes the public vocabulary once. Workers must not download
    # a tokenizer implicitly or hang on external access while checking admission.
    cache=Path(os.environ.get('TIKTOKEN_CACHE_DIR',os.environ.get('DATA_GYM_CACHE_DIR',str(Path(tempfile.gettempdir())/'data-gym-cache'))))
    if not (cache/hashlib.sha1(VOCAB_URL.encode()).hexdigest()).is_file():
        raise ValueError('LF2 tokenizer cache is missing; prime o200k_base during reviewed environment setup')
    import tiktoken
    return tiktoken.get_encoding(ENCODING)


def measure(message,*,tokenizer=None):
    prompt=build_prompt(message);schema=output_schema(message.stage)
    encoded_schema=json.dumps(schema,ensure_ascii=False,sort_keys=True,separators=(',',':'))
    wire=encode(message)
    if len(wire)>65536:raise ValueError('LF2 request exceeds 65,536 UTF-8 wire bytes')
    tokenizer=tokenizer or local_tokenizer()
    # These are exact counts only for the named local encoding/plain text.
    # CLI/system/tool/reasoning overhead and billing remain observed-or-unknown.
    prompt_tokens=len(tokenizer.encode(prompt,disallowed_special=()))
    schema_tokens=len(tokenizer.encode(encoded_schema,disallowed_special=()))
    admitted_input=prompt_tokens+schema_tokens+512
    if admitted_input>message.token_policy.maximum_input_tokens:
        raise ValueError(f'LF2 local input admission exceeds budget: {admitted_input} > {message.token_policy.maximum_input_tokens}')
    output_reservation=min(message.token_policy.maximum_output_tokens,2500 if message.stage=='research' else 6000 if message.stage=='review' else 16000)
    reserved=admitted_input+output_reservation
    if reserved>message.token_policy.total_reserved_tokens:
        raise ValueError('LF2 call cannot fit the total reserved-text-token budget')
    return dict(prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),schema_sha256=hashlib.sha256(encoded_schema.encode()).hexdigest(),
        request_sha256=hashlib.sha256(wire).hexdigest(),request_bytes=len(wire),prompt_bytes=len(prompt.encode()),schema_bytes=len(encoded_schema.encode()),
        local_encoding=ENCODING,plain_text_prompt_tokens=prompt_tokens,plain_text_schema_tokens=schema_tokens,
        input_reservation=admitted_input,output_reservation=output_reservation,total_reservation=reserved,
        resource_hashes=preflight(template_version=PROFILE),
        notice='Local text/schema admission and conservative reservations; provider overhead, reasoning, observed usage and subscription allowance are separate. No provider-side hard output cap is asserted.')
