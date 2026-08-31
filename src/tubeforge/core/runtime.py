"""Application composition for the API and single-job worker."""

from __future__ import annotations

from dataclasses import dataclass, replace

from tubeforge.core.config import Settings
from tubeforge.db.repositories import (
    ApprovalRepository,
    AssetCacheRepository,
    ArtifactRepository,
    ExternalOperationRepository,
    JobEventRepository,
    JobRepository,
)
from tubeforge.db.session import Database, create_database
from tubeforge.pipeline.assets import AssetAcquisitionService, AssetDownloader, asset_limits_from_config
from tubeforge.pipeline.orchestrator import PipelineOrchestrator
from tubeforge.pipeline.sources import SourceIngestor
from tubeforge.providers.content.factory import create_content_provider
from tubeforge.providers.fake import FakePublisher
from tubeforge.providers.media.factory import create_media_provider
from tubeforge.providers.publishing.youtube import YouTubeDataApiPublisher
from tubeforge.providers.voice.factory import create_voice_provider


@dataclass(frozen=True, slots=True)
class Runtime:
    """Fully composed local runtime; constructing it performs no provider IO."""

    database: Database
    jobs: JobRepository
    artifacts: ArtifactRepository
    approvals: ApprovalRepository
    events: JobEventRepository
    orchestrator: PipelineOrchestrator


def create_runtime(settings: Settings) -> Runtime:
    """Build all adapters from validated settings at the application boundary."""
    database = create_database(settings.database)
    jobs = JobRepository(database.session_factory)
    artifacts = ArtifactRepository(database.session_factory)
    approvals = ApprovalRepository(database.session_factory)
    media = create_media_provider(settings.pipeline.media, settings.pipeline.fake)
    publisher = (
        YouTubeDataApiPublisher(settings.pipeline.youtube)
        if settings.pipeline.youtube.enabled
        else FakePublisher()
    )
    limits = asset_limits_from_config(settings.pipeline.media)
    # The fake adapter uses an inert example.invalid provenance URL while
    # copying its provider-created local fixture; do not widen real policies.
    if settings.pipeline.media.provider == "fake":
        limits = replace(limits, allowed_hosts=limits.allowed_hosts | frozenset({"example.invalid"}))
    acquirer = AssetAcquisitionService(
        AssetCacheRepository(database.session_factory),
        AssetDownloader(settings.pipeline.media.cache_root, limits),
    )
    orchestrator = PipelineOrchestrator.from_settings(
        settings,
        jobs,
        artifacts,
        approvals,
        create_content_provider(settings, database.session_factory),
        media,
        create_voice_provider(settings),
        publisher,
        ExternalOperationRepository(database.session_factory),
    )
    # The constructor deliberately has safe defaults for tests. Production
    # composition overrides its policy-bearing asset dependencies explicitly.
    orchestrator.asset_limits = limits
    orchestrator.asset_acquirer = acquirer
    source_policy = settings.pipeline.sources
    if source_policy.enabled:
        orchestrator.source_ingestor = SourceIngestor(
            frozenset(source_policy.allowed_hosts),
            max_bytes=source_policy.max_bytes,
            max_chars=source_policy.max_chars,
            timeout_seconds=source_policy.timeout_seconds,
        )
    return Runtime(database, jobs, artifacts, approvals, orchestrator.events, orchestrator)
