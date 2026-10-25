from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from tubeforge.api.app import create_app
from tubeforge.core.config import AppConfig, AuthConfig, DatabaseConfig, Settings
from tubeforge.domain.contracts import ContentRequest, SourceReference


def test_dashboard_requires_login_and_csrf_for_mutation(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]; db = tmp_path / "auth.db"
    config = Config(str(root / "alembic.ini")); config.set_main_option("script_location", str(root / "migrations")); config.cmd_opts = Namespace(x=[f"database_url=sqlite:///{db}"])
    command.upgrade(config, "head")
    settings = Settings(app=AppConfig(name="test", environment="test"), database=DatabaseConfig(url=f"sqlite:///{db}"), auth=AuthConfig(enabled=True))
    with TestClient(create_app(settings)) as client:
        runtime = client.app.state.runtime; runtime.auth.create_admin("operator", "correct-horse-battery-staple")
        assert client.get("/").status_code == 200  # TestClient follows login redirect.
        login_page = client.get("/login")
        assert login_page.status_code == 200
        assert "TubeForge Studio" in login_page.text
        assert "Signing in…" in login_page.text
        assert "aria-live" in login_page.text
        assert client.get("/api/jobs").status_code == 401
        assert client.get("/api/jobs/missing/diagnostics").status_code == 401
        assert client.post("/login", json={"username": "operator", "password": "wrong"}).status_code == 401
        assert client.post("/login", json={"username": "operator", "password": "correct-horse-battery-staple"}).status_code == 200
        dashboard = client.get("/", follow_redirects=False)
        assert dashboard.status_code == 200
        assert "presetSelect" in dashboard.text
        assert "Review script and sources" in dashboard.text
        assert r"split('\n')" in dashboard.text
        assert "Add licensed music" in dashboard.text
        assert "musicUpload" in dashboard.text
        assert "Publishing accounts" in dashboard.text
        assert "sidebar.id='studioSidebar'" in dashboard.text
        assert 'data-studio-nav="studio"' in dashboard.text
        assert 'data-studio-nav="publishing"' in dashboard.text
        assert 'data-studio-nav="accounts"' in dashboard.text
        assert 'data-studio-nav="scheduling"' in dashboard.text
        assert "pages.studio.append(overview,createPanel);pages.generations.append(generationList)" in dashboard.text
        assert 'window.addEventListener(\'hashchange\',showPage)' in dashboard.text
        assert '@media(max-width:760px)' in dashboard.text
        assert '.studio-sidebar.open{transform:translateX(0)}' in dashboard.text
        assert "Connections require verified platform authorization" in dashboard.text
        assert "Download diagnostics JSONL" in dashboard.text
        assert "Visual layout<select id=\"sceneLayout\"" in dashboard.text
        csrf_wrapper = dashboard.text.index("window.fetch=(url, init={})")
        scene_revision = dashboard.text.index("/api/jobs/${parent}/scene-revisions")
        assert csrf_wrapper < scene_revision
        assert "'x-csrf-token':decodeURIComponent(csrf)" in dashboard.text
        assert client.get("/api/jobs/missing/diagnostics").status_code == 404
        assert client.get("/api/social-accounts").status_code == 200
        runtime.jobs.create("diagnostics-auth", ContentRequest(topic="Rain", angle="Explainer", target_duration_seconds=45, language="en", audience="general", prompt_version="test-v1", sources=(SourceReference(source_id="rain", url="https://example.invalid/rain", title="Rain"),)))
        runtime.events.append("diagnostics-auth", "stage_execution", stage="content_generating", elapsed_ms=21, outcome="succeeded", memory_scope="container_lifetime", cgroup_peak_bytes=123)
        assert client.get("/api/jobs/diagnostics-auth/diagnostics").json()["stage_metrics"]["content_generating"]["elapsed_ms"] == 21
        assert '"elapsed_ms": 21' in client.get("/api/jobs/diagnostics-auth/diagnostics.jsonl").text
        assert client.post("/api/topics", json={"title": "A topic"}).status_code == 403
        csrf = client.cookies.get("tubeforge_csrf")
        assert client.post("/api/topics", json={"title": "A topic"}, headers={"x-csrf-token": csrf}).status_code == 201
        assert client.post("/logout", headers={"x-csrf-token": csrf}).status_code == 200
        assert client.get("/api/topics").status_code == 401


def test_signed_in_research_intake_explains_notes_are_not_evidence(tmp_path):
    from tubeforge.core.config import PipelineConfig, SourceIngestionConfig
    root = Path(__file__).resolve().parents[1]; db = tmp_path / "research-ui.db"
    config = Config(str(root / "alembic.ini")); config.set_main_option("script_location", str(root / "migrations")); config.cmd_opts = Namespace(x=[f"database_url=sqlite:///{db}"])
    command.upgrade(config, "head")
    settings = Settings(app=AppConfig(name="test", environment="test"), database=DatabaseConfig(url=f"sqlite:///{db}"), auth=AuthConfig(enabled=True), pipeline=PipelineConfig(sources=SourceIngestionConfig(research_enabled=True)))
    with TestClient(create_app(settings)) as client:
        client.app.state.runtime.auth.create_admin("operator", "correct-horse-battery-staple")
        assert client.post("/login", json={"username": "operator", "password": "correct-horse-battery-staple"}).status_code == 200
        assert "Codex researches primary sources before writing" in client.get("/").text
