"""M17--M19 explicit, human-authorized optimization lifecycle."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tubeforge.core.config import OptimizationConfig, PublicationPreparationConfig
from tubeforge.core.errors import AmbiguousProviderError, ProviderValidationError
from tubeforge.db.repositories import AnalyticsRepository, ApprovalRepository, OptimizationRepository, PublicationRepository
from tubeforge.domain.contracts import PublishPrivacy, PublishRequest, VideoMetadata
from tubeforge.domain.states import ApprovalGate
from tubeforge.pipeline.performance import identity
from tubeforge.pipeline.publication import render_thumbnail, validate_thumbnail


def approval_identity(*, publication: str, candidate: str, proposal: str, evaluation: str, remote_video: str, expected_title: str, executor_version: str) -> str:
    return identity({"publication": publication, "candidate": candidate, "proposal": proposal, "evaluation": evaluation, "remote_video": remote_video, "expected_title": expected_title, "executor": executor_version})


class OptimizationCandidateService:
    """Generate bounded local candidates only; this service has no publisher dependency."""
    def __init__(self, publications: PublicationRepository, analytics: AnalyticsRepository, store: OptimizationRepository, config: OptimizationConfig, metadata: PublicationPreparationConfig, artifact_root: Path) -> None:
        self.publications, self.analytics, self.store, self.config, self.metadata, self.artifact_root = publications, analytics, store, config, metadata, artifact_root

    def generate(self, proposal_identity: str, *, current_title: str, current_thumbnail_identity: str | None = None) -> list[object]:
        proposal = self.analytics.proposal(proposal_identity)
        if not self.config.candidates.enabled or proposal is None or proposal.status != "GENERATED" or proposal.proposal_type not in {"TITLE", "THUMBNAIL", "TITLE_AND_THUMBNAIL"}: return []
        generation = identity({"proposal": proposal_identity, "evaluation": proposal.evaluation_identity, "title": current_title, "thumbnail": current_thumbnail_identity, "template": self.config.candidates.template_version, "limits": self.config.candidates.model_dump(mode="json")})
        candidate_set = self.store.save_set({"publication_identity": proposal.publication_identity, "proposal_identity": proposal_identity, "evaluation_identity": proposal.evaluation_identity, "generation_identity": generation, "state": "GENERATED", "template_version": self.config.candidates.template_version, "created_at": datetime.now(UTC)})
        values: list[object] = []
        if proposal.proposal_type == "TITLE_AND_THUMBNAIL":
            for number, title in enumerate(self._titles(current_title)[:self.config.candidates.max_thumbnail_candidates]):
                candidate_id = identity({"generation": generation, "type": "TITLE_AND_THUMBNAIL", "title": title, "layout": number})
                path = self.artifact_root / proposal.publication_identity / f"optimization-{candidate_id}.png"; path.parent.mkdir(parents=True, exist_ok=True); temporary = path.with_suffix(".tmp")
                if not path.is_file():
                    render_thumbnail(temporary, thumbnail_identity=candidate_id, title=title, width=self.metadata.thumbnail_width, height=self.metadata.thumbnail_height); validate_thumbnail(temporary, self.metadata); temporary.replace(path)
                values.append(self.store.save_candidate({"candidate_set_id": candidate_set.id, "publication_identity": proposal.publication_identity, "proposal_identity": proposal_identity, "evaluation_identity": proposal.evaluation_identity, "candidate_identity": candidate_id, "candidate_type": "TITLE_AND_THUMBNAIL", "title": title, "thumbnail_path": str(path), "thumbnail_identity": candidate_id, "state": "GENERATED", "evidence_json": json.dumps({"expected_title": current_title, "current_thumbnail_identity": current_thumbnail_identity, "rationale": json.loads(proposal.rationale_json)}, sort_keys=True), "created_at": datetime.now(UTC)}))
            return values
        if proposal.proposal_type in {"TITLE", "TITLE_AND_THUMBNAIL"}:
            for title in self._titles(current_title):
                candidate_id = identity({"generation": generation, "type": "TITLE", "title": title})
                values.append(self.store.save_candidate({"candidate_set_id": candidate_set.id, "publication_identity": proposal.publication_identity, "proposal_identity": proposal_identity, "evaluation_identity": proposal.evaluation_identity, "candidate_identity": candidate_id, "candidate_type": "TITLE", "title": title, "thumbnail_path": None, "thumbnail_identity": None, "state": "GENERATED", "evidence_json": json.dumps({"expected_title": current_title, "rationale": json.loads(proposal.rationale_json)}, sort_keys=True), "created_at": datetime.now(UTC)}))
        if proposal.proposal_type in {"THUMBNAIL", "TITLE_AND_THUMBNAIL"}:
            title = self._titles(current_title)[0]
            for number in range(self.config.candidates.max_thumbnail_candidates):
                candidate_id = identity({"generation": generation, "type": "THUMBNAIL", "title": title, "layout": number})
                path = self.artifact_root / proposal.publication_identity / f"optimization-{candidate_id}.png"; path.parent.mkdir(parents=True, exist_ok=True); temporary = path.with_suffix(".tmp")
                if not path.is_file():
                    render_thumbnail(temporary, thumbnail_identity=candidate_id, title=title, width=self.metadata.thumbnail_width, height=self.metadata.thumbnail_height); validate_thumbnail(temporary, self.metadata); temporary.replace(path)
                values.append(self.store.save_candidate({"candidate_set_id": candidate_set.id, "publication_identity": proposal.publication_identity, "proposal_identity": proposal_identity, "evaluation_identity": proposal.evaluation_identity, "candidate_identity": candidate_id, "candidate_type": "THUMBNAIL", "title": None, "thumbnail_path": str(path), "thumbnail_identity": candidate_id, "state": "GENERATED", "evidence_json": json.dumps({"expected_title": current_title, "current_thumbnail_identity": current_thumbnail_identity, "rationale": json.loads(proposal.rationale_json)}, sort_keys=True), "created_at": datetime.now(UTC)}))
        return values

    def _titles(self, current: str) -> list[str]:
        variants = [f"{current}: What You Need to Know", f"The Truth About {current}", f"{current} Explained"]
        unique: list[str] = []
        for title in variants:
            title = " ".join(title.split())
            normalized = "".join(char.casefold() for char in title if char.isalnum())
            if title and len(title) <= self.metadata.title_max_length and not any(ord(char) < 32 for char in title) and normalized not in {"".join(char.casefold() for char in value if char.isalnum()) for value in unique}: unique.append(title)
            if len(unique) == self.config.candidates.max_title_candidates: break
        return unique


class OptimizationExecutor:
    """Apply one exact approval after reconciliation; never creates/uploads videos."""
    def __init__(self, publications: PublicationRepository, analytics: AnalyticsRepository, store: OptimizationRepository, approvals: ApprovalRepository, publisher: Any, config: OptimizationConfig) -> None:
        self.publications, self.analytics, self.store, self.approvals, self.publisher, self.config = publications, analytics, store, approvals, publisher, config

    def execute(self, candidate_identity: str, *, cancellation_requested=lambda: False) -> object | None:
        candidate = self.store.candidate(candidate_identity)
        if candidate is None or candidate.state != "SELECTED": return None
        proposal = self.analytics.proposal(candidate.proposal_identity); publication = self.publications.get(candidate.publication_identity)
        if proposal is None or proposal.status != "GENERATED" or publication is None or not publication.remote_video_id or publication.state == "remote_missing": return None
        expected_title = str(json.loads(candidate.evidence_json)["expected_title"])
        approval = approval_identity(publication=publication.publication_identity, candidate=candidate_identity, proposal=candidate.proposal_identity, evaluation=candidate.evaluation_identity, remote_video=str(publication.remote_video_id), expected_title=expected_title, executor_version=self.config.execution.executor_version)
        if self.approvals.approved(publication.job_id, ApprovalGate.OPTIMIZATION, reviewed_identity=approval) is None or cancellation_requested(): return None
        execution_id = identity({"candidate": candidate_identity, "approval": approval, "executor": self.config.execution.executor_version})
        prior = self.store.execution(execution_id)
        snapshot = self.publisher.fetch_publication_snapshot(str(publication.remote_video_id))
        permitted_title = snapshot.title == expected_title or (prior is not None and prior.title_applied and snapshot.title == candidate.title)
        if not snapshot.exists or not permitted_title or self.publisher.authenticated_channel_id() != publication.channel_id: return None
        preview = {"video_id": publication.remote_video_id, "current_title": snapshot.title, "proposed_title": candidate.title, "selected_candidate": candidate_identity, "approval_identity": approval, "operations": ["title" if candidate.title else None, "thumbnail" if candidate.thumbnail_path else None]}
        record = self.store.save_execution({"publication_identity": publication.publication_identity, "candidate_identity": candidate_identity, "execution_identity": execution_id, "approval_identity": approval, "state": "PENDING", "title_applied": False, "thumbnail_applied": False, "prechange_json": json.dumps({"title": snapshot.title, "privacy": snapshot.privacy.value if snapshot.privacy else None, "remote_video_id": publication.remote_video_id, "channel_id": publication.channel_id}, sort_keys=True), "preview_json": json.dumps(preview, sort_keys=True), "error_message": None, "created_at": datetime.now(UTC), "updated_at": datetime.now(UTC)})
        if not self.config.execution.enabled or self.config.execution.dry_run: return self.store.update_execution(execution_id, state="DRY_RUN")
        if candidate.thumbnail_path: validate_thumbnail(Path(candidate.thumbnail_path), PublicationPreparationConfig())
        try:
            if candidate.title and not record.title_applied:
                if snapshot.title != candidate.title:
                    request = PublishRequest(platform="youtube", artifact_path="optimization-no-upload", metadata=VideoMetadata(title_options=(candidate.title,), description=snapshot.description or "", tags=snapshot.tags or ()), privacy=snapshot.privacy or PublishPrivacy.PRIVATE, idempotency_key=execution_id)
                    self.publisher.apply_metadata(str(publication.remote_video_id), request)
                record = self.store.update_execution(execution_id, title_applied=True, state="TITLE_APPLIED")
            if cancellation_requested(): return record
            if candidate.thumbnail_path and not record.thumbnail_applied:
                self.publisher.set_thumbnail(str(publication.remote_video_id), candidate.thumbnail_path)
                record = self.store.update_execution(execution_id, thumbnail_applied=True, state="THUMBNAIL_APPLIED")
        except AmbiguousProviderError:
            return self.store.update_execution(execution_id, state="RECONCILIATION_REQUIRED", error_message="mutation outcome ambiguous")
        except Exception as error:
            return self.store.update_execution(execution_id, state="RETRYABLE", error_message=type(error).__name__)
        complete = self.store.update_execution(execution_id, state="APPLIED")
        self.store.save_experiment({"publication_identity": publication.publication_identity, "candidate_identity": candidate_identity, "execution_identity": execution_id, "proposal_identity": candidate.proposal_identity, "evaluation_identity": candidate.evaluation_identity, "baseline_snapshot_identity": proposal.snapshot_identity, "status": "ACTIVE", "changed_dimensions": candidate.candidate_type.lower(), "experiment_version": self.config.experiment.model_dump_json(), "started_at": datetime.now(UTC)})
        return complete
