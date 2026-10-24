"""Signed-in Studio exposes audio and video health through durable QA artifacts."""
from __future__ import annotations

import asyncio

import httpx

from tubeforge.api.app import create_app
from tubeforge.core.config import AppConfig, AuthConfig, DatabaseConfig, Settings
from tubeforge.db.models import Base


def test_signed_in_generation_record_exposes_audio_report_states(tmp_path):
    settings = Settings(app=AppConfig(name="test", environment="test"),
                        database=DatabaseConfig(url=f"sqlite:///{tmp_path / 'studio.db'}"),
                        auth=AuthConfig(enabled=True))
    app = create_app(settings)
    Base.metadata.create_all(app.state.database.engine)
    app.state.runtime.auth.create_admin("reviewer", "correct-horse-battery-staple")

    async def verify():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://studio") as client:
            assert (await client.get("/", follow_redirects=False)).status_code == 303
            assert (await client.post("/login", json={"username": "reviewer", "password": "correct-horse-battery-staple"})).status_code == 200
            page = await client.get("/")
            assert page.status_code == 200
            assert 'id="generationAudio"' in page.text
            assert "Audio report pending" in page.text and "Could not load audio report" in page.text
            assert 'id="generationVideo"' in page.text
            assert "Video report pending" in page.text and "Could not load video report" in page.text
            assert "Black frames" in page.text and "Frozen frames" in page.text
            assert "final_qa" in page.text and "preview_qa" in page.text
            assert (await client.get("/api/jobs/missing/artifacts/final_qa")).status_code == 404

    try:
        asyncio.run(verify())
    finally:
        app.state.database.dispose()
