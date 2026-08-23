"""M20--M23 offline learning coverage; no provider mutations."""
from datetime import UTC, datetime, timedelta
import json
from types import SimpleNamespace

from tubeforge.core.config import DatabaseConfig, LearningConfig
from tubeforge.db.models import Base, ExperimentOutcomeRecord, LearningEventRecord, NextVideoBriefRecord
from tubeforge.db.repositories import AnalyticsRepository, LearningRepository, OptimizationRepository, PublicationRepository
from tubeforge.db.session import create_database
from tubeforge.pipeline.learning import ChannelLearningService, ExperimentEvaluationService

def metric(value): return {"value": value, "availability": "available"}
def snapshot(analytics, publication, channel, name, observed, views, impressions=1000):
    return analytics.save_snapshot({"publication_identity": publication, "remote_video_id": publication + "-video", "channel_id": channel, "snapshot_identity": name, "report_start": observed - timedelta(days=2), "report_end": observed, "observed_at": observed, "status": "COMPLETE", "views": views, "impressions": impressions, "metrics_json": json.dumps({"views": metric(views), "impressions": metric(impressions), "watch_time_seconds": metric(views * 60), "likes": metric(views // 10)}), "provenance_json": "{}", "created_at": observed})
def stores(tmp_path):
    db = create_database(DatabaseConfig(url=f"sqlite:///{tmp_path / 'learning.db'}")); Base.metadata.create_all(db.engine)
    return db, PublicationRepository(db.session_factory), AnalyticsRepository(db.session_factory), OptimizationRepository(db.session_factory), LearningRepository(db.session_factory)

def test_experiment_outcome_is_duration_normalized_idempotent_and_creates_event(tmp_path):
    db, pubs, analytics, experiments, learning = stores(tmp_path)
    try:
        now = datetime.now(UTC); pubs.ensure("job", "pub", "pkg", "channel", {}); pubs.update("pub", state="healthy", remote_video_id="video")
        snapshot(analytics, "pub", "channel", "before", now - timedelta(days=5), 200)
        experiments.save_experiment({"publication_identity":"pub", "candidate_identity":"candidate", "execution_identity":"execution", "proposal_identity":"proposal", "evaluation_identity":"evaluation", "baseline_snapshot_identity":"before", "status":"ACTIVE", "changed_dimensions":"title", "experiment_version":"m19", "started_at":now - timedelta(days=3)})
        snapshot(analytics, "pub", "channel", "after", now - timedelta(days=1), 500)
        service = ExperimentEvaluationService(analytics, experiments, pubs, learning, LearningConfig(minimum_post_hours=24, minimum_views=100))
        first, second = service.evaluate("execution", now=now), service.evaluate("execution", now=now)
        assert first.outcome == second.outcome == "IMPROVED"
        assert json.loads(first.evidence_json)["duration_normalized"] is True
        with db.session_factory() as session: assert session.query(ExperimentOutcomeRecord).count() == session.query(LearningEventRecord).count() == 1
    finally: db.dispose()

def test_experiment_handles_unavailable_and_insufficient_data(tmp_path):
    db, pubs, analytics, experiments, learning = stores(tmp_path)
    try:
        now = datetime.now(UTC); pubs.ensure("job", "pub", "pkg", "channel", {}); pubs.update("pub", state="healthy", remote_video_id="video")
        experiments.save_experiment({"publication_identity":"pub", "candidate_identity":"candidate", "execution_identity":"missing", "proposal_identity":"proposal", "evaluation_identity":"evaluation", "baseline_snapshot_identity":None, "status":"ACTIVE", "changed_dimensions":"title", "experiment_version":"m19", "started_at":now - timedelta(days=3)})
        assert ExperimentEvaluationService(analytics, experiments, pubs, learning, LearningConfig()).evaluate("missing", now=now).outcome == "UNAVAILABLE"
        snapshot(analytics, "pub", "channel", "before", now - timedelta(days=3), 10); experiments.save_experiment({"publication_identity":"pub", "candidate_identity":"candidate", "execution_identity":"low", "proposal_identity":"proposal", "evaluation_identity":"evaluation", "baseline_snapshot_identity":"before", "status":"ACTIVE", "changed_dimensions":"title", "experiment_version":"m19", "started_at":now - timedelta(hours=2)})
        assert ExperimentEvaluationService(analytics, experiments, pubs, learning, LearningConfig()).evaluate("low", now=now).outcome == "INSUFFICIENT_DATA"
    finally: db.dispose()

def test_experiment_classifies_degraded_mixed_and_no_meaningful_change(tmp_path):
    db, pubs, analytics, experiments, learning = stores(tmp_path)
    try:
        service = ExperimentEvaluationService(analytics, experiments, pubs, learning, LearningConfig(minimum_views=1))
        now = datetime.now(UTC); start = now - timedelta(days=2)
        def row(name, values): return SimpleNamespace(snapshot_identity=name, observed_at=now, report_start=now - timedelta(days=2), metrics_json=json.dumps({key: metric(value) for key, value in values.items()}))
        before = row("before", {"views":100, "impressions":100, "watch_time_seconds":100, "likes":100})
        assert service._outcome(before, [row("after", {"views":50, "impressions":50, "watch_time_seconds":50, "likes":50})], start, now)[0] == "DEGRADED"
        assert service._outcome(before, [row("after", {"views":120, "impressions":80, "watch_time_seconds":100, "likes":100})], start, now)[0] == "MIXED"
        assert service._outcome(before, [row("after", {"views":105, "impressions":105, "watch_time_seconds":105, "likes":105})], start, now)[0] == "NO_MEANINGFUL_CHANGE"
    finally: db.dispose()

def test_channel_baseline_recommendations_and_reviewable_brief_are_bounded(tmp_path):
    db, pubs, analytics, experiments, learning = stores(tmp_path)
    try:
        now = datetime.now(UTC)
        for number, views in enumerate((100, 300, 900)):
            publication = f"pub-{number}"; pubs.ensure(f"job-{number}", publication, "pkg", "channel", {}); pubs.update(publication, state="healthy", remote_video_id=publication)
            snapshot(analytics, publication, "channel", f"snapshot-{number}", now - timedelta(days=number), views)
        service = ChannelLearningService(analytics, learning, LearningConfig(minimum_history_videos=3, max_active_recommendations=1))
        baseline = service.baseline("channel", now=now); data = json.loads(baseline.statistics_json)
        assert data["sufficient_history"] and data["metrics"]["views"]["median"] == 300
        first, second = service.recommend("channel", now=now), service.recommend("channel", now=now)
        brief = service.brief("channel", now=now)
        assert len(first) == len(second) == 1 and first[0].recommendation_identity == second[0].recommendation_identity
        assert json.loads(brief.recommendation_identities_json) == [first[0].recommendation_identity]
        with db.session_factory() as session: assert session.query(NextVideoBriefRecord).count() == 1
    finally: db.dispose()
