"""A worker started for one kind of job leaves the other kind queued."""
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tubeforge.core.config import DatabaseConfig
from tubeforge.db.models import Base
from tubeforge.db.repositories import JobRepository
from tubeforge.db.session import create_database
from tubeforge.domain.contracts import ContentRequest, SourceReference


def request(clip: bool) -> ContentRequest:
    base = dict(topic="Topic", angle="angle", target_duration_seconds=30, language="en", audience="general", sources=(SourceReference(source_id="s", url="https://example.com/a", title="A"),), review_mode="auto")
    if clip:
        return ContentRequest(**base, prompt_version="source-clip-v1", production_mode="source_clip", source_url="https://example.com/a", clip_count=1)
    return ContentRequest(**base, prompt_version="test-v1")


@pytest.fixture
def jobs(tmp_path: Path):
    database = create_database(DatabaseConfig(url=f"sqlite:///{tmp_path / 'kinds.db'}"))
    Base.metadata.create_all(database.engine)
    repository = JobRepository(database.session_factory)
    repository.create("short-job", request(False))
    repository.create("clip-job", request(True))
    return repository


@pytest.mark.parametrize("kinds,expected", [("clips", "clip-job"), ("shorts", "short-job"), ("all", "short-job")])
def test_worker_claims_only_its_kind(jobs, kinds, expected):
    claimed = jobs.claim_oldest_eligible("w", now=datetime.now(UTC), lease_seconds=300, job_kinds=kinds)
    assert claimed is not None and claimed.id == expected
