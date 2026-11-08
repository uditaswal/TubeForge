import json
from tubeforge.reference.brief import build_reference_brief
from tubeforge.reference.extractor import YoutubeReferenceExtractor
from test_reference_intake_extractor import FixtureHTTP,request,player


def test_brief_is_bounded_snapshot_bound_and_source_timestamped():
    snapshot=YoutubeReferenceExtractor(FixtureHTTP()).capture(request())
    brief=build_reference_brief(snapshot,720)
    assert brief==build_reference_brief(snapshot,720)
    assert len(json.dumps(brief).encode())<12000
    assert 'no AI analysis' in brief['classification']
    for row in brief['samples']:
        cue=snapshot.cues[row['cue_index']]
        assert row['start_seconds']==cue.start_seconds and row['excerpt']==cue.text[:240]
    for row in brief['proposed_improvements']:
        assert row['source_excerpt']==snapshot.cues[row['cue_index']].text[:240]
        assert row['supporting_evidence'].startswith('NOT STARTED')
    changed=snapshot.model_copy(update={'title':'Changed title'})
    assert build_reference_brief(changed,720)['reference_snapshot_sha256']!=brief['reference_snapshot_sha256']


def test_missing_transcript_does_not_invent_improvements():
    raw=player();raw['captions']={}
    brief=build_reference_brief(YoutubeReferenceExtractor(FixtureHTTP(raw)).capture(request()),600)
    assert brief['samples']==[] and brief['proposed_improvements']==[]
    assert brief['caption_interval_coverage_percent']==0
