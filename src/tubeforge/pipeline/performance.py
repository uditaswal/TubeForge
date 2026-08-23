"""M15/M16 post-publication observation; it never mutates remote YouTube videos."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from statistics import median
from typing import Any

from tubeforge.core.config import AnalyticsConfig, PerformanceConfig
from tubeforge.db.repositories import AnalyticsRepository, PublicationRepository
from tubeforge.domain.contracts import AnalyticsSnapshotData, MetricAvailability

_NORMALIZED = {"estimatedMinutesWatched": "watch_time_seconds", "averageViewDuration": "average_view_duration_seconds", "averageViewPercentage": "average_percentage_viewed", "impressionsClickThroughRate": "impressions_ctr", "subscribersGained": "subscribers_gained", "subscribersLost": "subscribers_lost"}


def identity(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def normalized_metrics(snapshot: AnalyticsSnapshotData) -> dict[str, dict[str, object]]:
    """Use one canonical internal vocabulary and 0--100 percentage semantics."""
    result: dict[str, dict[str, object]] = {}
    for name, metric in snapshot.metrics.items():
        key = _NORMALIZED.get(name, name)
        normalized = metric.model_dump(mode="json")
        if name == "estimatedMinutesWatched" and normalized.get("value") is not None:
            normalized["value"] = float(normalized["value"]) * 60
        result[key] = normalized
    return result


class AnalyticsIngestionService:
    """Collect an explicit reporting window and persist an idempotent snapshot."""
    def __init__(self, publications: PublicationRepository, analytics: AnalyticsRepository, provider: Any, config: AnalyticsConfig) -> None:
        self.publications, self.analytics, self.provider, self.config = publications, analytics, provider, config

    def collect(self, publication_identity: str, *, now: datetime | None = None) -> object | None:
        if not self.config.enabled: return None
        record = self.publications.get(publication_identity)
        if record is None or record.state != "healthy" or not record.remote_video_id: return None
        current = now or datetime.now(UTC)
        created_at = _utc(record.created_at)
        if current < created_at + timedelta(hours=self.config.initial_delay_hours): return None
        report_end, report_start = current.date(), created_at.date()
        data: AnalyticsSnapshotData = self.provider.fetch_video_analytics(str(record.remote_video_id), record.channel_id, report_start, report_end)
        metrics = normalized_metrics(data)
        snapshot_identity = identity({"publication": publication_identity, "start": report_start, "end": report_end, "query_version": self.config.query_version})
        status = "complete" if data.completeness == "complete" else data.completeness
        return self.analytics.save_snapshot({"publication_identity": publication_identity, "remote_video_id": str(record.remote_video_id), "channel_id": record.channel_id, "snapshot_identity": snapshot_identity, "report_start": datetime.combine(report_start, datetime.min.time(), UTC), "report_end": datetime.combine(report_end, datetime.min.time(), UTC), "observed_at": data.observed_at, "status": status, "views": _integer(metrics, "views"), "impressions": _integer(metrics, "impressions"), "metrics_json": json.dumps(metrics, sort_keys=True), "provenance_json": json.dumps({"source": data.source, "query_version": self.config.query_version, "provider_query_version": data.query_version}, sort_keys=True), "created_at": current})

    def collect_due(self, *, now: datetime | None = None) -> list[object]:
        """A bounded scheduler hook: callers invoke periodically; this is not a polling loop."""
        current = now or datetime.now(UTC); collected = []
        for publication in self.publications.healthy_with_remote_ids():
            if current > _utc(publication.created_at) + timedelta(days=self.config.collection_horizon_days): continue
            snapshots = self.analytics.snapshots(publication.publication_identity)
            if snapshots and current < snapshots[-1].observed_at + timedelta(hours=self.config.collection_interval_hours): continue
            item = self.collect(publication.publication_identity, now=current)
            if item is not None: collected.append(item)
        return collected


def _integer(metrics: dict[str, dict[str, object]], key: str) -> int | None:
    item = metrics.get(key, {})
    return int(item["value"]) if item.get("availability") == MetricAvailability.AVAILABLE.value else None


@dataclass(frozen=True)
class Evaluation:
    dimensions: dict[str, dict[str, object]]
    derived: dict[str, float | None]
    recommendations: list[dict[str, object]]


class PerformanceEvaluator:
    """Transparent rule-based scoring for persisted normalized snapshots."""
    def __init__(self, config: PerformanceConfig) -> None: self.config = config

    def evaluate(self, metrics: dict[str, dict[str, object]], *, publication_age_days: float, previous: dict[str, dict[str, object]] | None = None, video_duration_seconds: float | None = None, baseline: dict[str, float] | None = None) -> Evaluation:
        value = lambda key: _value(metrics, key)
        views, impressions, ctr, retention = value("views"), value("impressions"), value("impressions_ctr"), value("average_percentage_viewed")
        derived = {"views_per_day": _divide(views, max(publication_age_days, 1)), "watch_time_per_day": _divide(value("watch_time_seconds"), max(publication_age_days, 1)), "likes_per_view": _divide(value("likes"), views), "comments_per_view": _divide(value("comments"), views), "net_subscribers": _subtract(value("subscribers_gained"), value("subscribers_lost")), "subscribers_per_view": _divide(_subtract(value("subscribers_gained"), value("subscribers_lost")), views), "retention_duration_ratio": _divide(value("average_view_duration_seconds"), video_duration_seconds)}
        if previous: derived["recent_view_growth"] = _subtract(views, _value(previous, "views"))
        discovery = "UNAVAILABLE" if impressions is None or ctr is None else "INSUFFICIENT_DATA" if impressions < self.config.min_impressions_for_ctr else "WEAK" if ctr < 3 else "STRONG" if ctr >= 6 else "NORMAL"
        retention_state = "UNAVAILABLE" if retention is None else "INSUFFICIENT_DATA" if (views or 0) < self.config.min_views_for_retention else "WEAK" if retention < 35 else "STRONG" if retention >= 55 else "NORMAL"
        engagement = "UNAVAILABLE" if views is None or not views else "INSUFFICIENT_DATA" if views < self.config.min_views_for_retention else "STRONG" if (derived["likes_per_view"] or 0) >= .05 else "WEAK" if (derived["likes_per_view"] or 0) < .01 else "NORMAL"
        growth = "UNAVAILABLE" if views is None else "INSUFFICIENT_DATA" if views < self.config.min_views_for_retention else "STRONG" if (derived["views_per_day"] or 0) >= (baseline or {}).get("views_per_day", float("inf")) else "NORMAL"
        dimensions = {"discovery": {"state": discovery, "impressions": impressions, "ctr": ctr}, "retention": {"state": retention_state, "average_percentage_viewed": retention}, "engagement": {"state": engagement, "likes_per_view": derived["likes_per_view"]}, "growth": {"state": growth, "views_per_day": derived["views_per_day"]}}
        recommendations = self._recommend(dimensions)
        return Evaluation(dimensions, derived, recommendations)

    def _recommend(self, dimensions: dict[str, dict[str, object]]) -> list[dict[str, object]]:
        discovery, retention = dimensions["discovery"]["state"], dimensions["retention"]["state"]
        if discovery == "INSUFFICIENT_DATA" or retention == "INSUFFICIENT_DATA": return [{"category": "wait", "priority": "low", "action_type": "NO_CHANGE", "confidence": "insufficient_data", "evidence": dimensions}]
        if discovery == "WEAK" and retention in {"STRONG", "NORMAL"}: return [{"category": "packaging", "priority": "high", "action_type": "TITLE_AND_THUMBNAIL", "confidence": "sufficient", "evidence": dimensions}]
        if discovery == "STRONG" and retention == "WEAK": return [{"category": "opening", "priority": "high", "action_type": "CONTENT_LEARNING", "confidence": "sufficient", "evidence": dimensions}]
        if discovery == "WEAK": return [{"category": "packaging", "priority": "medium", "action_type": "THUMBNAIL", "confidence": "sufficient", "evidence": dimensions}]
        return [{"category": "preserve", "priority": "low", "action_type": "NO_CHANGE", "confidence": "sufficient", "evidence": dimensions}]


class PerformanceService:
    def __init__(self, publications: PublicationRepository, analytics: AnalyticsRepository, config: PerformanceConfig) -> None: self.publications, self.analytics, self.config, self.evaluator = publications, analytics, config, PerformanceEvaluator(config)
    def evaluate(self, publication_identity: str, *, video_duration_seconds: float | None = None, now: datetime | None = None) -> object | None:
        snapshots = self.analytics.snapshots(publication_identity)
        if not snapshots: return None
        publication = self.publications.get(publication_identity)
        if publication is None or not publication.remote_video_id: return None
        latest = snapshots[-1]; metrics = json.loads(latest.metrics_json); previous = json.loads(snapshots[-2].metrics_json) if len(snapshots) > 1 else None
        result = self.evaluator.evaluate(metrics, publication_age_days=max(((now or datetime.now(UTC)) - _utc(publication.created_at)).total_seconds() / 86400, 0), previous=previous, video_duration_seconds=video_duration_seconds, baseline=self._baseline())
        snapshot_ids = [snapshot.snapshot_identity for snapshot in snapshots]
        evaluation_identity = identity({"publication": publication_identity, "snapshots": snapshot_ids, "evaluator": self.config.evaluator_version, "config": self.config.model_dump(mode="json")})
        evaluation = self.analytics.save_evaluation({"publication_identity": publication_identity, "evaluation_identity": evaluation_identity, "snapshot_identities_json": json.dumps(snapshot_ids), "evaluator_version": self.config.evaluator_version, "dimensions_json": json.dumps(result.dimensions, sort_keys=True), "derived_metrics_json": json.dumps(result.derived, sort_keys=True), "recommendations_json": json.dumps(result.recommendations, sort_keys=True), "created_at": now or datetime.now(UTC)})
        action = str(result.recommendations[0]["action_type"])
        proposal_identity = identity({"evaluation": evaluation_identity, "action": action, "version": self.config.proposal_version})
        self.analytics.save_proposal({"publication_identity": publication_identity, "remote_video_id": str(publication.remote_video_id), "evaluation_identity": evaluation_identity, "snapshot_identity": latest.snapshot_identity, "proposal_identity": proposal_identity, "proposal_type": action, "status": "GENERATED", "rationale_json": json.dumps(result.recommendations[0], sort_keys=True), "proposal_version": self.config.proposal_version, "created_at": now or datetime.now(UTC)})
        return evaluation
    def _baseline(self) -> dict[str, float] | None:
        # Baselines stay deliberately light: only mature TubeForge history already in this store.
        velocities: list[float] = []
        for snapshot in self.analytics.latest_snapshots():
            publication = self.publications.get(snapshot.publication_identity)
            if publication is None: continue
            views = _value(json.loads(snapshot.metrics_json), "views")
            age = (_utc(snapshot.observed_at) - _utc(publication.created_at)).total_seconds() / 86400
            if views is not None and age >= 1: velocities.append(views / age)
        return {"views_per_day": median(velocities)} if len(velocities) >= self.config.baseline_min_videos else None


def _value(metrics: dict[str, dict[str, object]], key: str) -> float | None:
    item = metrics.get(key)
    return float(item["value"]) if item and item.get("availability") == MetricAvailability.AVAILABLE.value else None
def _divide(left: float | None, right: float | None) -> float | None: return None if left is None or right in {None, 0} else left / right
def _subtract(left: float | None, right: float | None) -> float | None: return None if left is None or right is None else left - right
def _utc(value: datetime) -> datetime: return value if value.tzinfo else value.replace(tzinfo=UTC)
