from argparse import Namespace
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from tubeforge.db.repositories import JobRepository
from tubeforge.db.session import create_database
from tubeforge.core.config import DatabaseConfig
from tubeforge.domain.contracts import ContentRequest, SourceReference


def test_fresh_sqlite_database_upgrades_to_head(tmp_path: Path) -> None:
    repository_root = Path(__file__).resolve().parents[1]
    database_path = tmp_path / "migrated.db"
    database_url = f"sqlite:///{database_path}"
    config = Config(str(repository_root / "alembic.ini"))
    config.set_main_option("script_location", str(repository_root / "migrations"))
    config.cmd_opts = Namespace(x=[f"database_url={database_url}"])

    command.upgrade(config, "head")

    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "20260831_0015"
            assert connection.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='heavy_work_leases'")).scalar_one() == "heavy_work_leases"
            assert connection.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='publication_observations'")).scalar_one() == "publication_observations"
            assert connection.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='analytics_snapshots'")).scalar_one() == "analytics_snapshots"
            assert connection.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='next_video_briefs'")).scalar_one() == "next_video_briefs"
            assert connection.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='job_events'")).scalar_one() == "job_events"
            assert connection.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='source_media'")).scalar_one() == "source_media"
            assert connection.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='creator_sources'")).scalar_one() == "creator_sources"
    finally:
        engine.dispose()


def test_alembic_creates_missing_sqlite_parent(tmp_path: Path) -> None:
    repository_root = Path(__file__).resolve().parents[1]
    database_path = tmp_path / "missing" / "parent" / "migrated.db"
    config = Config(str(repository_root / "alembic.ini"))
    config.set_main_option("script_location", str(repository_root / "migrations"))
    config.cmd_opts = Namespace(x=[f"database_url=sqlite:///{database_path}"])
    command.upgrade(config, "head")
    assert database_path.is_file()


def test_upgrade_from_m4_revision(tmp_path: Path) -> None:
    repository_root = Path(__file__).resolve().parents[1]
    database_url = f"sqlite:///{tmp_path / 'upgrade.db'}"
    config = Config(str(repository_root / "alembic.ini")); config.set_main_option("script_location", str(repository_root / "migrations"))
    config.cmd_opts = Namespace(x=[f"database_url={database_url}"])
    command.upgrade(config, "20260803_0002")
    command.upgrade(config, "head")
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            assert connection.execute(text("SELECT attempt_count FROM pipeline_jobs")).keys() == ["attempt_count"]
    finally:
        engine.dispose()


def test_upgrade_from_worker_lease_revision_adds_generation_cache(tmp_path: Path) -> None:
    repository_root = Path(__file__).resolve().parents[1]
    database_url = f"sqlite:///{tmp_path / 'worker-upgrade.db'}"
    config = Config(str(repository_root / "alembic.ini")); config.set_main_option("script_location", str(repository_root / "migrations"))
    config.cmd_opts = Namespace(x=[f"database_url={database_url}"])
    command.upgrade(config, "20260803_0003")
    command.upgrade(config, "head")
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            assert connection.execute(text("SELECT cache_key FROM generation_cache")).keys() == ["cache_key"]
    finally:
        engine.dispose()


def test_m8_upgrade_keeps_legacy_job_states_readable_and_nonrunnable(tmp_path: Path) -> None:
    """M9/M10 must never deserialize an M8 job into an unknown enum value."""
    repository_root = Path(__file__).resolve().parents[1]
    database_path = tmp_path / "m8-upgrade.db"
    database_url = f"sqlite:///{database_path}"
    config = Config(str(repository_root / "alembic.ini")); config.set_main_option("script_location", str(repository_root / "migrations"))
    config.cmd_opts = Namespace(x=[f"database_url={database_url}"])
    command.upgrade(config, "20260803_0005")
    states = (
        "preview_approval_required", "private_upload_ready", "private_uploading",
        "publish_approval_required", "published", "final_rendering",
    )
    now = "2026-08-10 00:00:00"
    request = ContentRequest(
        topic="Rain", angle="Explainer", target_duration_seconds=60, language="en-IN",
        audience="general", prompt_version="test-v1",
        sources=(SourceReference(source_id="source-1", url="https://example.invalid/rain", title="Rain"),),
    ).model_dump_json()
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            for index, state in enumerate(states):
                connection.execute(text("""INSERT INTO pipeline_jobs
                    (id, request_json, state, resume_state, failure_message, created_at, updated_at, attempt_count)
                    VALUES (:id, :request, :state, NULL, NULL, :now, :now, 0)"""),
                    {"id": f"legacy-{index}", "request": request, "state": state, "now": now})
            connection.execute(text("""INSERT INTO approvals (id, job_id, gate, status, created_at)
                VALUES ('legacy-approval', 'legacy-0', 'preview', 'approved', :now)"""), {"now": now})
        command.upgrade(config, "head")
    finally:
        engine.dispose()

    database = create_database(DatabaseConfig(url=database_url))
    try:
        jobs = JobRepository(database.session_factory)
        assert [jobs.get(f"legacy-{index}").state.value for index in range(len(states))] == list(states)
        assert jobs.claim_oldest_eligible("worker", now=datetime.now(UTC), lease_seconds=60).id == "legacy-5"
        with database.engine.connect() as connection:
            assert connection.execute(text("SELECT actor, reviewed_identity, audit_json FROM approvals WHERE id = 'legacy-approval'")).one() == (None, None, None)
    finally:
        database.dispose()
