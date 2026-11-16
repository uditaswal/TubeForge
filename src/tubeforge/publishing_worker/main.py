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
from tubeforge.pipeline.youtube_quota import YouTubeQuotaLedger
from tubeforge.providers.publishing.account_youtube import AccountYouTubeAdapter
from tubeforge.publishing_worker.presence import PublisherWorkerPresence
from tubeforge.security.account_credentials import AccountCredentialManager, GoogleCredentialRefresher, InstagramCredentialRefresher
from tubeforge.security.secrets import TokenCipher


PLATFORMS = {"youtube", "instagram"}


def main() -> None:
    # Publishing has no dependency on the rendering models or writer process.
    settings = load_settings(validate_providers=False)
    encryption_key = os.environ.get("TUBEFORGE_ACCOUNT_ENCRYPTION_KEY")
    database = create_database(settings.database)
    cipher = None
    if encryption_key:
        try:
            cipher = TokenCipher(encryption_key)
        except (ValueError, TypeError):
            logging.warning("publisher worker is idle: account encryption key is invalid")
    else:
        logging.info("publisher worker is idle until an account encryption key is configured")
    youtube = google_refresh = executor = None
    active_platforms: set[str] = set()
    if cipher is not None:
        youtube = AccountYouTubeAdapter(
            ffprobe=str(settings.pipeline.voice.ffprobe_executable),
            max_bytes=settings.pipeline.youtube.max_upload_bytes,
            category_id=settings.pipeline.youtube.category_id,
            self_declared_made_for_kids=settings.pipeline.youtube.self_declared_made_for_kids,
            youtube_api_audited=settings.pipeline.youtube.youtube_api_audited,
        )
        google_refresh = GoogleCredentialRefresher()
        manager = AccountCredentialManager(database.session_factory, cipher, {"youtube": google_refresh})
        queue = DeliveryQueue(database.session_factory)
        stage_root = settings.pipeline.voice.artifact_root.parent / "publishing" / "staging"
        quota = YouTubeQuotaLedger(database.session_factory, daily_units=settings.pipeline.youtube.daily_quota_units, upload_units=settings.pipeline.youtube.upload_quota_units)
        executor = DeliveryExecutor(database.session_factory, queue, cipher, stage_root, {"youtube": youtube}, manager, quota)
        active_platforms = {"youtube"}
    presence = PublisherWorkerPresence(database.session_factory)
    worker_id = f"publisher-{uuid4().hex}"
    stopping = False
    heartbeat_stop = Event()

    def keep_presence() -> None:
        while not heartbeat_stop.wait(10):
            try:
                presence.heartbeat(worker_id, active_platforms)
            except Exception:
                logging.exception("publisher worker heartbeat failed")

    def stop(_: int, __: object) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    presence.heartbeat(worker_id, active_platforms)
    heartbeat_thread = Thread(target=keep_presence, name="publisher-heartbeat", daemon=True)
    heartbeat_thread.start()
    try:
        while not stopping:
            try:
                delivery_id = executor.run_requested_action(worker_id) if executor is not None else None
                if delivery_id is None and executor is not None:
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
        if youtube is not None:
            youtube.client.close()
        if google_refresh is not None:
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
