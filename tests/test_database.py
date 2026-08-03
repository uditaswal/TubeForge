from pathlib import Path

from sqlalchemy import text

from tubeforge.core.config import DatabaseConfig
from tubeforge.db.session import create_database


def test_sqlite_connections_enable_wal_and_busy_timeout(tmp_path: Path) -> None:
    database = create_database(
        DatabaseConfig(url=f"sqlite:///{tmp_path / 'tubeforge.db'}", busy_timeout_ms=3210)
    )
    try:
        with database.engine.connect() as connection:
            assert connection.execute(text("PRAGMA journal_mode")).scalar_one().lower() == "wal"
            assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
            assert connection.execute(text("PRAGMA busy_timeout")).scalar_one() == 3210
    finally:
        database.dispose()
