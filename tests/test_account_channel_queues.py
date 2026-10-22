"""Account-first topic queues never feed another channel's schedule."""

from argparse import Namespace
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from tubeforge.api.app import create_app
from tubeforge.core.config import AppConfig, DatabaseConfig, Settings
from tubeforge.db.models import Base


def test_channel_schedules_only_reserve_their_own_topics(tmp_path: Path) -> None:
    settings = Settings(app=AppConfig(name="test", environment="test"), database=DatabaseConfig(url=f"sqlite:///{tmp_path / 'channels.db'}"))
    app = create_app(settings)
    Base.metadata.create_all(app.state.database.engine)
    with TestClient(app) as client:
        accounts = []
        for platform, name in (("youtube", "Virtual World Master"), ("instagram", "History Channel")):
            result = client.post("/api/social-accounts", json={"platform": platform, "display_name": name, "category": "Tech" if platform == "youtube" else "History", "default_description": name + " default"})
            assert result.status_code == 201
            accounts.append(result.json())
        tech_id, history_id = (item["id"] for item in accounts)
        assert client.post("/api/topics", json={"title": "Wrong account", "account_id": "missing"}).status_code == 422
        legacy = client.post("/api/topics", json={"title": "Legacy topic"}).json()
        history = client.post("/api/topics", json={"title": "Ancient maps", "account_id": history_id}).json()
        tech = client.post("/api/topics", json={"title": "Virtual worlds", "account_id": tech_id}).json()
        assert [item["id"] for item in client.get("/api/topics", params={"account_id": tech_id}).json()] == [tech["id"]]
        assert [item["id"] for item in client.get("/api/topics", params={"account_id": history_id}).json()] == [history["id"]]

        invalid = client.post("/api/schedules", json={"name": "Wrong", "cron": "0 9 * * *", "account_id": tech_id, "options": {"destination_account_ids": [history_id]}})
        assert invalid.status_code == 422
        tech_schedule = client.post("/api/schedules", json={"name": "Tech daily", "cron": "0 9 * * *", "account_id": tech_id}).json()
        history_schedule = client.post("/api/schedules", json={"name": "History daily", "cron": "0 10 * * *", "account_id": history_id}).json()
        assert tech_schedule["account_id"] == tech_id
        assert [item["id"] for item in client.get("/api/schedules", params={"account_id": tech_id}).json()] == [tech_schedule["id"]]
        first = client.post(f"/api/schedules/{tech_schedule['id']}/run").json()
        assert first["state"] == "created" and first["topic_id"] == tech["id"]
        assert [item["account_id"] for item in client.get(f"/api/jobs/{first['job_id']}/destination-intents").json()] == [tech_id]
        assert client.post(f"/api/schedules/{tech_schedule['id']}/run").json()["state"] == "no_topic"
        second = client.post(f"/api/schedules/{history_schedule['id']}/run").json()
        assert second["state"] == "created" and second["topic_id"] == history["id"]
        assert [item["account_id"] for item in client.get(f"/api/jobs/{second['job_id']}/destination-intents").json()] == [history_id]
        assert app.state.runtime.topics.get(legacy["id"]).status == "ready"
        assert "Choose a channel" in client.get("/").text


def test_account_queue_migration_keeps_existing_items_unassigned(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    path = tmp_path / "migration.db"
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    config.cmd_opts = Namespace(x=[f"database_url=sqlite:///{path}"])
    command.upgrade(config, "20261022_0029")
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO topics (id,title,notes,priority,status,options_json,attempts,created_at,updated_at) VALUES ('old-topic','Existing','','0','ready','{}',0,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
        connection.execute(text("INSERT INTO schedules (id,name,cron,timezone,enabled,options_json,created_at,updated_at) VALUES ('old-schedule','Existing','0 9 * * *','UTC',1,'{}',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
    engine.dispose()
    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{path}")
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT account_id FROM topics WHERE id='old-topic'")) is None
        assert connection.scalar(text("SELECT account_id FROM schedules WHERE id='old-schedule'")) is None
        assert connection.scalar(text("SELECT count(*) FROM topics WHERE id='old-topic'")) == 1
        assert connection.scalar(text("SELECT count(*) FROM schedules WHERE id='old-schedule'")) == 1
    engine.dispose()
