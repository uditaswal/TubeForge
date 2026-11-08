"""Intake shares the existing worker loop and honours service shutdown."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from tubeforge.workers import main as worker_main


@pytest.mark.parametrize('stop_during_intake',[False,True])
def test_existing_worker_polls_intake_and_disposes_safely(monkeypatch,stop_during_intake):
    handlers={};order=[]
    monkeypatch.setattr(worker_main.signal,'signal',lambda signum,handler:handlers.setdefault(signum,handler))
    settings=SimpleNamespace(worker=object())
    runtime=SimpleNamespace(database=Mock(),jobs=object(),orchestrator=object(),reference_intakes=Mock())
    worker=Mock(worker_id='worker-test')
    def intake(owner,*,cancelled):
        assert owner=='worker-test' and not cancelled()
        order.append('intake')
        if stop_during_intake:handlers[worker_main.signal.SIGTERM](0,None)
        return {'intake':{'state':'ready'}}
    def generation():
        order.append('generation');handlers[worker_main.signal.SIGTERM](0,None)
    runtime.reference_intakes.run_once.side_effect=intake;worker.run_once.side_effect=generation
    monkeypatch.setattr(worker_main,'load_settings',lambda:settings)
    monkeypatch.setattr(worker_main,'create_runtime',lambda configured:runtime)
    monkeypatch.setattr(worker_main,'WorkerService',lambda *args:worker)
    worker_main.main()
    assert order==(['intake'] if stop_during_intake else ['intake','generation'])
    runtime.database.dispose.assert_called_once_with()
