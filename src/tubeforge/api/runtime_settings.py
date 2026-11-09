"""Dashboard Settings page and API for the operator-editable runtime settings (see core/runtime_settings.py).

Authentication and CSRF come from the application middleware, like every other /api route.
"""
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict

from tubeforge.api.studio_shell import STUDIO_CSS, STUDIO_STATIC_MENU_SCRIPT, wrap_studio_page
from tubeforge.core import runtime_settings as store_module

_MAIN_HTML = '''<main>
<div class="studio-page-head"><div><h1>Settings</h1><p class="sub">Values you can change without a restart. A change applies to the next job. Everything else stays in <code>config/*.yaml</code>.</p></div></div>
<p id="settingsStatus" class="sub" role="status" aria-live="polite">Loading settings…</p>
<div id="settingsGroups"></div>
<section class="panel"><h2>Recent changes</h2><ul id="settingsAudit" class="audit"></ul></section>
<section class="panel"><h2>Not editable here</h2><p class="sub">The two-attempt limit per source packet is part of the safety contract and is not a setting: a rejected script is retried automatically using the remaining attempt, and a revised brief or new sources starts a fresh packet.</p></section>
</main>'''

_PAGE_HEAD = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Settings — TubeForge</title><style>''' + STUDIO_CSS + '''
main{max-width:900px;margin:32px auto;padding:0 20px;display:flex;flex-direction:column;gap:22px}
.panel h2{margin:0 0 12px}
.setting{padding:14px 0;border-top:1px solid var(--line)}.setting:first-of-type{border-top:0;padding-top:0}
.setting-head{display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin-bottom:4px}.setting-head strong{font-size:14px}
.setting .help{margin:0 0 10px;color:var(--muted);font-size:12px;line-height:1.5}
.setting-row{display:flex;flex-wrap:wrap;align-items:center;gap:10px}
.setting input[type=number]{width:160px}.setting .default{color:var(--muted);font-size:12px}
.setting .state{font-size:12px;min-height:1.2em;margin-top:6px}.state.bad{color:#ffb3bf}.state.good{color:#9fd9b6}
.audit{list-style:none;padding:0;margin:0;display:grid;gap:6px;font-size:12px;color:var(--muted)}
.checkbox{display:flex;align-items:center;gap:8px;margin:0;font-weight:540}.checkbox input{margin:0}
@media(max-width:640px){main{margin:16px auto;padding:0 14px}.setting input[type=number]{width:100%}}</style>
'''

_SCRIPT = r'''
<script>
const groupsEl=document.querySelector('#settingsGroups'),statusEl=document.querySelector('#settingsStatus'),auditEl=document.querySelector('#settingsAudit');
const csrf=()=>decodeURIComponent((document.cookie.match(/(?:^|; )tubeforge_csrf=([^;]+)/)||[])[1]||'');
function el(tag,text,cls){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e}
const shown=v=>typeof v==='boolean'?(v?'on':'off'):String(v);
async function call(method,path,body){const r=await fetch(path,{method,headers:{'content-type':'application/json','x-csrf-token':csrf()},body:body===undefined?undefined:JSON.stringify(body)});const data=await r.json().catch(()=>({}));if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:'Request failed ('+r.status+')');return data}
function renderAudit(list){auditEl.replaceChildren();if(!list.length){auditEl.append(el('li','No changes yet.'));return}for(const a of list)auditEl.append(el('li',`${a.at.replace('T',' ').replace('+00:00',' UTC')} · ${a.by} · ${a.key}: ${shown(a.old)} → ${shown(a.new)}`))}
function row(s){
  const box=el('div',undefined,'setting');box.dataset.key=s.key;
  const head=el('div',undefined,'setting-head');head.append(el('strong',s.label));
  const badge=el('span',s.overridden?'Changed from default':'Default','badge '+(s.overridden?'pending':'ready'));head.append(badge);
  const state=el('div','','state');state.setAttribute('role','status');state.setAttribute('aria-live','polite');
  let input;const row=el('div',undefined,'setting-row');
  if(s.kind==='bool'){const label=el('label',undefined,'checkbox');input=el('input');input.type='checkbox';input.checked=!!s.value;label.append(input,document.createTextNode(' On'));row.append(label)}
  else{input=el('input');input.type='number';input.value=s.value;input.min=s.minimum;input.max=s.maximum;input.step=1;input.setAttribute('aria-label',s.label);row.append(input)}
  const save=el('button','Save');save.type='button';const reset=el('button','Reset to default','secondary');reset.type='button';reset.disabled=!s.overridden;
  row.append(save,reset,el('span',`Default ${shown(s.default)}`+(s.kind==='int'?` · allowed ${s.minimum} to ${s.maximum}`:''),'default'));
  const busy=on=>{save.disabled=on;reset.disabled=on||!s.overridden;input.disabled=on};
  const finish=(next,message)=>{Object.assign(s,next);badge.textContent=s.overridden?'Changed from default':'Default';badge.className='badge '+(s.overridden?'pending':'ready');if(s.kind==='bool')input.checked=!!s.value;else input.value=s.value;state.className='state good';state.textContent=message;reset.disabled=!s.overridden;loadAudit()};
  save.onclick=async()=>{busy(true);state.className='state';state.textContent='Saving…';try{const value=s.kind==='bool'?input.checked:Number(input.value);if(s.kind==='int'&&!Number.isInteger(value))throw Error('Enter a whole number');finish(await call('PUT','/api/runtime-settings/'+encodeURIComponent(s.key),{value}),'Saved. Applies to the next job.')}catch(e){state.className='state bad';state.textContent=e.message}finally{busy(false)}};
  reset.onclick=async()=>{busy(true);state.className='state';state.textContent='Resetting…';try{finish(await call('DELETE','/api/runtime-settings/'+encodeURIComponent(s.key)),'Back to the default.')}catch(e){state.className='state bad';state.textContent=e.message}finally{busy(false)}};
  box.append(head,el('p',s.help,'help'),row,state);return box}
