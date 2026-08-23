"""Application factory and operational endpoints."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from tubeforge.core.config import Settings, load_settings, validate_selected_provider
from tubeforge.core.runtime import Runtime, create_runtime
from tubeforge.domain.contracts import ContentPackage, ContentRequest
from tubeforge.domain.states import ApprovalGate, ApprovalStatus, JobState


class ApprovalRequest(BaseModel):
    """An explicit, audit-friendly human decision from the private dashboard."""

    model_config = ConfigDict(extra="forbid")

    status: ApprovalStatus
    actor: str = Field(min_length=1, max_length=200)
    reviewed_identity: str | None = Field(default=None, min_length=1, max_length=128)


def _job_payload(job: object) -> dict[str, object]:
    return {"id": job.id, "state": job.state, "failure_message": job.failure_message}


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create the HTTP application using explicit settings when supplied."""
    application_settings = settings or load_settings()
    validate_selected_provider(application_settings)
    runtime: Runtime = create_runtime(application_settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
        try:
            yield
        finally:
            runtime.database.dispose()

    app = FastAPI(title=application_settings.app.name, lifespan=lifespan)
    app.state.settings = application_settings
    app.state.database = runtime.database
    app.state.runtime = runtime

    @app.get("/healthz", tags=["operations"])
    def healthz() -> dict[str, str]:
        """Report process and database reachability without exposing settings."""
        try:
            with runtime.database.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="database unavailable",
            ) from error
        return {"status": "ok", "database": "ok"}

    @app.post("/api/jobs", status_code=status.HTTP_201_CREATED, tags=["jobs"])
    def create_job(request: ContentRequest) -> dict[str, object]:
        """Create a durable job; a separate worker advances it."""
        job = runtime.jobs.create(uuid4().hex, request)
        return _job_payload(job)

    @app.get("/api/jobs/{job_id}", tags=["jobs"])
    def get_job(job_id: str) -> dict[str, object]:
        try:
            return _job_payload(runtime.jobs.get(job_id))
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found") from error

    @app.post("/api/jobs/{job_id}/approvals/{gate}", tags=["approvals"])
    def decide(job_id: str, gate: ApprovalGate, decision: ApprovalRequest) -> dict[str, object]:
        """Record one immutable approval; the worker validates identities before use."""
        try:
            runtime.jobs.get(job_id)
            runtime.approvals.record(
                uuid4().hex,
                job_id,
                gate,
                decision.status,
                actor=decision.actor,
                reviewed_identity=decision.reviewed_identity,
            )
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found") from error
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
        return {"job_id": job_id, "gate": gate, "status": decision.status}

    @app.post("/api/jobs/{job_id}/script-revision", tags=["jobs"])
    def revise_script(job_id: str, package: ContentPackage, actor: str = "operator") -> dict[str, object]:
        """Replace only a rejected script package before costly stages begin.

        Revision is intentionally local: the submitted package must use the
        already checkpointed effective request, so this endpoint never calls a
        model or silently changes source evidence.
        """
        try:
            job = runtime.jobs.get(job_id)
            if job.state is not JobState.SCRIPT_APPROVAL_REQUIRED:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="script revisions are allowed only while script approval is pending")
            if runtime.approvals.rejected(job_id, ApprovalGate.SCRIPT) is None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="script revision requires a recorded script rejection")
            effective = runtime.orchestrator._required_json(job_id, JobState.CONTENT_GENERATING, "effective_content_request")
            if package.request != ContentRequest.model_validate(effective):
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="revision must retain the checkpointed content request and sources")
            artifact = runtime.orchestrator._replace_json(
                job_id,
                JobState.CONTENT_GENERATING,
                "content_package",
                package.model_dump(mode="json"),
            )
            runtime.orchestrator._replace_json(
                job_id,
                JobState.CONTENT_GENERATING,
                "script_revision",
                {"actor": actor, "content_package_checksum": artifact.checksum_sha256},
            )
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found") from error
        return {"job_id": job_id, "reviewed_identity": artifact.checksum_sha256}

    @app.get("/api/jobs/{job_id}/artifacts/{name}", tags=["artifacts"])
    def get_artifact(job_id: str, name: str) -> FileResponse:
        """Serve only a registered artifact, never a caller-supplied path."""
        artifact = next(
            (
                item
                for stage in JobState
                if (item := runtime.artifacts.get(job_id, stage, name)) is not None
            ),
            None,
        )
        if artifact is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="artifact not found")
        path = Path(artifact.path)
        if not path.is_file():
            raise HTTPException(status_code=status.HTTP_410_GONE, detail="artifact is unavailable")
        media_type = "video/mp4" if path.suffix.lower() == ".mp4" else "application/json"
        return FileResponse(path, media_type=media_type)

    return app
