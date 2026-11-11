"""A shared daily quota cannot be oversubscribed or bypassed by a stale lease."""
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tubeforge.core.config import DatabaseConfig
from tubeforge.db.models import Base, DestinationDeliveryRecord
from tubeforge.db.session import create_database
from tubeforge.pipeline.delivery_queue import DeliveryClaim
from tubeforge.pipeline.youtube_quota import YouTubeQuotaExhausted, YouTubeQuotaLedger


def test_atomic_quota_reservations_and_pacific_day_rollover(tmp_path: Path) -> None:
    db = create_database(DatabaseConfig(url=f"sqlite:///{tmp_path / 'quota.db'}"))
    Base.metadata.create_all(db.engine)
    now = datetime(2026, 11, 11, 7, 30, tzinfo=UTC)  # Nov 10 in Pacific time.
    claims = []
    with db.session_factory.begin() as session:
        for i in range(2):
            delivery_id = f'delivery-{i}'
            session.add(DestinationDeliveryRecord(id=delivery_id, publish_job_id=f'post-{i}', asset_id=f'asset-{i}', account_id=f'acct-{i}', platform='youtube', external_account_id=f'channel-{i}', edition=0, state='uploading', required=True, metadata_json='{}', attempt_count=1, claim_owner='worker', claim_token=f'token-{i}', lease_expires_at=now + timedelta(days=2), created_at=now, updated_at=now))
            claims.append(DeliveryClaim(delivery_id, f'post-{i}', 'worker', f'token-{i}', 'upload', 'youtube', f'acct-{i}', f'channel-{i}', None, None))
    ledger = YouTubeQuotaLedger(db.session_factory, daily_units=1600, upload_units=1600)
    def reserve(claim):
        try:
            ledger.reserve(claim, now=now)
            return True
        except YouTubeQuotaExhausted:
            return False
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(reserve, claims))
        assert sorted(results) == [False, True]
        winner = claims[results.index(True)]
        ledger.reserve(winner, now=now)  # same attempt is idempotent
        assert ledger.status(now=now) == {'day': '2026-11-10', 'daily_units': 1600, 'reserved_units': 1600, 'remaining_units': 0, 'upload_units': 1600}
        # A cost increase cannot reuse an underfunded reservation.
        higher_cost = YouTubeQuotaLedger(db.session_factory, daily_units=2000, upload_units=2000)
        higher_cost.reserve(winner, now=now)
        assert higher_cost.status(now=now)['reserved_units'] == 2000
        with pytest.raises(YouTubeQuotaExhausted):
            YouTubeQuotaLedger(db.session_factory, daily_units=2000, upload_units=2001).reserve(winner, now=now)
        after_midnight = datetime(2026, 11, 11, 8, 1, tzinfo=UTC)
        ledger.reserve(claims[results.index(False)], now=after_midnight)
        assert ledger.status(now=after_midnight)['day'] == '2026-11-11'
        stale = DeliveryClaim(winner.delivery_id, winner.post_id, winner.owner, 'wrong-token', 'upload', 'youtube', winner.account_id, winner.external_account_id, None, None)
        with pytest.raises(ValueError, match='lease'):
            ledger.reserve(stale, now=now)
    finally:
        db.dispose()
