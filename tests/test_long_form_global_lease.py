"""LF2 must share the existing singleton admission lease with media workers."""
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC,datetime
import threading

from sqlalchemy.orm import Session
from tubeforge.core.config import DatabaseConfig
from tubeforge.db.models import Base,HeavyWorkLeaseRecord
from tubeforge.db.repositories import HeavyWorkLeaseRepository
from tubeforge.db.session import create_database


def test_released_global_lease_cannot_be_acquired_by_two_stale_readers(tmp_path,monkeypatch):
    database=create_database(DatabaseConfig(url=f'sqlite:///{tmp_path}/global.db'));Base.metadata.create_all(database.engine)
    lease=HeavyWorkLeaseRepository(database.session_factory);now=datetime(2026,11,8,tzinfo=UTC)
    assert lease.acquire('seed',now=now,lease_seconds=60);lease.release('seed')
    barrier=threading.Barrier(2);original=Session.get
    def stale_read(self,entity,*args,**kwargs):
        row=original(self,entity,*args,**kwargs)
        if entity is HeavyWorkLeaseRecord:barrier.wait(timeout=5)
        return row
    monkeypatch.setattr(Session,'get',stale_read)
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda owner:lease.acquire(owner,now=now,lease_seconds=60),['one','two']))
    assert sum(results)==1
    database.dispose()


def test_fenced_run_handoff_does_not_let_old_finalizer_release_new_owner(tmp_path):
    database=create_database(DatabaseConfig(url=f'sqlite:///{tmp_path}/handoff.db'));Base.metadata.create_all(database.engine)
    lease=HeavyWorkLeaseRepository(database.session_factory);now=datetime(2026,11,8,tzinfo=UTC)
    assert lease.acquire('lf2-exact-run-old',now=now,lease_seconds=1200)
    assert not lease.acquire('lf2-other-run-new',now=now,lease_seconds=1200,reclaim_prefix='lf2-other-run-')
    assert lease.acquire('lf2-exact-run-new',now=now,lease_seconds=1200,reclaim_prefix='lf2-exact-run-')
    lease.release('lf2-exact-run-old')
    assert lease.owns('lf2-exact-run-new',now=now)
    assert not lease.acquire('media',now=now,lease_seconds=60)
    database.dispose()