async function loadAudit(){try{renderAudit((await call('GET','/api/runtime-settings')).audit)}catch(_){}}
async function load(){try{const data=await call('GET','/api/runtime-settings');groupsEl.replaceChildren();const groups={};for(const s of data.settings)(groups[s.group]=groups[s.group]||[]).push(s);for(const [name,list] of Object.entries(groups)){const panel=el('section',undefined,'panel');panel.append(el('h2',name));for(const s of list)panel.append(row(s));groupsEl.append(panel)}renderAudit(data.audit);statusEl.textContent='Changes are saved to data/config/runtime-settings.json and shared by the web server and the worker.'}catch(e){statusEl.textContent='Could not load settings: '+e.message+'. Reload the page to retry.'}}
load();
''' + STUDIO_STATIC_MENU_SCRIPT + '''
</script>'''


class SettingValue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: Any


def render_settings_html(username: str | None = None) -> str:
    return _PAGE_HEAD + wrap_studio_page("settings", username, "Workspace / Settings", _MAIN_HTML) + _SCRIPT + "</html>"


def register_settings_routes(app, runtime):
    def actor(request: Request) -> str:
        session = runtime.auth.session(request.cookies.get("tubeforge_session"))
        return (runtime.auth.username_for(session.user_id) if session else None) or "operator"

    @app.get("/api/runtime-settings", tags=["settings"])
    def list_settings():
        store = store_module.shared()
        return {"settings": store.snapshot(app.state.settings), "audit": store.audit(20), "path": str(store.path)}

    @app.put("/api/runtime-settings/{key}", tags=["settings"])
    def put_setting(key: str, body: SettingValue, request: Request):
        try:
            return store_module.shared().update(key, body.value, actor(request), app.state.settings)
        except store_module.SettingError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.delete("/api/runtime-settings/{key}", tags=["settings"])
    def reset_setting(key: str, request: Request):
        try:
            return store_module.shared().reset(key, actor(request), app.state.settings)
        except store_module.SettingError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.get("/settings", response_class=HTMLResponse, include_in_schema=False)
    def settings_page(request: Request):
        session = runtime.auth.session(request.cookies.get("tubeforge_session"))
        return render_settings_html(runtime.auth.username_for(session.user_id) if session else None)
