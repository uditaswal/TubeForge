"""Single-process worker entry point for Docker Compose and system services."""

from __future__ import annotations

import logging
import os
import signal
import time
import uuid

from tubeforge.core.config import load_settings
from tubeforge.core.runtime import create_runtime
from tubeforge.workers.service import WorkerService


def main() -> None:
    """Poll conservatively; each expensive operation remains globally leased."""
    from tubeforge.core.tempdir import ensure_tempdir
    ensure_tempdir()
    settings = load_settings()
    kinds = os.environ.get("TUBEFORGE_WORKER_MODES", "").strip().lower()
    if kinds:
        if kinds not in {"all", "clips", "shorts"}:
            raise SystemExit("TUBEFORGE_WORKER_MODES must be all, clips or shorts")
        settings.worker.job_kinds = kinds
    runtime = create_runtime(settings)
    worker = WorkerService(f"worker-{uuid.uuid4().hex}", runtime.jobs, runtime.orchestrator, settings.worker)
    from tubeforge.core.job_focus import JobFocus, focus_path
    try:
        worker.focus = JobFocus(focus_path(settings.pipeline.voice.artifact_root))
    except AttributeError:  # a stripped-down settings object (tests); the worker then simply has no focus
        worker.focus = None
    stopping = False

    def stop(_: int, __: object) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        while not stopping:
            intake = runtime.reference_intakes.run_once(worker.worker_id, cancelled=lambda: stopping)
            if stopping: break
            writing = runtime.long_form_writing.run_once(worker.worker_id, cancelled=lambda: stopping)
            if stopping: break
            result = worker.run_once()
            if result is None and intake is None and writing is None:
                time.sleep(2)
    finally:
        runtime.database.dispose()


if __name__ == "__main__":
    from tubeforge.core.app_logging import configure_logging

    configure_logging("worker")
    try:
        main()
    except Exception:
        logging.getLogger("tubeforge.worker").exception("service_crashed", extra={"event": "service_crashed"})
        raise
