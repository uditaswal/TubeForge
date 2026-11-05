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


def test_catalog_terms_are_resolved_by_actual_audio_checksum(tmp_path):
    import json
    from types import SimpleNamespace
    from tubeforge.pipeline.channel_safety import read_audio
    folder=tmp_path/'reference'/'mix'
    folder.mkdir(parents=True)
    (folder/'audio-provenance.json').write_text(json.dumps({'audio_licenses':[{'asset':'music','mode':'track','source_sha256':'actual'}]}))
    class Rights:
        checksum_sha256='actual'
        def model_dump(self, **kwargs):
            return {'license_name':'CC BY 4.0','license_url':'https://creativecommons.org/licenses/by/4.0/'}
    audio=read_audio(tmp_path/'final.mp4', SimpleNamespace(list=lambda:[Rights()]))
    assert disclosure_record(evidence(),audio,job_id='job',final_checksum='abc')['eligible']
    Rights.checksum_sha256='different'
    assert not disclosure_record(evidence(),read_audio(tmp_path/'final.mp4',SimpleNamespace(list=lambda:[Rights()])),job_id='job',final_checksum='abc')['eligible']


def test_reused_final_backfills_disclosure_without_render_or_script_calls(tmp_path):
    from types import SimpleNamespace as NS
    from tubeforge.pipeline.orchestrator import PipelineOrchestrator
    from tubeforge.domain.states import JobState
    runner=object.__new__(PipelineOrchestrator)
    package=NS(model_dump=lambda **kwargs:evidence())
    runner._reference_package=lambda job:package
    runner._reference_inputs=lambda job,p:({},'inputs')
    runner._reference_music=lambda job:None
    runner._music_identity=lambda music:'music'
    runner._reference_source_identity=lambda *args,**kwargs:'source'
    final=NS(path=str(tmp_path/'final.mp4'),checksum_sha256='final')
    runner._valid_artifact=lambda *args:final
    runner._load_json_artifact=lambda *args:{'source_render_identity':'source','input_identity':'inputs','render_identity':'render'}
    runner.music_catalog=None
    captured=[]
    runner._replace_json=lambda *args:captured.append(args)
    actual,identity=runner._reference_render_checkpoint(NS(id='job'),JobState.FINAL_RENDERING,'final','final.mp4',lambda:False,approval_identity='approved',approval_id='approval')
    assert actual is final and identity=='render'
    assert captured[0][2]=='disclosure_record'
    assert captured[0][3]['final_checksum']=='final'
    assert not captured[0][3]['eligible']  # Missing audio remains missing, never invented.


def test_malformed_or_incomplete_audio_trail_is_unavailable():
    for licenses in [[{}], ['invalid'], [{'asset':'sfx:key','license':'terms'}]]:
        assert not disclosure_record(evidence(), {'audio_licenses':licenses},job_id='job',final_checksum='abc')['eligible']
