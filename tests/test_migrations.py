from argparse import Namespace
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text


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
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "20260803_0003"
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
