"""Resolve an exact Day-review decision and its final disclosure checkpoint."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from tubeforge.db.models import ArtifactRecord, PublishingAssetRecord, TopicRecord
from tubeforge.domain.states import JobState


def reviewed_youtube_disclosure(session: Session, asset: PublishingAssetRecord, reviews: object) -> dict[str, object]:
    """Return only a current, checksum-bound operator disclosure decision.

    The generated record contains evidence; Day review stores the operator's
    boolean separately. Both must agree with the current final and review.
    """
    if not asset.source_job_id:
        raise ValueError("reviewed disclosure record is missing for this final")
    topics = list(session.scalars(select(TopicRecord).where(TopicRecord.generation_job_id == asset.source_job_id)))
    active = []
    for topic in topics:
        try:
            options = json.loads(topic.options_json)
        except (TypeError, ValueError):
            continue
        if options.get("batch_plan") and not options.get("batch_history"):
            active.append(topic)
    if len(active) != 1:
        raise ValueError("this final needs one current Day-review approval")
    snapshot = reviews._snapshot(session, active[0])
    disclosure = snapshot.get("disclosure") or {}
    if (not snapshot.get("available") or not snapshot.get("qa_ok")
            or snapshot.get("state") not in {"approved", "ready"}
            or snapshot.get("decision") != "approved"
            or snapshot.get("checksum") != asset.sha256
            or disclosure.get("reviewed_identity") != snapshot.get("reviewed_identity")
            or disclosure.get("final_checksum") != asset.sha256
            or disclosure.get("eligible") is not True
            or type(disclosure.get("platform_disclosure_required")) is not bool):
        raise ValueError("current Day-review approval and reviewed disclosure are required for this final")
    artifact = session.scalar(select(ArtifactRecord).where(
        ArtifactRecord.job_id == asset.source_job_id,
        ArtifactRecord.stage == JobState.FINAL_RENDERING.value,
        ArtifactRecord.name == "disclosure_record",
    ))
    if artifact is None:
        raise ValueError("final disclosure record is missing")
    try:
        path = Path(artifact.path)
        root = reviews.exports.artifact_root
        if path.is_symlink() or not path.resolve(strict=True).is_relative_to(root) or path.stat().st_size > 2_000_000:
            raise ValueError("invalid disclosure path")
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != artifact.checksum_sha256:
            raise ValueError("disclosure checkpoint changed")
        generated = json.loads(content)
        if (not isinstance(generated, dict) or generated.get("job_id") != asset.source_job_id
                or generated.get("final_checksum") != asset.sha256
                or generated.get("evidence_identity") != disclosure.get("evidence_identity")):
            raise ValueError("disclosure evidence does not match the reviewed final")
    except (OSError, ValueError, TypeError) as error:
        raise ValueError("final disclosure record is missing, changed, or does not match the review") from error
    return {
        "contains_synthetic_media": disclosure["platform_disclosure_required"],
        "reviewed_identity": snapshot["reviewed_identity"],
        "evidence_identity": disclosure["evidence_identity"],
        "record_sha256": artifact.checksum_sha256,
    }
