"""Configuration-only provider selection at the application boundary."""

from sqlalchemy.orm import Session, sessionmaker

from tubeforge.core.config import Settings
from tubeforge.db.repositories import GenerationCacheRepository
from tubeforge.domain.providers import ContentProvider
from tubeforge.providers.content.codex_cli import CodexCliContentProvider
from tubeforge.providers.fake import FakeContentProvider, FixedScriptContentProvider


def create_content_provider(settings: Settings, session_factory: sessionmaker[Session]) -> ContentProvider:
    """Return fake content by default; create Codex only after explicit selection."""
    if settings.pipeline.content_provider == "fake":
        return FakeContentProvider()
    if settings.pipeline.content_provider == "fixed":
        return FixedScriptContentProvider()
    return CodexCliContentProvider(settings.pipeline.codex, GenerationCacheRepository(session_factory))
