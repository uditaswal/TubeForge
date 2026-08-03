"""Application factory and operational endpoints."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from tubeforge.core.config import Settings, load_settings
from tubeforge.db.session import Database, create_database


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create the HTTP application using explicit settings when supplied."""
    application_settings = settings or load_settings()
    database = create_database(application_settings.database)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
        try:
            yield
        finally:
            database.dispose()

    app = FastAPI(title=application_settings.app.name, lifespan=lifespan)
    app.state.settings = application_settings
    app.state.database = database

    @app.get("/healthz", tags=["operations"])
    def healthz() -> dict[str, str]:
        """Report process and database reachability without exposing settings."""
        try:
            with database.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="database unavailable",
            ) from error
        return {"status": "ok", "database": "ok"}

    return app
