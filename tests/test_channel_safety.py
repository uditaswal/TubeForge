from tubeforge.pipeline.channel_safety import disclosure_record


def evidence():
    return {'request': {'sources': [{'source_id': 'one', 'url': 'https://example.com', 'excerpt': 'A completely different source excerpt.', 'title': 'Source'}]}, 'reference_short': {'scenes': [{'vo': 'A useful original explanation.', 'source_ids': ['one']}]}}


def test_disclosure_reuses_licenses_and_requires_operator_decision():
    record = disclosure_record(evidence(), {'audio_licenses': [{'asset': 'music', 'mode': 'synthesized', 'note': 'original signals'}]}, job_id='job', final_checksum='abc')
    assert record['eligible']
    assert record['platform_disclosure_required'] is None
    assert record['originality']['status'] == 'pass'
    assert record['sources'][0]['url'] == 'https://example.com'


def test_missing_evidence_and_catalog_pointer_fail_closed():
    assert not disclosure_record({}, {}, job_id='job', final_checksum='abc')['eligible']
    record = disclosure_record(evidence(), {'audio_licenses': [{'asset': 'music', 'mode': 'track', 'source_path': '/private/music.wav'}]}, job_id='job', final_checksum='abc')
    assert not record['eligible']
    assert 'source_path' not in record['audio_licenses'][0]


def test_copied_narration_and_evidence_changes():
    package = evidence()
    package['request']['sources'][0]['excerpt'] = package['reference_short']['scenes'][0]['vo'] = 'one two three four five six seven eight nine ten'
    audio = {'audio_licenses': [{'asset': 'music', 'mode': 'synthesized'}]}
    first = disclosure_record(package, audio, job_id='job', final_checksum='abc')
    assert not first['eligible'] and first['originality']['status'] == 'fail'
    assert first['evidence_identity'] != disclosure_record(package, audio, job_id='job', final_checksum='changed')['evidence_identity']


def test_nonfactual_loop_does_not_require_citation():
    package = evidence()
    package['reference_short']['scenes'].append({'template': 'loop', 'vo': 'Which brings us back to'})
    assert disclosure_record(package, {'audio_licenses': [{'asset': 'music', 'mode': 'synthesized'}]}, job_id='job', final_checksum='abc')['eligible']
