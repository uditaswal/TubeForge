from tubeforge.long_form.usage import observed_usage


def test_codex_cached_tokens_are_not_added_twice():
    usage=observed_usage({'input_tokens':100,'output_tokens':20,'cached_input_tokens':80})
    assert usage.input_tokens==100 and usage.cached_input_tokens==80
    assert usage.reasoning_tokens is None and usage.reported_cost_usd is None


def test_claude_uncached_cache_read_and_cache_creation_are_summed_once():
    usage=observed_usage({'input_tokens':50,'output_tokens':20,'cache_read_input_tokens':100000,'cache_creation_input_tokens':0},provider='claude')
    assert usage.input_tokens==100050 and usage.cached_input_tokens==100000
    partial=observed_usage({'input_tokens':50,'output_tokens':20,'cache_read_input_tokens':100000},provider='claude')
    assert partial.input_tokens is None and partial.output_tokens==20


def test_absent_or_invalid_usage_stays_unknown():
    assert observed_usage(None) is None
    assert observed_usage({'input_tokens':True,'output_tokens':-1,'total_cost_usd':'NaN'}) is None
    usage=observed_usage({'input_tokens':0,'output_tokens':0,'total_cost_usd':0})
    assert usage.input_tokens==0 and usage.output_tokens==0 and usage.reported_cost_usd==0
