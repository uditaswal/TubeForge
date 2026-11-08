from concurrent.futures import ThreadPoolExecutor
import threading

import pytest
from tubeforge.long_form.receipts import HostReceiptStore,ReceiptConflict
from test_long_form_writing import writing_inputs


def test_prepare_execute_and_lost_response_reconcile_without_second_launch(tmp_path):
    message,_,_,_=writing_inputs();store=HostReceiptStore(tmp_path);calls=[]
    assert store.inspect(message)['state']=='not_found'
    assert store.prepare(message)['state']=='prepared'
    def invoke(value):calls.append(value.call_id);return {'output':{'status':'ready'},'usage':{'input_tokens':10},'provenance':{'model':'fixture'}}
    completed=store.execute(message,invoke)
    assert completed['state']=='succeeded' and completed['invocation_started'] is True
    # The worker lost its socket response: recreate the store and inspect/replay.
    restarted=HostReceiptStore(tmp_path)
    assert restarted.inspect(message)==completed
    assert restarted.execute(message,invoke)==completed
    assert calls==[message.call_id]


def test_concurrent_execute_launches_exactly_once(tmp_path):
    message,_,_,_=writing_inputs();store=HostReceiptStore(tmp_path);store.prepare(message)
    entered=threading.Event();finish=threading.Event();calls=[]
    def invoke(value):calls.append(value.call_id);entered.set();assert finish.wait(5);return {'output':{}}
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(store.execute,message,invoke)
        assert entered.wait(5)
        second=pool.submit(store.execute,message,invoke).result()
        assert second['state']=='running'
        finish.set();assert first.result()['state']=='succeeded'
    assert len(calls)==1


def test_crashed_launch_stays_unknown_and_is_never_replayed(tmp_path):
    message,_,_,_=writing_inputs();now=[1000.];store=HostReceiptStore(tmp_path,clock=lambda:now[0],timeout_seconds=10);store.prepare(message);calls=[]
    def crash(value):calls.append(value.call_id);raise SystemExit('simulated host termination')
    with pytest.raises(SystemExit):store.execute(message,crash)
    now[0]+=71
    restarted=HostReceiptStore(tmp_path,clock=lambda:now[0],timeout_seconds=10)
    assert restarted.inspect(message)['state']=='unknown'
    assert restarted.execute(message,crash)['state']=='unknown'
    assert len(calls)==1


def test_prepare_and_payload_binding_prevent_extra_stage_or_hidden_input(tmp_path):
    message,_,_,_=writing_inputs();store=HostReceiptStore(tmp_path)
    with pytest.raises(ReceiptConflict,match='Prepare'):store.execute(message,lambda _:None)
    store.prepare(message)
    changed=message.model_copy(update={'call_id':'lf2-'+'b'*32+'-call-1'})
    with pytest.raises(ReceiptConflict,match='one stage'):store.prepare(changed)
    changed=message.model_copy(update={'request':message.request.model_copy(update={'script_owner':'claude'})})
    with pytest.raises(ReceiptConflict,match='different immutable'):store.inspect(changed)


def test_failed_launch_retains_unknown_usage_and_does_not_refund(tmp_path):
    message,_,_,_=writing_inputs();store=HostReceiptStore(tmp_path);store.prepare(message)
    def timeout(_):raise TimeoutError('simulated model timeout')
    receipt=store.execute(message,timeout)
    assert receipt['state']=='failed' and receipt['invocation_started'] is None
    assert receipt['result']['usage'] is None
    assert store.execute(message,timeout)==receipt


def test_unknown_essential_usage_prevents_another_host_stage(tmp_path):
    first,_,_,_=writing_inputs();store=HostReceiptStore(tmp_path);store.prepare(first)
    store.execute(first,lambda _: {'output':{},'usage':{'input_tokens':100}})
    next_stage,_,_,_=writing_inputs('review');next_stage=next_stage.model_copy(update={'call_id':'lf2-'+'a'*32+'-call-2'})
    with pytest.raises(ReceiptConflict,match='unknown launch/input/output usage'):store.prepare(next_stage)


def test_oversized_receipt_keeps_prefix_hash_and_fits_app_persistence(tmp_path):
    import json
    from tubeforge.long_form.receipts import MAX_RECEIPT_BYTES
    message,_,_,_=writing_inputs();store=HostReceiptStore(tmp_path);store.prepare(message)
    receipt=store.execute(message,lambda _:{'output':None,'raw_output':'Synthetic oversized payload. '*100000,'usage':{'input_tokens':100,'output_tokens':100}})
    assert receipt['state']=='failed' and receipt['result']['truncated']
    assert receipt['result']['original_response_bytes']>1500000
    assert len(json.dumps(receipt,ensure_ascii=False).encode())<min(MAX_RECEIPT_BYTES,2000000)
    assert store.inspect(message)==receipt
