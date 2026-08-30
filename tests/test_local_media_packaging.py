"""Deployment contracts for the no-paid-API local media pipeline."""

from pathlib import Path

import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_worker_image_installs_piper_and_ffmpeg() -> None:
    dockerfile = (REPOSITORY_ROOT / "Dockerfile").read_text(encoding="utf-8")
    project = (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "apt-get install -y --no-install-recommends ffmpeg" in dockerfile
    assert '".[dev,local-media]"' in dockerfile
    assert '"piper-tts>=1.3,<2"' in project


def test_compose_mounts_operator_supplied_voice_models_read_only() -> None:
    compose = yaml.safe_load((REPOSITORY_ROOT / "compose.yaml").read_text(encoding="utf-8"))
    worker_volumes = compose["services"]["worker"]["volumes"]

    assert "./models:/app/models:ro" in worker_volumes


def test_production_piper_paths_match_model_mount() -> None:
    production = yaml.safe_load((REPOSITORY_ROOT / "config" / "production.yaml").read_text(encoding="utf-8"))
    piper = production["pipeline"]["piper"]

    assert piper["executable"] == "piper"
    assert piper["model_path"].startswith("/app/models/")
    assert piper["config_path"] == f'{piper["model_path"]}.json'
    assert piper["cache_root"].startswith("/app/data/")
