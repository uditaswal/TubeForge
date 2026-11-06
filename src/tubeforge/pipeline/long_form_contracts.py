"""Long-form contract verification without production admission or approvals."""
from __future__ import annotations

import hashlib

from tubeforge.domain.contracts import ContentPackage
from tubeforge.domain.long_form import LongFormPlanningContract
from tubeforge.pipeline.scene_contracts import validate_source_packet


def validate_long_form_package(
    planning: LongFormPlanningContract,
    package_bytes: bytes,
    source_packet_bytes: bytes,
    *,
    accepted_script_identity: str | None,
    reference_snapshot_bytes: bytes | None = None,
) -> ContentPackage:
    """Check exact evidence and an existing gate identity; never grant approval.

    The caller must obtain accepted_script_identity from the durable approval
    repository, as with the existing scene contract. No identity is synthesized
    here. Packet comparison delegates to the existing provenance validator.
    """
    package_hash = hashlib.sha256(package_bytes).hexdigest()
    if accepted_script_identity is None or package_hash != accepted_script_identity:
        raise ValueError("long-form package does not match the accepted script revision")
    if hashlib.sha256(source_packet_bytes).hexdigest() != planning.source_packet_sha256:
        raise ValueError("long-form source packet hash is stale")
    if planning.reference_snapshot_sha256 is not None:
        if reference_snapshot_bytes is None:
            raise ValueError("long-form reference snapshot hash is stale")
        from tubeforge.pipeline.long_form_reference import validate_planned_reference
        validate_planned_reference(planning, reference_snapshot_bytes)
    elif reference_snapshot_bytes is not None:
        raise ValueError("long-form reference snapshot must be bound in the plan")
    package = ContentPackage.model_validate_json(package_bytes)
    if package.request != planning.request:
        raise ValueError("long-form package differs from the canonical brief")
    validate_source_packet(package, source_packet_bytes)
    if tuple(s.section_id for s in package.script_sections) != planning.section_ids:
        raise ValueError("long-form package section order differs from chapter inventory")
    if tuple(s.scene_id for s in package.scene_plans) != tuple(s.scene_id for s in package.script_sections):
        raise ValueError("long-form scenes must match ordered narration exactly once")
    expected_chapters = tuple((c.section_ids[0], c.title) for c in planning.chapters)
    if tuple((c.section_id, c.label) for c in package.metadata.chapters) != expected_chapters:
        raise ValueError("long-form package chapter boundaries or labels differ from plan")
    cited = {source for claim in package.claims for source in claim.source_ids}
    if cited != set(planning.cited_source_ids):
        raise ValueError("long-form package citations differ from plan")
    return package
