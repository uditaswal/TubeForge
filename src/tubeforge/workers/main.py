"""Single-process worker entry point for Docker Compose and system services."""

from __future__ import annotations

import logging
import signal
import time
import uuid

from tubeforge.core.config import load_settings
from tubeforge.core.runtime import create_runtime
from tubeforge.workers.service import WorkerService


def main() -> None:
    """Poll conservatively; each expensive operation remains globally leased."""
    settings = load_settings()
    runtime = create_runtime(settings)
    worker = WorkerService(f"worker-{uuid.uuid4().hex}", runtime.jobs, runtime.orchestrator, settings.worker)
    stopping = False

    def stop(_: int, __: object) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        while not stopping:
            result = worker.run_once()
            if result is None:
                time.sleep(2)
    finally:
        runtime.database.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
