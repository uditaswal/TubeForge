"""SQLite engine creation with safe connection-local pragmas."""

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from tubeforge.core.config import DatabaseConfig


@dataclass(frozen=True)
class Database:
    """Database resources owned by the application process."""

    engine: Engine
    session_factory: sessionmaker[Session]

    def dispose(self) -> None:
        """Release pooled database connections during application shutdown."""
        self.engine.dispose()


def create_database(settings: DatabaseConfig) -> Database:
    """Create a SQLite engine configured for WAL, foreign keys, and busy waits."""
    url = make_url(settings.url)
    database_path = url.database
    if database_path and database_path != ":memory:":
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(
        settings.url,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )

    @event.listens_for(engine, "connect")
    def configure_sqlite_connection(dbapi_connection: object, _: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute(f"PRAGMA busy_timeout={settings.busy_timeout_ms}")
            cursor.execute("PRAGMA journal_mode=WAL")
        finally:
            cursor.close()

    return Database(engine=engine, session_factory=sessionmaker(bind=engine, expire_on_commit=False))
