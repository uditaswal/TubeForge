"""Host-side prepare/execute/inspect receipts: an unknown launch is never replayed."""
from __future__ import annotations

from datetime import UTC,datetime
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
import time

from tubeforge.long_form.admission import measure
from tubeforge.long_form.wire import encode
from tubeforge.long_form.usage import observed_usage


class ReceiptConflict(ValueError):pass
MAX_RESULT_BYTES=1_500_000
MAX_RECEIPT_BYTES=1_600_000


def fingerprint(message):
    return hashlib.sha256(encode(message.model_copy(update={'operation':'LongFormStageV1'}))).hexdigest()


class HostReceiptStore:
    def __init__(self,root:Path,*,clock=time.time,timeout_seconds=600):
        self.root=Path(root);self.clock=clock;self.timeout_seconds=timeout_seconds

    @contextmanager
    def _database(self):
        self.root.mkdir(mode=0o700,parents=True,exist_ok=True)
        path=self.root/'long-form-receipts.sqlite3'
        db=sqlite3.connect(path,timeout=10);db.row_factory=sqlite3.Row
        path.chmod(0o600)
        db.execute('''CREATE TABLE IF NOT EXISTS calls (
            call_id TEXT PRIMARY KEY, brief_sha256 TEXT NOT NULL, stage TEXT NOT NULL,
            payload_sha256 TEXT NOT NULL, admission_json TEXT NOT NULL, policy_json TEXT NOT NULL, charged_tokens INTEGER NOT NULL, state TEXT NOT NULL,
            result_json TEXT, created_at REAL NOT NULL, started_at REAL, finished_at REAL,
            UNIQUE(brief_sha256,stage))''')
        try:yield db
        finally:db.close()

    def _view(self,row,message):
        if row['payload_sha256']!=fingerprint(message):raise ReceiptConflict('Call ID is bound to different immutable input')
        state=row['state']
        if state=='running' and self.clock()-row['started_at']>self.timeout_seconds+60:state='unknown'
        result=json.loads(row['result_json']) if row['result_json'] else None
        view=dict(call_id=row['call_id'],state=state,payload_sha256=row['payload_sha256'],admission=json.loads(row['admission_json']),result=result,
            charged_tokens=row['charged_tokens'],
            invocation_started=True if state in {'running','succeeded','unknown'} else result.get('invocation_started') if result else False)
        if len(json.dumps(view,ensure_ascii=False,separators=(',',':')).encode())>MAX_RECEIPT_BYTES:raise ReceiptConflict('Host receipt exceeds transport/persistence bounds')
        return view

    def inspect(self,message):
        with self._database() as db:
            row=db.execute('SELECT * FROM calls WHERE call_id=?',(message.call_id,)).fetchone()
            if row is None:return dict(call_id=message.call_id,state='not_found',payload_sha256=fingerprint(message),result=None,invocation_started=None)
            return self._view(row,message)

    def prepare(self,message):
        admission=measure(message.model_copy(update={'operation':'LongFormStageV1'}))
        with self._database() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM calls WHERE call_id=?',(message.call_id,)).fetchone()
            if row is not None:return self._view(row,message)
            existing=db.execute('SELECT call_id FROM calls WHERE brief_sha256=? AND stage=?',(message.brief_sha256,message.stage)).fetchone()
            if existing:raise ReceiptConflict('This exact brief already reserved its one stage invocation')
            count=db.execute('SELECT COUNT(*) FROM calls WHERE brief_sha256=?',(message.brief_sha256,)).fetchone()[0]
            if count>=5:raise ReceiptConflict('Host five-call allowance exhausted')
            policy=message.token_policy.model_dump_json()
            previous=db.execute('SELECT admission_json,policy_json,charged_tokens,state,stage,result_json FROM calls WHERE brief_sha256=?',(message.brief_sha256,)).fetchall()
            if any(r['policy_json']!=policy for r in previous):raise ReceiptConflict('Host token policy cannot change for an existing brief')
            if any(r['state'] in {'prepared','running'} for r in previous):raise ReceiptConflict('Resolve the existing prepared/running call before another stage')
            for prior in previous:
                result=json.loads(prior['result_json']) if prior['result_json'] else {}
                usage=observed_usage(result.get('usage'),provider=result.get('provenance',{}).get('provider',message.request.script_owner))
                if result.get('invocation_started') is None or (result.get('invocation_started') and (usage is None or usage.input_tokens is None or usage.output_tokens is None)):
                    raise ReceiptConflict('Resolve unknown launch/input/output usage before another stage')
            if message.stage in {'draft','repair'} and sum(r['stage'] in {'draft','repair'} for r in previous)>=message.token_policy.maximum_narration_attempts:
                raise ReceiptConflict('Host narration allowance exhausted')
            total=sum(r['charged_tokens'] for r in previous)+admission['total_reservation']
            if total>message.token_policy.total_reserved_tokens:raise ReceiptConflict('Host reserved text-token budget exhausted')
            db.execute('INSERT INTO calls(call_id,brief_sha256,stage,payload_sha256,admission_json,policy_json,charged_tokens,state,created_at) VALUES(?,?,?,?,?,?,?,?,?)',
                (message.call_id,message.brief_sha256,message.stage,fingerprint(message),json.dumps(admission,sort_keys=True),policy,admission['total_reservation'],'prepared',self.clock()))
            db.commit()
        return self.inspect(message)

    def execute(self,message,invoke):
        """The callback makes exactly one CLI call and preserves its raw result.

        Receipt commit precedes callback. Repeated execute or process restart
        returns the same receipt; it never launches a running/unknown call again.
        """
        admission=measure(message.model_copy(update={'operation':'LongFormStageV1'}))
        with self._database() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM calls WHERE call_id=?',(message.call_id,)).fetchone()
            if row is None:raise ReceiptConflict('Prepare the exact host receipt before dispatch')
            self._view(row,message)
            if row['state']!='prepared':return self._view(row,message)
            if json.loads(row['admission_json'])!=admission:raise ReceiptConflict('Host prompt/resources changed after preparation; no invocation launched')
            db.execute("UPDATE calls SET state='running',started_at=? WHERE call_id=? AND state='prepared'",(self.clock(),message.call_id));db.commit()
        try:
            result=invoke(message)
            if not isinstance(result,dict):raise ValueError('Invocation adapter must return bounded structured evidence')
            # A successful adapter return means a launch happened. Provider/CLI
            # usage may still be unknown, which is preserved rather than zeroed.
            result={**result,'invocation_started':True}
            state='succeeded'
        except Exception as error:
            # An exception does not prove an unstarted call. Until the adapter supplies
            # a receipt proving otherwise, launch/usage remain conservative.
            state='failed';result=dict(output=None,raw_output=None,usage=None,provenance={},invocation_started=None,
                error=f'{type(error).__name__}: invocation failed; inspect saved receipt before another stage.')
            evidence=getattr(error,'evidence',None)
            if isinstance(evidence,dict):result.update(evidence)
        encoded=json.dumps(result,ensure_ascii=False,sort_keys=True,separators=(',',':'))
        if len(encoded.encode())>MAX_RESULT_BYTES:
            state='failed';result=dict(output=None,raw_output=encoded[:40000],truncated=True,original_response_bytes=len(encoded.encode()),original_response_sha256=hashlib.sha256(encoded.encode()).hexdigest(),
                usage=result.get('usage'),provenance=result.get('provenance',{}),invocation_started=result.get('invocation_started'),error='Invocation result exceeded receipt bounds; retained prefix is not a complete draft.')
            encoded=json.dumps(result,ensure_ascii=False,sort_keys=True,separators=(',',':'))
        with self._database() as db:
            db.execute('BEGIN IMMEDIATE')
            usage=observed_usage(result.get('usage'),provider=result.get('provenance',{}).get('provider',message.request.script_owner))
            charged=admission['total_reservation']
            if usage and usage.input_tokens is not None and usage.output_tokens is not None:charged=max(charged,usage.input_tokens+usage.output_tokens)
            db.execute("UPDATE calls SET state=?,result_json=?,charged_tokens=?,finished_at=? WHERE call_id=? AND state='running'",(state,encoded,charged,self.clock(),message.call_id));db.commit()
        return self.inspect(message)
