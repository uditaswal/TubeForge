"""Register one finished local video as immutable, content-addressed media."""
from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from tubeforge.db.models import PublishingAssetRecord
from tubeforge.db.repositories import ArtifactRepository, JobRepository
from tubeforge.domain.states import JobState


READY_STATES = {
    JobState.FINAL_READY, JobState.PUBLICATION_PREPARING,
    JobState.PUBLICATION_APPROVAL_REQUIRED, JobState.PUBLICATION_READY,
    JobState.PUBLISHING, JobState.PUBLICATION_VERIFICATION_PENDING,
    JobState.PUBLICATION_RECONCILING, JobState.PUBLISHED,
}


class PublishingAssetRegistry:
    def __init__(
        self, session_factory: sessionmaker[Session], jobs: JobRepository,
        artifacts: ArtifactRepository, artifact_root: Path,
        *, ffprobe: str = "ffprobe", max_bytes: int = 2_000_000_000,
    ) -> None:
        self.session_factory = session_factory
        self.jobs = jobs
        self.artifacts = artifacts
        self.artifact_root = artifact_root
        self.stage_root = artifact_root.parent / "publishing" / "staging"
        self.ffprobe = ffprobe
        self.max_bytes = max_bytes

    def register_final(self, job_id: str) -> PublishingAssetRecord:
        job = self.jobs.get(job_id)
        if job.state not in READY_STATES or job.claim_owner is not None:
            raise ValueError("generation does not have a stable final video")
        artifact = self.artifacts.get(job_id, JobState.FINAL_RENDERING, "final")
        if artifact is None:
            raise ValueError("generation has no final video artifact")
        root = self.artifact_root.resolve()
        source = Path(artifact.path).resolve(strict=True)
        if not source.is_relative_to(root) or not source.is_file() or source.suffix.lower() != ".mp4":
            raise ValueError("final video is outside the approved artifact root")
        before = source.stat()
        if before.st_size <= 0 or before.st_size > self.max_bytes:
            raise ValueError("final video size is invalid")
        self.stage_root.mkdir(parents=True, exist_ok=True)
        if self.stage_root.is_symlink():
            raise ValueError("publishing staging root must not be a symlink")
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(prefix="asset-", suffix=".tmp", dir=self.stage_root, delete=False) as target:
                temporary = Path(target.name)
                digest = hashlib.sha256()
                with source.open("rb") as original:
                    while chunk := original.read(1024 * 1024):
                        digest.update(chunk)
                        target.write(chunk)
                target.flush()
                os.fsync(target.fileno())
            after = source.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns) or digest.hexdigest() != artifact.checksum_sha256:
                raise ValueError("final video changed after its artifact checkpoint")
            duration, width, height = self._probe(temporary)
            staged = self.stage_root / f"{digest.hexdigest()}.mp4"
            if staged.is_symlink():
                raise ValueError("staged video path must not be a symlink")
            if staged.exists():
                if staged.stat().st_size != before.st_size or self._hash(staged) != digest.hexdigest():
                    raise ValueError("existing staged video does not match its fingerprint")
            else:
                os.replace(temporary, staged)
                temporary = None
            now = datetime.now(UTC)
            try:
                with self.session_factory.begin() as session:
                    record = session.scalar(select(PublishingAssetRecord).where(PublishingAssetRecord.sha256 == digest.hexdigest()))
                    if record is None:
                        record = PublishingAssetRecord(id=uuid4().hex, sha256=digest.hexdigest(), staged_path=str(staged), source_job_id=job_id, size_bytes=before.st_size, duration_seconds=duration, width=width, height=height, state="ready", created_at=now)
                        session.add(record)
                    session.flush()
                    return record
            except IntegrityError:
                with self.session_factory() as session:
                    record = session.scalar(select(PublishingAssetRecord).where(PublishingAssetRecord.sha256 == digest.hexdigest()))
                    if record is None:
                        raise
                    return record
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def preview_path(self, asset_id: str) -> Path:
        """Serve only the exact immutable staged asset after hash verification."""
        with self.session_factory() as session:
            record = session.get(PublishingAssetRecord, asset_id)
            if record is None:
                raise KeyError(asset_id)
            expected_hash, staged_path = record.sha256, record.staged_path
        root = self.stage_root.resolve(strict=True)
        path = Path(staged_path)
        if path.is_symlink() or path.parent.resolve(strict=True) != root or path.name != f"{expected_hash}.mp4":
            raise ValueError("staged video path is invalid")
        if not path.is_file() or self._hash(path) != expected_hash:
            raise ValueError("staged video is unavailable or changed")
        return path

    def _probe(self, path: Path) -> tuple[float, int, int]:
        try:
            result = subprocess.run(
                [self.ffprobe, "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height", "-of", "json", str(path)],
                capture_output=True, text=True, check=True, timeout=20,
            )
            data = json.loads(result.stdout)
            video = next(stream for stream in data.get("streams", []) if stream.get("codec_type") == "video")
            duration = float(data["format"]["duration"])
            width, height = int(video["width"]), int(video["height"])
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError, KeyError, StopIteration, TypeError, json.JSONDecodeError) as error:
            raise ValueError("final video failed media probing") from error
        if duration <= 0 or width <= 0 or height <= 0:
            raise ValueError("final video has invalid dimensions or duration")
        return duration, width, height

    @staticmethod
    def _hash(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()
