"""Compile only the exact approved reference scene package and source packet."""
from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import Field

from tubeforge.domain.contracts import ContentPackage, DomainModel
from tubeforge.pipeline.scene_contracts import validate_source_packet
from tubeforge.rendering.shorts.schema import ShortsTopic


class ReferenceContract(DomainModel):
    schema_version: Literal["reference-contract-v1"] = "reference-contract-v1"
    package_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_packet_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    script_gate_identity: str = Field(pattern=r"^[a-f0-9]{64}$")
    topic: ShortsTopic

    def validate_against(self, package_bytes: bytes, source_packet_bytes: bytes,
                         *, accepted_script_identity: str | None) -> ContentPackage:
        package_hash = hashlib.sha256(package_bytes).hexdigest()
        if self.package_sha256 != package_hash or accepted_script_identity != package_hash or self.script_gate_identity != package_hash:
            raise ValueError("reference contract differs from exact approved package")
        if self.source_packet_sha256 != hashlib.sha256(source_packet_bytes).hexdigest():
            raise ValueError("reference source packet hash is stale")
        package = ContentPackage.model_validate_json(package_bytes)
        validate_source_packet(package, source_packet_bytes)
        if package.reference_short != self.topic:
            raise ValueError("reference visuals differ from exact approved package")
        return package


def compile_reference_contract(package_bytes: bytes, source_packet_bytes: bytes,
                               *, accepted_script_identity: str | None) -> ReferenceContract:
    package = ContentPackage.model_validate_json(package_bytes)
    if package.reference_short is None:
        raise ValueError("package has no reference scene profile")
    contract = ReferenceContract(package_sha256=hashlib.sha256(package_bytes).hexdigest(),
                                 source_packet_sha256=hashlib.sha256(source_packet_bytes).hexdigest(),
                                 script_gate_identity=accepted_script_identity or "0" * 64,
                                 topic=package.reference_short)
    contract.validate_against(package_bytes, source_packet_bytes, accepted_script_identity=accepted_script_identity)
    return contract
