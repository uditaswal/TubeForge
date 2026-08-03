"""SQLAlchemy declarative metadata for TubeForge persistence."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for future persisted domain models."""


class PipelineJobRecord(Base):
    """Durable state and request data for one deterministic pipeline run."""

    __tablename__ = "pipeline_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    request_json: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(String(64), nullable=False)
    resume_state: Mapped[str | None] = mapped_column(String(64))
    failure_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ArtifactRecord(Base):
    """A validated checkpoint artifact; binaries remain on disk."""

    __tablename__ = "artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    stage: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    provenance_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ApprovalRecord(Base):
    """An immutable approved/rejected gate decision for a job."""

    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    gate: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
