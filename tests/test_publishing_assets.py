"""Finished media is copied, fingerprinted, probed, and deduplicated."""
from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess

import pytest
from sqlalchemy import text

from tubeforge.core.config import DatabaseConfig
from tubeforge.db.models import Base
from tubeforge.db.repositories import Artifact, ArtifactRepository, JobRepository
from tubeforge.db.session import create_database
from tubeforge.domain.contracts import ContentRequest, SourceReference
from tubeforge.domain.states import JobState
from tubeforge.pipeline.publishing_assets import PublishingAssetRegistry


def test_register_final_copies_real_video_and_reuses_fingerprint(tmp_path: Path) -> None:
    database = create_database(DatabaseConfig(url=f"sqlite:///{tmp_path / 'assets.db'}"))
    Base.metadata.create_all(database.engine)
    root = tmp_path / "artifacts"
    video = root / "job-1" / "final.mp4"
    video.parent.mkdir(parents=True)
    subprocess.run([
        "ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=navy:s=320x568:d=1",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-y", str(video),
    ], check=True, timeout=20)
    original = video.read_bytes()
    digest = hashlib.sha256(original).hexdigest()
    jobs = JobRepository(database.session_factory)
    request = ContentRequest(topic="Test", angle="Video", target_duration_seconds=30, language="en", audience="general", prompt_version="test-v1", sources=(SourceReference(source_id="local", url="https://example.invalid/test", title="Test"),))
    jobs.create("job-1", request)
    with database.engine.begin() as connection:
        connection.execute(text("UPDATE pipeline_jobs SET state='final_ready' WHERE id='job-1'"))
    artifacts = ArtifactRepository(database.session_factory)
    artifacts.save(Artifact("job-1", JobState.FINAL_RENDERING, "final", str(video), digest, {}))
    registry = PublishingAssetRegistry(database.session_factory, jobs, artifacts, root)
    try:
        first = registry.register_final("job-1")
        staged = Path(first.staged_path)
        assert staged != video and staged.read_bytes() == original
        assert first.sha256 == digest and first.width == 320 and first.height == 568
        assert 0.9 <= first.duration_seconds <= 1.1
        assert registry.register_final("job-1").id == first.id
        video.write_bytes(b"changed after checkpoint")
        with pytest.raises(ValueError, match="changed after"):
            registry.register_final("job-1")
        assert staged.read_bytes() == original
    finally:
        database.dispose()
