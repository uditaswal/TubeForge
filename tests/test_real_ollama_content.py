"""Opt-in proof that production Shorts use a real local source-grounded writer."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tubeforge.core.config import DatabaseConfig, OllamaProviderConfig
from tubeforge.db.models import Base
from tubeforge.db.repositories import GenerationCacheRepository
from tubeforge.db.session import create_database
from tubeforge.domain.contracts import ContentRequest, SourceReference
from tubeforge.providers.content.ollama import OllamaContentProvider


OLLAMA_URL = os.environ.get("TUBEFORGE_SMOKE_OLLAMA_URL")
OLLAMA_MODEL = os.environ.get("TUBEFORGE_SMOKE_OLLAMA_MODEL", "qwen2.5:3b")


@pytest.mark.skipif(not OLLAMA_URL, reason="set TUBEFORGE_SMOKE_OLLAMA_URL for the real local writer smoke")
def test_real_ollama_generates_source_grounded_shorts_package(tmp_path: Path) -> None:
    database = create_database(DatabaseConfig(url=f"sqlite:///{tmp_path / 'ollama-smoke.db'}"))
    Base.metadata.create_all(database.engine)
    provider = OllamaContentProvider(
        OllamaProviderConfig(
            base_url=OLLAMA_URL or "http://ollama:11434",
            model=OLLAMA_MODEL,
            inference_timeout_seconds=900,
            retries=1,
            validation_retries=2,
            prompt_template_version="m6-content-v4",
        ),
        GenerationCacheRepository(database.session_factory),
    )
    request = ContentRequest(
        topic="The debugging habit that saves hours",
        angle="Start from the first observable failure and test one assumption at a time.",
        target_duration_seconds=45,
        language="en",
        audience="software engineers",
        prompt_version="real-ollama-shorts-v5",
        sources=(
            SourceReference(
                source_id="approved-debugging-brief",
                url="https://example.invalid/approved-debugging-brief",
                title="Operator-approved debugging brief",
                excerpt=(
                    "Start at the first point where observed behavior differs from expected behavior. "
                    "State one assumption about that boundary, make the smallest test that could falsify it, "
                    "change one variable, and record the result before moving to the next boundary."
                ),
            ),
        ),
        notes=("Do not add statistics or quotations.", "Use practical language for working engineers."),
        review_mode="manual",
        preset_name="shorts",
        aspect_ratio="9:16",
    )
    try:
        package = provider.generate_package(request)
        words = sum(len(section.narration.split()) for section in package.script_sections)
        assert 108 <= words <= 166
        assert len(package.script_sections) >= 6
        assert package.script_sections[0].narration.rstrip().endswith((".", "!", "?", "…"))
        assert all(claim.source_ids == ("approved-debugging-brief",) for claim in package.claims)

        evidence = {
            "provider": provider.provider_name,
            "model": OLLAMA_MODEL,
            "provenance": provider.last_provenance,
            "usage": provider.last_usage,
            "package": package.model_dump(mode="json"),
        }
        destination = Path(__file__).resolve().parents[1] / "artifacts" / "smoke" / "ollama_shorts_content.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(".part.json")
        temporary.write_text(json.dumps(evidence, indent=2, default=str), encoding="utf-8")
        temporary.replace(destination)
    finally:
        database.dispose()
