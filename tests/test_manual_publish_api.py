"""Signed-in manual draft API uses a real final video and verified destination."""
from __future__ import annotations

from argparse import Namespace
from datetime import UTC, datetime
import hashlib
from pathlib import Path
import subprocess

from alembic import command
from alembic.config import Config
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from tubeforge.api.app import create_app
from tubeforge.core.config import AppConfig, AuthConfig, DatabaseConfig, Settings
from tubeforge.db.models import DeliveryAttemptRecord, DestinationDeliveryRecord, SocialAccountRecord
from tubeforge.db.repositories import Artifact
from tubeforge.domain.contracts import ContentRequest, SourceReference
from tubeforge.domain.states import JobState
from tubeforge.publishing_worker.presence import PublisherWorkerPresence


def test_signed_in_manual_draft_snapshots_real_video_and_destination(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TUBEFORGE_ACCOUNT_ENCRYPTION_KEY", Fernet.generate_key().decode())
    db_path = tmp_path / "publish-api.db"
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    config.cmd_opts = Namespace(x=[f"database_url=sqlite:///{db_path}"])
    command.upgrade(config, "head")
    settings = Settings(app=AppConfig(name="test", environment="test"), database=DatabaseConfig(url=f"sqlite:///{db_path}"), auth=AuthConfig(enabled=True))
    settings.pipeline.voice.artifact_root = tmp_path / "artifacts"
    video = settings.pipeline.voice.artifact_root / "job-1" / "final.mp4"
    video.parent.mkdir(parents=True)
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=navy:s=320x568:d=1", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-y", str(video)], check=True, timeout=20)
    digest = hashlib.sha256(video.read_bytes()).hexdigest()
    with TestClient(create_app(settings)) as client:
        runtime = client.app.state.runtime
        request = ContentRequest(topic="One video", angle="A test", target_duration_seconds=30, language="en", audience="general", prompt_version="test-v1", sources=(SourceReference(source_id="local", url="https://example.invalid/test", title="Test"),))
        runtime.jobs.create("job-1", request)
        with runtime.database.engine.begin() as connection:
            connection.execute(text("UPDATE pipeline_jobs SET state='final_ready' WHERE id='job-1'"))
        runtime.artifacts.save(Artifact("job-1", JobState.FINAL_RENDERING, "final", str(video), digest, {}))
        now = datetime.now(UTC)
        with runtime.database.session_factory.begin() as session:
            session.add(SocialAccountRecord(id="yt", platform="youtube", display_name="Real channel", external_account_id="UC-real", auth_type="oauth", credential_ciphertext="encrypted", scopes_json='["youtube.upload"]', token_expires_at=None, status="connected", capabilities_json='["upload_video"]', is_default=False, disabled=False, last_validated_at=now, created_at=now, updated_at=now))
        runtime.auth.create_admin("operator", "correct-horse-battery-staple")
        assert client.get("/api/publishing/ready-videos").status_code == 401
        client.post("/login", json={"username": "operator", "password": "correct-horse-battery-staple"})
        csrf = client.cookies.get("tubeforge_csrf")
        dashboard = client.get("/")
        assert dashboard.status_code == 200
        assert "Compose manual post" in dashboard.text
        assert "savePublishDraft" in dashboard.text
        assert "Preview selected video" in dashboard.text
        assert "/api/publishing/ready-videos" in dashboard.text
        assert "nothing is uploaded" in dashboard.text
        assert "/api/publishing/status" in dashboard.text
        assert "Submit private YouTube post" in dashboard.text
        assert "Refresh publishing activity" in dashboard.text
        assert "Inspect saved remote session" in dashboard.text
        assert "Continue saved upload session" in dashboard.text
        assert "Destination attempt history" in dashboard.text
        assert "Resume after account reconnect" in dashboard.text
        assert "I reviewed this exact video and every destination detail" in dashboard.text
        assert "'/submit'" in dashboard.text
        assert client.get("/api/publishing/status").json() == {"worker_online": False, "platforms": [], "manual_submission_enabled": False}
        PublisherWorkerPresence(runtime.database.session_factory).heartbeat("test-publisher", {"youtube"})
        assert client.get("/api/publishing/status").json() == {"worker_online": True, "platforms": ["youtube"], "manual_submission_enabled": True}
        assert client.get("/api/publishing/ready-videos").json()[0]["job_id"] == "job-1"
        body = {"job_id": "job-1", "destinations": {"yt": {"title": "A real test", "caption": "A sourced description", "tags": ["test"]}}}
        assert client.post("/api/publishing/drafts", json=body).status_code == 403
        created = client.post("/api/publishing/drafts", json=body, headers={"x-csrf-token": csrf})
        assert created.status_code == 201, created.text
        assert created.json()["asset_sha256"] == digest
        assert created.json()["destinations"] == [{"account_id": "yt", "platform": "youtube", "external_account_id": "UC-real", "state": "draft"}]
        listed = client.get("/api/publishing/drafts").json()
        assert listed[0]["destinations"][0]["metadata"]["title"] == "A real test"
        assert listed[0]["asset_sha256"] == digest
        assert client.get(listed[0]["video_url"]).content == video.read_bytes()
        assert Path(tmp_path / "publishing" / "staging" / f"{digest}.mp4").read_bytes() == video.read_bytes()
        submit_url = f"/api/publishing/drafts/{created.json()['id']}/submit"
        assert client.post(submit_url, json={"reviewed_identity": listed[0]["reviewed_identity"]}).status_code == 403
        assert client.post(submit_url, json={"reviewed_identity": "0" * 64}, headers={"x-csrf-token": csrf}).status_code == 409
        submitted = client.post(submit_url, json={"reviewed_identity": listed[0]["reviewed_identity"]}, headers={"x-csrf-token": csrf})
        assert submitted.status_code == 200 and submitted.json()["state"] == "queued"
        assert client.get("/api/publishing/drafts").json()[0]["destinations"][0]["state"] == "pending"
        assert client.post(submit_url, json={"reviewed_identity": listed[0]["reviewed_identity"]}, headers={"x-csrf-token": csrf}).status_code == 409
        assert client.post("/api/publishing/drafts", json=body, headers={"x-csrf-token": csrf}).status_code == 409
        with runtime.database.session_factory.begin() as session:
            delivery = session.scalar(select(DestinationDeliveryRecord))
            delivery.state = "unknown_outcome"
            delivery.remote_session_id = runtime.token_cipher.encrypt({"session_id": "saved-session"})
            delivery.error_message = "remote upload outcome is unknown"
            session.add(DeliveryAttemptRecord(id="attempt-1", delivery_id=delivery.id, claim_token="claim-1", kind="upload", state="unknown_outcome", remote_session_id=delivery.remote_session_id, remote_id=None, error_message=delivery.error_message, started_at=now, finished_at=now))
        destination = client.get("/api/publishing/drafts").json()[0]["destinations"][0]
        assert destination["can_inspect"] and not destination["can_resume"]
        assert destination["attempts"][0]["kind"] == "upload"
        assert destination["attempts"][0]["state"] == "unknown_outcome"
        assert "remote_session_id" not in destination["attempts"][0]
        action_url = f"/api/publishing/deliveries/{destination['id']}/actions"
        assert client.post(action_url, json={"action": "inspect"}).status_code == 403
        assert client.post(action_url, json={"action": "resume"}, headers={"x-csrf-token": csrf}).status_code == 409
        requested = client.post(action_url, json={"action": "inspect"}, headers={"x-csrf-token": csrf})
        assert requested.status_code == 200 and requested.json()["state"] == "pending"
        assert client.get("/api/publishing/drafts").json()[0]["destinations"][0]["requested_action"] == "inspect"
        assert client.post(action_url, json={"action": "inspect"}, headers={"x-csrf-token": csrf}).status_code == 409
        with runtime.database.session_factory.begin() as session:
            session.get(DestinationDeliveryRecord, destination["id"]).requested_action = None
            session.get(DestinationDeliveryRecord, destination["id"]).state = "auth_required"
            session.get(SocialAccountRecord, "yt").status = "reconnect_required"
        assert not client.get("/api/publishing/drafts").json()[0]["destinations"][0]["can_retry_after_reconnect"]
        assert client.post(action_url, json={"action": "retry_after_reconnect"}, headers={"x-csrf-token": csrf}).status_code == 409
        with runtime.database.session_factory.begin() as session:
            session.get(SocialAccountRecord, "yt").status = "connected"
        assert client.get("/api/publishing/drafts").json()[0]["destinations"][0]["can_retry_after_reconnect"]
        requeued = client.post(action_url, json={"action": "retry_after_reconnect"}, headers={"x-csrf-token": csrf})
        assert requeued.status_code == 200 and requeued.json()["state"] == "unknown_outcome"
