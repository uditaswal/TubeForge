"""Dashboard Settings page and API for the operator-editable runtime settings (see core/runtime_settings.py).

Authentication and CSRF come from the application middleware, like every other /api route.
"""
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict

from tubeforge.api.design_system import standalone_style
from tubeforge.api.studio_shell import STUDIO_STATIC_MENU_SCRIPT, wrap_studio_page
from tubeforge.core import runtime_settings as store_module

_MAIN_HTML = '''<main>
<div class="studio-page-head"><div><h1>Settings</h1><p class="sub">Values you can change without a restart. A change applies to the next job. Everything else stays in <code>config/*.yaml</code>.</p></div></div>
<p id="settingsStatus" class="sub" role="status" aria-live="polite">Loading settings…</p>
<div id="settingsGroups"></div>
<section class="panel"><h2>Recent changes</h2><ul id="settingsAudit" class="audit"></ul></section>
<section class="panel"><h2>Everything else (read-only)</h2><p class="sub">Every other value from <code>config/production.yaml</code>, and the environment variables that change how runs behave. They are listed so nothing is hidden. Changing one means editing the file (or the process environment) and restarting; some are locked on purpose.</p><div id="referenceGroups"><p class="sub">Loading…</p></div></section>
<section class="panel"><h2>Not editable here</h2><p class="sub">The two-attempt limit per source packet is part of the safety contract and is not a setting: a rejected script is retried automatically using the remaining attempt, and a revised brief or new sources starts a fresh packet.</p></section>
</main>'''

_SETTINGS_COMPONENTS = """
  .setting{@apply grid gap-2.5 border-t border-tf-line py-3.5 first-of-type:border-t-0 first-of-type:pt-0;}
  .setting-head{@apply mb-1 flex flex-wrap items-center gap-2.5;}
  .setting-head strong{@apply text-base font-semibold text-tf-text;}
  .setting .help{@apply m-0 mb-2.5 text-sm text-tf-muted;}
  .setting-row{@apply flex flex-wrap items-center gap-2.5;}
  .setting input[type=number]{@apply w-40;}
  .setting .default{@apply text-xs text-tf-muted;}
  .setting .state{@apply mt-1.5 min-h-5 text-xs;}
  .state.bad{@apply text-tf-bad;}
  .state.good{@apply text-tf-ok;}
  .audit{@apply m-0 grid list-none gap-1.5 p-0 text-xs text-tf-muted;}
  .ref{@apply border-t border-tf-line py-2;}
  .ref summary{@apply cursor-pointer font-semibold text-tf-text;}
  .ref-table{@apply mt-2 w-full border-collapse text-xs;}
  .ref-table td{@apply break-words border-t border-tf-line px-2 py-1.5 align-top;}
  .ref-table td:first-child{@apply w-[34%] font-mono;}
  .ref-table tr.here td{@apply text-tf-ok;}
  .ref-table tr.locked td{@apply text-tf-muted;}
  @media (max-width:640px){.setting input[type=number]{width:100%}.ref-table td{display:block;width:auto!important;border-top:0}.ref-table tr{display:block;border-top:1px solid var(--tf-line);padding:6px 0}}
"""

_PAGE_HEAD = ('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Settings — TubeForge</title>'
              + standalone_style(_SETTINGS_COMPONENTS) + '\n')

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
async function loadReference(){const holder=document.querySelector('#referenceGroups');try{const data=await call('GET','/api/runtime-settings/reference');holder.replaceChildren();
  for(const group of data.groups){const box=document.createElement('details');box.className='ref';const sum=document.createElement('summary');sum.textContent=group.name+' ('+group.rows.length+')';box.append(sum);
    const table=document.createElement('table');table.className='ref-table';for(const row of group.rows){const tr=document.createElement('tr');if(row.editable_here)tr.className='here';else if(row.locked)tr.className='locked';
      const k=document.createElement('td');k.textContent=row.key;const v=document.createElement('td');v.textContent=String(row.value);const h=document.createElement('td');h.textContent=row.how;tr.append(k,v,h);table.append(tr)}box.append(table);holder.append(box)}
  const env=document.createElement('details');env.className='ref';const s2=document.createElement('summary');s2.textContent='Environment variables ('+data.environment.length+')';env.append(s2);
  const t2=document.createElement('table');t2.className='ref-table';for(const row of data.environment){const tr=document.createElement('tr');const a=document.createElement('td');a.textContent=row.names;const b=document.createElement('td');b.textContent=row.process;const c=document.createElement('td');c.textContent=row.effect+(row.restart?' (needs a restart)':'');tr.append(a,b,c);t2.append(tr)}env.append(t2);holder.append(env)}catch(error){holder.textContent='Could not load the reference: '+error.message}}
