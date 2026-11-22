"""Source-video clip jobs have no script package; their thumbnail must still be creatable, with operator notes."""
from pathlib import Path
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


def test_clip_job_thumbnail_is_created_and_keeps_notes(tmp_path: Path) -> None:
    settings = Settings(app=AppConfig(name="TubeForge test", environment="test"), database=DatabaseConfig(url=f"sqlite:///{tmp_path / 'clip.db'}"), auth=AuthConfig(enabled=True))
    settings.pipeline.voice.artifact_root = tmp_path / "artifacts"
    app = create_app(settings)
    Base.metadata.create_all(app.state.database.engine)
    with TestClient(app) as client:
        app.state.runtime.auth.create_admin("operator", "correct-horse-battery-staple")
        assert client.post("/login", json={"username": "operator", "password": "correct-horse-battery-staple"}).status_code == 200
        csrf = {"x-csrf-token": client.cookies.get("tubeforge_csrf")}
        job_id = client.post("/api/videos", json={"title": "Clip stand-in", "notes": ["x"]}, headers=csrf).json()["id"]
        folder = settings.pipeline.voice.artifact_root / job_id
        folder.mkdir(parents=True)
        video = folder / "final.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=navy:s=64x112:r=10:d=4", "-frames:v", "40", "-threads", "1", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-y", str(video)], check=True, timeout=30)
        meta = folder / "metadata.json"
        meta.write_text(json.dumps({"title": "A CLIP TITLE", "description": "d", "tags": ["shorts"]}))
        with app.state.database.engine.begin() as connection:
            connection.execute(text("UPDATE pipeline_jobs SET state='publication_approval_required' WHERE id=:id"), {"id": job_id})
        artifacts = app.state.runtime.artifacts
        artifacts.save(Artifact(job_id, JobState.FINAL_RENDERING, "final", str(video), hashlib.sha256(video.read_bytes()).hexdigest(), {}))
        artifacts.save(Artifact(job_id, JobState.PUBLICATION_PREPARING, "metadata", str(meta), hashlib.sha256(meta.read_bytes()).hexdigest(), {}))
        created = client.post(f"/api/publishing/jobs/{job_id}/thumbnail", json={"notes": "close-up, bold text"}, headers=csrf)
        assert created.status_code == 200, created.text
        assert created.json()["notes"] == "close-up, bold text" and created.json()["text"] == "A CLIP TITLE" and created.json()["portrait"] is True
        assert client.get(f"/api/publishing/jobs/{job_id}/thumbnail.jpg").status_code == 200
        again = client.post(f"/api/publishing/jobs/{job_id}/thumbnail", json={"text": "NEW TEXT"}, headers=csrf)
        assert again.json()["text"] == "NEW TEXT" and again.json()["notes"] == "close-up, bold text"
        assert client.get(f"/api/publishing/jobs/{job_id}/suggestion").json()["title"] == "A CLIP TITLE"


def test_clip_jobs_expose_source_title_and_clip_titles(tmp_path: Path) -> None:
    from types import SimpleNamespace
    from tubeforge.api.app import _clip_titles
    (tmp_path / "source_metadata.json").write_text(json.dumps({"title": "Real Source Title"}))
    (tmp_path / "clip_manifest.json").write_text(json.dumps({"clips": [{"candidate": {"hook_title": "First clip"}}, {"candidate": {"hook_title": "Second clip"}}, {"candidate": {}}]}))
    files = [SimpleNamespace(name="source_metadata", path=str(tmp_path / "source_metadata.json")), SimpleNamespace(name="clip_manifest", path=str(tmp_path / "clip_manifest.json"))]
    runtime = SimpleNamespace(artifacts=SimpleNamespace(list_for_job=lambda job_id: files))
    clip_job = SimpleNamespace(id="j", request=SimpleNamespace(prompt_version="source-clip-v1"))
    assert _clip_titles(clip_job, runtime) == {"display_title": "Real Source Title", "clip_titles": ["First clip", "Second clip"]}
    assert _clip_titles(SimpleNamespace(id="j", request=SimpleNamespace(prompt_version="m6-content-v8")), runtime) == {}
