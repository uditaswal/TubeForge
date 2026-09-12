from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from tubeforge.api.app import create_app
from tubeforge.core.config import AppConfig, AuthConfig, DatabaseConfig, Settings


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
        assert client.post("/login", json={"username": "operator", "password": "wrong"}).status_code == 401
        assert client.post("/login", json={"username": "operator", "password": "correct-horse-battery-staple"}).status_code == 200
        assert client.post("/api/topics", json={"title": "A topic"}).status_code == 403
        csrf = client.cookies.get("tubeforge_csrf")
        assert client.post("/api/topics", json={"title": "A topic"}, headers={"x-csrf-token": csrf}).status_code == 201
        assert client.post("/logout", headers={"x-csrf-token": csrf}).status_code == 200
        assert client.get("/api/topics").status_code == 401
