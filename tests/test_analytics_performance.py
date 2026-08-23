"""Focused M15/M16 offline tests; no Google calls or YouTube mutations."""

from datetime import UTC, datetime, timedelta
import json

from tubeforge.core.config import AnalyticsConfig, DatabaseConfig, PerformanceConfig
from tubeforge.db.models import Base
from tubeforge.db.repositories import AnalyticsRepository, PublicationRepository
from tubeforge.db.session import create_database
from tubeforge.pipeline.performance import AnalyticsIngestionService, PerformanceEvaluator, PerformanceService
from tubeforge.providers.fake import FakeYouTubePublisher


def metrics(*, views=1000, impressions=1000, ctr=2.0, retention=60.0):
    available = lambda value: {"value": value, "availability": "available"}
    return {"views": available(views), "estimatedMinutesWatched": available(100), "averageViewDuration": available(120), "averageViewPercentage": available(retention), "impressions": available(impressions), "impressionsClickThroughRate": available(ctr), "likes": available(50), "comments": available(10), "subscribersGained": available(5), "subscribersLost": available(1)}


def stores(tmp_path):
    database = create_database(DatabaseConfig(url=f"sqlite:///{tmp_path / 'analytics.db'}")); Base.metadata.create_all(database.engine)
    publications = PublicationRepository(database.session_factory); analytics = AnalyticsRepository(database.session_factory)
    publications.ensure("job-1", "publication-1", "package-1", "channel-1", {})
    publications.update("publication-1", state="healthy", remote_video_id="video-1", created_at=datetime.now(UTC) - timedelta(days=3))
    return database, publications, analytics


def test_ingestion_preserves_zero_and_missing_semantics_is_idempotent_and_read_only(tmp_path) -> None:
    database, publications, analytics = stores(tmp_path)
    try:
        provider = FakeYouTubePublisher(); provider.videos["video-1"] = {"analytics": metrics(views=0, impressions=0)}
        service = AnalyticsIngestionService(publications, analytics, provider, AnalyticsConfig(initial_delay_hours=0))
        first = service.collect("publication-1"); second = service.collect("publication-1")
        rows = analytics.snapshots("publication-1")
        assert first.id == second.id and len(rows) == 1 and rows[0].views == rows[0].impressions == 0
        payload = json.loads(rows[0].metrics_json)
        assert payload["views"]["value"] == 0 and payload["watch_time_seconds"]["value"] == 6000
        assert provider.analytics_calls == 2 and provider.create_calls == provider.metadata_calls == provider.thumbnail_calls == 0
        assert AnalyticsIngestionService(publications, analytics, provider, AnalyticsConfig(enabled=False)).collect("publication-1") is None
    finally: database.dispose()


def test_evaluator_rules_distinguish_insufficient_packaging_and_retention() -> None:
    evaluator = PerformanceEvaluator(PerformanceConfig(min_views_for_retention=100, min_impressions_for_ctr=500))
    low_sample = evaluator.evaluate({"views": {"value": 20, "availability": "available"}, "impressions": {"value": 20, "availability": "available"}, "impressions_ctr": {"value": 1, "availability": "available"}}, publication_age_days=1)
    assert low_sample.dimensions["discovery"]["state"] == "INSUFFICIENT_DATA" and low_sample.recommendations[0]["action_type"] == "NO_CHANGE"
    packaging = evaluator.evaluate({"views": {"value": 1000, "availability": "available"}, "impressions": {"value": 2000, "availability": "available"}, "impressions_ctr": {"value": 2, "availability": "available"}, "average_percentage_viewed": {"value": 60, "availability": "available"}}, publication_age_days=2)
    assert packaging.dimensions["discovery"]["state"] == "WEAK" and packaging.recommendations[0]["action_type"] == "TITLE_AND_THUMBNAIL"
    opening = evaluator.evaluate({"views": {"value": 1000, "availability": "available"}, "impressions": {"value": 2000, "availability": "available"}, "impressions_ctr": {"value": 7, "availability": "available"}, "average_percentage_viewed": {"value": 20, "availability": "available"}}, publication_age_days=2)
    assert opening.dimensions["retention"]["state"] == "WEAK" and opening.recommendations[0]["action_type"] == "CONTENT_LEARNING"


def test_evaluation_and_proposal_are_durable_and_idempotent(tmp_path) -> None:
    database, publications, analytics = stores(tmp_path)
    try:
        provider = FakeYouTubePublisher(); provider.videos["video-1"] = {"analytics": metrics()}
        AnalyticsIngestionService(publications, analytics, provider, AnalyticsConfig(initial_delay_hours=0)).collect("publication-1")
        service = PerformanceService(publications, analytics, PerformanceConfig())
        first = service.evaluate("publication-1"); second = service.evaluate("publication-1")
        assert first.evaluation_identity == second.evaluation_identity
        with database.session_factory() as session:
            from tubeforge.db.models import OptimizationProposalRecord, PerformanceEvaluationRecord
            assert session.query(PerformanceEvaluationRecord).count() == 1
            proposal = session.query(OptimizationProposalRecord).one()
            assert proposal.status == "GENERATED" and proposal.evaluation_identity == first.evaluation_identity and proposal.snapshot_identity
    finally: database.dispose()
