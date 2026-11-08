"""Whitelisted observed provider counters; absent or invalid values stay unknown."""
from decimal import Decimal,InvalidOperation
from tubeforge.domain.long_form_budget import ObservedUsage


def observed_usage(raw,*,provider=None):
    if not isinstance(raw,dict):return None
    def counter(*names):
        for name in names:
            value=raw.get(name)
            if isinstance(value,int) and not isinstance(value,bool) and value>=0:return value
        return None
    cost=raw.get('reported_cost_usd',raw.get('total_cost_usd'))
    try:
        cost=Decimal(str(cost)) if cost is not None else None
        if cost is not None and (not cost.is_finite() or cost<0):cost=None
    except (InvalidOperation,ValueError):cost=None
    input_tokens=counter('input_tokens')
    # Claude reports uncached input, cache reads and cache writes separately:
    # https://platform.claude.com/docs/en/build-with-claude/prompt-caching
    # Codex cached_input_tokens is a subset and must not be added a second time.
    claude=(provider or '').startswith(('claude','host-claude')) or any(k in raw for k in ('cache_read_input_tokens','cache_creation_input_tokens'))
    if claude:
        components=[input_tokens,counter('cache_read_input_tokens'),counter('cache_creation_input_tokens')]
        input_tokens=sum(components) if all(v is not None for v in components) else None
    values=dict(input_tokens=input_tokens,output_tokens=counter('output_tokens'),
        cached_input_tokens=counter('cached_input_tokens','cache_read_input_tokens'),reasoning_tokens=counter('reasoning_tokens'),reported_cost_usd=cost)
    return ObservedUsage(**values) if any(v is not None for v in values.values()) else None