loadReference();
load();
''' + STUDIO_STATIC_MENU_SCRIPT + '''
</script>'''


# Values that must never be changed from a web page, with the reason shown next to them.
_LOCKED = (
    ("invocation_limit", "The two-attempt allowance per request is part of the safety contract."),
    ("reservation_seconds", "Tied to the two-attempt allowance; changing it could double-spend a request."),
    ("auth.", "Login security: change it in the file and restart."),
    ("app.port", "The address the dashboard listens on; change it in the file and restart."),
    ("database.", "Database connection; change it in the file and restart."),
    ("socket_path", "Where the host runner listens; a wrong value cuts the worker off from it."),
    ("socket_timeout_seconds", "Must stay below the runner's own time limit; change it in the file and restart."),
    ("width", "Render geometry: quality checks assume it."), ("height", "Render geometry: quality checks assume it."),
    ("sample_rate", "Audio format the quality checks assume."), ("crf", "Encoder quality used by the quality checks."),
    ("fps", "Frame rate the quality checks assume."), ("caption_", "Caption layout tuned for the render size."),
)
# Where a file value has an equivalent on this page.
_ON_PAGE = {
    "pipeline.claude.max_prompt_chars": "prompt.max_chars_claude", "worker.max_attempts": "worker.max_attempts",
    "worker.retry_base_seconds": "worker.retry_base_seconds", "worker.retry_max_seconds": "worker.retry_max_seconds",
    "pipeline.source_clips.max_clip_seconds": "clips.max_clip_seconds", "pipeline.source_clips.engaging_only": "clips.engaging_only",
    "pipeline.source_clips.timeout_seconds": "clips.inspect_timeout_seconds",
    "pipeline.source_clips.max_source_duration_seconds": "clips.max_source_minutes",
    "pipeline.source_clips.max_download_bytes": "clips.max_download_gb",
}
_SECRET_WORDS = ("key", "token", "secret", "password", "encryption", "cookie")
# Environment variables that change how runs behave. Values are never shown: they live in the process that reads them.
_ENVIRONMENT = (
    ("TUBEFORGE_CONFIG", "web, worker", "Which config file to load.", True),
    ("TUBEFORGE_WORKER_MODES", "worker", "all, clips or shorts: which kind of job this worker takes (scripts/stackctl.sh sets it).", True),
    ("TUBEFORGE_RUNTIME_SETTINGS", "web, worker, runner", "Where this page's values are stored.", True),
    ("TUBEFORGE_CLAUDE_MAX_CALLS_PER_DAY", "Claude runner", "Shared daily call limit across scripts and clips (default 40).", True),
    ("TUBEFORGE_CLAUDE_MAX_USD_PER_DAY", "Claude runner", "Shared daily spend limit (default $8).", True),
    ("TUBEFORGE_CLAUDE_MAX_USD_PER_CALL", "Claude runner", "Spend limit for a single call (default $1.50).", True),
    ("TUBEFORGE_CLAUDE_CLIP_CALLS_PER_DAY", "Claude runner", "Default for the clip allowance; the value on this page overrides it.", True),
    ("TUBEFORGE_CLAUDE_CLIP_MODEL", "Claude runner", "Which Claude model answers clip requests.", True),
    ("TUBEFORGE_CLAUDE_MAX_PROMPT_CHARS", "Claude runner", "The runner's own prompt ceiling; the script prompt setting above is clamped to it.", True),
    ("TUBEFORGE_CLAUDE_BIN / TUBEFORGE_CLAUDE_SOCKET / TUBEFORGE_CLAUDE_LEDGER", "Claude runner", "Where the Claude program, its socket and its spend ledger are.", True),
    ("YOUTUBE_DOWNLOAD_PROVIDER / YOUTUBE_PROXY_URL / YOUTUBE_PROXY_TIMEOUT_SECONDS", "worker", "How videos are downloaded; a proxy is optional.", True),
    ("YOUTUBE_DIRECT_SECTIONS / YOUTUBE_SECTION_PADDING_SECONDS", "worker", "Download only the needed sections of a video (needs a JavaScript runtime for yt-dlp).", True),
    ("WHISPER_MODEL / WHISPER_COMPUTE_TYPE / TRANSCRIPTION_LANGUAGE", "worker", "Which speech model transcribes, how precisely, and the language.", True),
    ("TEMP_DIR / TUBEFORGE_CLIPS_LOCK_DIR", "worker", "Scratch folders. Keep them on the data disk: /tmp here is a 1.9 GB memory disk.", True),
    ("TUBEFORGE_LOG_LEVEL / TUBEFORGE_LOG_MAX_MB / TUBEFORGE_LOG_RETENTION_DAYS", "all", "How much is logged and for how long.", True),
    ("TUBEFORGE_PIXABAY_API_KEY, YOUTUBE_DATA_API_KEY, PEXELS_API_KEY, TUBEFORGE_ACCOUNT_ENCRYPTION_KEY", "various", "Secrets: never shown or editable here.", True),
)


def _leaves(value, path=""):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _leaves(item, f"{path}.{key}" if path else str(key))
    elif isinstance(value, (str, int, float, bool)) or value is None:
        yield path, value


def configuration_reference(settings, store) -> dict:
    """Every other file value, read-only, with how to change it; plus the environment variables that matter."""
    rows = []
    for path, value in _leaves(settings.model_dump(mode="json")):
        if ".presets." in path or path.startswith("pipeline.video_generation.presets"):
            continue
        lowered = path.lower()
        if any(word in lowered for word in _SECRET_WORDS):
            value = "set" if value else "not set"
        locked = next((reason for needle, reason in _LOCKED if needle in lowered), None)
        page_key = _ON_PAGE.get(path)
        if page_key:
            how = "Editable on this page without a restart: " + (store_module.BY_KEY[page_key].label if page_key in store_module.BY_KEY else page_key)
        elif locked:
            how = "Not editable from here. " + locked
        else:
            how = "Edit config/production.yaml and restart the worker (and the web server if it is a web value)."
        rows.append({"key": path, "value": value, "how": how, "editable_here": bool(page_key), "locked": bool(locked and not page_key)})
    groups: dict[str, list] = {}
    for row in rows:
        parts = row["key"].split(".")
        groups.setdefault(".".join(parts[:2]) if parts[0] == "pipeline" and len(parts) > 2 else parts[0], []).append(row)
    return {
        "groups": [{"name": name, "rows": items} for name, items in sorted(groups.items())],
        "environment": [{"names": names, "process": process, "effect": effect, "restart": restart} for names, process, effect, restart in _ENVIRONMENT],
    }


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

    @app.get("/api/runtime-settings/reference", tags=["settings"])
    def settings_reference():
        return configuration_reference(app.state.settings, store_module.shared())

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
