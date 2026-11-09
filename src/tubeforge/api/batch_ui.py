"""Batch intake surface; shares Studio tokens and operator authentication."""
from tubeforge.api.script_tools_ui import SCRIPT_TOOLS_CSS, SCRIPT_TOOLS_SCRIPT
from tubeforge.api.studio_shell import STUDIO_CSS, STUDIO_STATIC_MENU_SCRIPT, wrap_studio_page

_MAIN_HTML = '''<main>
<div class="studio-page-head"><div><h1>Batch plans</h1><p class="sub">Import shorts for review. Publish dates are metadata only.</p></div><a href="/batch/review" class="button-link">Day review queue</a></div>
<section class="panel">
<h2>Import a plan</h2>
<p class="sub">One markdown file, one short per heading. Re-importing skips identical IDs and reports conflicts.</p>
<label for="batchPlan">Plan ID</label><input id="batchPlan" value="default" pattern="[a-z0-9-]{1,80}" required>
<form id="batchForm">
<div id="dropZone" class="dropzone" role="button" tabindex="0" aria-label="Choose or drop a markdown plan file"><strong>Drop a .md plan here</strong><span>or press Enter to choose a file</span></div>
<label for="batchFile">Markdown file</label><input id="batchFile" type="file" accept=".md,.markdown,text/markdown,text/plain">
<label for="batchText">Markdown plan</label><textarea id="batchText" required></textarea>
<ol id="importErrors" class="import-errors" role="alert" hidden></ol>
<p id="scriptFit" class="sub" role="status" aria-live="polite"></p>
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
<h2>Shorts</h2><p id="cadenceWarnings" class="sub" role="status" aria-live="polite"></p>
<div class="day-row"><div><label for="day">Day (publish metadata)</label><input id="day" type="date"></div><button id="produce" type="button">Produce selected shorts</button></div>
<ul id="safetyWarnings" class="safety-warnings" aria-label="Cadence and repetition warnings"></ul>
<p id="progress" class="sub" role="status"></p><p id="result" class="sub" role="status" aria-live="polite"></p>
<div id="rows" class="day-groups" aria-live="off"></div>
</section>
</main>'''

