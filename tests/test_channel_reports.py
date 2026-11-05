from tubeforge.pipeline.channel_reports import ChannelSafetyConfig, cadence_report, repetition_report, scope_cadence, similar_and_close


def short(id, at='2026-11-04T10:00:00+05:30', channel='a', hook='If your cache fails, where do requests go?'):
    return {'short': {'id': id, 'title': 'Cache 1 failure', 'publish_at': at, 'channel': channel, 'hook': hook},
            'script': {'reference_short': {'scenes': [{'vo': hook, 'template': 'hook'}]}}, 'layout_family': 'terminal_led', 'voice': 'voice-a', 'music': 'synthesized'}


def test_repetitive_openings_production_and_week_window():
    config = ChannelSafetyConfig()
    report = repetition_report([short('one'), short('two'), short('other', channel='b'), short('old', at='2026-10-20T10:00:00+05:30')], config, '2026-11-04')
    assert len(report['warnings']) == 1
    assert report['warnings'][0]['ids'] == ['one', 'two']
    assert {r['code'] for r in report['warnings'][0]['reasons']} == {'opening_similarity', 'title_pattern_similarity', 'repeated_phrases', 'shared_production_choices'}
    assert len(report['entries']) == 3
    assert report['entries'][0]['templates'] == {'hook': 1}


def test_configurable_similarity_and_unknown_fields_do_not_match():
    report = repetition_report([short('one', hook='a b c d'), short('two', hook='a b c e')], ChannelSafetyConfig(similarity_threshold=.9), '2026-11-04')
    assert all(r['code'] != 'opening_similarity' for r in report['warnings'][0]['reasons'])
    a,b=short('a'),short('b')
    for item in [a,b]:
        item['music']=item['voice']=item['layout_family']=None
    report = repetition_report([a,b], ChannelSafetyConfig(), '2026-11-04')
    assert all(r['code'] != 'shared_production_choices' for r in report['warnings'][0]['reasons'])


def test_cadence_channel_timezone_and_cross_midnight_spacing():
    config=ChannelSafetyConfig(defaults={'max_per_day': 1, 'min_spacing_minutes': 180})
    shorts=[short('a', at='2026-11-04T23:00:00+05:30')['short'],short('b',at='2026-11-05T00:00:00+05:30')['short'],short('c',at='2026-11-04T20:00:00Z')['short'],short('other',channel='b')['short']]
    report=cadence_report(shorts,config)
    assert any(w['code']=='minimum_spacing' and w['ids']==['a','b'] for w in report['warnings'])
    assert any(w['code']=='daily_limit' and w['day']=='2026-11-05' and w['ids']==['b','c'] for w in report['warnings'])
    assert all('other' not in w['ids'] for w in report['warnings'])


def test_spacing_boundary_and_missing_time():
    config=ChannelSafetyConfig()
    assert not cadence_report([short('a')['short'],short('b',at='2026-11-04T13:00:00+05:30')['short']],config)['warnings']
    assert cadence_report([short('a',at=None)['short']],config)['warnings'][0]['code']=='publish_time_missing'


def test_channel_override_and_invalid_timezone():
    import pytest
    config=ChannelSafetyConfig(channels={'a': {'max_per_day': 1, 'min_spacing_minutes': 0, 'timezone': 'UTC'}})
    warnings=cadence_report([short('a')['short'],short('b')['short']],config)['warnings']
    assert [w['code'] for w in warnings] == ['daily_limit']
    with pytest.raises(ValueError):
        ChannelSafetyConfig(defaults={'timezone': 'not-a-timezone'})


def test_undated_render_uses_creation_time_for_recent_window():
    a,b=short('a',at=None),short('b',at=None)
    a['created_at']=b['created_at']='2026-11-03T10:00:00+00:00'
    report=repetition_report([a,b,short('unknown',at=None)],ChannelSafetyConfig(),'2026-11-04')
    assert len(report['warnings'])==1
    assert report['entries'][0]['window_basis']=='created_at'
    assert report['unassessed_ids']==['unknown']


def test_cadence_reports_resolved_limits_and_can_be_scoped_to_one_day():
    config = ChannelSafetyConfig(defaults={'max_per_day': 1, 'min_spacing_minutes': 180}, channels={'a': {'max_per_day': 5, 'min_spacing_minutes': 30, 'timezone': 'UTC'}})
    items = [short('d1a', '2026-11-04T10:00:00+00:00'), short('d1b', '2026-11-04T10:10:00+00:00'),
             short('d2a', '2026-11-05T09:00:00+00:00', channel='b'), short('d2b', '2026-11-05T09:30:00+00:00', channel='b')]
    report = cadence_report([i['short'] for i in items], config)
    assert report['resolved_limits']['a'] == {'max_per_day': 5, 'min_spacing_minutes': 30, 'timezone': 'UTC'}
    assert report['resolved_limits']['b']['max_per_day'] == 1                      # falls back to the default limits
    assert len(report['warnings']) >= 3
    scoped = scope_cadence(report, '2026-11-05', ['d2a', 'd2b'])
    assert scoped['scope'] == {'day': '2026-11-05', 'filtered': True, 'all_warnings': len(report['warnings'])}
    assert scoped['warnings'] and all(set(w['ids']) <= {'d2a', 'd2b'} or w.get('day') == '2026-11-05' for w in scoped['warnings'])
    assert not any(w['channel'] == 'a' for w in scoped['warnings'])


def test_similar_and_close_joins_only_pairs_that_are_both_similar_and_planned_close():
    config = ChannelSafetyConfig(defaults={'min_spacing_minutes': 180})
    close = [short('one', '2026-11-04T10:00:00+05:30'), short('two', '2026-11-04T10:30:00+05:30')]
    far = [short('three', '2026-11-04T10:00:00+05:30'), short('four', '2026-11-04T20:00:00+05:30')]
    for items in (close, far):
        report = repetition_report(items, config, '2026-11-04')
        pairs = similar_and_close(report, [i['short'] for i in items], config)
        assert bool(pairs) is (items is close)
    assert pairs == [] and similar_and_close(repetition_report(close, config, '2026-11-04'), [i['short'] for i in close], config)[0]['ids'] == ['one', 'two']


def test_entries_name_the_fields_whose_history_is_unknown():
    item = short('one')
    item['music'] = None
    report = repetition_report([item], ChannelSafetyConfig(), '2026-11-04')
    assert report['entries'][0]['unknown_fields'] == ['music']
