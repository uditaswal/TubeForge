"""Dedicated scheduler entrypoint; no render/provider work happens here."""
from __future__ import annotations

import logging
import signal
import time
import uuid

from tubeforge.core.config import load_settings
from tubeforge.core.runtime import create_runtime
from tubeforge.scheduling.service import SchedulerService


def main() -> None:
    settings = load_settings(); runtime = create_runtime(settings)
    scheduler = SchedulerService(runtime.schedules, runtime.topics, scheduler_id=f"scheduler-{uuid.uuid4().hex}", reservation_seconds=settings.scheduler.topic_reservation_seconds, codex_config=settings.pipeline.codex)
    stopping = False
    def stop(_: int, __: object) -> None:
        nonlocal stopping; stopping = True
    signal.signal(signal.SIGINT, stop); signal.signal(signal.SIGTERM, stop)
    try:
        while not stopping:
            results = scheduler.tick()
            for result in results: logging.info("scheduler run: %s", result)
            time.sleep(settings.scheduler.poll_seconds)
    finally:
        runtime.database.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
