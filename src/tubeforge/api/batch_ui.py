"""Batch intake surface; shares Studio tokens and operator authentication."""
from tubeforge.api.studio_shell import STUDIO_CSS, STUDIO_STATIC_MENU_SCRIPT, wrap_studio_page

_MAIN_HTML = '''<main>
<div class="studio-page-head"><div><h1>Batch plans</h1><p class="sub">Import shorts for review. Publish dates are metadata only.</p></div><a href="/batch/review" class="button-link">Day review queue</a></div>
<section class="panel">
<h2>Import a plan</h2>
<p class="sub">One markdown file, one short per heading. Re-importing skips identical IDs and reports conflicts.</p>
<label for="batchPlan">Plan ID</label><input id="batchPlan" value="default" pattern="[a-z0-9-]{1,80}" required>
<form id="batchForm">
<label for="batchFile">Markdown file</label><input id="batchFile" type="file" accept=".md,.markdown,text/markdown,text/plain">
<label for="batchText">Markdown plan</label><textarea id="batchText" required></textarea>
<div class="actions"><button id="validate" type="submit">Validate and preview</button><button id="commit" type="button" class="secondary" disabled>Commit import</button></div>
</form>
</section>
<section class="panel">
<h2>Overnight production</h2>
<fieldset>
<label class="checkbox"><input id="autoEnabled" type="checkbox"> Produce automatically</label>
<div class="field-grid">
<div><label for="autoTime">Local start</label><input id="autoTime" type="time" value="22:00"></div>
<div><label for="autoZone">Time zone</label><input id="autoZone" value="Asia/Kolkata"></div>
<div><label for="autoOffset">Target day offset</label><input id="autoOffset" type="number" min="0" max="7" value="1"></div>
</div>
<div class="actions"><button id="saveAutomation" type="button">Save automatic production</button></div>
<p id="automationState" class="sub" role="status" aria-live="polite">Loading production settings…</p>
<label class="checkbox"><input id="batchHold" type="checkbox"> Hold all batch production</label>
<div class="actions"><button id="saveHold" type="button" class="secondary">Save hold</button></div>
<p id="holdState" class="sub" role="status" aria-live="polite"></p>
</fieldset>
</section>
<section class="panel">
<h2>Shorts</h2>
<div class="day-row"><div><label for="day">Day (publish metadata)</label><input id="day" type="date"></div><button id="produce" type="button">Produce selected shorts</button></div>
<p id="progress" class="sub" role="status"></p><p id="result" class="sub" role="status" aria-live="polite"></p>
<div class="table-frame"><table><thead><tr><th>Select / short</th><th>Publish metadata</th><th>Channel</th><th>Length</th><th>Status</th></tr></thead><tbody id="rows"></tbody></table></div>
</section>
</main>'''

