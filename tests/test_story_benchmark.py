"""Prepared benchmark assets must not silently change before an expensive render."""
import hashlib
import json

import pytest

from scripts.benchmark_story_short import verify_prepared
from tubeforge.pipeline.capture import CAPTURE_POLICY


def test_modified_prepared_asset_fails_before_timeline_load(tmp_path):
    asset=tmp_path/'plate.png'
    asset.write_bytes(b'original fixture')
    proof={'capture_policy':CAPTURE_POLICY,'files':{'plate.png':hashlib.sha256(asset.read_bytes()).hexdigest()}}
    (tmp_path/'prepared-inputs.json').write_text(json.dumps(proof))
    asset.write_bytes(b'changed fixture')
    with pytest.raises(ValueError,match='prepared input changed'):
        verify_prepared(tmp_path)


def test_prepared_assets_cannot_escape_comparison_directory(tmp_path):
    (tmp_path/'prepared-inputs.json').write_text(json.dumps({
        'capture_policy':CAPTURE_POLICY,'files':{'../outside.png':'unused'}}))
    with pytest.raises(ValueError,match='prepared input changed'):
        verify_prepared(tmp_path)


def test_visual_quote_revision_preserves_narration_and_requires_stored_source(tmp_path):
    from scripts.benchmark_story_short import apply_visual_revision
    from test_reference_shorts import topic_data
    reference=tmp_path/'reference';reference.mkdir()
    topic=topic_data()
    old='Flags are applied on a best-effort basis'
    topic['scenes'][1]['visual']={'kind':'source','quote':old}
    topic_path=reference/'topic.json';topic_path.write_text(json.dumps(topic))
    package={'reference_short':topic,'request':{'sources':[{'source_id':'fixture',
        'excerpt':'The service is applied on a best-effort basis as documented.'}]},
        'script_sections':[{'narration':'Exact captured narration remains unchanged.'}]}
    (tmp_path/'content_package.json').write_text(json.dumps(package))
    (reference/'timeline.json').write_text(json.dumps({'topic_sha256':'old','narration_sha256':'unchanged','scenes':[]}))
    revision=tmp_path/'patch.json'
    revision.write_text(json.dumps({'expected_topic_sha256':hashlib.sha256(topic_path.read_bytes()).hexdigest(),
        'source_quotes':[{'scene_id':topic['scenes'][1]['scene_id'],'expected_quote':old,'quote':'on a best-effort basis'}]}))
    apply_visual_revision(tmp_path,revision)
    result=json.loads((tmp_path/'content_package.json').read_text())
    assert result['script_sections']==package['script_sections']
    assert [s['vo'] for s in result['reference_short']['scenes']]==[s['vo'] for s in topic['scenes']]
    assert result['reference_short']['scenes'][1]['visual']['quote']=='on a best-effort basis'
    assert json.loads((reference/'timeline.json').read_text())['narration_sha256']=='unchanged'


def test_visual_quote_revision_rejects_new_unsupported_wording(tmp_path):
    from scripts.benchmark_story_short import apply_visual_revision
    from test_reference_shorts import topic_data
    reference=tmp_path/'reference';reference.mkdir()
    topic=topic_data();topic['scenes'][1]['visual']={'kind':'source','quote':'original bounded quote'}
    path=reference/'topic.json';path.write_text(json.dumps(topic))
    (tmp_path/'content_package.json').write_text(json.dumps({'request':{'sources':[{
        'source_id':'fixture','excerpt':'original bounded quote'}]}}))
    revision=tmp_path/'patch.json';revision.write_text(json.dumps({
        'expected_topic_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'source_quotes':[{'scene_id':topic['scenes'][1]['scene_id'],'expected_quote':'original bounded quote',
                          'quote':'new invented wording'}]}))
    with pytest.raises(ValueError,match='exact bounded excerpt'):
        apply_visual_revision(tmp_path,revision)
