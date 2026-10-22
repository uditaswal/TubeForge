"""Account choices are local, durable generation metadata."""
from pathlib import Path
from datetime import UTC, datetime
import hashlib
import json
import subprocess

from fastapi.testclient import TestClient
from sqlalchemy import text

from tubeforge.api.app import create_app
from tubeforge.core.config import AppConfig, AuthConfig, DatabaseConfig, Settings
from tubeforge.db.models import Base
from tubeforge.db.repositories import Artifact
from tubeforge.domain.states import JobState


def test_video_creation_snapshots_exact_accounts_and_description_defaults(tmp_path: Path) -> None:
    settings = Settings(app=AppConfig(name="TubeForge test", environment="test"), database=DatabaseConfig(url=f"sqlite:///{tmp_path / 'intents.db'}"), auth=AuthConfig(enabled=True))
    settings.pipeline.voice.artifact_root = tmp_path / "artifacts"
    app = create_app(settings)
    Base.metadata.create_all(app.state.database.engine)
    with TestClient(app) as client:
        app.state.runtime.auth.create_admin("operator", "correct-horse-battery-staple")
        assert client.post("/login", json={"username": "operator", "password": "correct-horse-battery-staple"}).status_code == 200
        csrf = {"x-csrf-token": client.cookies.get("tubeforge_csrf")}
        ids = []
        for platform, name, category, default in (("youtube", "Virtual World Master", "Tech", "Tech channel default"), ("snapchat", "History Channel", "History", "History channel default")):
            response = client.post("/api/social-accounts", json={"platform": platform, "display_name": name, "category": category, "default_description": default}, headers=csrf)
            assert response.status_code == 201
            ids.append(response.json()["id"])
        brief = {"title": "The first computing machines", "notes": ["Explain the mechanism"], "destination_account_ids": ids}
        assert client.post("/api/videos", json={**brief, "destination_account_ids": [ids[0], ids[0]]}, headers=csrf).status_code == 422
        assert client.post("/api/videos", json={**brief, "destination_account_ids": [ids[0], "missing"]}, headers=csrf).status_code == 422
        assert client.get("/api/jobs").json() == []
        created = client.post("/api/videos", json=brief, headers=csrf)
        assert created.status_code == 201, created.text
        job_id = created.json()["id"]
        intents = created.json()["destination_intents"]
        assert {row["account_id"]: row["description"] for row in intents} == {ids[0]: "Tech channel default", ids[1]: "History channel default"}
        assert {row["category"] for row in intents} == {"Tech", "History"}
        assert client.get(f"/api/jobs/{job_id}/destination-intents").json() == intents
        assert client.put(f"/api/social-accounts/{ids[0]}/profile", json={"display_name": "Renamed", "category": "Science", "default_description": "Changed"}, headers=csrf).status_code == 200
        assert client.get(f"/api/jobs/{job_id}/destination-intents").json() == intents
        custom = client.post("/api/videos", json={**brief, "description": "One description for both destinations"}, headers=csrf)
        assert custom.status_code == 201
        assert custom.json()["video_description"] == "One description for both destinations"
        assert {row["description"] for row in custom.json()["destination_intents"]} == {"One description for both destinations"}
        with app.state.database.engine.begin() as connection:
            connection.execute(text("UPDATE pipeline_jobs SET state='script_approval_required' WHERE id=:id"), {"id": custom.json()["id"]})
        revised = app.state.runtime.jobs.create_scene_revision("revised-job", custom.json()["id"], app.state.runtime.jobs.get(custom.json()["id"]).request, (), scene_id="scene-1", actor="test", content_checksum="a" * 64)
        assert revised.id == "revised-job"
        assert app.state.runtime.jobs.destination_intents(revised.id) == custom.json()["destination_intents"]
        assert app.state.runtime.jobs.video_description(revised.id) == "One description for both destinations"
        assert client.post(f"/api/social-accounts/{ids[1]}/disable", headers=csrf).status_code == 204
        assert client.post("/api/videos", json=brief, headers=csrf).status_code == 422
        assert client.get(f"/api/jobs/{job_id}/destination-intents").json() == intents
        no_destination = client.post("/api/videos", json={"title": "Unassigned", "notes": ["A note"], "description": "Keep this video description"}, headers=csrf)
        assert no_destination.status_code == 201
        assert no_destination.json()["video_description"] == "Keep this video description"
        assert no_destination.json()["destination_intents"] == []
        no_destination_id = no_destination.json()["id"]
        assert "videoDestinationIntent" in client.get("/").text
        assert "no upload or online connection starts" in client.get("/").text
        video_path = settings.pipeline.voice.artifact_root / job_id / "final.mp4"
        video_path.parent.mkdir(parents=True)
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=navy:s=64x112:r=1:d=1", "-frames:v", "1", "-threads", "1", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-y", str(video_path)], check=True, timeout=20)
        media = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,width,height", "-of", "json", str(video_path)], capture_output=True, text=True, check=True, timeout=20).stdout)
        assert (media["streams"][0]["codec_name"], media["streams"][0]["width"], media["streams"][0]["height"]) == ("h264", 64, 112)
        digest = hashlib.sha256(video_path.read_bytes()).hexdigest()
        with app.state.database.engine.begin() as connection:
            connection.execute(text("UPDATE pipeline_jobs SET state='final_ready' WHERE id=:id"), {"id": job_id})
            connection.execute(text("UPDATE social_accounts SET status='connected', external_account_id='UC-tested', credential_ciphertext='test-only', last_validated_at=:now WHERE id=:id"), {"id": ids[0], "now": datetime.now(UTC)})
        app.state.runtime.artifacts.save(Artifact(job_id, JobState.FINAL_RENDERING, "final", str(video_path), digest, {}))
        ready = client.get("/api/publishing/ready-videos").json()
        assert ready[0]["job_id"] == job_id
        assert ready[0]["destination_intents"] == intents
        dashboard = client.get("/").text
        assert "plannedVideoDestinations" in dashboard
        assert "applyVideoIntent" in dashboard
        draft = client.post("/api/publishing/drafts", json={"job_id": job_id, "destinations": {ids[0]: {"title": "The first computing machines", "caption": intents[1]["description"] if intents[1]["account_id"] == ids[0] else intents[0]["description"], "tags": ["history"]}}}, headers=csrf)
        assert draft.status_code == 201, draft.text
        assert draft.json()["asset_sha256"] == digest
        assert draft.json()["destinations"][0]["state"] == "draft"
    reopened = create_app(settings)
    with TestClient(reopened) as client:
        assert client.post("/login", json={"username": "operator", "password": "correct-horse-battery-staple"}).status_code == 200
        assert client.get(f"/api/jobs/{job_id}/destination-intents").json() == intents
        assert reopened.state.runtime.jobs.video_description(no_destination_id) == "Keep this video description"