_PAGE_HEAD = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Batch plans — TubeForge</title><style>''' + STUDIO_CSS + SCRIPT_TOOLS_CSS + '''
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
.dropzone{display:flex;flex-direction:column;align-items:center;gap:4px;padding:22px 16px;margin-bottom:6px;border:1.5px dashed #3c5067;border-radius:12px;background:#0f1a28;color:#d5e0ee;cursor:pointer;text-align:center}
.dropzone span{color:var(--muted);font-size:12px}
.dropzone:hover,.dropzone:focus-visible,.dropzone.over{border-color:var(--cyan);background:#12263a;outline:none}
.import-errors{margin:12px 0 0;padding:10px 12px 10px 30px;border:1px solid #7a3b46;border-radius:10px;background:#2a1519;color:#ffd5db;font-size:13px}
.import-errors li{margin:4px 0}.import-errors button{background:none;border:0;color:#ffb3bf;text-decoration:underline;padding:0;font:inherit;cursor:pointer}
.day-group{margin-top:20px}.day-group h3{display:flex;align-items:center;gap:10px;margin:0 0 10px;font-size:15px}
.day-group h3 .count{color:var(--muted);font-size:12px;font-weight:500}.day-group h3 label{margin:0 0 0 auto;display:flex;align-items:center;gap:6px;font-size:12px;font-weight:500;color:var(--muted)}
.card-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px}
.short-card{display:flex;flex-direction:column;border:1px solid var(--line);border-radius:14px;background:#0f1a28;overflow:hidden}
.short-card .thumb{aspect-ratio:16/9;background:#162538;display:flex;align-items:center;justify-content:center;color:var(--muted);font-size:12px;overflow:hidden}
.short-card .thumb img{width:100%;height:100%;object-fit:cover;display:block}
.short-card .body{padding:12px 14px 14px;display:flex;flex-direction:column;gap:8px}
.short-card .pick{display:flex;gap:8px;align-items:flex-start;margin:0;font-weight:600;color:#eaf4ff}
.short-card .meta{color:var(--muted);font-size:12px;overflow-wrap:anywhere}
.stages{display:flex;flex-wrap:wrap;gap:4px;margin:0;padding:0;list-style:none}
.stages li{font-size:11px;padding:2px 8px;border-radius:999px;border:1px solid var(--line);color:var(--muted)}
.stages li.done{color:#9fd9b6;border-color:#2c5a43}.stages li.current{background:#1d4a6d;border-color:var(--cyan);color:#eaf4ff;font-weight:600}
.stages li.attention{background:#4a1d26;border-color:#a8505e;color:#ffd5db;font-weight:600}
.safety-warnings{margin:0 0 14px;padding-left:18px;color:#f1d9a6;font-size:13px}.safety-warnings:empty{display:none}.safety-warnings li.info{color:var(--muted)}
.short-card a{font-size:12px}
@media(max-width:640px){.card-grid{grid-template-columns:1fr}}
textarea{display:block;width:100%;min-height:200px}
label{display:block;margin:14px 0 6px}
#day{display:inline-block;width:auto;margin-right:8px}
.day-row{display:flex;align-items:flex-end;flex-wrap:wrap;gap:12px;margin-bottom:14px}
.day-row label{margin:0}
</style>
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
const stateBadgeClass=status=>/fail|cancel/i.test(status)?'failed':/ready|finished|approved|published/i.test(status)?'ready':'pending';
const qaText=qa=>qa?`QA: ${qa.exit_code===0?'Passed checks':qa.exit_code===null?'Unavailable':'Failed checks'}`:'QA pending';
const qaBadgeClass=qa=>!qa?'pending':qa.exit_code===0?'ready':qa.exit_code===null?'pending':'failed';
const STAGE_ORDER=['imported','scripting','rendering','needs_review','approved','ready'],STAGE_LABEL={imported:'Imported',scripting:'Scripting',rendering:'Rendering',needs_review:'Needs review',approved:'Approved',ready:'Ready',attention:'Needs attention'};
function stagesHTML(stage){stage=stage||'imported';if(stage==='attention')return `<li class="attention" aria-current="step">${STAGE_LABEL.attention}</li>`;const at=STAGE_ORDER.indexOf(stage);return STAGE_ORDER.map((name,i)=>`<li class="${i<at?'done':i===at?'current':''}"${i===at?' aria-current="step"':''}>${STAGE_LABEL[name]}</li>`).join('');}
const thumbHTML=x=>x.thumbnail_url?`<img src="${esc(x.thumbnail_url)}" alt="Thumbnail for ${esc(x.short.title)}" loading="lazy">`:'No thumbnail yet';
function card(x){const s=x.short,state=x.action||x.status;return `<article class="short-card" data-short="${esc(s.id)}"><div class="thumb">${thumbHTML(x)}</div><div class="body"><label class="pick"><input type="checkbox" class="batch-select" value="${esc(s.id)}"> <span>${esc(s.title)}</span></label><div class="meta">${esc(s.id)} · ${esc(s.channel||'Unassigned')} · ${s.length_s}s</div><ol class="stages" aria-label="Progress">${stagesHTML(x.stage)}</ol><div><span class="badge batch-state ${stateBadgeClass(state)}">${esc(state)}</span> <span class="badge batch-qa ${qaBadgeClass(x.qa)}">${qaText(x.qa)}</span></div>${x.failure_message?`<div class="meta">${esc(x.failure_message)}</div>`:''}${x.job_id?`<a href="/#generations" onclick="sessionStorage.setItem('tubeforge:focus-job','${esc(x.job_id)}')">Open generation and Activity</a>`:''}</div></article>`}
function display(items){const groups={};for(const x of items){const day=(x.short.publish_at||'').slice(0,10)||'Unassigned';(groups[day]=groups[day]||[]).push(x)}const days=Object.keys(groups).sort((a,b)=>a==='Unassigned'?1:b==='Unassigned'?-1:a.localeCompare(b));rows.innerHTML=days.map(day=>`<section class="day-group" data-day="${esc(day)}"><h3>${esc(day)} <span class="count">${groups[day].length} short${groups[day].length===1?'':'s'}</span><label><input type="checkbox" class="day-select" data-day="${esc(day)}" aria-label="Select every short on ${esc(day)}"> Select day</label></h3><div class="card-grid">${groups[day].map(card).join('')}</div></section>`).join('')||'<p class="sub">No imported shorts yet. Drop a markdown plan above.</p>';}
rows.onchange=e=>{const t=e.target;if(t&&t.className==='day-select'){for(const box of rows.querySelectorAll('.batch-select')){if(box.closest('[data-day]').dataset.day===t.dataset.day)box.checked=t.checked}}};
const errorsEl=document.querySelector('#importErrors');
function showErrors(list){errorsEl.hidden=!list.length;errorsEl.innerHTML=list.map(e=>`<li>${e.line?`<button type="button" data-line="${esc(e.line)}">Line ${esc(e.line)}</button>`:'Plan'}: ${esc(e.message||e.msg)}</li>`).join('');}
errorsEl.onclick=e=>{const line=Number(e.target&&e.target.dataset&&e.target.dataset.line);if(!line)return;const lines=input.value.split('\\n');const start=lines.slice(0,line-1).join('\\n').length+(line>1?1:0);input.focus();input.setSelectionRange(start,start+(lines[line-1]||'').length);};
async function readPlanFile(f){input.value=f?await f.text():'';input.oninput()}
const drop=document.querySelector('#dropZone');
drop.onclick=()=>file.click();drop.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();file.click()}};
drop.ondragover=e=>{e.preventDefault();drop.className='dropzone over'};drop.ondragleave=()=>{drop.className='dropzone'};
drop.ondrop=async e=>{e.preventDefault();drop.className='dropzone';const f=e.dataTransfer&&e.dataTransfer.files[0];if(f)await readPlanFile(f)};
input.oninput=()=>{validated=null;commit.disabled=true;showErrors([])};file.onchange=()=>readPlanFile(file.files[0]);
async function submit(save){if(busy)return;if(save&&validated!==input.value)return;busy=true;commit.disabled=true;document.querySelector('#validate').disabled=true;result.textContent=save?'Saving import…':'Validating…';try{const csrf=decodeURIComponent((document.cookie.match(/(?:^|; )tubeforge_csrf=([^;]+)/)||[])[1]||'');const response=await fetch('/api/batch-plans/import',{method:'POST',headers:{'content-type':'application/json','x-csrf-token':csrf},body:JSON.stringify({markdown:input.value,commit:save,plan_id:document.querySelector('#batchPlan').value||'default'})});const data=await response.json();if(!response.ok){validated=null;if(Array.isArray(data.detail)){showErrors(data.detail);throw Error(`${data.detail.length} problem${data.detail.length===1?'':'s'} found in the plan. Nothing was saved.`)}throw Error(data.detail)}showErrors([]);display(data.items);document.querySelector('#scriptFit').textContent=Object.entries(data.script_fit||{}).map(([id,f])=>id+': '+f.words+' words, '+f.estimated_seconds+' s of speech ('+f.suggestion+')').join(' · ');document.querySelector('#cadenceWarnings').textContent=(data.cadence?.warnings||[]).map(w=>`${w.ids.join(', ')}: ${w.code}`).join(' · ')||'No cadence warnings in the available publish metadata.';if(save)loadSafety();validated=input.value;result.textContent=save?'Import saved. Conflicts were preserved.':'Validation passed. Review the rows before committing.';}catch(e){result.textContent=e.message;}finally{busy=false;document.querySelector('#validate').disabled=false;commit.disabled=validated!==input.value||validated===null;}}
document.querySelector('#day').onchange=async()=>{try{const r=await fetch(planURL());if(!r.ok)throw Error('Could not load day');const items=await r.json();display(items.filter(x=>!document.querySelector('#day').value||(x.short.publish_at||'').slice(0,10)===document.querySelector('#day').value));}catch(e){result.textContent=e.message}};
document.querySelector('#produce').onclick=async e=>{const ids=[...document.querySelectorAll('.batch-select:checked')].map(x=>x.value);if(!ids.length){result.textContent='Select at least one short.';return}e.currentTarget.disabled=true;try{const csrf=decodeURIComponent((document.cookie.match(/(?:^|; )tubeforge_csrf=([^;]+)/)||[])[1]||'');const r=await fetch('/api/batch-plans/produce',{method:'POST',headers:{'content-type':'application/json','x-csrf-token':csrf},body:JSON.stringify({ids})});if(!r.ok)throw Error(await r.text());result.textContent='Jobs queued. Script and preview approvals remain required in Generations.';document.querySelector('#day').onchange();}catch(e){result.textContent=e.message}finally{document.querySelector('#produce').disabled=false}};
setInterval(async()=>{try{const response=await fetch(planURL());if(!response.ok)return;const items=await response.json();for(const row of rows.querySelectorAll('[data-short]')){const item=items.find(x=>x.short.id===row.dataset.short);if(item){const state=item.action||item.status,stateEl=row.querySelector('.batch-state'),qaEl=row.querySelector('.batch-qa');stateEl.textContent=state;stateEl.className='badge batch-state '+stateBadgeClass(state);row.querySelector('.stages').innerHTML=stagesHTML(item.stage);const thumb=row.querySelector('.thumb');if(item.thumbnail_url&&!thumb.querySelector('img'))thumb.innerHTML=thumbHTML(item);qaEl.textContent=qaText(item.qa);qaEl.className='badge batch-qa '+qaBadgeClass(item.qa);}}const p=items[0]?.progress;if(p)document.querySelector('#progress').textContent=`${p.finished} / ${p.total} finished · ${p.eta_seconds===null?'ETA unavailable while awaiting measured work or approvals':`About ${Math.ceil(p.eta_seconds/60)} minutes remaining`}`;}catch(_){/* Keep the visible rows and selection during background refresh. */}},10000);
const pretty=t=>String(t).split('_').join(' ');
async function loadSafety(){try{const r=await fetch('/api/batch-plans/safety-report');if(!r.ok)throw Error('Channel checks unavailable.');const rep=await r.json(),out=[];for(const pair of rep.similar_and_close||[])out.push(`<li>Similar and planned ${Math.round(pair.minutes_apart??pair.minutes??0)} min apart (minimum ${esc(pair.minimum_minutes)}): ${esc(pair.ids.join(' + '))} - ${esc((pair.reasons||[]).map(pretty).join(', '))}</li>`);for(const w of [...(rep.repetition?.warnings||[]),...(rep.cadence?.warnings||[])])out.push(`<li>${esc((w.ids||[]).join(', '))}: ${esc(w.code?pretty(w.code):(w.reasons||[]).map(x=>pretty(x.code)).join(', '))}</li>`);if(!out.length)out.push('<li class="info">No repetition or cadence warnings in the available plan and render evidence. Warnings never block production.</li>');setting('safetyWarnings').innerHTML=out.join('');}catch(e){setting('safetyWarnings').innerHTML=`<li class="info">${esc(e.message)}</li>`;}}
let automationDirty=false;
const setting=id=>document.querySelector('#'+id);
for(const id of ['autoEnabled','autoTime','autoZone','autoOffset','batchHold'])setting(id).onchange=()=>automationDirty=true;
async function loadAutomation(initial=false){try{const r=await fetch('/api/batch-plans/automation/'+encodeURIComponent(setting('batchPlan').value||'default'));if(!r.ok)throw Error(await r.text());const data=await r.json();if(!automationDirty){setting('autoEnabled').checked=data.enabled;setting('autoTime').value=data.start_time;setting('autoZone').value=data.timezone;setting('autoOffset').value=data.day_offset;setting('batchHold').checked=data.hold;}setting('automationState').textContent=(data.enabled?'Enabled':'Off')+' · Next: '+(data.next_run_at||'No run scheduled')+' · Last submission: '+(data.last_run?data.last_run.state+' '+JSON.stringify(data.last_run.result||{}):'pending');setting('holdState').textContent=data.hold?'Hold on: batch creation and new stages are stopped.':'Hold off.';}catch(e){setting('automationState').textContent='Could not load settings: '+e.message;}}
async function saveSetting(url,body,button){button.disabled=true;setting('automationState').textContent='Saving…';try{const csrf=decodeURIComponent((document.cookie.match(/(?:^|; )tubeforge_csrf=([^;]+)/)||[])[1]||'');const r=await fetch(url,{method:'PUT',headers:{'content-type':'application/json','x-csrf-token':csrf},body:JSON.stringify(body)});if(!r.ok)throw Error(await r.text());automationDirty=false;await loadAutomation(true);}catch(e){setting('automationState').textContent='Could not save: '+e.message;}finally{button.disabled=false}}
setting('saveAutomation').onclick=()=>saveSetting('/api/batch-plans/automation/'+encodeURIComponent(setting('batchPlan').value||'default'),{enabled:setting('autoEnabled').checked,start_time:setting('autoTime').value,timezone:setting('autoZone').value,day_offset:Number(setting('autoOffset').value)},setting('saveAutomation'));
setting('saveHold').onclick=()=>saveSetting('/api/batch-plans/hold',{hold:setting('batchHold').checked},setting('saveHold'));
setting('batchPlan').onchange=()=>{validated=null;commit.disabled=true;automationDirty=false;loadAutomation(true);setting('day').onchange()};loadAutomation(true);setInterval(()=>loadAutomation(false),10000);loadSafety();setInterval(loadSafety,30000);
form.onsubmit=e=>{e.preventDefault();submit(false)};commit.onclick=()=>submit(true);fetch(planURL()).then(async r=>{if(!r.ok)throw Error('Could not load imported shorts');display(await r.json())}).catch(e=>result.textContent=e.message);
''' + STUDIO_STATIC_MENU_SCRIPT + '''
</script>''' + SCRIPT_TOOLS_SCRIPT + '''</html>'''
    )


BATCH_HTML = render_batch_html(None)
