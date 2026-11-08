import hashlib
import json
from datetime import UTC,datetime

import pytest
from tubeforge.core.errors import InsufficientSourcesError,ProviderCancellation
from tubeforge.domain.reference_video import ReferenceSnapshot,TranscriptCue
from tubeforge.long_form.evidence import capture_primary_packet,full_reference_comparison,reference_excerpts
from tubeforge.providers.content.research import ResearchResult
from tubeforge.pipeline.scene_contracts import validate_request_source_packet
from test_long_form_writing import writing_inputs


def result():return ResearchResult(status='ready',assessment='Synthetic research only.',sources=[dict(source_id='p1',url='https://first.example/docs',title='First synthetic source'),dict(source_id='p2',url='https://second.example/docs',title='Second synthetic source')])


def test_primary_capture_keeps_http_and_excerpt_hashes_without_claiming_approval():
    message,_,_,_=writing_inputs();calls=[]
    payloads={url:b'<html><script>ignored script</script><article>'+url.encode()+b' '+b'Synthetic primary text evidence. '*100+b'</article></html>' for url in ['https://first.example/docs','https://second.example/docs']}
    class HTTP:
        def __init__(self,**options):calls.append(options)
        def fetch(self,url,maximum):assert maximum==2_000_000;return payloads[url]
    request,packet=capture_primary_packet(message.request,result(),http_factory=HTTP)
    assert len(request.sources)==2 and all(c['allowed_content_types']=={'text/html','text/plain'} for c in calls)
    assert [c['allowed_hosts'] for c in calls]==[{'first.example'},{'second.example'}]
    for source in packet['sources']:
        assert source['original_content_sha256']==hashlib.sha256(payloads[source['url']]).hexdigest()
        assert source['content_sha256']==hashlib.sha256(source['excerpt'].encode()).hexdigest()
        assert source['content_sha256']!=source['original_content_sha256']
        assert source['snapshot_kind']=='captured_primary_excerpt' and source['untrusted'] is True
        assert 'ignored script' not in source['excerpt']
    validate_request_source_packet(request,json.dumps(packet).encode())
    assert request.model_dump(exclude={'sources'})==message.request.model_dump(exclude={'sources'})


def test_missing_substantive_primary_pages_stop_before_narration():
    message,_,_,_=writing_inputs()
    class HTTP:
        def __init__(self,**kwargs):pass
        def fetch(self,*args):return b'<html>Short navigation</html>'
    with pytest.raises(InsufficientSourcesError):capture_primary_packet(message.request,result(),http_factory=HTTP)
    with pytest.raises(ProviderCancellation):capture_primary_packet(message.request,result(),http_factory=HTTP,cancelled=lambda:True)


def test_full_reference_comparison_includes_cross_cue_and_cross_section_phrases():
    _,draft,reference,_=writing_inputs()
    phrase='alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu'.split()
    cues=(TranscriptCue(start_seconds=0,end_seconds=5,text=' '.join(phrase[:6])),TranscriptCue(start_seconds=5,end_seconds=10,text=' '.join(phrase[6:])))
    reference=reference.model_copy(update={'cues':cues})
    sections=(draft.package.script_sections[0].model_copy(update={'narration':' '.join(phrase[:6])}),draft.package.script_sections[1].model_copy(update={'narration':' '.join(phrase[6:])}))
    changed=draft.model_copy(update={'package':draft.package.model_copy(update={'script_sections':sections})})
    report=full_reference_comparison(changed,reference)
    assert report['matched_shingles']==6 and report['script_shingle_count']==6 and report['matched_fraction']==1
    assert report['examples'][0]['reference_cue_index']==0
    assert 'does not prove originality' in report['notice']
    assert len(reference_excerpts(reference))==2


def test_private_or_binary_source_targets_are_rejected_before_body_read(monkeypatch):
    from unittest.mock import Mock
    from tubeforge.reference.extractor import PublicHTTPS,IntakeFailure
    connect=Mock();monkeypatch.setattr('socket.create_connection',connect)
    http=PublicHTTPS(allowed_hosts={'internal.example'},resolver=lambda *a,**k:[(None,None,None,None,('127.0.0.1',443))])
    with pytest.raises(IntakeFailure,match='private'):http.fetch('https://internal.example/doc',1000)
    connect.assert_not_called()


def test_primary_http_rejects_binary_content_type(monkeypatch):
    from unittest.mock import Mock
    from tubeforge.reference.extractor import PublicHTTPS,IntakeFailure
    response=Mock(status=200);headers={'Content-Type':'application/pdf'}
    response.getheader.side_effect=lambda name,default=None:headers.get(name,default)
    connection=Mock();connection.getresponse.return_value=response
    monkeypatch.setattr('http.client.HTTPSConnection',lambda *a,**k:connection)
    monkeypatch.setattr('socket.create_connection',lambda *a,**k:Mock())
    http=PublicHTTPS(allowed_hosts={'primary.example'},allowed_content_types={'text/html','text/plain'},resolver=lambda *a,**k:[(None,None,None,None,('8.8.8.8',443))])
    with pytest.raises(IntakeFailure,match='HTML or plain text'):http.fetch('https://primary.example/paper.pdf',1000)
    response.read.assert_not_called()


def test_duplicate_primary_responses_do_not_count_as_two_independent_sources():
    message,_,_,_=writing_inputs()
    class HTTP:
        def __init__(self,**kwargs):pass
        def fetch(self,*args):return b'Synthetic identical copied article text. '*100
    with pytest.raises(InsufficientSourcesError) as caught:capture_primary_packet(message.request,result(),http_factory=HTTP)
    assert len(caught.value.evidence['captured_sources'])==1
    assert 'Duplicate captured' in caught.value.evidence['excluded_sources'][0]['reason']
