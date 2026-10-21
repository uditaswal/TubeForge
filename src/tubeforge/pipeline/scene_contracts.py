"""Versioned, non-executable scene layouts bound to one approved package."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum

from pydantic import Field, model_validator

from tubeforge.domain.contracts import CardRevealCues, ContentPackage, DomainModel, MediaSearchRequest, SourceReference, TeachingRevealCues, TerminalRevealCues
from tubeforge.providers.content.prompts import reject_instruction_spoofing


class SceneLayout(StrEnum):
    TERMINAL = "terminal"
    FLOW_DIAGRAM = "flow_diagram"
    COMPARISON = "comparison"
    TIMELINE = "timeline"
    SOURCE_CARD = "source_card"


EXPLICIT_SCENE_LAYOUTS = frozenset(layout.value for layout in SceneLayout)
SUPPORTED_SOURCE_PACKET_VERSIONS = frozenset({"1.0", "1.1"})


class SceneContractRow(DomainModel):
    scene_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    layout: SceneLayout
    heading: str = Field(min_length=1, max_length=120)
    command: str | None = Field(default=None, min_length=1, max_length=160)
    display_elements: tuple[str, ...] = Field(min_length=1, max_length=4)
    source_ids: tuple[str, ...] = Field(max_length=20)
    terminal_cues: TerminalRevealCues | None = None
    card_cues: CardRevealCues | None = None
    teaching_cues: TeachingRevealCues | None = None

    @model_validator(mode="after")
    def validate_display(self) -> SceneContractRow:
        for name in ("heading", "command", "display_elements"):
            reject_instruction_spoofing(getattr(self, name), field=f"scene_contract.{self.scene_id}.{name}")
        if any(not value.strip() or len(value) > 80 for value in self.display_elements):
            raise ValueError("display elements must be nonblank and at most 80 characters")
        if self.layout in {SceneLayout.FLOW_DIAGRAM, SceneLayout.COMPARISON, SceneLayout.TIMELINE, SceneLayout.SOURCE_CARD} and len(self.display_elements) != 3:
            raise ValueError("flow, comparison, timeline and source-card layouts require exactly three display elements")
        if (self.layout is SceneLayout.TERMINAL) != (self.command is not None):
            raise ValueError("only terminal layouts require a command")
        if self.layout is SceneLayout.TERMINAL and len(self.display_elements) > 3:
            raise ValueError("terminal layout supports at most three output elements")
        if self.terminal_cues is not None and (self.layout is not SceneLayout.TERMINAL or len(self.display_elements) < 2):
            raise ValueError("terminal reveal cues require two terminal display elements")
        if self.terminal_cues is not None and self.terminal_cues.third_word_index is not None and len(self.display_elements) != 3:
            raise ValueError("terminal third reveal requires a third display element")
        if self.card_cues is not None and (self.layout not in {SceneLayout.COMPARISON, SceneLayout.FLOW_DIAGRAM, SceneLayout.TIMELINE} or len(self.display_elements) != 3 or self.terminal_cues is not None):
            raise ValueError("card reveal cues require three comparison, flow diagram, or timeline display elements")
        if self.teaching_cues is not None and (self.layout not in {SceneLayout.FLOW_DIAGRAM, SceneLayout.COMPARISON, SceneLayout.TIMELINE, SceneLayout.SOURCE_CARD} or len(self.display_elements) != 3 or self.terminal_cues is not None or self.card_cues is not None):
            raise ValueError("teaching reveal cues require three non-terminal display elements")
        if self.teaching_cues is not None and self.teaching_cues.comparison_panels_first and self.layout is not SceneLayout.COMPARISON:
            raise ValueError("comparison panel reveal order requires a comparison scene")
        if len(set(self.source_ids)) != len(self.source_ids):
            raise ValueError("scene source IDs must be unique")
        return self


class ScriptBoundSceneContract(DomainModel):
    """A visual overlay bound to accepted script bytes; visuals need separate review."""

    schema_version: str = Field(pattern=r"^1\.0$")
    package_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_packet_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    script_gate_identity: str = Field(pattern=r"^[a-f0-9]{64}$")
    scenes: tuple[SceneContractRow, ...] = Field(min_length=1, max_length=500)

    def validate_against(
        self, package_bytes: bytes, source_packet_bytes: bytes, *, accepted_script_identity: str | None
    ) -> ContentPackage:
        if hashlib.sha256(package_bytes).hexdigest() != self.package_sha256:
            raise ValueError("scene contract package hash is stale")
        if hashlib.sha256(source_packet_bytes).hexdigest() != self.source_packet_sha256:
            raise ValueError("scene contract source packet hash is stale")
        if accepted_script_identity is None or accepted_script_identity != self.package_sha256 or self.script_gate_identity != accepted_script_identity:
            raise ValueError("scene contract does not match the accepted script revision")
        package = ContentPackage.model_validate_json(package_bytes)
        validate_source_packet(package, source_packet_bytes)
        expected = [section.scene_id for section in package.script_sections]
        actual = [scene.scene_id for scene in self.scenes]
        if actual != expected or len(set(actual)) != len(actual):
            raise ValueError("scene contract order must match the approved narration")
        claims = {claim.claim_id: claim for claim in package.claims}
        sources = {source.source_id for source in package.request.sources}
        approved_plans = {scene.scene_id: scene for scene in package.scene_plans}
        for row, section in zip(self.scenes, package.script_sections, strict=True):
            plan = approved_plans[row.scene_id]
            if plan.visual_type in EXPLICIT_SCENE_LAYOUTS:
                expected_layout = SceneLayout(plan.visual_type)
                expected_heading = (
                    (plan.visual_subject or plan.on_screen_text or plan.search_queries[0])
                    if expected_layout is SceneLayout.TERMINAL
                    else (plan.on_screen_text or plan.visual_subject or plan.search_queries[0])
                )
                expected_command = plan.on_screen_text if expected_layout is SceneLayout.TERMINAL else None
                if (
                    row.layout is not expected_layout
                    or row.heading != expected_heading
                    or row.command != expected_command
                    or row.display_elements != plan.visual_elements
                ):
                    raise ValueError(f"scene {row.scene_id} visuals differ from the accepted scene plan")
            if row.terminal_cues != approved_plans[row.scene_id].terminal_cues:
                raise ValueError(f"scene {row.scene_id} reveal cues differ from the accepted script revision")
            if row.card_cues != approved_plans[row.scene_id].card_cues:
                raise ValueError(f"scene {row.scene_id} card cues differ from the accepted script revision")
            if row.teaching_cues != approved_plans[row.scene_id].teaching_cues:
                raise ValueError(f"scene {row.scene_id} teaching cues differ from the accepted script revision")
            cited = {source_id for claim_id in section.claim_ids for source_id in claims[claim_id].source_ids}
            if cited and not row.source_ids:
                raise ValueError(f"scene {row.scene_id} omits its narrated claim sources")
            if not set(row.source_ids) <= cited or not set(row.source_ids) <= sources:
                raise ValueError(f"scene {row.scene_id} cites sources outside its narrated claims")
        return package


def validate_source_packet(package: ContentPackage, source_packet_bytes: bytes) -> None:
    """Verify the exact approved source captures for either renderer contract."""
    packet = json.loads(source_packet_bytes)
    if not isinstance(packet, dict) or packet.get("schema_version") not in SUPPORTED_SOURCE_PACKET_VERSIONS:
        raise ValueError("scene contract requires a versioned source packet")
    packet_sources = packet.get("sources")
    if not isinstance(packet_sources, list):
        raise ValueError("scene contract source packet differs from the approved package")
    packet_references: list[SourceReference] = []
    packet_metadata = {"captured_at", "snapshot_kind", "untrusted", "original_content_sha256"}
    source_fields = set(SourceReference.model_fields)
    for entry in packet_sources:
        if not isinstance(entry, dict) or set(entry) - source_fields - packet_metadata:
            raise ValueError("scene contract source packet differs from the approved package")
        reference = SourceReference.model_validate({key: value for key, value in entry.items() if key in source_fields})
        if reference.content_sha256 and reference.excerpt is not None:
            excerpt_hash = hashlib.sha256(reference.excerpt.encode("utf-8")).hexdigest()
            if reference.content_sha256 != excerpt_hash:
                raise ValueError("scene contract source packet differs from the approved package")
        packet_references.append(reference)
    if len(packet_references) != len(package.request.sources):
        raise ValueError("scene contract source packet differs from the approved package")
    for entry, packet_reference, approved_reference in zip(packet_sources, packet_references, package.request.sources, strict=True):
        # approved_excerpt_snapshot strips only boundary whitespace.
        # A semantically cached package may retain that whitespace; compare
        # against the documented capture transformation, after verifying
        # the packet's exact excerpt hash above. Never normalize its body.
        if entry.get("snapshot_kind") == "approved_excerpt" and approved_reference.excerpt is not None:
            approved_reference = approved_reference.model_copy(
                update={"excerpt": approved_reference.excerpt.strip()}
            )
        # Snapshot integrity hashes may be added while capturing an
        # operator-supplied excerpt; the package retains the original
        # request, where that optional hash can be absent.
        if approved_reference.content_sha256 is None:
            packet_reference = packet_reference.model_copy(update={"content_sha256": None})
        if packet_reference != approved_reference:
            raise ValueError("scene contract source packet differs from the approved package")


def scene_media_request(row: SceneContractRow, *, orientation: str = "portrait") -> MediaSearchRequest:
    """Compile one approved layout into the existing deterministic local provider."""
    return MediaSearchRequest(
        scene_id=row.scene_id,
        queries=(row.heading,),
        visual_type=row.layout.value,
        required_license="licensed",
        orientation=orientation,
        visual_source="generated",
        visual_subject=row.heading,
        visual_purpose=row.heading,
        composition=row.layout.value,
        on_screen_text=row.command or "",
        visual_elements=row.display_elements,
    )


def compile_scene_contract(
    package_bytes: bytes, source_packet_bytes: bytes, *, accepted_script_identity: str | None
) -> ScriptBoundSceneContract | None:
    """Compile new explicit ScenePlans; leave wholly legacy packages unchanged."""
    package = ContentPackage.model_validate_json(package_bytes)
    explicit = [scene.visual_type in EXPLICIT_SCENE_LAYOUTS for scene in package.scene_plans]
    if not any(explicit):
        return None
    if not all(explicit):
        raise ValueError("explicit and legacy scene layouts cannot be mixed in one package")
    if accepted_script_identity is None:
        raise ValueError("explicit scene layouts require an exact accepted script identity")
    planned = {scene.scene_id: scene for scene in package.scene_plans}
    claims = {claim.claim_id: claim for claim in package.claims}
    rows: list[SceneContractRow] = []
    for section in package.script_sections:
        scene = planned[section.scene_id]
        layout = SceneLayout(scene.visual_type)
        sources = tuple(dict.fromkeys(
            source_id for claim_id in section.claim_ids for source_id in claims[claim_id].source_ids
        ))
        rows.append(SceneContractRow(
            scene_id=scene.scene_id,
            layout=layout,
            heading=(scene.visual_subject or scene.on_screen_text or scene.search_queries[0]) if layout is SceneLayout.TERMINAL else (scene.on_screen_text or scene.visual_subject or scene.search_queries[0]),
            command=scene.on_screen_text if layout is SceneLayout.TERMINAL else None,
            display_elements=scene.visual_elements,
            source_ids=sources,
            terminal_cues=scene.terminal_cues,
            card_cues=scene.card_cues,
            teaching_cues=scene.teaching_cues,
        ))
    contract = ScriptBoundSceneContract(
        schema_version="1.0",
        package_sha256=hashlib.sha256(package_bytes).hexdigest(),
        source_packet_sha256=hashlib.sha256(source_packet_bytes).hexdigest(),
        script_gate_identity=accepted_script_identity,
        scenes=tuple(rows),
    )
    contract.validate_against(package_bytes, source_packet_bytes, accepted_script_identity=accepted_script_identity)
    return contract
