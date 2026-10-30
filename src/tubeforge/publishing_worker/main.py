"""Poll fenced destination work independently from generation and scheduling."""
from __future__ import annotations

import logging
import os
import signal
from threading import Event, Thread
import time
from uuid import uuid4

from tubeforge.core.config import load_settings
from tubeforge.db.session import create_database
from tubeforge.pipeline.delivery_executor import DeliveryExecutor
from tubeforge.pipeline.delivery_queue import DeliveryQueue
from tubeforge.providers.publishing.account_youtube import AccountYouTubeAdapter
from tubeforge.publishing_worker.presence import PublisherWorkerPresence
from tubeforge.security.account_credentials import AccountCredentialManager, GoogleCredentialRefresher
from tubeforge.security.secrets import TokenCipher


def main() -> None:
    settings = load_settings()
    encryption_key = os.environ.get("TUBEFORGE_ACCOUNT_ENCRYPTION_KEY")
    if not encryption_key:
        raise RuntimeError("publisher worker requires an account encryption key")
    database = create_database(settings.database)
    cipher = TokenCipher(encryption_key)
    youtube = AccountYouTubeAdapter()
    google_refresh = GoogleCredentialRefresher()
    manager = AccountCredentialManager(database.session_factory, cipher, {"youtube": google_refresh})
    queue = DeliveryQueue(database.session_factory)
    stage_root = settings.pipeline.voice.artifact_root.parent / "publishing" / "staging"
    executor = DeliveryExecutor(database.session_factory, queue, cipher, stage_root, {"youtube": youtube}, manager)
    presence = PublisherWorkerPresence(database.session_factory)
    worker_id = f"publisher-{uuid4().hex}"
    stopping = False
    heartbeat_stop = Event()

    def keep_presence() -> None:
        while not heartbeat_stop.wait(10):
            try:
                presence.heartbeat(worker_id, {"youtube"})
            except Exception:
                logging.exception("publisher worker heartbeat failed")

    def stop(_: int, __: object) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    presence.heartbeat(worker_id, {"youtube"})
    heartbeat_thread = Thread(target=keep_presence, name="publisher-heartbeat", daemon=True)
    heartbeat_thread.start()
    try:
        while not stopping:
            try:
                delivery_id = executor.run_requested_action(worker_id)
                if delivery_id is None:
                    delivery_id = executor.run_once(worker_id)
            except Exception:
                # An in-flight lease will expire to UNKNOWN_OUTCOME; no new
                # upload starts for that destination after an unexpected error.
                logging.exception("publisher worker iteration failed")
                time.sleep(5)
            else:
                if delivery_id is None:
                    time.sleep(2)
    finally:
        heartbeat_stop.set()
        heartbeat_thread.join(timeout=5)
        presence.stop(worker_id)
        youtube.client.close()
        google_refresh.client.close()
        database.dispose()


if __name__ == "__main__":
    from tubeforge.core.app_logging import configure_logging

    configure_logging("publisher")
    try:
        main()
    except Exception:
        logging.getLogger("tubeforge.publisher").exception("service_crashed", extra={"event": "service_crashed"})
        raise
