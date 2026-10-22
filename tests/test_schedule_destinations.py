"""Per-schedule account plans survive through the atomic topic-to-job handoff."""

from pathlib import Path

from fastapi.testclient import TestClient

from tubeforge.api.app import create_app
from tubeforge.core.config import AppConfig, AuthConfig, DatabaseConfig, Settings
from tubeforge.db.models import Base


def test_schedules_keep_separate_account_plans_and_reject_disabled_destinations(tmp_path: Path) -> None:
    settings = Settings(app=AppConfig(name="test", environment="test"), database=DatabaseConfig(url=f"sqlite:///{tmp_path / 'schedules.db'}"), auth=AuthConfig(enabled=True))
    app = create_app(settings)
    Base.metadata.create_all(app.state.database.engine)
    with TestClient(app) as client:
        app.state.runtime.auth.create_admin("operator", "correct-horse-battery-staple")
        assert client.post("/login", json={"username": "operator", "password": "correct-horse-battery-staple"}).status_code == 200
        csrf = {"x-csrf-token": client.cookies.get("tubeforge_csrf")}
        accounts = []
        for platform, name, category in (("youtube", "Virtual World Master", "Tech"), ("instagram", "History Channel", "History")):
            response = client.post("/api/social-accounts", json={"platform": platform, "display_name": name, "category": category, "default_description": f"Default for {name}"}, headers=csrf)
            assert response.status_code == 201
            accounts.append(response.json())

        def schedule(name: str, ids: list[str], description: str | None = None):
            return client.post("/api/schedules", json={"name": name, "cron": "0 9 * * *", "options": {"destination_account_ids": ids, "video_description": description}}, headers=csrf)

        assert schedule("Invalid", ["missing"]).status_code == 422
        assert schedule("Duplicate", [accounts[0]["id"], accounts[0]["id"]]).status_code == 422
        tech = schedule("Tech daily", [accounts[0]["id"]])
        history = schedule("History daily", [accounts[1]["id"]], "A custom history caption")
        assert tech.status_code == history.status_code == 201
        saved = {item["id"]: item for item in client.get("/api/schedules").json()}
        assert saved[tech.json()["id"]]["options"]["destination_account_ids"] == [accounts[0]["id"]]
        assert saved[history.json()["id"]]["options"]["destination_account_ids"] == [accounts[1]["id"]]

        assert client.post("/api/topics", json={"title": "Virtual worlds"}, headers=csrf).status_code == 201
        first = client.post(f"/api/schedules/{tech.json()['id']}/run", headers=csrf).json()
        assert first["state"] == "created"
        assert client.get(f"/api/jobs/{first['job_id']}/destination-intents").json() == [{"account_id": accounts[0]["id"], "platform": "youtube", "account_name": "Virtual World Master", "category": "Tech", "description": "Default for Virtual World Master"}]

        assert client.post("/api/topics", json={"title": "Ancient cities"}, headers=csrf).status_code == 201
        second = client.post(f"/api/schedules/{history.json()['id']}/run", headers=csrf).json()
        assert second["state"] == "created"
        assert app.state.runtime.jobs.video_description(second["job_id"]) == "A custom history caption"
        assert client.get(f"/api/jobs/{second['job_id']}/destination-intents").json() == [{"account_id": accounts[1]["id"], "platform": "instagram", "account_name": "History Channel", "category": "History", "description": "A custom history caption"}]

        assert client.post("/api/topics", json={"title": "A third topic"}, headers=csrf).status_code == 201
        assert client.post(f"/api/social-accounts/{accounts[1]['id']}/disable", headers=csrf).status_code == 204
        blocked = client.post(f"/api/schedules/{history.json()['id']}/run", headers=csrf).json()
        assert blocked["state"] == "invalid_request"
        assert "disabled" in blocked["reason"]
        assert [item["title"] for item in client.get("/api/topics").json() if item["status"] == "ready"] == ["A third topic"]
        dashboard = client.get("/").text
        assert "channelAccountGrid" in dashboard
        assert "channelTopicList" in dashboard
        assert "channelScheduleList" in dashboard
