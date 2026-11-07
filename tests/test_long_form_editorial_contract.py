"""LF0-B acceptance fixtures and canonical local tools; no live generation."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import jsonschema
from pydantic import ValidationError
import pytest

from tubeforge.core.errors import ProviderValidationError
from tubeforge.domain.contracts import ContentPackage, VideoMetadata, SourceReference
from tubeforge.domain.reference_video import ReferenceIntakeRequest, ReferenceIntakeView
from tubeforge.providers.content.youtube_skills import evaluate
from test_long_form_envelopes import representative_package
from test_long_form_contract import bound_candidate
from test_long_form_chapters import timing_for, export

ROOT=Path(__file__).resolve().parents[1]
FIXTURES=ROOT/'tests/fixtures/long_form/editorial'


def cases(): return json.loads((FIXTURES/'cases.json').read_text())


def editorial_package():
    value=cases()
    request,package=representative_package()
    raw=package.model_dump(mode='json')
    raw['hook_options']=value['hooks']
    raw['script_sections'][0]['narration']=value['hooks'][0]
    raw['metadata']['title_options']=value['titles']
    raw['thumbnail_brief']['text_options']=[value['thumbnail_text']]
    for scene in raw['scene_plans']: scene['on_screen_text']='Synthetic trace'
    return ContentPackage.model_validate(raw)


@pytest.fixture(scope='module')
def local_reports(tmp_path_factory):
    folder=tmp_path_factory.mktemp('editorial-tools')
    value=cases()
    for name,items in [('hooks',value['hooks']),('titles',value['titles'])]:
        (folder/f'{name}.txt').write_text('\n'.join(items)+'\n')
    hook=subprocess.run([sys.executable,str(ROOT/'.agents/skills/yt-script/hookscore.py'),'--json',str(folder/'hooks.txt')],capture_output=True,text=True,timeout=10,check=True)
    title=subprocess.run([sys.executable,str(ROOT/'.agents/skills/yt-package/title.py'),'--json',str(folder/'titles.txt'),'--thumb',value['thumbnail_text']],capture_output=True,text=True,timeout=10,check=True)
    return json.loads(hook.stdout),json.loads(title.stdout)


def test_canonical_hook_and_title_tools_execute_for_all_candidates(local_reports):
    hooks,titles=local_reports
    assert cases()['synthetic'] is True
    assert len(hooks)==5 and {r['hook'] for r in hooks}==set(cases()['hooks'])
    assert len(titles)==10 and {r['title'] for r in titles}==set(cases()['titles'])
    assert all(0<=r['verdict']<=100 for r in hooks)
    assert [r['verdict'] for r in hooks]==sorted((r['verdict'] for r in hooks),reverse=True)
    assert all('views' not in r and 'retention' not in r for r in hooks)


def test_local_package_evaluation_preserves_chosen_opening_and_reports_real_tools():
    package=editorial_package()
    report=evaluate(package)
    assert report['selected_hook']==package.script_sections[0].narration
    assert len(report['hooks'])==5 and len(report['titles'])==10
    assert report['tools_executed']==['hookscore.py','title.py']
    assert package.script_sections[0].narration==cases()['hooks'][0]
    assert report['resource_hashes']['yt-script/automation.md']==hashlib.sha256((ROOT/'.agents/skills/yt-script/automation.md').read_bytes()).hexdigest()
    # Standalone scoring is not host support for the proposed profile.
    from tubeforge.providers.content.prompts import SUPPORTED_CONTENT_TEMPLATE_VERSIONS
    assert package.request.prompt_version not in SUPPORTED_CONTENT_TEMPLATE_VERSIONS


def test_application_rejects_four_word_thumbnail_even_when_title_helper_misses_it(tmp_path):
    value=cases();text=value['invalid_thumbnail_text']
    result=subprocess.run([sys.executable,str(ROOT/'.agents/skills/yt-package/title.py'),'--json','--title',value['titles'][0],'--thumb',text],capture_output=True,text=True,timeout=10,check=True)
    assert not any(issue[0]=='thumb-length' for issue in json.loads(result.stdout)[0]['issues'])
    raw=editorial_package().model_dump(mode='json');raw['thumbnail_brief']['text_options']=[text]
    with pytest.raises(ProviderValidationError,match='at most three words'):
        evaluate(ContentPackage.model_validate(raw))


@pytest.mark.parametrize('change',['opening','hooks','titles'])
def test_existing_evaluator_rejects_mismatched_or_duplicate_candidates(change):
    raw=editorial_package().model_dump(mode='json')
    if change=='opening': raw['script_sections'][0]['narration']='A different opening.'
    elif change=='hooks': raw['hook_options']=[raw['hook_options'][0]]*5
    else: raw['metadata']['title_options']=[raw['metadata']['title_options'][0]]*10
    with pytest.raises(ProviderValidationError): evaluate(ContentPackage.model_validate(raw))


@pytest.mark.parametrize('raw',json.loads((FIXTURES/'intake_examples.json').read_text()),ids=lambda raw:raw['state'])
def test_frozen_api_examples_match_serialization_schema_and_read_only_identity(raw):
    view=ReferenceIntakeView.model_validate(raw)
    schema=json.loads((FIXTURES.parent/'ReferenceIntakeViewResponse.schema.json').read_text())
    response=view.model_dump(mode='json')
    jsonschema.validate(response,schema)
    if view.snapshot is None:
        assert response['reference_snapshot_sha256'] is None
    else:
        assert response['reference_snapshot_sha256']==hashlib.sha256(view.snapshot.model_dump_json().encode()).hexdigest()
    assert schema['properties']['reference_snapshot_sha256']['readOnly'] is True
    with pytest.raises(ValidationError):
        ReferenceIntakeRequest.model_validate({**raw['request'],'reference_snapshot_sha256':'a'*64})
    with pytest.raises(ValidationError):
        ReferenceIntakeView.model_validate({**raw,'reference_snapshot_sha256':'a'*64})


def test_frozen_response_schema_stays_current():
    assert json.loads((FIXTURES.parent/'ReferenceIntakeViewResponse.schema.json').read_text())==ReferenceIntakeView.model_json_schema(mode='serialization')


def test_proposed_long_description_uses_measured_chapters_and_stays_inside_stricter_qa_limit():
    plan,package,packet=bound_candidate()
    chapters=export(plan,timing_for(plan,package))
    description='\n'.join([
        'Inspect a fictional ExampleQueue restart trace.',
        'Synthetic example only; no measured performance benefit is claimed.',
        '',chapters,'','Sources','Synthetic fixture: https://example.com/lf0-editorial-fixture',
        'Reference inspiration is separate from factual evidence.'])
    metadata=VideoMetadata(title_options=(cases()['titles'][0],),description=description)
    assert len(metadata.description.splitlines())>2
    assert len(metadata.description)<=5000 and len(metadata.description.splitlines()[0])<=125
    assert '<' not in metadata.description and '>' not in metadata.description
    assert '00:00 Promise' in metadata.description
    assert '03:20 Mechanism' in metadata.description
    assert '06:40 Result' in metadata.description


def test_editorial_review_fixture_keeps_reference_observations_separate_from_factual_packet():
    value=cases()
    sources=tuple(SourceReference.model_validate(s) for s in value['primary_sources'])
    case=next(c for c in value['editorial_cases'] if c['id']=='qualified-new-example')
    assert set(case['evidence_source_ids']) <= {s.source_id for s in sources}
    assert value['reference_observations'][0]['inspection']=='synthetic-caption-only'
    assert value['reference_observations'][0]['start_seconds'] < value['reference_observations'][0]['end_seconds']
    assert 'does not establish' in sources[0].excerpt
    assert 'does not' in sources[0].excerpt and 'measure' in sources[0].excerpt
