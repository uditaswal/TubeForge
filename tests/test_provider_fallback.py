"""Real worker adapters and SQLite caches; all runner sockets are stubbed."""
import json
from datetime import UTC,datetime
from concurrent.futures import ThreadPoolExecutor

import pytest
from tubeforge.core.config import CodexProviderConfig, DatabaseConfig
from tubeforge.core.errors import ProviderAuthenticationError,ProviderValidationError,RetryableProviderError,ProviderCancellation
from tubeforge.db.models import Base,GenerationCacheRecord
from tubeforge.db.repositories import GenerationCacheRepository
from tubeforge.db.session import create_database
from tubeforge.domain.contracts import ContentPackage,ContentRequest
from tubeforge.providers.content.factory import ScriptOwnerRouter,ClaudeHostRunnerContentProvider
from tubeforge.providers.content.host_runner import HostRunnerContentProvider
from tubeforge.providers.content.routing_errors import RunnerFallbackFailure
from test_codex_content import request as base_request,package as raw_package


def request(**updates):
    values={'script_owner':'claude','script_model':'sonnet-medium','script_routing_mode':'automatic',**updates}
    if values['script_owner']=='codex':values['script_model']=None
    return base_request(prompt_version='m6-content-v4').model_copy(update=values)


@pytest.fixture
def cache(tmp_path):
    db=create_database(DatabaseConfig(url=f'sqlite:///{tmp_path / "cache.db"}'))
    Base.metadata.create_all(db.engine)
    yield GenerationCacheRepository(db.session_factory)
    db.dispose()


def adapter(owner,cache,answers,calls):
    def transport(path,payload,timeout):
        calls.append(owner)
        req=ContentRequest.model_validate(json.loads(payload)['request'])
        answer=answers.pop(0)
        if isinstance(answer,Exception):raise answer
        if isinstance(answer,dict):
            result={'ok':True,'result':{'package':answer,'provenance':{'writer':owner},'usage':{'input_tokens':12}}}
        elif answer=='ok':
            result={'ok':True,'result':{'package':raw_package(req),'provenance':{'writer':owner},'usage':{'input_tokens':12,'output_tokens':34}}}
        else:
            result={'ok':False,'failure':{'code':answer,'message':'api_key=supersecret failure','invocation_started':False}}
        return json.dumps(result).encode()
    cls=ClaudeHostRunnerContentProvider if owner=='claude' else HostRunnerContentProvider
    return cls(CodexProviderConfig(),cache,transport=transport)


def test_one_shot_fallback_records_actual_provider_and_replays_without_sockets(cache):
    calls=[]
    providers={o:adapter(o,cache,a,calls) for o,a in [('claude',['quota_exhausted']),('codex',['ok'])]}
    router=ScriptOwnerRouter(providers,cache)
    package=router.generate_package(request())
    assert calls==['claude','codex']
    assert package.request.script_owner=='claude' and package.request.script_routing_mode=='automatic'
    assert package.script_routing.actual_owner=='codex'
    assert package.script_routing.attempts[0]['code']=='quota_exhausted'
    assert router.last_provenance['script_routing']['actual_owner']=='codex'
    assert router.last_usage['input_tokens']==12
    resumed=ScriptOwnerRouter(providers,cache).generate_package(request())
    assert resumed==package and calls==['claude','codex']
    # Accepted delegate cache is usable even after cancelling its runner.
    assert providers['codex'].generate_package(router._request(request(),'codex'))
    assert calls==['claude','codex']


@pytest.mark.parametrize('code,kind',[('authentication_failed',ProviderAuthenticationError),('unavailable',ProviderAuthenticationError),('invalid_output',ProviderValidationError),('quality_rejected',ProviderValidationError),('source_mismatch',ProviderValidationError),('insufficient_sources',ProviderValidationError),('allowance_exhausted',ProviderValidationError),('timeout',RetryableProviderError)])
def test_ineligible_runner_errors_never_fallback(cache,code,kind):
    calls=[]
    router=ScriptOwnerRouter({'claude':adapter('claude',cache,[code],calls),'codex':adapter('codex',cache,['ok'],calls)},cache)
    with pytest.raises(kind):router.generate_package(request())
    assert calls==['claude']


@pytest.mark.parametrize('mode,owner',[('claude_only','claude'),('codex_only','codex')])
def test_single_provider_mode_never_contacts_other_membership(cache,mode,owner):
    calls=[]
    providers={o:adapter(o,cache,['ok'],calls) for o in ['claude','codex']}
    result=ScriptOwnerRouter(providers,cache).generate_package(request(script_routing_mode=mode,script_owner=owner))
    assert calls==[owner] and result.script_routing.actual_owner==owner


def test_failed_fallback_exposes_both_redacted_causes_and_never_cycles_on_restart(cache):
    calls=[]
    providers={'claude':adapter('claude',cache,['quota_exhausted'],calls),'codex':adapter('codex',cache,['authentication_failed'],calls)}
    for _ in range(2):
        with pytest.raises(ProviderValidationError) as failure:
            ScriptOwnerRouter(providers,cache).generate_package(request())
        assert 'claude: quota_exhausted' in str(failure.value)
        assert 'codex: authentication_failed' in str(failure.value)
        assert 'supersecret' not in str(failure.value)
    assert calls==['claude','codex']


