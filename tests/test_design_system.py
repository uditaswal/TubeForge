"""The design system stays consistent: tokens, guide, DESIGN.md and checker agree."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _checker():
    spec = importlib.util.spec_from_file_location("check_design", ROOT / "scripts" / "check_design.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_design_check_passes(capsys):
    checker = _checker()
    assert checker.main(["check_design.py"]) == 0, capsys.readouterr().out


def test_checker_catches_common_mistakes(tmp_path, monkeypatch):
    checker = _checker()
    guide = tmp_path / "guide.html"
    guide.write_text(
        '<section id="x" data-component="x"><div class="bg-slate-800 text-2xl rounded-xl shadow-md bg-tf-ok/20 '
        'text-[#fff] p-[13px]" style="color:red"><button>Go</button><input id="a"></div></section>'
    )
    monkeypatch.setattr(checker, "GUIDE", guide)
    monkeypatch.setattr(checker, "ROOT", tmp_path)
    checker.errors.clear()
    checker.check_classes()
    checker.check_accessibility()
    joined = "\n".join(checker.errors)
    for expected in (
        "Tailwind palette",
        "not in the type scale",
        "not an allowed radius",
        "shadows are not used",
        "opacity modifier",
        "arbitrary value",
        "inline style",
        "without type=",
        "has no <label",
    ):
        assert expected in joined, f"checker missed: {expected}\n{joined}"


def test_contrast_math_matches_wcag_reference():
    checker = _checker()
    assert round(checker.contrast("#000000", "#ffffff"), 1) == 21.0
    assert round(checker.contrast("#777777", "#ffffff"), 2) == 4.48


def test_shared_design_files_are_public_and_the_shell_uses_them(tmp_path):
    """/static/ui is served without sign-in, and the standalone pages load the design system and its shell."""
    from fastapi.testclient import TestClient

    from tubeforge.api.app import create_app
    from tubeforge.core.config import AppConfig, AuthConfig, DatabaseConfig, Settings
    from tubeforge.db.models import Base
    from tubeforge.db.session import create_database

    settings = Settings(
        app=AppConfig(name="test", environment="test"),
        database=DatabaseConfig(url=f"sqlite:///{tmp_path / 'design.db'}"),
        auth=AuthConfig(enabled=True),
    )
    Base.metadata.create_all(create_database(settings.database).engine)
    with TestClient(create_app(settings)) as client:
        tokens = client.get("/static/ui/tokens.css")
        assert tokens.status_code == 200 and "--tf-bg:" in tokens.text
        assert client.get("/static/ui/tubeforge-ui.js").status_code == 200
        # Encoded traversal must not leave the static folder (the test client would normalise a plain "../").
        escaped = client.get("/static/ui/%2e%2e/%2e%2e/config/production.yaml", follow_redirects=False)
        assert escaped.status_code == 404 and "auth" not in escaped.text.lower()
        assert client.get("/batch", follow_redirects=False).status_code == 303  # pages stay private

        client.app.state.runtime.auth.create_admin("design-test", "design-test-password-123")
        client.post("/login", json={"username": "design-test", "password": "design-test-password-123"})
        page = client.get("/settings").text
        assert "/static/ui/tokens.css" in page and "cdn.tailwindcss.com/3.4.17" in page
        assert 'class="tf-nav ' in page and 'data-nav-open' in page
        assert "!grid-cols-1" in page, "legacy .grid collision guard missing from the shell"
        assert 'no-underline' in page
        assert 'id="signOutButton"' in page