_PAGE_HEAD = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Batch plans — TubeForge</title><style>''' + STUDIO_CSS + '''
main{max-width:980px;margin:32px auto;padding:0 20px;display:flex;flex-direction:column;gap:22px}
.panel h2{margin:0 0 4px}
.panel>p.sub{margin:0 0 18px}
.field-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:4px 16px;margin-bottom:4px}
.field-grid label{margin:14px 0 6px}
.checkbox{display:flex;align-items:center;gap:8px;margin:14px 0;color:#d5e0ee;font-size:12px;font-weight:540}
.checkbox input{margin:0}
.actions{display:flex;flex-wrap:wrap;gap:10px;margin-top:16px;align-items:center}
a.button-link{display:inline-flex;align-items:center;flex:none;background:#223346;color:#eaf4ff;border:1px solid #3c5067;border-radius:9px;padding:10px 14px;font-size:13px;font-weight:600;text-decoration:none;white-space:nowrap}
a.button-link:hover{background:#2d4258;border-color:#60758c}
table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:12px;border-bottom:1px solid var(--line);vertical-align:top;overflow-wrap:anywhere}th{font-weight:500;color:var(--muted)}.table-frame{overflow:auto;margin-top:14px}
textarea{display:block;width:100%;min-height:200px}
label{display:block;margin:14px 0 6px}
#day{display:inline-block;width:auto;margin-right:8px}
.day-row{display:flex;align-items:flex-end;flex-wrap:wrap;gap:12px;margin-bottom:14px}
.day-row label{margin:0}
@media(max-width:640px){table,thead,tbody,tr,td{display:block}thead{display:none}tr{border:1px solid var(--line);border-radius:12px;margin:10px 0;padding:6px}td{border:0;padding:6px 8px;font-size:14px}td:nth-child(2)::before{content:'Publish: ';color:var(--muted)}td:nth-child(3)::before{content:'Channel: ';color:var(--muted)}td:nth-child(4)::before{content:'Length: ';color:var(--muted)}}</style>
'''


def render_batch_html(username: str | None = None) -> str:
    return (
        _PAGE_HEAD
        + wrap_studio_page('batch', username, 'Workspace / Batch plans', _MAIN_HTML)
        + '''
<script>
const form=document.querySelector('#batchForm'),input=document.querySelector('#batchText'),file=document.querySelector('#batchFile'),commit=document.querySelector('#commit'),result=document.querySelector('#result'),rows=document.querySelector('#rows');
let validated=null,busy=false;
const planURL=()=>'/api/batch-plans?plan_id='+encodeURIComponent(document.querySelector('#batchPlan').value||'default')+(document.querySelector('#day').value?'&day='+encodeURIComponent(document.querySelector('#day').value):'');
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function display(items){rows.innerHTML=items.map(x=>{const s=x.short;return `<tr data-short="${esc(s.id)}"><td><label><input type="checkbox" class="batch-select" value="${esc(s.id)}"> ${esc(s.title)}</label><br>${esc(s.id)}</td><td>${esc(s.publish_at||'Unassigned')}</td><td>${esc(s.channel||'Unassigned')}</td><td>${s.length_s}s</td><td><span class="batch-state">${esc(x.action||x.status)}</span>${x.job_id?`<br><a href="/#generations" onclick="sessionStorage.setItem('tubeforge:focus-job','${esc(x.job_id)}')">Open generation and Activity</a>`:''}<br><span class="batch-qa">${x.qa?`QA: ${x.qa.exit_code===0?'Passed checks':x.qa.exit_code===null?'Unavailable':'Failed checks'}`:'QA pending'}</span></td></tr>`}).join('')||'<tr><td colspan="5">No imported shorts yet.</td></tr>';}
input.oninput=()=>{validated=null;commit.disabled=true};file.onchange=async()=>{input.value=file.files[0]?await file.files[0].text():'';input.oninput()};
async function submit(save){if(busy)return;if(save&&validated!==input.value)return;busy=true;commit.disabled=true;document.querySelector('#validate').disabled=true;result.textContent=save?'Saving import…':'Validating…';try{const csrf=decodeURIComponent((document.cookie.match(/(?:^|; )tubeforge_csrf=([^;]+)/)||[])[1]||'');const response=await fetch('/api/batch-plans/import',{method:'POST',headers:{'content-type':'application/json','x-csrf-token':csrf},body:JSON.stringify({markdown:input.value,commit:save,plan_id:document.querySelector('#batchPlan').value||'default'})});const data=await response.json();if(!response.ok){validated=null;throw Error(Array.isArray(data.detail)?data.detail.map(e=>`Line ${e.line||'?'}: ${e.message||e.msg}`).join(' / '):data.detail)}display(data.items);validated=input.value;result.textContent=save?'Import saved. Conflicts were preserved.':'Validation passed. Review the rows before committing.';}catch(e){result.textContent=e.message;}finally{busy=false;document.querySelector('#validate').disabled=false;commit.disabled=validated!==input.value||validated===null;}}
document.querySelector('#day').onchange=async()=>{try{const r=await fetch(planURL());if(!r.ok)throw Error('Could not load day');const items=await r.json();display(items.filter(x=>!document.querySelector('#day').value||(x.short.publish_at||'').slice(0,10)===document.querySelector('#day').value));}catch(e){result.textContent=e.message}};
document.querySelector('#produce').onclick=async e=>{const ids=[...document.querySelectorAll('.batch-select:checked')].map(x=>x.value);if(!ids.length){result.textContent='Select at least one short.';return}e.currentTarget.disabled=true;try{const csrf=decodeURIComponent((document.cookie.match(/(?:^|; )tubeforge_csrf=([^;]+)/)||[])[1]||'');const r=await fetch('/api/batch-plans/produce',{method:'POST',headers:{'content-type':'application/json','x-csrf-token':csrf},body:JSON.stringify({ids})});if(!r.ok)throw Error(await r.text());result.textContent='Jobs queued. Script and preview approvals remain required in Generations.';document.querySelector('#day').onchange();}catch(e){result.textContent=e.message}finally{document.querySelector('#produce').disabled=false}};
setInterval(async()=>{try{const response=await fetch(planURL());if(!response.ok)return;const items=await response.json();for(const row of rows.querySelectorAll('[data-short]')){const item=items.find(x=>x.short.id===row.dataset.short);if(item){row.querySelector('.batch-state').textContent=item.status;row.querySelector('.batch-qa').textContent=item.qa?`QA: ${item.qa.exit_code===0?'Passed checks':item.qa.exit_code===null?'Unavailable':'Failed checks'}`:'QA pending';}}const p=items[0]?.progress;if(p)document.querySelector('#progress').textContent=`${p.finished} / ${p.total} finished · ${p.eta_seconds===null?'ETA unavailable while awaiting measured work or approvals':`About ${Math.ceil(p.eta_seconds/60)} minutes remaining`}`;}catch(_){/* Keep the visible rows and selection during background refresh. */}},10000);
let automationDirty=false;
const setting=id=>document.querySelector('#'+id);
for(const id of ['autoEnabled','autoTime','autoZone','autoOffset','batchHold'])setting(id).onchange=()=>automationDirty=true;
async function loadAutomation(initial=false){try{const r=await fetch('/api/batch-plans/automation/'+encodeURIComponent(setting('batchPlan').value||'default'));if(!r.ok)throw Error(await r.text());const data=await r.json();if(!automationDirty){setting('autoEnabled').checked=data.enabled;setting('autoTime').value=data.start_time;setting('autoZone').value=data.timezone;setting('autoOffset').value=data.day_offset;setting('batchHold').checked=data.hold;}setting('automationState').textContent=(data.enabled?'Enabled':'Off')+' · Next: '+(data.next_run_at||'No run scheduled')+' · Last submission: '+(data.last_run?data.last_run.state+' '+JSON.stringify(data.last_run.result||{}):'pending');setting('holdState').textContent=data.hold?'Hold on: batch creation and new stages are stopped.':'Hold off.';}catch(e){setting('automationState').textContent='Could not load settings: '+e.message;}}
async function saveSetting(url,body,button){button.disabled=true;setting('automationState').textContent='Saving…';try{const csrf=decodeURIComponent((document.cookie.match(/(?:^|; )tubeforge_csrf=([^;]+)/)||[])[1]||'');const r=await fetch(url,{method:'PUT',headers:{'content-type':'application/json','x-csrf-token':csrf},body:JSON.stringify(body)});if(!r.ok)throw Error(await r.text());automationDirty=false;await loadAutomation(true);}catch(e){setting('automationState').textContent='Could not save: '+e.message;}finally{button.disabled=false}}
setting('saveAutomation').onclick=()=>saveSetting('/api/batch-plans/automation/'+encodeURIComponent(setting('batchPlan').value||'default'),{enabled:setting('autoEnabled').checked,start_time:setting('autoTime').value,timezone:setting('autoZone').value,day_offset:Number(setting('autoOffset').value)},setting('saveAutomation'));
setting('saveHold').onclick=()=>saveSetting('/api/batch-plans/hold',{hold:setting('batchHold').checked},setting('saveHold'));
setting('batchPlan').onchange=()=>{validated=null;commit.disabled=true;automationDirty=false;loadAutomation(true);setting('day').onchange()};loadAutomation(true);setInterval(()=>loadAutomation(false),10000);
form.onsubmit=e=>{e.preventDefault();submit(false)};commit.onclick=()=>submit(true);fetch(planURL()).then(async r=>{if(!r.ok)throw Error('Could not load imported shorts');display(await r.json())}).catch(e=>result.textContent=e.message);
''' + STUDIO_STATIC_MENU_SCRIPT + '''
</script></html>'''
    )


BATCH_HTML = render_batch_html(None)
