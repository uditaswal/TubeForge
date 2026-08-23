"""Private HTTP control-plane coverage without starting a worker or provider."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from tubeforge.api.app import create_app
from tubeforge.core.config import AppConfig, DatabaseConfig, Settings
from tubeforge.db.repositories import Artifact
from tubeforge.domain.states import JobState


def _migrate(path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    config.cmd_opts = Namespace(x=[f"database_url=sqlite:///{path}"])
    command.upgrade(config, "head")


def test_private_job_api_creates_and_records_an_approval(tmp_path: Path) -> None:
    database_path = tmp_path / "api.db"
    _migrate(database_path)
    settings = Settings(
        app=AppConfig(name="TubeForge test", environment="test"),
        database=DatabaseConfig(url=f"sqlite:///{database_path}"),
    )
    request = {
        "topic": "Rain",
        "angle": "A 30-second explainer",
        "target_duration_seconds": 30,
        "language": "en-IN",
        "audience": "general",
        "prompt_version": "test-v1",
        "sources": [{"source_id": "rain", "url": "https://example.invalid/rain", "title": "Rain"}],
    }
    with TestClient(create_app(settings)) as client:
        created = client.post("/api/jobs", json=request)
        assert created.status_code == 201
        job_id = created.json()["id"]
        assert client.get(f"/api/jobs/{job_id}").json()["state"] == "topic_created"
        approval = client.post(
            f"/api/jobs/{job_id}/approvals/script",
            json={"status": "approved", "actor": "test-operator"},
        )
        assert approval.status_code == 200
        preview = tmp_path / "preview.mp4"
        preview.write_bytes(b"synthetic-preview")
        runtime = client.app.state.runtime
        runtime.artifacts.save(Artifact(job_id, JobState.PREVIEW_RENDERING, "preview", str(preview), "a" * 64, {}))
        assert client.get(f"/api/jobs/{job_id}/artifacts/preview").content == b"synthetic-preview"
        assert client.get(f"/api/jobs/{job_id}/artifacts/preview.mp4").content == b"synthetic-preview"
        assert client.get("/api/jobs/missing").status_code == 404
