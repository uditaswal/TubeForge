"""A real isolated worker process advertises and removes its readiness."""
from __future__ import annotations

from pathlib import Path
import os
import subprocess
import sys
import time

from cryptography.fernet import Fernet

from tubeforge.core.config import DatabaseConfig
from tubeforge.db.models import Base
from tubeforge.db.session import create_database
from tubeforge.publishing_worker.presence import PublisherWorkerPresence


def test_isolated_publisher_worker_starts_without_external_requests(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'publisher.db'}"
    database = create_database(DatabaseConfig(url=database_url))
    Base.metadata.create_all(database.engine)
    config = tmp_path / "worker.yaml"
    config.write_text(
        f"app:\n  name: worker-smoke\n  environment: test\ndatabase:\n  url: {database_url}\npipeline:\n  voice:\n    artifact_root: {tmp_path / 'artifacts'}\n",
        encoding="utf-8",
    )
    env = {**os.environ, "TUBEFORGE_CONFIG": str(config), "TUBEFORGE_ACCOUNT_ENCRYPTION_KEY": Fernet.generate_key().decode()}
    process = subprocess.Popen([sys.executable, "-m", "tubeforge.publishing_worker.main"], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    presence = PublisherWorkerPresence(database.session_factory)
    try:
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline and "youtube" not in presence.live_platforms():
            if process.poll() is not None:
                raise AssertionError(f"publisher worker exited early with code {process.returncode}")
            time.sleep(0.1)
        assert presence.live_platforms() == {"youtube"}
        process.terminate()
        process.wait(timeout=8)
        assert process.returncode == 0
        assert presence.live_platforms() == set()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        database.dispose()


def test_publisher_without_encryption_key_stays_alive_and_cannot_claim(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'idle-publisher.db'}"
    database = create_database(DatabaseConfig(url=database_url))
    Base.metadata.create_all(database.engine)
    config = tmp_path / 'worker.yaml'
    config.write_text(f'app:\n  name: worker-idle\n  environment: test\ndatabase:\n  url: {database_url}\npipeline:\n  voice_provider: hybrid-http\n  piper:\n    model_path: {tmp_path / "missing-piper.onnx"}\n    server_url: http://127.0.0.1:5000\n  kokoro:\n    model_path: {tmp_path / "missing-kokoro.onnx"}\n    voices_path: {tmp_path / "missing-voices.bin"}\n  voice:\n    artifact_root: {tmp_path / "artifacts"}\n')
    env = dict(os.environ)
    env.pop('TUBEFORGE_ACCOUNT_ENCRYPTION_KEY', None)
    env['TUBEFORGE_CONFIG'] = str(config)
    process = subprocess.Popen([sys.executable, '-m', 'tubeforge.publishing_worker.main'], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    presence = PublisherWorkerPresence(database.session_factory)
    try:
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline and not presence.is_online():
            if process.poll() is not None:
                raise AssertionError(f'idle publisher exited early with code {process.returncode}')
            time.sleep(.1)
        assert presence.is_online() and presence.live_platforms() == set()
        assert process.poll() is None
        process.terminate()
        process.wait(timeout=8)
        assert process.returncode == 0 and not presence.is_online()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        database.dispose()
