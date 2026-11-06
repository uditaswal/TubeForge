"""Representative synthetic sizes, not real writer output or quality evidence."""
import json
from pathlib import Path

import pytest

from tubeforge.domain.contracts import ContentPackage, ContentRequest
from tubeforge.providers.content.host_runner_protocol import GenerateShortsScriptRequest, HostRunnerResponse, HostRunnerSuccess


def representative_package(scene_count=60, words_per_scene=36, excerpt='Synthetic source evidence. ' * 500):
    brief = json.loads((Path(__file__).parent / 'fixtures/long_form/planning_contract.json').read_text())['request']
    brief['sources'][0]['excerpt'] = excerpt
    brief['target_duration_seconds'] = 900
    request = ContentRequest.model_validate(brief)
    words = 'Synthetic fixture words demonstrate only serialized payload size and cannot establish factual accuracy narration quality viewer demand source grounding or creative acceptance of any generated video'.split()
    narration = ' '.join(words[i % len(words)] for i in range(words_per_scene)) + '.'
    package = ContentPackage.model_validate(dict(
        schema_version='1.0', request=request,
        claims=[dict(claim_id='synthetic',text='Synthetic claim for envelope testing only.',source_ids=['fixture'],confidence='low',human_review_required=True,review_status='needs_review')],
        script_sections=[dict(section_id=f'section-{i}',scene_id=f'scene-{i}',narration=narration,claim_ids=['synthetic'],contains_factual_claims=True) for i in range(scene_count)],
        scene_plans=[dict(scene_id=f'scene-{i}',visual_type='illustration',search_queries=['synthetic teaching diagram'],fallback_visual='synthetic_fixture',visual_subject='Synthetic subject',visual_purpose='Payload testing only',composition='Native landscape',visual_elements=['Before','After']) for i in range(scene_count)],
        metadata=dict(title_options=[f'Synthetic title {i}' for i in range(10)],description='Synthetic description only.',chapters=[dict(section_id=f'section-{i}',label=f'Chapter {i // 10 + 1}') for i in range(0,scene_count,10)]),
        thumbnail_brief=dict(text_options=['SYNTHETIC TEST'],visual_direction='Fixture only',accessibility_description='Synthetic fixture'),
        hook_options=[f'Synthetic hook option {i}.' for i in range(5)],
    ))
    return request, package


def envelope_sizes(request, package):
    return {
        'request_bytes': len(GenerateShortsScriptRequest(request=request).model_dump_json().encode()),
        'package_bytes': len(package.model_dump_json().encode()),
        'response_bytes': len(HostRunnerResponse(ok=True,result=HostRunnerSuccess(package=package.model_dump(mode='json'))).model_dump_json().encode()),
        'narration_words': sum(len(s.narration.split()) for s in package.script_sections),
    }


@pytest.mark.parametrize('scenes,words', [(30,45),(60,36)])
def test_representative_synthetic_envelopes_fit_existing_byte_limits(scenes,words):
    from tubeforge.host_codex_runner import MAX_MESSAGE_BYTES, MAX_OUTPUT_BYTES, MAX_RESPONSE_BYTES
    from tubeforge.host_claude_runner import MAX_MESSAGE_BYTES as CLAUDE_MESSAGE_BYTES
    request, package = representative_package(scenes,words)
    sizes = envelope_sizes(request,package)
    assert sizes['request_bytes'] < min(MAX_MESSAGE_BYTES, CLAUDE_MESSAGE_BYTES)
    assert sizes['package_bytes'] < MAX_OUTPUT_BYTES
    assert sizes['response_bytes'] < MAX_RESPONSE_BYTES
    assert sizes['narration_words'] == scenes * words


def test_source_character_limit_can_exceed_transport_bytes_for_non_ascii():
    from tubeforge.host_codex_runner import MAX_MESSAGE_BYTES
    request, package = representative_package(excerpt='界' * 24000)
    assert len(request.sources[0].excerpt) == 24000
    assert envelope_sizes(request,package)['request_bytes'] > MAX_MESSAGE_BYTES
