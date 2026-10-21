from pathlib import Path

import pytest
from pydantic import ValidationError

from tubeforge.core.config import Settings, ShortsFinalRenderConfig, VoicePipelineConfig, load_settings
from tubeforge.domain.video_duration import shorts_duration_allowed


def test_loads_fake_yaml_configuration(tmp_path: Path) -> None:
    config_file = tmp_path / "fake.yaml"
    config_file.write_text(
        """app:
  name: Test TubeForge
  environment: test
  bind_host: 127.0.0.1
  port: 9090
database:
  url: sqlite:///./test.db
  busy_timeout_ms: 1234
""",
        encoding="utf-8",
    )

    settings = load_settings(config_file)

    assert settings.app.environment == "test"
    assert settings.app.port == 9090
    assert settings.database.busy_timeout_ms == 1234
    assert settings.pipeline.content_provider == "fake"
    assert settings.pipeline.voice_provider == "fake"


def test_shorts_final_defaults_match_phone_first_video_and_audio_contract() -> None:
    assert ShortsFinalRenderConfig().caption_font_size == 84
    assert ShortsFinalRenderConfig().renderer_version == "shorts-final-v4"
    assert ShortsFinalRenderConfig().audio_sample_rate == 48_000
    assert ShortsFinalRenderConfig().caption_center_x == 490
    assert ShortsFinalRenderConfig().caption_margin_vertical == 470
    assert load_settings().pipeline.shorts_final.caption_font_size == 84
    assert load_settings().pipeline.shorts_final.caption_center_x == 490
    with pytest.raises(ValidationError, match="caption_font_size"):
        ShortsFinalRenderConfig(caption_font_size=83)
    with pytest.raises(ValidationError, match="audio_sample_rate"):
        ShortsFinalRenderConfig(audio_sample_rate=44_100)


def test_production_shorts_use_codex_local_piper_and_measured_audio() -> None:
    production = load_settings(Path("config/production.yaml"))
    assert production.pipeline.content_provider == "codex"
    assert production.pipeline.voice_provider == "piper-http"
    assert production.pipeline.piper.listen_host == "127.0.0.1"
    assert production.pipeline.piper.listen_port == 5000
    for profile in (production.pipeline.shorts_preview, production.pipeline.shorts_final):
        assert profile.audio_sample_rate == 48_000
        assert profile.audio_normalization_enabled is True


def test_piper_listener_is_loopback_by_default_and_deployment_overridable(monkeypatch) -> None:
    from tubeforge.core.config import PiperProviderConfig

    default = PiperProviderConfig()
    assert (default.listen_host, default.listen_port) == ("127.0.0.1", 5000)
    monkeypatch.setenv("TUBEFORGE_PIPER_LISTEN_HOST", "127.0.0.2")
    monkeypatch.setenv("TUBEFORGE_PIPER_LISTEN_PORT", "5012")
    overridden = load_settings(Path("config/default.yaml")).pipeline.piper
    assert (overridden.listen_host, overridden.listen_port) == ("127.0.0.2", 5012)


def test_configuration_rejects_non_sqlite_database() -> None:
    with pytest.raises(ValidationError, match="sqlite"):
        Settings.model_validate(
            {
                "app": {"name": "Test", "environment": "test"},
                "database": {"url": "postgresql://example.invalid/tubeforge"},
            }
        )

def test_media_provider_supports_local_generated_stock_and_hybrid_routing() -> None:
    from tubeforge.core.config import FakeProviderConfig, MediaPipelineConfig
    from tubeforge.providers.fake import FakeMediaProvider
    from tubeforge.providers.media.factory import create_media_provider
    from tubeforge.providers.media.router import VisualMediaProvider
    from tubeforge.providers.media.wikimedia import WikimediaCommonsProvider
    assert isinstance(create_media_provider(MediaPipelineConfig(), FakeProviderConfig()), FakeMediaProvider)
    assert isinstance(create_media_provider(MediaPipelineConfig(provider="wikimedia"), FakeProviderConfig()), WikimediaCommonsProvider)
    assert isinstance(create_media_provider(MediaPipelineConfig(provider="hybrid"), FakeProviderConfig()), VisualMediaProvider)

def test_default_yaml_uses_safe_per_job_visual_media_policy() -> None:
    settings = load_settings()
    assert settings.pipeline.media.provider == "hybrid"
    assert settings.pipeline.media.max_redirects == 0
    assert not settings.pipeline.sources.enabled


def test_default_voice_duration_tolerance_accepts_real_local_pacing() -> None:
    config = VoicePipelineConfig()
    assert config.target_duration_tolerance_ratio == 0.30
    assert 60 * (1 + config.target_duration_tolerance_ratio) >= 78
    assert config.alignment_provider == "local-waveform-v1"


def test_audio_grounded_alignment_requires_pinned_local_model(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="requires a local model path and SHA-256 pin"):
        VoicePipelineConfig(alignment_provider="whisper-base-en-dtw-v1")
    selected = VoicePipelineConfig(alignment_provider="whisper-base-en-dtw-v1", alignment_model_path=tmp_path, alignment_model_sha256="a" * 64)
    assert selected.alignment_model_path == tmp_path


def test_shorts_duration_policy_accepts_measured_git_audio_and_bounds() -> None:
    assert shorts_duration_allowed(46.684333)
    assert shorts_duration_allowed(30)
    assert shorts_duration_allowed(120)
    assert not shorts_duration_allowed(29.999)
    assert not shorts_duration_allowed(120.001)
    settings = load_settings()
    assert settings.pipeline.video_generation.presets["shorts"].maximum_duration_seconds == 120


def test_source_ingestion_needs_explicit_hosts() -> None:
    with pytest.raises(ValidationError, match="source ingestion requires"):
        Settings.model_validate({
            "app": {"name": "Test", "environment": "test"},
            "database": {"url": "sqlite:///./test.db"},
            "pipeline": {"sources": {"enabled": True}},
        })


def test_channel_approved_sources_require_actual_excerpts() -> None:
    good = {"source_id": "docs", "url": "https://example.org/docs", "title": "Docs", "excerpt": "An approved fact"}
    settings = Settings.model_validate({"app": {"name": "Test", "environment": "test"}, "database": {"url": "sqlite:///./test.db"}, "pipeline": {"sources": {"channel_approved": {"default": [good]}}}})
    assert settings.pipeline.sources.channel_approved["default"][0].excerpt == "An approved fact"
    with pytest.raises(ValidationError, match="approved excerpts"):
        Settings.model_validate({"app": {"name": "Test", "environment": "test"}, "database": {"url": "sqlite:///./test.db"}, "pipeline": {"sources": {"channel_approved": {"default": [{**good, "excerpt": None}]}}}})


def test_codex_and_piper_selection_requires_an_absolute_socket_path(tmp_path: Path) -> None:
    model = tmp_path / "voice.onnx"
    model.write_bytes(b"model")
    piper = tmp_path / "piper"
    piper.write_text("#!/bin/sh\n", encoding="utf-8")
    config = tmp_path / "combined.yaml"
    config.write_text(
        "\n".join(
            (
                "app:",
                "  name: TubeForge",
                "  environment: test",
                "database:",
                "  url: sqlite:///test.db",
                "pipeline:",
                "  content_provider: codex",
                "  voice_provider: piper",
                "  codex:",
                "    socket_path: relative-codex.sock",
                "  piper:",
                f"    executable: {piper}",
                f"    model_path: {model}",
            )
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="pipeline.codex.socket_path"):
        load_settings(config)
