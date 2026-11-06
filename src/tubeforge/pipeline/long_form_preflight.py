"""Combined local contract audit; no provider, render, approval or publication."""
from __future__ import annotations

import hashlib

from tubeforge.domain.contracts import generation_request_content
from tubeforge.domain.long_form import LongFormPlanningContract, LongFormTimingManifest
from tubeforge.domain.long_form_budget import LongFormCallLedger
from tubeforge.domain.reference_video import ReferenceIntakeRequest
from tubeforge.pipeline.long_form_budget import long_form_brief_identity, summarize_usage
from tubeforge.pipeline.long_form_chapters import export_chapters
from tubeforge.pipeline.long_form_context import build_source_context
from tubeforge.pipeline.long_form_contracts import validate_long_form_package
from tubeforge.pipeline.long_form_reference import validate_planned_reference, reference_content_identity, reference_cache_key
from tubeforge.providers.content.host_runner_protocol import GenerateShortsScriptRequest, encode_request


def audit_reference_package(planning: LongFormPlanningContract, *, intake: ReferenceIntakeRequest,
                            package_bytes: bytes, source_packet_bytes: bytes, reference_snapshot_bytes: bytes,
                            accepted_script_identity: str | None, ledger: LongFormCallLedger,
                            timing: LongFormTimingManifest, audio_sha256: str, artifact_sha256: str,
                            maximum_context_bytes: int = 24000) -> dict:
    """Audit supplied measurements/evidence, never assert that media was watched.

    The caller obtains approval identity, checkpoint and media hashes from durable
    job repositories. This adapter cannot grant approvals or prove supplied probe
    measurements really ran. No production operation registers this helper yet.
    """
    snapshot = validate_planned_reference(planning,reference_snapshot_bytes,intake_request=intake)
    package = validate_long_form_package(planning,package_bytes,source_packet_bytes,
                                        accepted_script_identity=accepted_script_identity,
                                        reference_snapshot_bytes=reference_snapshot_bytes)
    if ledger.brief_sha256 != long_form_brief_identity(planning,reference=snapshot):
        raise ValueError('call ledger belongs to a different reference brief')
    if any(c.state == 'pending' for c in ledger.calls):
        raise ValueError('pending writer call must be reconciled before final audit')
    if not any(c.stage in {'draft','repair'} and c.state == 'succeeded' for c in ledger.calls):
        raise ValueError('reference audit requires a recorded successful narration call')
    context = build_source_context(planning,source_packet_bytes,maximum_bytes=maximum_context_bytes)
    request_bytes = encode_request(GenerateShortsScriptRequest(request=generation_request_content(package.request)))
    package_hash = hashlib.sha256(package_bytes).hexdigest()
    chapters = export_chapters(planning,timing,package_sha256=package_hash,audio_sha256=audio_sha256,artifact_sha256=artifact_sha256)
    return dict(scope='local-contract-audit-v1',package_sha256=package_hash,
                reference_content_sha256=reference_content_identity(snapshot),
                reference_cache_key=reference_cache_key(intake,snapshot),
                source_context_sha256=hashlib.sha256(context).hexdigest(),source_context_bytes=len(context),
                runner_request_bytes=len(request_bytes),chapters=chapters,usage=summarize_usage(ledger))
