from __future__ import annotations
import copy
import pytest
from tubeforge.core.errors import ProviderValidationError
from tubeforge.domain.contracts import ContentPackage,ContentRequest,SourceReference
from tubeforge.providers.fake import FakeContentProvider
from tubeforge.providers.content.output import unwrap_generation
from tubeforge.host_codex_runner import codex_output_schema


def payload():
    request=ContentRequest(topic='Rust migration',angle='Verify the premise',target_duration_seconds=60,language='en',audience='general',prompt_version='m6-content-v7',sources=(SourceReference(source_id='primary',url='https://example.com/source',title='Primary evidence',excerpt=('“Exact” Unicode — punctuation and newlines.\n' * 100)),))
    package=FakeContentProvider().generate_package(request).model_dump(mode='json')
    package.pop('request')
    return request, {'status':'ready','package':package,'reason':None}


def test_application_binds_exact_input_without_mutating_generated_fields():
    request, raw=payload();before=copy.deepcopy(raw)
    result=unwrap_generation(raw,request=request)
    assert raw==before
    assert ContentPackage.model_validate(result).request==request
    assert {k:v for k,v in result.items() if k!='request'}==raw['package']


def test_conflicting_legacy_echo_is_rejected_not_repaired():
    request,raw=payload();raw['package']['request']=request.model_dump(mode='json')
    raw['package']['request']['sources'][0]['excerpt']='Model altered evidence'
    with pytest.raises(ProviderValidationError,match='echo differs'):
        unwrap_generation(raw,request=request)


def test_binding_does_not_accept_invented_citations():
    request,raw=payload();raw['package']['claims'][0]['source_ids']=['invented-source']
    with pytest.raises(ValueError,match='source'):
        unwrap_generation(raw,request=request)


def test_cli_schema_cannot_request_echo_but_legacy_schema_is_preserved():
    schema=codex_output_schema(envelope=True)['$defs']['ContentPackage']
    assert 'request' not in schema['properties']
    assert 'request' not in schema['required']
    assert schema['additionalProperties'] is False
    assert 'request' in codex_output_schema()['properties']


def test_envelope_prompt_tells_writer_not_to_echo_input():
    from tubeforge.providers.content.prompts import build_content_prompt
    request,_=payload()
    prompt=build_content_prompt(request,template_version=request.prompt_version,max_chars=60000)
    assert "Do not return a request field" in prompt
    assert "Copy ContentPackage.request exactly" not in prompt
