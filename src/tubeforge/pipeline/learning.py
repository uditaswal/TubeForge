"""Deterministic M20--M23 learning; it only reads analytics and writes local records."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from statistics import median

from tubeforge.core.config import LearningConfig
from tubeforge.db.repositories import AnalyticsRepository, LearningRepository, OptimizationRepository, PublicationRepository
from tubeforge.pipeline.performance import identity

METRICS = ("views", "watch_time_seconds", "impressions", "likes")

def _utc(value: datetime) -> datetime: return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
def _value(snapshot, key: str) -> float | None:
    payload = json.loads(snapshot.metrics_json).get(key, {})
    value = payload.get("value") if isinstance(payload, dict) else None
    return float(value) if isinstance(value, (int, float)) else None
def _rate(value: float | None, days: float) -> float | None: return value / max(days, 1 / 24) if value is not None else None
def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values); index = round((len(ordered) - 1) * fraction); return ordered[index]

class ExperimentEvaluationService:
    """Compare one pre-change snapshot with mature post-change snapshots."""
    def __init__(self, analytics: AnalyticsRepository, experiments: OptimizationRepository, publications: PublicationRepository, store: LearningRepository, config: LearningConfig) -> None:
        self.analytics, self.experiments, self.publications, self.store, self.config = analytics, experiments, publications, store, config
    def evaluate_all(self, *, now: datetime | None = None) -> list[object]:
        return [item for experiment in self.experiments.experiments() if (item := self.evaluate(experiment.execution_identity, now=now)) is not None]
    def evaluate(self, execution_identity: str, *, now: datetime | None = None) -> object | None:
        experiment = next((item for item in self.experiments.experiments() if item.execution_identity == execution_identity), None)
        if experiment is None: return None
        current = now or datetime.now(UTC); baseline = self.analytics.snapshot(experiment.baseline_snapshot_identity) if experiment.baseline_snapshot_identity else None
        snapshots = self.analytics.snapshots(experiment.publication_identity)
        post = [s for s in snapshots if _utc(s.observed_at) >= _utc(experiment.started_at)]
        post_ids = [s.snapshot_identity for s in post]
        outcome_id = identity({"execution": execution_identity, "baseline": experiment.baseline_snapshot_identity, "post": post_ids, "evaluator": self.config.evaluator_version, "config": self.config.model_dump(mode="json")})
        outcome, evidence = self._outcome(baseline, post, experiment.started_at, current)
        record = self.store.save_outcome({"execution_identity": execution_identity, "outcome_identity": outcome_id, "evaluator_version": self.config.evaluator_version, "outcome": outcome, "baseline_snapshot_identity": experiment.baseline_snapshot_identity, "post_snapshot_identities_json": json.dumps(post_ids), "evidence_json": json.dumps(evidence, sort_keys=True), "created_at": current})
        publication = self.publications.get(experiment.publication_identity)
        if publication:
            event_id = identity({"outcome": outcome_id, "channel": publication.channel_id, "type": "EXPERIMENT_OUTCOME"})
            self.store.save_event({"event_identity": event_id, "outcome_identity": outcome_id, "channel_id": publication.channel_id, "event_type": "EXPERIMENT_OUTCOME", "payload_json": json.dumps({"outcome": outcome, "changed_dimensions": experiment.changed_dimensions, "evidence": evidence}, sort_keys=True), "created_at": current})
        return record
    def _outcome(self, baseline, post, started_at: datetime, now: datetime) -> tuple[str, dict[str, object]]:
        if baseline is None: return "UNAVAILABLE", {"reason": "baseline_snapshot_missing"}
        age_hours = (_utc(now) - _utc(started_at)).total_seconds() / 3600
        if age_hours < self.config.minimum_post_hours or not post: return "INSUFFICIENT_DATA", {"reason": "maturity_window", "post_hours": age_hours, "post_snapshots": len(post)}
        latest = post[-1]; baseline_views = _value(baseline, "views"); post_views = _value(latest, "views")
        if baseline_views is None or post_views is None: return "UNAVAILABLE", {"reason": "required_metric_unavailable"}
        if post_views < self.config.minimum_views: return "INSUFFICIENT_DATA", {"reason": "minimum_views", "views": post_views}
        before_days = max((_utc(baseline.observed_at) - _utc(baseline.report_start)).total_seconds() / 86400, 1 / 24)
        after_days = max((_utc(latest.observed_at) - _utc(started_at)).total_seconds() / 86400, 1 / 24)
        changes: dict[str, float] = {}
        for metric in METRICS:
            old, new = _rate(_value(baseline, metric), before_days), _rate(_value(latest, metric), after_days)
            if old is not None and new is not None and old > 0: changes[metric] = (new - old) / old
        meaningful = {key: value for key, value in changes.items() if abs(value) >= .10}
        positives, negatives = sum(value > 0 for value in meaningful.values()), sum(value < 0 for value in meaningful.values())
        outcome = "IMPROVED" if positives and not negatives else "DEGRADED" if negatives and not positives else "MIXED" if positives and negatives else "NO_MEANINGFUL_CHANGE"
        return outcome, {"maturity": "early" if after_days < 3 else "developing" if after_days < 14 else "mature", "duration_normalized": True, "relative_changes": changes, "post_views": post_views}

class ChannelLearningService:
    """Build robust per-channel baselines and bounded evidence-backed next steps."""
    def __init__(self, analytics: AnalyticsRepository, store: LearningRepository, config: LearningConfig) -> None: self.analytics, self.store, self.config = analytics, store, config
    def baseline(self, channel_id: str, *, now: datetime | None = None) -> object:
        snapshots = self.analytics.channel_latest_snapshots(channel_id); values = {key: [_value(item, key) for item in snapshots] for key in METRICS}
        stats = {key: {"median": median(valid), "p25": _percentile(valid, .25), "p75": _percentile(valid, .75)} for key, raw in values.items() if (valid := [item for item in raw if item is not None])}
        baseline_id = identity({"channel": channel_id, "snapshots": [item.snapshot_identity for item in snapshots], "version": self.config.evaluator_version})
        return self.store.save_baseline({"channel_id": channel_id, "baseline_identity": baseline_id, "baseline_version": self.config.evaluator_version, "sample_size": len(snapshots), "statistics_json": json.dumps({"sufficient_history": len(snapshots) >= self.config.minimum_history_videos, "metrics": stats}, sort_keys=True), "created_at": now or datetime.now(UTC)})
    def recommend(self, channel_id: str, *, now: datetime | None = None) -> list[object]:
        baseline = self.baseline(channel_id, now=now); stats = json.loads(baseline.statistics_json); current = now or datetime.now(UTC)
        if not stats["sufficient_history"]: return []
        evidence = {"baseline_identity": baseline.baseline_identity, "sample_size": baseline.sample_size, "metrics": stats["metrics"]}
        recommendation_type = "REPEAT_EFFECTIVE_PACKAGING" if stats["metrics"].get("impressions", {}).get("median", 0) else "MAINTAIN_MEASUREMENT"
        rec_id = identity({"channel": channel_id, "type": recommendation_type, "baseline": baseline.baseline_identity, "version": self.config.recommendation_version})
        active = self.store.active_recommendations(channel_id)
        if len(active) >= self.config.max_active_recommendations and not any(item.recommendation_identity == rec_id for item in active): return []
        return [self.store.save_recommendation({"channel_id": channel_id, "recommendation_identity": rec_id, "recommendation_version": self.config.recommendation_version, "status": "ACTIVE", "recommendation_type": recommendation_type, "confidence": "HIGH" if baseline.sample_size >= 10 else "MEDIUM", "evidence_json": json.dumps(evidence, sort_keys=True), "created_at": current})]
    def brief(self, channel_id: str, *, now: datetime | None = None) -> object:
        recommendations = self.recommend(channel_id, now=now); ids = sorted(item.recommendation_identity for item in recommendations or self.store.active_recommendations(channel_id))
        brief_id = identity({"channel": channel_id, "recommendations": ids, "template": self.config.brief_template_version})
        content = {"purpose": "Human-reviewable next-video planning input; no video is created.", "recommendation_identities": ids}
        return self.store.save_brief({"channel_id": channel_id, "brief_identity": brief_id, "template_version": self.config.brief_template_version, "status": "REVIEW_REQUIRED", "recommendation_identities_json": json.dumps(ids), "content_json": json.dumps(content, sort_keys=True), "created_at": now or datetime.now(UTC)})
