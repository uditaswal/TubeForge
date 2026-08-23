"""Focused M17--M19 safety tests using the deterministic YouTube fake."""
from datetime import UTC, datetime
from pathlib import Path

from tubeforge.core.config import DatabaseConfig, OptimizationConfig, PublicationPreparationConfig
from tubeforge.db.models import Base, OptimizationExperimentRecord
from tubeforge.db.repositories import AnalyticsRepository, ApprovalRepository, OptimizationRepository, PublicationRepository
from tubeforge.db.session import create_database
from tubeforge.domain.states import ApprovalGate
from tubeforge.pipeline.optimization import OptimizationCandidateService, OptimizationExecutor, approval_identity
from tubeforge.providers.fake import FakeYouTubePublisher


def setup(tmp_path):
    database = create_database(DatabaseConfig(url=f"sqlite:///{tmp_path / 'opt.db'}")); Base.metadata.create_all(database.engine)
    pubs = PublicationRepository(database.session_factory); analytics = AnalyticsRepository(database.session_factory); store = OptimizationRepository(database.session_factory); approvals = ApprovalRepository(database.session_factory)
    pubs.ensure("job", "pub", "package", "channel", {}); pubs.update("pub", state="healthy", remote_video_id="video")
    analytics.save_evaluation({"publication_identity":"pub","evaluation_identity":"eval","snapshot_identities_json":"[]","evaluator_version":"v","dimensions_json":"{}","derived_metrics_json":"{}","recommendations_json":"[]","created_at":datetime.now(UTC)})
    analytics.save_proposal({"publication_identity":"pub","remote_video_id":"video","evaluation_identity":"eval","snapshot_identity":"snapshot","proposal_identity":"proposal","proposal_type":"TITLE","status":"GENERATED","rationale_json":"{}","proposal_version":"v","created_at":datetime.now(UTC)})
    return database, pubs, analytics, store, approvals


def candidate_service(pubs, analytics, store, tmp_path):
    return OptimizationCandidateService(pubs, analytics, store, OptimizationConfig(), PublicationPreparationConfig(), tmp_path / "artifacts")


def test_bounded_deterministic_candidates_and_non_mutating_proposals(tmp_path) -> None:
    db, pubs, analytics, store, approvals = setup(tmp_path)
    try:
        service = candidate_service(pubs, analytics, store, tmp_path)
        first = service.generate("proposal", current_title="Rain Explained")
        second = service.generate("proposal", current_title="Rain Explained")
        assert 1 <= len(first) <= 3 and [x.candidate_identity for x in first] == [x.candidate_identity for x in second]
        analytics.save_proposal({"publication_identity":"pub","remote_video_id":"video","evaluation_identity":"eval","snapshot_identity":"snapshot","proposal_identity":"no-change","proposal_type":"NO_CHANGE","status":"GENERATED","rationale_json":"{}","proposal_version":"v","created_at":datetime.now(UTC)})
        assert service.generate("no-change", current_title="Rain") == []
    finally: db.dispose()


def test_thumbnail_candidates_are_bounded_and_validated(tmp_path) -> None:
    db, pubs, analytics, store, approvals = setup(tmp_path)
    try:
        analytics.save_proposal({"publication_identity":"pub","remote_video_id":"video","evaluation_identity":"eval","snapshot_identity":"snapshot","proposal_identity":"thumbnail","proposal_type":"THUMBNAIL","status":"GENERATED","rationale_json":"{}","proposal_version":"v","created_at":datetime.now(UTC)})
        generated = candidate_service(pubs, analytics, store, tmp_path).generate("thumbnail", current_title="Rain Explained", current_thumbnail_identity="old")
        assert len(generated) == 2 and all(Path(item.thumbnail_path).is_file() for item in generated)
    finally: db.dispose()


def test_execution_requires_exact_approval_and_dry_run_never_mutates(tmp_path) -> None:
    db, pubs, analytics, store, approvals = setup(tmp_path)
    try:
        candidate = candidate_service(pubs, analytics, store, tmp_path).generate("proposal", current_title="Rain Explained")[0]; store.select(candidate.candidate_identity)
        provider = FakeYouTubePublisher(channel_id="channel"); provider.videos["video"] = {"title":"Rain Explained", "description":"Description", "tags":("one",), "privacy":"private"}
        executor = OptimizationExecutor(pubs, analytics, store, approvals, provider, OptimizationConfig())
        assert executor.execute(candidate.candidate_identity) is None and provider.metadata_calls == provider.thumbnail_calls == provider.create_calls == 0
        binding = approval_identity(publication="pub", candidate=candidate.candidate_identity, proposal="proposal", evaluation="eval", remote_video="video", expected_title="Rain Explained", executor_version="m18-v1")
        approvals.record("approved", "job", ApprovalGate.OPTIMIZATION, reviewed_identity=binding)
        preview = executor.execute(candidate.candidate_identity)
        assert preview.state == "DRY_RUN" and provider.metadata_calls == provider.thumbnail_calls == provider.create_calls == 0
    finally: db.dispose()


def test_execution_preserves_metadata_is_idempotent_and_creates_experiment(tmp_path) -> None:
    db, pubs, analytics, store, approvals = setup(tmp_path)
    try:
        candidate = candidate_service(pubs, analytics, store, tmp_path).generate("proposal", current_title="Rain Explained")[0]; store.select(candidate.candidate_identity)
        provider = FakeYouTubePublisher(channel_id="channel"); provider.videos["video"] = {"title":"Rain Explained", "description":"Description", "tags":("one",), "privacy":"private"}
        config = OptimizationConfig.model_validate({"execution":{"enabled":True,"dry_run":False}})
        binding = approval_identity(publication="pub", candidate=candidate.candidate_identity, proposal="proposal", evaluation="eval", remote_video="video", expected_title="Rain Explained", executor_version="m18-v1")
        approvals.record("approved", "job", ApprovalGate.OPTIMIZATION, reviewed_identity=binding)
        executor = OptimizationExecutor(pubs, analytics, store, approvals, provider, config)
        first = executor.execute(candidate.candidate_identity); second = executor.execute(candidate.candidate_identity)
        assert first.state == second.state == "APPLIED" and provider.metadata_calls == 1 and provider.create_calls == provider.thumbnail_calls == 0
        assert provider.videos["video"]["metadata"]["description"] == "Description"
        with db.session_factory() as session: assert session.query(OptimizationExperimentRecord).count() == 1
    finally: db.dispose()


def test_manual_remote_drift_blocks_mutation(tmp_path) -> None:
    db, pubs, analytics, store, approvals = setup(tmp_path)
    try:
        candidate = candidate_service(pubs, analytics, store, tmp_path).generate("proposal", current_title="Rain Explained")[0]; store.select(candidate.candidate_identity)
        provider = FakeYouTubePublisher(channel_id="channel"); provider.videos["video"] = {"title":"Manual Better Title", "description":"Description", "privacy":"private"}
        config = OptimizationConfig.model_validate({"execution":{"enabled":True,"dry_run":False}})
        binding = approval_identity(publication="pub", candidate=candidate.candidate_identity, proposal="proposal", evaluation="eval", remote_video="video", expected_title="Rain Explained", executor_version="m18-v1")
        approvals.record("approved", "job", ApprovalGate.OPTIMIZATION, reviewed_identity=binding)
        assert OptimizationExecutor(pubs, analytics, store, approvals, provider, config).execute(candidate.candidate_identity) is None
        assert provider.metadata_calls == provider.thumbnail_calls == provider.create_calls == 0
    finally: db.dispose()
