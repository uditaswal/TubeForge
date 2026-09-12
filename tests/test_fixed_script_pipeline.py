"""M24/M25 deterministic script and offline visual-provider coverage."""

import re

from pathlib import Path

from tubeforge.core.config import FakeProviderConfig, Settings
from tubeforge.domain.contracts import ContentRequest, MediaSearchRequest, SourceReference
from tubeforge.providers.content.factory import create_content_provider
from tubeforge.providers.fake import FakeContentProvider, FakeMediaProvider, FixedScriptContentProvider


def _request() -> ContentRequest:
    return ContentRequest(topic="How TubeForge builds a local video", angle="A local pipeline demonstration", target_duration_seconds=60, language="en", audience="general", prompt_version="m24-fixed-v1", sources=(SourceReference(source_id="local-source", url="https://example.invalid/local", title="Local deterministic fixture"),))


def test_fixed_script_has_six_ordered_complete_scenes() -> None:
    package = FixedScriptContentProvider().generate_package(_request())
    assert len(package.script_sections) == len(package.scene_plans) == 6
    assert [section.scene_id for section in package.script_sections] == [scene.scene_id for scene in package.scene_plans]
    assert all(section.narration.strip() for section in package.script_sections)
    assert all(scene.search_queries[0].strip() for scene in package.scene_plans)
    # A 60-second Piper smoke needs substantially more than the original
    # 110-word fixture. Keep the deterministic script near a normal narration
    # budget while allowing real voices to vary in speaking rate.
    word_count = sum(len(re.findall(r"\b\w+\b", section.narration)) for section in package.script_sections)
    assert 145 <= word_count <= 200


def test_fixed_provider_is_configuration_selectable(tmp_path: Path) -> None:
    settings = Settings.model_validate({"app": {"name": "x", "environment": "test"}, "database": {"url": "sqlite:///x.db"}, "pipeline": {"content_provider": "fixed"}})
    assert isinstance(create_content_provider(settings, object()), FixedScriptContentProvider)  # type: ignore[arg-type]


def test_local_visuals_are_scene_specific_and_decodable(tmp_path: Path) -> None:
    provider = FakeMediaProvider(FakeProviderConfig(artifact_root=tmp_path))
    paths = []
    payloads = []
    for scene in FixedScriptContentProvider().generate_package(_request()).scene_plans:
        candidate = provider.search(MediaSearchRequest(scene_id=scene.scene_id, queries=scene.search_queries, visual_type=scene.visual_type, required_license="licensed"))[0]
        path = Path(candidate.local_path or "")
        paths.append(path)
        payloads.append(path.read_bytes())
        assert path.stat().st_size > 0 and candidate.width == 1280 and candidate.height == 720
    assert len(set(paths)) == len(set(payloads)) == 6


def test_local_content_uses_operator_notes_for_multiple_readable_scenes() -> None:
    request = _request().model_copy(update={"notes": ("Learn Linux fundamentals", "Deploy a small Docker service", "Practice AWS troubleshooting")})
    package = FakeContentProvider().generate_package(request)
    narration = " ".join(section.narration for section in package.script_sections).casefold()
    assert len(package.script_sections) == len(package.scene_plans) == 5
    assert "context" not in narration
    assert "learn linux fundamentals" in narration
    assert len({scene.search_queries[0] for scene in package.scene_plans}) == 5
