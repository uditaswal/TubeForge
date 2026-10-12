from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from tubeforge.domain.contracts import (
    AssetCandidate,
    CitedClaim,
    ClaimReviewStatus,
    ConfidenceLevel,
    ContentPackage,
    ContentRequest,
    PublishPrivacy,
    PublishRequest,
    ScenePlan,
    ScriptSection,
    SourceReference,
    ThumbnailBrief,
    VideoMetadata,
    video_plan_from_package,
)


def content_request() -> ContentRequest:
    return ContentRequest(
        topic="How rain forms",
        angle="A concise science explainer",
        target_duration_seconds=120,
        language="en-IN",
        audience="general",
        prompt_version="content-v1",
        sources=(
            SourceReference(
                source_id="S1",
                url="https://example.com/rain",
                title="Rain science",
            ),
        ),
    )


def metadata() -> VideoMetadata:
    return VideoMetadata(title_options=("How rain forms",), description="An explainer.")


def test_content_package_validates_cross_references() -> None:
    package = ContentPackage(
        schema_version="1.0",
        request=content_request(),
        claims=(
            CitedClaim(
                claim_id="C1",
                text="Water vapour condenses into droplets.",
                source_ids=("S1",),
                confidence=ConfidenceLevel.HIGH,
                review_status=ClaimReviewStatus.VERIFIED,
                human_review_required=False,
            ),
        ),
        script_sections=(
            ScriptSection(
                section_id="SEG-1",
                narration="Water vapour condenses into droplets.",
                scene_id="SC-1",
                claim_ids=("C1",),
                contains_factual_claims=True,
            ),
        ),
        scene_plans=(
            ScenePlan(
                scene_id="SC-1",
                visual_type="diagram",
                search_queries=("rain formation diagram",),
                fallback_visual="text_card",
            ),
        ),
        metadata=metadata(),
        thumbnail_brief=ThumbnailBrief(
            text_options=("RAIN EXPLAINED",),
            visual_direction="Cloud and rain diagram",
            accessibility_description="Cloud releasing rain over a landscape",
        ),
    )

    assert package.claims[0].source_ids == ("S1",)
    plan = video_plan_from_package(package)
    assert plan.scenes[0].visual_subject == "rain formation diagram"
    assert plan.scenes[0].visual_purpose == "diagram"
    assert plan.scenes[0].search_queries == ("rain formation diagram",)
    specified = package.scene_plans[0].model_copy(update={
        "visual_subject": "Water vapour and droplets",
        "visual_purpose": "Show condensation",
        "composition": "layer diagram",
        "visual_elements": ("water vapour", "droplets"),
    })
    directed = video_plan_from_package(package.model_copy(update={"scene_plans": (specified,)}))
    assert directed.scenes[0].visual_subject == "Water vapour and droplets"
    assert directed.scenes[0].visual_elements == ("water vapour", "droplets")


def test_contract_rejects_unknown_source_and_unsupported_factual_section() -> None:
    with pytest.raises(ValidationError, match="unknown source"):
        ContentPackage(
            schema_version="1.0",
            request=content_request(),
            claims=(
                CitedClaim(
                    claim_id="C1",
                    text="A claim",
                    source_ids=("missing",),
                    confidence=ConfidenceLevel.HIGH,
                    review_status=ClaimReviewStatus.VERIFIED,
                    human_review_required=False,
                ),
            ),
            script_sections=(ScriptSection(section_id="SEG-1", narration="A claim", scene_id="SC-1"),),
            scene_plans=(ScenePlan(scene_id="SC-1", visual_type="card", search_queries=("card",), fallback_visual="text_card"),),
            metadata=metadata(),
            thumbnail_brief=ThumbnailBrief(text_options=("RAIN",), visual_direction="diagram", accessibility_description="diagram"),
        )

    with pytest.raises(ValidationError, match="factual script sections"):
        ScriptSection(
            section_id="SEG-1",
            narration="A factual statement",
            scene_id="SC-1",
            contains_factual_claims=True,
        )


def test_low_confidence_claim_requires_human_review() -> None:
    with pytest.raises(ValidationError, match="low-confidence"):
        CitedClaim(
            claim_id="C1",
            text="An uncertain claim",
            source_ids=("S1",),
            confidence=ConfidenceLevel.LOW,
            review_status=ClaimReviewStatus.NEEDS_REVIEW,
            human_review_required=False,
        )


def test_public_publish_request_requires_explicit_approval() -> None:
    with pytest.raises(ValidationError, match="explicit public approval"):
        PublishRequest(
            platform="youtube",
            artifact_path="final.mp4",
            metadata=metadata(),
            privacy=PublishPrivacy.PUBLIC,
            idempotency_key="publish-1",
        )

    request = PublishRequest(
        platform="youtube",
        artifact_path="final.mp4",
        metadata=metadata(),
        privacy=PublishPrivacy.PUBLIC,
        idempotency_key="publish-1",
        public_publish_approval_id="approval-42",
    )
    assert request.public_publish_approval_id == "approval-42"


def test_asset_candidate_requires_rights_provenance() -> None:
    asset = AssetCandidate(
        provider_asset_id="asset-1",
        source_url="https://example.com/asset",
        license_name="CC BY 4.0",
        retrieved_at=datetime.now(UTC),
    )
    assert asset.license_name == "CC BY 4.0"
