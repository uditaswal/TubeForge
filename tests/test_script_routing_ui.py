"""Execute the actual mode editor against authenticated local API calls."""
import json
from fastapi.testclient import TestClient
from tubeforge.api.app import create_app
from tubeforge.api.script_routing_ui import ROUTING_SCRIPT
from test_provider_routing_api import settings_for,sign_in
from test_batch_ui_runtime import runtime


PREFACE=r'''
const window=globalThis;
Element.prototype.setAttribute=function(key,value){this[key]=value;};
Element.prototype.addEventListener=function(type,fn){this.listeners=this.listeners||{};this.listeners[type]=fn;};
Element.prototype.insertBefore=function(child,before){const index=this.children.indexOf(before);if(index<0)this.children.push(child);else this.children.splice(index,0,child);};
const form=document.createElement('form'),ownerLabel=document.createElement('label'),ownerSelect=document.createElement('select'),submitButton=document.createElement('button');
form.append(ownerLabel,submitButton);ownerLabel.append(ownerSelect);form.querySelector=selector=>selector==='[type=submit]'?submitButton:null;
'''


def editor(client):
    return runtime(client,'<script>'+PREFACE+ROUTING_SCRIPT+'</script>')


def test_mode_editor_saves_confirms_models_and_preserves_unsaved_generation_guard(tmp_path):
    with TestClient(create_app(settings_for(tmp_path))) as client:
        sign_in(client,True)
        context,run=editor(client)
        assert context.eval('routingReady')
        context.eval('routingMode.value="codex_only"')
        run('routingMode.onchange()')
        assert context.eval('submitButton.disabled')
        assert not context.eval('routingCanSubmit()')
        run('routingSave.onclick()')
        assert client.get('/api/script-routing').json()['mode']=='codex_only'
        assert context.eval('routingStatus.textContent.includes("Saved: Codex only")')
        assert context.eval('ownerSelect.children.map(x=>x.value).join(",")')=='gpt-sol'
        assert not context.eval('submitButton.disabled')
        context.eval('routingMode.value="automatic"')
        run('routingMode.onchange()')
        context.eval('routingPreferred.value="sonnet-medium"')
        run('routingPreferred.onchange()')
        run('routingSave.onclick()')
        assert client.get('/api/script-routing').json()['mode']=='automatic'
        assert context.eval('ownerSelect.children.length')==3
        assert context.eval('ownerSelect.value')=='sonnet-medium'


def test_stale_save_reports_failure_and_requires_reload(tmp_path):
    with TestClient(create_app(settings_for(tmp_path))) as client:
        sign_in(client,True)
        context,run=editor(client)
        client.put('/api/script-routing',json={'mode':'claude_only','preferred_model':'opus','expected_revision':0})
        context.eval('routingMode.value="codex_only"');run('routingMode.onchange()')
        run('routingSave.onclick()')
        assert 'changed' in context.eval('routingStatus.textContent')
        assert context.eval('submitButton.disabled')
        assert client.get('/api/script-routing').json()['mode']=='claude_only'
        run('routingReload.onclick()')
        assert context.eval('routingMode.value')=='claude_only'
        assert context.eval('ownerSelect.value')=='opus'
        assert not context.eval('submitButton.disabled')


def test_load_and_unconfirmed_save_failures_are_truthful(tmp_path):
    with TestClient(create_app(settings_for(tmp_path))) as client:
        sign_in(client,True)
        context,run=editor(client)
        context.eval('globalThis.originalFetch=fetch;fetch=(url,options)=>url==="/api/script-routing"?Promise.reject(Error("Connection lost")):originalFetch(url,options)')
        run('routingSave.onclick()')
        assert 'Save not confirmed' in context.eval('routingStatus.textContent')
        assert context.eval('submitButton.disabled')
        assert client.get('/api/script-routing').json()['mode'] is None
        run('routingReload.onclick()')
        assert 'Reload' in context.eval('routingStatus.textContent')
        context.eval('fetch=originalFetch');run('routingReload.onclick()')
        assert context.eval('routingReady') and not context.eval('submitButton.disabled')


def test_unavailable_modes_are_disabled_in_editor(tmp_path):
    with TestClient(create_app(settings_for(tmp_path,False))) as client:
        sign_in(client,True)
        context,run=editor(client)
        assert context.eval('routingMode.children.filter(x=>x.disabled).map(x=>x.value).sort().join(",")')=='automatic,claude_only'
        assert context.eval('ownerSelect.children.map(x=>x.value).join(",")')=='gpt-sol'


def test_all_dashboard_inline_scripts_parse(tmp_path):
    import re,quickjs
    with TestClient(create_app(settings_for(tmp_path))) as client:
        sign_in(client,True)
        scripts=re.findall(r'<script[^>]*>(.*?)</script>',client.get('/').text,re.S)
        assert len(scripts)>1
        context=quickjs.Context()
        for script in scripts:
            context.eval('new Function('+json.dumps(script)+')')


def test_async_generation_preserves_confirmed_policy_after_form_reset(tmp_path):
    from tubeforge.api.script_routing_ui import GENERATION_SUBMIT_SCRIPT
    with TestClient(create_app(settings_for(tmp_path))) as client:
        sign_in(client,True)
        client.put('/api/script-routing',json={'mode':'codex_only','preferred_model':'gpt-sol','expected_revision':0})
        context,run=editor(client)
        context.eval(r'''
        const notice=document.createElement('p'),durationField=document.createElement('input'),captionField=document.createElement('input');
        globalThis.refresh=async()=>{};elements['#createForm']=form;form.querySelector=selector=>selector==='[type=submit]'?submitButton:selector.includes('duration_seconds')?durationField:captionField;
        form.reset=()=>{routingMode.value='claude_only';routingPreferred.value='sonnet-medium';ownerSelect.value='sonnet-medium';};
        class FormData{get(name){return {title:'Async create',notes:'Local test notes',duration_seconds:'60',review_mode:'manual'}[name]||null;}has(name){return name==='captions_enabled';}}
        ''')
        context.eval(GENERATION_SUBMIT_SCRIPT)
        context.eval('globalThis.event={currentTarget:form,preventDefault:()=>{}};globalThis.creation=form.onsubmit(event);event.currentTarget=null;')
        assert context.eval('submitButton.disabled')
        run('creation')
        assert 'Generation created' in context.eval('notice.textContent')
        assert context.eval('routingMode.value')=='codex_only'
        assert context.eval('ownerSelect.value')=='gpt-sol'
        assert not context.eval('submitButton.disabled')
        assert len(client.get('/api/jobs').json())==1
        context.eval('fetch=()=>Promise.reject(Error("Connection lost"));globalThis.failedEvent={currentTarget:form,preventDefault:()=>{}};globalThis.failure=form.onsubmit(failedEvent);failedEvent.currentTarget=null;')
        run('failure')
        assert 'not confirmed' in context.eval('notice.textContent')
        assert not context.eval('submitButton.disabled')
        assert context.eval('routingMode.value')=='codex_only'
