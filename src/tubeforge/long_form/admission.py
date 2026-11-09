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
VOCAB_SHA256='446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d'


def stage_output_limit(message):
    stage_limits = {'research': 2500, 'review': 6000}
    return min(message.token_policy.maximum_output_tokens, stage_limits.get(message.stage, 16000))


def claude_stage_limits(message):
    """Bind the CLI execution limits into the worker and host admission receipt."""
    research = message.stage == 'research'
    return {
        'effort': 'high' if message.request.script_model == 'opus' else 'medium' if research else 'low',
        'max_turns': 6 if research else 2,
        'max_output_tokens': stage_output_limit(message),
        'structured_output_attempts': 1,
    }


def local_tokenizer():
    # Explicit setup primes the public vocabulary once. Workers must not download
    # a tokenizer implicitly or hang on external access while checking admission.
    cache=Path(os.environ.get('TIKTOKEN_CACHE_DIR',os.environ.get('DATA_GYM_CACHE_DIR',str(Path(tempfile.gettempdir())/'data-gym-cache'))))
    vocabulary=cache/hashlib.sha1(VOCAB_URL.encode()).hexdigest()
    if not vocabulary.is_file():
        raise ValueError('LF2 tokenizer cache is missing; prime o200k_base during reviewed environment setup')
    if hashlib.sha256(vocabulary.read_bytes()).hexdigest()!=VOCAB_SHA256:
        raise ValueError('LF2 tokenizer cache integrity failed; repair it during reviewed setup')
    import tiktoken
    return tiktoken.get_encoding(ENCODING)


def output_text_tokens(value):
    text=value if isinstance(value,str) else json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))
    return len(local_tokenizer().encode(text,disallowed_special=()))


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
    output_reservation=stage_output_limit(message)
    reserved=admitted_input+output_reservation
    if reserved>message.token_policy.total_reserved_tokens:
        raise ValueError('LF2 call cannot fit the total reserved-text-token budget')
    execution = {'claude_cli': claude_stage_limits(message)} if message.request.script_owner == 'claude' else {}
    return dict(prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),schema_sha256=hashlib.sha256(encoded_schema.encode()).hexdigest(),
        request_sha256=hashlib.sha256(wire).hexdigest(),request_bytes=len(wire),prompt_bytes=len(prompt.encode()),schema_bytes=len(encoded_schema.encode()),
        local_encoding=ENCODING,plain_text_prompt_tokens=prompt_tokens,plain_text_schema_tokens=schema_tokens,
        input_reservation=admitted_input,output_reservation=output_reservation,total_reservation=reserved,
        resource_hashes=preflight(template_version=PROFILE), **execution,
        notice='Local text/schema admission and conservative reservations; provider overhead, reasoning, observed usage and subscription allowance are separate. No provider-side hard output cap is asserted.')
