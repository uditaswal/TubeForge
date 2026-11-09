import json
import socket
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from tubeforge.domain.long_form_writing import LongFormHostRequest
from tubeforge.long_form import host
from tubeforge.long_form.receipts import HostReceiptStore
from tubeforge.providers.content.host_runner_protocol import encode_request,receive_message
from test_long_form_writing import writing_inputs


def test_lf2_wire_parser_preserves_typed_binding_and_legacy_payload():
    message,_,_,_=writing_inputs('review');payload=encode_request(message)
    assert 'request' not in json.loads(payload)['draft']['package']
    client,server=socket.socketpair()
    try:
        client.sendall(payload);client.shutdown(socket.SHUT_WR)
        assert receive_message(server)==message
    finally:client.close();server.close()


def test_codex_prepared_stage_launches_one_cli_without_retry_or_editor(monkeypatch,tmp_path):
    from tubeforge import host_codex_runner as runner
    message,_,_,_=writing_inputs();message=message.model_copy(update={'resolved_model':runner.CODEX_MODEL});workspaces=[];calls=[]
    def command(workspace):workspaces.append(workspace);return ['stub-cli','exec']
    def invoke(argv,**kwargs):
        calls.append(argv);(workspaces[-1]/'content-package.json').write_text('{"status":"synthetic-output"}')
        return SimpleNamespace(returncode=0,stdout=b'{"type":"turn.completed","usage":{"input_tokens":111,"output_tokens":10}}\n',stderr=b'')
    monkeypatch.setattr(runner,'bubblewrap_args',command);monkeypatch.setattr(host.subprocess,'run',invoke)
    store=HostReceiptStore(tmp_path);store.prepare(message)
    receipt=store.execute(message,lambda m:host.invoke_codex(m,root=tmp_path))
    assert receipt['result']['output']=={'status':'synthetic-output'}
    assert receipt['result']['usage']=={'input_tokens':111,'output_tokens':10}
    assert len(calls)==1 and all(not folder.exists() for folder in workspaces)
    assert store.execute(message,lambda m:host.invoke_codex(m,root=tmp_path))==receipt
    assert len(calls)==1


@pytest.mark.parametrize('stage',['draft','research'])
def test_claude_stage_preserves_global_spend_guard_and_long_form_system_scope(monkeypatch,stage):
    from tubeforge import host_claude_runner as runner
    message,_,_,_=writing_inputs(stage=stage);message=message.model_copy(update={'request':message.request.model_copy(update={'script_owner':'claude'}),'resolved_model':runner.DEFAULT_MODEL})
    budget=Mock(max_usd_per_call=1.50);calls=[]
    monkeypatch.setattr(runner,'BUDGET',budget);monkeypatch.setattr(runner,'claude_binary',lambda:'stub-claude')
    def invoke(argv,**kwargs):
        calls.append(argv)
        if stage == 'draft':
            assert kwargs['env']['CLAUDE_CODE_EFFORT_LEVEL'] == 'low'
            assert kwargs['env']['CLAUDE_CODE_MAX_OUTPUT_TOKENS'] == '16000'
            assert kwargs['env']['MAX_STRUCTURED_OUTPUT_RETRIES'] == '1'
        else:
            assert kwargs['env'] == dict(host.os.environ)
        return SimpleNamespace(returncode=0,stdout=json.dumps({'structured_output':{'synthetic':True},'usage':{'input_tokens':100,'server_tool_use':{'web_search_requests':1}},'total_cost_usd':0.01}).encode(),stderr=b'')
    monkeypatch.setattr(host.subprocess,'run',invoke)
    evidence=host.invoke_claude(message)
    assert len(calls)==1 and calls[0][calls[0].index('--system-prompt')+1]==host.SYSTEM_PROMPT
    limits = host.measure(message)['claude_cli']
    assert calls[0][calls[0].index('--effort')+1] == limits['effort']
    if stage == 'draft':
        assert calls[0][calls[0].index('--tools')+1]==''
        assert limits['effort'] == 'low'
        assert int(calls[0][calls[0].index('--max-turns')+1]) == limits['max_turns'] == 2
    else:
        assert calls[0][calls[0].index('--tools')+1]=='WebSearch'
        assert limits['effort'] == 'medium' and '--max-turns' not in calls[0]
    assert evidence['provenance']['claude_cli'] == limits
    assert '--max-budget-usd' in calls[0]
    budget.check.assert_called_once_with();assert budget.record.call_count==2
    assert evidence['usage']['input_tokens']==100 and evidence['usage']['total_cost_usd']==0.01


def test_invalid_draft_output_is_retained_and_research_requires_search_evidence(monkeypatch,tmp_path):
    from tubeforge import host_codex_runner as runner
    message,_,_,_=writing_inputs();message=message.model_copy(update={'resolved_model':runner.CODEX_MODEL});workspaces=[]
    monkeypatch.setattr(runner,'bubblewrap_args',lambda workspace:workspaces.append(workspace) or ['stub-cli','exec'])
    def invoke(*args,**kwargs):
        (workspaces[-1]/'content-package.json').write_text('{bad output')
        return SimpleNamespace(returncode=0,stdout=b'',stderr=b'')
    monkeypatch.setattr(host.subprocess,'run',invoke)
    evidence=host.invoke_codex(message,root=tmp_path)
    assert evidence['output'] is None and evidence['raw_output']=='{bad output' and evidence['usage'] is None
    research=message.model_copy(update={'stage':'research','source_packet_sha256':None})
    with pytest.raises(host.LongFormInvocationError) as caught:host.invoke_codex(research,root=tmp_path)
    assert caught.value.evidence['error_code']=='insufficient_sources'
    assert caught.value.evidence['raw_output']=='{bad output'


