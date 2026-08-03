"""SQLite engine creation with safe connection-local pragmas."""

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session, sessionmaker

from tubeforge.core.config import DatabaseConfig, REPOSITORY_ROOT


@dataclass(frozen=True)
class Database:
    """Database resources owned by the application process."""

    engine: Engine
    session_factory: sessionmaker[Session]

    def dispose(self) -> None:
        """Release pooled database connections during application shutdown."""
        self.engine.dispose()


def prepare_sqlite_database_url(value: str, *, project_root: Path = REPOSITORY_ROOT) -> URL:
    """Resolve a file-backed SQLite URL from the project root and create its parent.

    Non-SQLite URLs and SQLite memory/URI-memory targets are intentionally left
    untouched.  Returning SQLAlchemy's URL object avoids platform-specific URL
    escaping while giving application and Alembic identical path semantics.
    """
    url = make_url(value)
    if url.get_backend_name() != "sqlite" or not url.database:
        return url
    database = url.database
    if database == ":memory:" or database.startswith("file:") or url.query.get("mode") == "memory":
        return url
    path = Path(database)
    if not path.is_absolute():
        path = project_root / path
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return url.set(database=str(path))


def create_database(settings: DatabaseConfig) -> Database:
    """Create a SQLite engine configured for WAL, foreign keys, and busy waits."""
    url = prepare_sqlite_database_url(settings.url)

    engine = create_engine(
        url,
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
