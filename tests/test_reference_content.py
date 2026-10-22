import copy

import pytest
from pydantic import ValidationError

from tubeforge.core.errors import ProviderValidationError
from tubeforge.domain.contracts import ContentPackage, ContentRequest, SourceReference
from tubeforge.host_codex_runner import codex_output_schema
from tubeforge.providers.content.output import unwrap_generation
from tubeforge.providers.content.prompts import build_content_prompt
from tubeforge.providers.fake import FakeContentProvider
from test_reference_shorts import topic_data


def candidate():
    request = ContentRequest(topic="Synthetic geometry test", angle="Test only", target_duration_seconds=35,
                             language="en", audience="test reviewers", aspect_ratio="9:16", prompt_version="m6-content-v7",
                             sources=(SourceReference(source_id="fixture", title="Synthetic test data",
                                                      url="https://example.com/test-fixture",
                                                      excerpt="This is synthetic source text for validation tests only."),))
    legacy = FakeContentProvider().generate_package(request)
    raw = legacy.model_dump(mode="json")
    raw.pop("request")
    raw.pop("scene_plans")
    topic = topic_data()
    raw["script_sections"] = [
        {"section_id": s["scene_id"], "scene_id": s["scene_id"], "narration": s["vo"],
         "claim_ids": ["operator-brief"], "contains_factual_claims": True} for s in topic["scenes"]]
    topic.pop("title")
    topic.pop("sources")
    for scene in topic["scenes"]:
        scene.pop("vo")
    raw["reference_short"] = topic
    request = request.model_copy(update={"prompt_version": "m6-content-v8"})
    return request, {"status": "ready", "package": raw, "reason": None}, legacy


def test_reference_binds_trusted_sources_and_exact_narration():
    request, raw, legacy = candidate()
    result = unwrap_generation(raw, request=request)
    package = ContentPackage.model_validate(result)
    assert [s.vo for s in package.reference_short.scenes] == [s.narration for s in package.script_sections]
    assert str(package.reference_short.sources[0].url) == str(request.sources[0].url)
    assert len(package.scene_plans) == 7
    assert "reference_short" not in legacy.model_dump(mode="json")
    assert ContentPackage.model_validate_json(legacy.model_dump_json()).model_dump_json() == legacy.model_dump_json()


@pytest.mark.parametrize("field,value", [
    ("vo", "This narration was changed outside the canonical script."),
    ("source_ids", ["unknown"]),
    ("scene_id", "out-of-order"),
])
def test_reference_rejects_conflicting_scene_data(field, value):
    request, raw, _ = candidate()
    raw["package"]["reference_short"]["scenes"][1][field] = value
    with pytest.raises((ProviderValidationError, ValidationError)):
        unwrap_generation(raw, request=request)


def test_reference_rejects_forged_attribution():
    request, raw, _ = candidate()
    raw["package"]["reference_short"]["sources"] = [
        {"source_id": "fixture", "name": "Wrong authority", "url": "https://example.com/forged"}]
    with pytest.raises(ProviderValidationError, match="trusted request"):
        unwrap_generation(raw, request=request)


def test_reference_schema_and_prompt_preserve_legacy_boundary():
    import jsonschema
    request, raw, _ = candidate()
    schema = codex_output_schema(envelope=True, reference=True)
    # Packaging fixtures deliberately use one title; pad to the schema's ten.
    raw = copy.deepcopy(raw)
    raw["package"]["metadata"]["title_options"] = [f"Synthetic title {i}" for i in range(10)]
    raw["package"]["hook_options"] = [f"Synthetic hook {i}" for i in range(5)]
    raw["package"]["metadata"]["engagement_comment"] = "Rust or C for new code: which would you bet your job on?"
    package = unwrap_generation(raw, request=request)
    package.pop("request")
    package.pop("scene_plans")
    topic = package["reference_short"]
    topic.pop("title")
    topic.pop("sources")
    for scene in topic["scenes"]:
        scene.pop("vo")
        scene["visual"] = None  # strict model output states every field explicitly
    raw = {"status": "ready", "package": package, "reason": None}
    jsonschema.validate(raw, schema)
    legacy = codex_output_schema(envelope=True)
    assert "reference_short" not in legacy["$defs"]["ContentPackage"]["properties"]
    assert "engagement_comment" not in legacy["$defs"]["VideoMetadata"]["properties"]
    assert "engagement_comment" in schema["$defs"]["VideoMetadata"]["required"]
    prompt = build_content_prompt(request, template_version="m6-content-v8", max_chars=60000)
    assert "reference-short-v1" in prompt
    assert "engagement_comment" in prompt
    assert "8–15" in prompt


def test_reference_contract_requires_exact_approval_sources_and_visuals():
    import hashlib
    import json
    from tubeforge.pipeline.reference_contract import compile_reference_contract
    request, raw, _ = candidate()
    package = ContentPackage.model_validate(unwrap_generation(raw, request=request))
    encoded = package.model_dump_json().encode()
    packet = json.dumps({"schema_version": "1.1", "sources": [
        s.model_dump(mode="json") for s in package.request.sources]}).encode()
    identity = hashlib.sha256(encoded).hexdigest()
    contract = compile_reference_contract(encoded, packet, accepted_script_identity=identity)
    assert contract.topic == package.reference_short
    with pytest.raises(ValueError, match="approved package"):
        compile_reference_contract(encoded, packet, accepted_script_identity=None)
    with pytest.raises(ValueError, match="stale"):
        contract.validate_against(encoded, packet + b" ", accepted_script_identity=identity)
    changed = package.reference_short.model_copy(update={"title": "Unapproved replacement"})
    with pytest.raises(ValueError, match="visuals"):
        contract.model_copy(update={"topic": changed}).validate_against(
            encoded, packet, accepted_script_identity=identity)
    corrupted = json.loads(packet)
    corrupted["sources"][0]["excerpt"] = "Changed evidence"
    with pytest.raises(ValueError, match="source packet differs"):
        compile_reference_contract(encoded, json.dumps(corrupted).encode(), accepted_script_identity=identity)


def test_engagement_comment_must_be_a_clean_question():
    from tubeforge.domain.contracts import VideoMetadata
    base = {"title_options": ["t"], "description": "d"}
    assert VideoMetadata(**base).model_dump(mode="json").get("engagement_comment", "absent") == "absent"
    assert VideoMetadata(**base, engagement_comment="Rust or C: which one?").engagement_comment
    for bad in ("Rust beats C.", "Rust or C? see https://x.test", "Rust or C? #flame", "Rust or C? @someone"):
        with pytest.raises(ValueError):
            VideoMetadata(**base, engagement_comment=bad)