def test_preflight_prepare_inspect_do_not_launch_and_mismatched_owner_is_rejected(tmp_path):
    message,_,_,_=writing_inputs();invoke=Mock();runtime_check=Mock()
    def handle(value):return host.handle(value,provider='codex',root=tmp_path,invoke=invoke,check_runtime=runtime_check,model='fixture-model')
    assert handle(message).provenance['preflight']
    message=message.model_copy(update={'resolved_model':'fixture-model'})
    assert handle(message.model_copy(update={'operation':'PrepareLongFormCallV1'})).package['state']=='prepared'
    assert handle(message.model_copy(update={'operation':'InspectLongFormCallV1'})).package['state']=='prepared'
    invoke.assert_not_called();runtime_check.assert_called_once_with()
    wrong=message.model_copy(update={'request':message.request.model_copy(update={'script_owner':'claude'})})
    with pytest.raises(ValueError,match='owner'):handle(wrong)


@pytest.mark.parametrize('failure',['timeout','oversized'])
def test_codex_failure_retains_rejected_bytes_before_workspace_cleanup(monkeypatch,tmp_path,failure):
    import hashlib,subprocess
    from tubeforge import host_codex_runner as runner
    message,_,_,_=writing_inputs();message=message.model_copy(update={'resolved_model':runner.CODEX_MODEL});workspaces=[];raw=b'{partial rejected narration'
    monkeypatch.setattr(runner,'bubblewrap_args',lambda workspace:workspaces.append(workspace) or ['stub-cli','exec'])
    monkeypatch.setattr(runner,'MAX_OUTPUT_BYTES',10 if failure=='oversized' else 2000000)
    def invoke(*args,**kwargs):
        (workspaces[-1]/'content-package.json').write_bytes(raw)
        if failure=='timeout':raise subprocess.TimeoutExpired(['stub-cli'],1,output=b'partial CLI events')
        return SimpleNamespace(returncode=0,stdout=b'',stderr=b'')
    monkeypatch.setattr(host.subprocess,'run',invoke)
    with pytest.raises(host.LongFormInvocationError) as caught:host.invoke_codex(message,root=tmp_path)
    evidence=caught.value.evidence
    assert evidence['raw_output']==raw.decode() and evidence['original_output_sha256']==hashlib.sha256(raw).hexdigest()
    assert evidence['original_output_bytes']==len(raw) and evidence['invocation_started'] is True
    assert not workspaces[-1].exists()


@pytest.mark.parametrize('failure',['malformed','timeout','oversized','error_envelope'])
def test_claude_failure_retains_bounded_original_evidence(monkeypatch,failure):
    import hashlib,subprocess
    from tubeforge import host_claude_runner as runner
    message,_,_,_=writing_inputs();message=message.model_copy(update={'request':message.request.model_copy(update={'script_owner':'claude'}),'resolved_model':runner.DEFAULT_MODEL})
    raw=b'incomplete rejected CLI response'
    if failure=='error_envelope':
        raw=b'{"is_error":true,"subtype":"error_max_turns","errors":["No structured response"],"usage":{"input_tokens":100}}'
    monkeypatch.setattr(runner,'BUDGET',Mock(max_usd_per_call=1.50));monkeypatch.setattr(runner,'claude_binary',lambda:'stub-claude')
    if failure=='oversized':monkeypatch.setattr(runner,'MAX_OUTPUT_BYTES',1)
    def invoke(*args,**kwargs):
        if failure=='timeout':raise subprocess.TimeoutExpired(['stub-claude'],1,output=raw)
        return SimpleNamespace(returncode=0,stdout=raw,stderr=b'')
    monkeypatch.setattr(host.subprocess,'run',invoke)
    with pytest.raises(host.LongFormInvocationError) as caught:host.invoke_claude(message)
    evidence=caught.value.evidence
    assert evidence['raw_output']==raw.decode() and evidence['original_output_sha256']==hashlib.sha256(raw).hexdigest()
    assert evidence['original_output_bytes']==len(raw) and evidence['invocation_started'] is True
    if failure=='error_envelope':
        assert evidence['raw_output_kind']=='cli_response'
        assert evidence['usage']['input_tokens']==100


def test_prepared_model_cannot_change_on_host_restart_before_launch(tmp_path):
    message,_,_,_=writing_inputs();message=message.model_copy(update={'resolved_model':'model-A','operation':'PrepareLongFormCallV1'})
    invoke=Mock()
    prepared=host.handle(message,provider='codex',root=tmp_path,invoke=invoke,check_runtime=lambda:None,model='model-A')
    assert prepared.package['state']=='prepared'
    execute=message.model_copy(update={'operation':'LongFormStageV1'})
    with pytest.raises(host.LongFormRuntimeMismatch) as caught:
        host.handle(execute,provider='codex',root=tmp_path,invoke=invoke,check_runtime=lambda:None,model='model-B')
    assert caught.value.invocation_started is False
    invoke.assert_not_called()
    # Old receipts remain inspectable across a deployment/model change.
    inspected=host.handle(message.model_copy(update={'operation':'InspectLongFormCallV1'}),provider='codex',root=tmp_path,invoke=invoke,check_runtime=lambda:None,model='model-B')
    assert inspected.package['state']=='prepared'