def test_cancellation_never_falls_back(cache):
    calls=[]
    provider=adapter('claude',cache,[ProviderCancellation('cancelled')],calls)
    with pytest.raises(ProviderCancellation):ScriptOwnerRouter({'claude':provider,'codex':adapter('codex',cache,['ok'],calls)},cache).generate_package(request())
    assert calls==['claude']


def test_legacy_exhaustion_survives_owner_model_and_mode_changes(cache):
    now=datetime.now(UTC)
    legacy=request(script_routing_mode=None)
    first=cache.reserve_or_get(legacy,'host-claude-runner','old-model',legacy.prompt_version,now=now,reservation_seconds=600)
    assert cache.consume_invocation(first,maximum=2,now=now)
    assert cache.consume_invocation(first,maximum=2,now=now)
    cache.release_after_invocation_failure(first,maximum=2,failure={'message':'rejected'},now=now)
    calls=[]
    router=ScriptOwnerRouter({'claude':adapter('claude',cache,['ok'],calls),'codex':adapter('codex',cache,['ok'],calls)},cache)
    with pytest.raises(ProviderValidationError,match='exhausted'):router.generate_package(request(script_model='opus'))
    assert calls==[]


def test_concurrent_owners_cannot_both_consume_last_allowance(cache):
    now=datetime.now(UTC)
    req=request()
    first=cache.reserve_or_get(req,'host-claude-runner','model-a',req.prompt_version,now=now,reservation_seconds=600)
    second=cache.reserve_or_get(req.model_copy(update={'script_owner':'codex','script_model':None}),'host-codex-runner','model-b',req.prompt_version,now=now,reservation_seconds=600)
    assert cache.consume_invocation(first,maximum=2,now=now)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda r:cache.consume_invocation(r,maximum=2,now=now),[first,second]))
    assert sorted(results)==[False,True]


def test_research_stays_on_preferred_owner_without_fallback():
    class Researcher:
        def __init__(self):self.calls=0
        def research_sources(self,request):
            self.calls+=1
            raise RunnerFallbackFailure('quota_exhausted','quota')
    a,b=Researcher(),Researcher()
    with pytest.raises(RunnerFallbackFailure):ScriptOwnerRouter({'claude':a,'codex':b}).research_sources(request())
    assert (a.calls,b.calls)==(1,0)


def test_source_mismatch_in_successful_response_still_blocks_without_fallback(cache):
    calls=[]
    wrong=raw_package(ScriptOwnerRouter._request(request(),'claude'))
    wrong['request']['sources'][0]['excerpt']='An entirely different source packet.'
    router=ScriptOwnerRouter({'claude':adapter('claude',cache,[wrong],calls),'codex':adapter('codex',cache,['ok'],calls)},cache)
    with pytest.raises(ProviderValidationError,match='source packet differs'):router.generate_package(request())
    assert calls==['claude']


@pytest.mark.parametrize('error,falls_back',[(FileNotFoundError('socket missing'),True),(ConnectionRefusedError('refused'),True),(TimeoutError('slow'),False)])
def test_socket_failure_categories_are_explicit(cache,error,falls_back):
    calls=[]
    router=ScriptOwnerRouter({'claude':adapter('claude',cache,[error],calls),'codex':adapter('codex',cache,['ok'],calls)},cache)
    if falls_back:
        assert router.generate_package(request()).script_routing.actual_owner=='codex'
    else:
        with pytest.raises(RetryableProviderError):router.generate_package(request())
    assert calls==(['claude','codex'] if falls_back else ['claude'])


def test_application_routing_fields_never_enter_writer_output_schema():
    from tubeforge.host_codex_runner import codex_output_schema
    schema=codex_output_schema()
    assert 'script_routing' not in schema['properties']
    assert 'ScriptRoutingEvidence' not in schema.get('$defs',{})
    assert 'script_routing_mode' not in schema['$defs']['ContentRequest']['properties']


@pytest.mark.parametrize('answer,kind',[('quota_exhausted',RunnerFallbackFailure),(FileNotFoundError('missing'),RunnerFallbackFailure),(TimeoutError('slow'),RetryableProviderError),('authentication_failed',ProviderAuthenticationError),(ProviderCancellation('cancelled'),ProviderCancellation)])
def test_preflight_failures_keep_their_category_and_do_not_charge_generation(cache,monkeypatch,answer,kind):
    from sqlalchemy import select,func
    monkeypatch.setattr('tubeforge.providers.content.host_runner.build_content_prompt',lambda *args,**kwargs:'stub prompt')
    monkeypatch.setattr('tubeforge.providers.content.youtube_skills.preflight',lambda **kwargs:{'skill':'hash'})
    calls=[]
    provider=adapter('claude',cache,[answer],calls)
    with pytest.raises(kind):provider.generate_package(request(prompt_version='m6-content-v6'))
    with cache._session_factory() as session:
        assert session.scalar(select(func.count()).select_from(GenerationCacheRecord))==0
    assert calls==['claude']
