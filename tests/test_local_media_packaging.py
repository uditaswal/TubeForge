"""Deployment contracts for the no-paid-API local media pipeline."""

from pathlib import Path

import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_worker_image_installs_local_voice_runtimes_and_ffmpeg() -> None:
    dockerfile = (REPOSITORY_ROOT / "Dockerfile").read_text(encoding="utf-8")
    project = (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "apt-get install -y --no-install-recommends ffmpeg" in dockerfile
    assert '".[dev,local-media,kokoro,alignment,reference-renderer]"' in dockerfile
    assert "chromium" in dockerfile  # source-page screenshots for reference Shorts
    assert '"piper-tts>=1.3,<2"' in project
    assert '"kokoro-onnx>=0.3.8,<1"' in project


def test_compose_mounts_operator_supplied_voice_models_read_only() -> None:
    compose = yaml.safe_load((REPOSITORY_ROOT / "compose.yaml").read_text(encoding="utf-8"))
    worker_volumes = compose["services"]["worker"]["volumes"]

    assert "./models:/app/models:ro" in worker_volumes
    tts = compose["services"]["piper-tts"]
    assert "ports" not in tts
    assert tts["environment"]["TUBEFORGE_PIPER_LISTEN_HOST"] == "0.0.0.0"
    assert tts["healthcheck"]
    assert compose["services"]["worker"]["environment"]["TUBEFORGE_PIPER_SERVER_URL"]
    assert compose["services"]["web"]["environment"]["TUBEFORGE_PIPER_SERVER_URL"]


def test_compose_exposes_only_the_documented_loopback_dashboard_port() -> None:
    compose = yaml.safe_load((REPOSITORY_ROOT / "compose.yaml").read_text(encoding="utf-8"))

    assert compose["services"]["web"]["ports"] == ["127.0.0.1:62065:8080"]


def test_production_paths_are_not_tied_to_container_filesystem() -> None:
    production = yaml.safe_load((REPOSITORY_ROOT / "config" / "production.yaml").read_text(encoding="utf-8"))
    piper = production["pipeline"]["piper"]

    assert production["app"]["bind_host"] == "127.0.0.1"
    # The image installs the Python Piper package; production invokes it as
    # ``python -m piper`` so no separate console-script shim is required.
    assert piper["executable"] == "python"
    assert piper["model_path"] == "./models/en_US-lessac-medium.onnx"
    assert piper["config_path"] == f'{piper["model_path"]}.json'
    assert piper["cache_root"] == "./data/cache/tts"
    kokoro = production["pipeline"]["kokoro"]
    assert production["pipeline"]["voice_provider"] == "hybrid-http"
    assert kokoro["model_path"] == "./models/kokoro-v1.0.int8.onnx"
    assert kokoro["voices_path"] == "./models/voices-v1.0.bin"
    for section in (production["database"], production["pipeline"]["voice"], production["pipeline"]["media"]):
        assert "/app/" not in str(section)

    example = yaml.safe_load((REPOSITORY_ROOT / "config" / "production.example.yaml").read_text(encoding="utf-8"))
    assert "/app/" not in str(example)


def test_piper_http_endpoint_is_runtime_configured_not_a_docker_dependency() -> None:
    production = yaml.safe_load((REPOSITORY_ROOT / "config" / "production.yaml").read_text(encoding="utf-8"))
    compose = yaml.safe_load((REPOSITORY_ROOT / "compose.yaml").read_text(encoding="utf-8"))

    assert production["pipeline"]["piper"]["server_url"] == "http://127.0.0.1:5000"
    for service in ("web", "worker"):
        assert compose["services"][service]["environment"]["TUBEFORGE_PIPER_SERVER_URL"] == "http://piper-tts:5000"
