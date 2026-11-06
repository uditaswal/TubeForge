import hashlib
import json
from pathlib import Path

from pydantic import ValidationError
import pytest

from tubeforge.domain.long_form import LongFormTimingManifest
from tubeforge.pipeline.long_form_chapters import export_chapters
from test_long_form_contract import bound_candidate


def timing_for(plan, package):
    return LongFormTimingManifest(package_sha256=hashlib.sha256(package).hexdigest(),audio_sha256='a'*64,artifact_sha256='b'*64,
        timing_method='measured_scene_audio',duration_seconds=600,
        sections=[dict(section_id=sid,start_seconds=i*200+0.2,end_seconds=(i+1)*200) for i,sid in enumerate(plan.section_ids)])


def export(plan,timing,**overrides):
    args=dict(package_sha256=timing.package_sha256,audio_sha256=timing.audio_sha256,artifact_sha256=timing.artifact_sha256)
    args.update(overrides)
    return export_chapters(plan,timing,**args)


def test_measured_chapters_preserve_titles_and_include_opening_leadin():
    plan,package,packet=bound_candidate(); timing=timing_for(plan,package)
    assert export(plan,timing)=='00:00 Promise\n03:20 Mechanism\n06:40 Result'


@pytest.mark.parametrize('identity',['package_sha256','audio_sha256','artifact_sha256'])
def test_stale_script_audio_or_final_identity_fails(identity):
    plan,package,packet=bound_candidate();timing=timing_for(plan,package)
    with pytest.raises(ValueError,match='stale'): export(plan,timing,**{identity:'c'*64})


@pytest.mark.parametrize('change',['reorder','estimate','nonfinite','outside','duplicate','overlap','short_last','bad_title','wrong_target'])
def test_chapter_export_rejects_guessed_or_invalid_timelines(change):
    plan,package,packet=bound_candidate(); timing=timing_for(plan,package);raw=timing.model_dump(mode='json')
    if change=='reorder': raw['sections'].reverse()
    elif change=='estimate': raw['timing_method']='estimated'
    elif change=='nonfinite': raw['sections'][1]['start_seconds']=float('nan')
    elif change=='outside': raw['sections'][-1]['end_seconds']=601
    elif change=='duplicate': raw['sections'][-1]['section_id']=raw['sections'][0]['section_id']
    elif change=='overlap': raw['sections'][1]['start_seconds']=1
    elif change=='short_last': raw['sections'][-1]['start_seconds']=595
    elif change=='bad_title':
        chapter=plan.chapters[-1].model_copy(update={'title':'Result\n09:59 Fake chapter'})
        plan=plan.model_copy(update={'chapters':(*plan.chapters[:-1],chapter)})
    else: plan=plan.model_copy(update={'request':plan.request.model_copy(update={'target_duration_seconds':900})})
    with pytest.raises((ValidationError,ValueError)):
        export(plan,LongFormTimingManifest.model_validate(raw))


def test_timing_schema_snapshot_is_current():
    path=Path(__file__).parent/'fixtures/long_form/LongFormTimingManifest.schema.json'
    assert json.loads(path.read_text())==LongFormTimingManifest.model_json_schema()
