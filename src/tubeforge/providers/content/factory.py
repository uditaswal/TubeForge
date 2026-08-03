"""Configuration-only provider selection at the application boundary."""

from sqlalchemy.orm import Session, sessionmaker

from tubeforge.core.config import Settings
from tubeforge.db.repositories import GenerationCacheRepository
from tubeforge.domain.providers import ContentProvider
from tubeforge.providers.content.codex_cli import CodexCliContentProvider
from tubeforge.providers.fake import FakeContentProvider


def create_content_provider(settings: Settings, session_factory: sessionmaker[Session]) -> ContentProvider:
    """Return fake content by default; create Codex only after explicit selection."""
    if settings.pipeline.provider == "fake":
        return FakeContentProvider()
    return CodexCliContentProvider(settings.pipeline.codex, GenerationCacheRepository(session_factory))
