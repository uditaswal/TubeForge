"""Batch intake surface; shares Studio tokens and operator authentication."""
from tubeforge.api.script_tools_ui import SCRIPT_TOOLS_SCRIPT
from tubeforge.api.studio_shell import STUDIO_STATIC_MENU_SCRIPT, wrap_studio_page

_MAIN_HTML = '''<main>
<div class="studio-page-head"><div><h1>Batch plans</h1><p class="sub">Import shorts for review. Publish dates are metadata only.</p></div><a href="/batch/review" class="button-link">Day review queue</a></div>
<section class="panel">
<h2>Import a plan</h2>
<p class="sub">One markdown file, one short per heading. Re-importing skips identical IDs and reports conflicts.</p>
<form id="batchForm">
<div id="dropZone" class="planbox" aria-label="Markdown plan: paste it here or drop a file onto this box">
<textarea id="batchText" required spellcheck="false" aria-label="Markdown plan" placeholder="Paste your plan here, or drop a .md file onto this box.&#10;&#10;## My short&#10;```yaml&#10;title: Why caching is hard&#10;concept: Explain cache invalidation with one real outage&#10;```&#10;&#10;Small mistakes (a missing id, a wrong length, an unknown field) are fixed for you and listed below."></textarea>
<div class="planbar"><button type="button" id="chooseFile" class="small secondary">Choose a file…</button><input id="batchFile" type="file" hidden accept=".md,.markdown,text/markdown,text/plain">
<label class="inline" for="batchPlan">Plan ID <input id="batchPlan" value="default" pattern="[a-z0-9\\-]{1,80}" required></label>
<label class="inline" for="scriptMode">Scripts <select id="scriptMode"><option value="">As set in each short</option><option value="assist">Assist: the writer fits and checks my script</option><option value="exact">Exact: use my script word for word</option></select></label></div>
</div>
<ol id="importErrors" class="import-errors" role="alert" hidden></ol>
<details id="importNotes" class="import-notes" hidden><summary id="importNotesSummary"></summary><ul id="importNotesList"></ul></details>
<p id="scriptFit" class="sub" role="status" aria-live="polite"></p>
<div class="actions"><button id="validate" type="submit">Validate and preview</button><button id="commit" type="button" class="secondary" aria-describedby="commitHint" disabled>Commit import</button></div>
<p id="commitHint" class="sub">Commit import unlocks after Validate and preview passes with no errors, and locks again if you edit the plan.</p>
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
<details id="safetyBox" class="safety-box"><summary id="safetySummary">Checking cadence and repetition…</summary><ul id="safetyWarnings" class="safety-warnings" aria-label="Cadence and repetition warnings"></ul></details>
<p id="progress" class="sub" role="status"></p><p id="result" class="sub" role="status" aria-live="polite"></p>
<div id="rows" class="day-groups" aria-live="off"></div>
</section>
</main>'''

_BATCH_COMPONENTS = """
  .planbox{@apply rounded-lg border border-dashed border-tf-line-strong bg-tf-input p-2.5;}
  .planbox:focus-within,.planbox.over{@apply border-tf-accent bg-tf-accent-soft;}
  .planbox textarea{@apply min-h-56 w-full resize-y border-0 bg-transparent p-0 text-tf-text outline-none;}
  .dropzone{@apply flex cursor-pointer flex-col items-center gap-1 rounded-lg border border-dashed border-tf-line-strong bg-tf-input px-4 py-5 text-center text-tf-text;}
  .dropzone span{@apply text-xs text-tf-muted;}
  .dropzone:hover,.dropzone:focus-visible,.dropzone.over{@apply border-tf-accent bg-tf-accent-soft;}
  .planbar{@apply mt-2 flex flex-wrap items-center gap-x-4 gap-y-2.5 border-t border-tf-line pt-2;}
  .planbar .inline{@apply flex items-center gap-2 text-xs font-medium text-tf-muted;}
  .planbar .inline input{@apply w-36;}
  .planbar .inline select{@apply max-w-[260px];}
  .import-notes{@apply mt-2.5 rounded-md border border-tf-warn-soft bg-tf-warn-soft px-3 py-2 text-xs text-tf-warn;}
  .import-notes ul{@apply mt-1.5 pl-4;}
  .import-errors{@apply mt-3 grid gap-1 rounded-md border border-tf-bad bg-tf-bad-soft py-2.5 pl-7 pr-3 text-sm text-tf-bad;}
  .import-errors button{@apply h-auto border-0 bg-transparent p-0 font-normal text-tf-bad underline;}
  .field-grid{@apply grid gap-x-4 sm:grid-cols-3;}
  .field-grid label{@apply mb-1 mt-0 block;}
  .field-grid input{@apply w-full;}
  .day-row{@apply flex flex-wrap items-end gap-3;}
  .day-row label{@apply m-0;}
  #day{@apply mr-2 inline-block w-auto;}
  .day-groups{@apply grid gap-6;}
  .day-group{@apply mt-0 grid gap-3;}
  .day-group h3{@apply flex items-center gap-2.5 text-md font-semibold;}
  .day-group h3 .count{@apply text-xs font-normal text-tf-muted;}
  .day-group h3 label{@apply ml-auto flex items-center gap-1.5 text-xs font-normal text-tf-muted;}
  .card-grid{@apply grid gap-3.5 grid-cols-[repeat(auto-fill,minmax(300px,1fr))];}
  .short-card{@apply flex overflow-hidden rounded-lg border border-tf-line bg-tf-surface;}
  .short-card .thumb{@apply flex w-[84px] aspect-[9/16] shrink-0 items-center justify-center self-start overflow-hidden bg-tf-raised text-center text-xs text-tf-muted;}
  .short-card .thumb img{@apply block h-full w-full object-cover;}
  .short-card .body{@apply flex min-w-0 flex-1 flex-col gap-2 px-3.5 pb-3.5 pt-3;}
  .short-card .pick{@apply m-0 flex items-start gap-2 font-semibold text-tf-text;}
  .short-card .meta{@apply break-words text-xs text-tf-muted;}
  .short-card a{@apply text-xs;}
  .stages{@apply m-0 flex list-none flex-wrap gap-1 p-0;}
  .stages li{@apply rounded-full border border-tf-line px-2 py-0.5 text-xs text-tf-muted;}
  .stages li.done{@apply border-tf-ok-soft text-tf-ok;}
  .stages li.current{@apply border-tf-accent bg-tf-accent-soft font-semibold text-tf-accent;}
  .stages li.attention{@apply border-tf-bad bg-tf-bad-soft font-semibold text-tf-bad;}
  .safety-box{@apply rounded-lg border border-tf-line bg-tf-input px-3 py-2;}
  .safety-box summary{@apply cursor-pointer text-sm text-tf-warn;}
  .safety-warnings{@apply mt-2 max-h-60 overflow-auto pl-4 text-sm text-tf-warn;}
  .safety-warnings li.info{@apply text-tf-muted;}
  .st-bar{@apply my-2.5 flex flex-wrap items-center gap-2;}
  .st-bar select{@apply w-auto m-0 p-2;}
  .st-bar button{@apply h-8 px-3 text-sm;}
  .st-meter{@apply my-2 rounded-md border border-tf-line bg-tf-input px-3 py-2 text-sm;}
  .st-meter.ok{@apply border-tf-ok;}
  .st-meter.warn{@apply border-tf-warn;}
  .st-meter.bad{@apply border-tf-bad;}
  .st-meter ul{@apply m-0 mt-1.5 pl-5 text-tf-muted;}
"""

_PAGE_HEAD = ('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Batch plans — TubeForge</title>'
              + '\n')


def render_batch_html(username: str | None = None) -> str:
    return (
        _PAGE_HEAD
        + wrap_studio_page('batch', username, 'Workspace / Batch plans', _MAIN_HTML, _BATCH_COMPONENTS)
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
const thumbHTML=x=>x.thumbnail_url?`<img src="${esc(x.thumbnail_url)}" alt="Thumbnail for ${esc(x.short.title)}" loading="lazy">`:'No thumbnail';
function card(x){const s=x.short,state=x.action||x.status;return `<article class="short-card" data-short="${esc(s.id)}"><div class="thumb">${thumbHTML(x)}</div><div class="body"><label class="pick"><input type="checkbox" class="batch-select" value="${esc(s.id)}"> <span>${esc(s.title)}</span></label><div class="meta">${esc(s.id)} · ${esc(s.channel||'Unassigned')} · ${s.length_s}s</div><ol class="stages" aria-label="Progress">${stagesHTML(x.stage)}</ol><div><span class="badge batch-state ${stateBadgeClass(state)}">${esc(state)}</span> <span class="badge batch-qa ${qaBadgeClass(x.qa)}">${qaText(x.qa)}</span></div>${x.failure_message?`<div class="meta">${esc(x.failure_message)}</div>`:''}${x.job_id?`<a href="/#generations" onclick="sessionStorage.setItem('tubeforge:focus-job','${esc(x.job_id)}')">Open generation and Activity</a>`:''}</div></article>`}
function display(items){const groups={};for(const x of items){const day=(x.short.publish_at||'').slice(0,10)||'Unassigned';(groups[day]=groups[day]||[]).push(x)}const days=Object.keys(groups).sort((a,b)=>a==='Unassigned'?1:b==='Unassigned'?-1:a.localeCompare(b));rows.innerHTML=days.map(day=>`<section class="day-group" data-day="${esc(day)}"><h3>${esc(day)} <span class="count">${groups[day].length} short${groups[day].length===1?'':'s'}</span><label><input type="checkbox" class="day-select" data-day="${esc(day)}" aria-label="Select every short on ${esc(day)}"> Select day</label></h3><div class="card-grid">${groups[day].map(card).join('')}</div></section>`).join('')||'<p class="sub">No imported shorts yet. Drop a markdown plan above.</p>';}
rows.onchange=e=>{const t=e.target;if(t&&t.className==='day-select'){for(const box of rows.querySelectorAll('.batch-select')){if(box.closest('[data-day]').dataset.day===t.dataset.day)box.checked=t.checked}}};
const errorsEl=document.querySelector('#importErrors');
function showErrors(list){errorsEl.hidden=!list.length;errorsEl.innerHTML=list.map(e=>`<li>${e.line?`<button type="button" data-line="${esc(e.line)}">Line ${esc(e.line)}</button>`:'Plan'}: ${esc(e.message||e.msg)}</li>`).join('');}
errorsEl.onclick=e=>{const line=Number(e.target&&e.target.dataset&&e.target.dataset.line);if(!line)return;const lines=input.value.split('\\n');const start=lines.slice(0,line-1).join('\\n').length+(line>1?1:0);input.focus();input.setSelectionRange(start,start+(lines[line-1]||'').length);};
async function readPlanFile(f){input.value=f?await f.text():'';input.oninput()}
const drop=document.querySelector('#dropZone');
document.querySelector('#chooseFile').onclick=()=>file.click();
drop.ondragover=e=>{e.preventDefault();drop.className='planbox over'};drop.ondragleave=()=>{drop.className='planbox'};
drop.ondrop=async e=>{e.preventDefault();drop.className='planbox';const f=e.dataTransfer&&e.dataTransfer.files[0];if(f)await readPlanFile(f)};
function showNotes(list){const box=document.querySelector('#importNotes');box.hidden=!list.length;document.querySelector('#importNotesSummary').textContent=list.length?list.length+' small thing'+(list.length===1?' was':'s were')+' fixed or ignored automatically (nothing blocks the import)':'';document.querySelector('#importNotesList').innerHTML=list.map(n=>`<li>Line ${esc(n.line)}: ${esc(n.message)}</li>`).join('')}
input.oninput=()=>{validated=null;commit.disabled=true;showErrors([]);showNotes([])};file.onchange=()=>readPlanFile(file.files[0]);
async function submit(save){if(busy)return;if(save&&validated!==input.value)return;busy=true;commit.disabled=true;document.querySelector('#validate').disabled=true;result.textContent=save?'Saving import…':'Validating…';try{const csrf=decodeURIComponent((document.cookie.match(/(?:^|; )tubeforge_csrf=([^;]+)/)||[])[1]||'');const response=await fetch('/api/batch-plans/import',{method:'POST',headers:{'content-type':'application/json','x-csrf-token':csrf},body:JSON.stringify({markdown:input.value,commit:save,plan_id:document.querySelector('#batchPlan').value||'default',script_mode:document.querySelector('#scriptMode').value||null})});const data=await response.json();if(!response.ok){validated=null;if(Array.isArray(data.detail)){showErrors(data.detail);throw Error(`${data.detail.length} problem${data.detail.length===1?'':'s'} found in the plan. Nothing was saved.`)}throw Error(data.detail)}showErrors([]);showNotes(data.parse_notes||[]);display(data.items);document.querySelector('#scriptFit').textContent=Object.entries(data.script_fit||{}).map(([id,f])=>id+': '+f.words+' words, '+f.estimated_seconds+' s of speech ('+f.suggestion+')'+(f.exact?' · exact mode'+(f.exact_notes&&f.exact_notes.length?': '+f.exact_notes.join(' '):': used as written'):'')).join(' · ');document.querySelector('#cadenceWarnings').textContent=(data.cadence?.warnings||[]).map(w=>`${w.ids.join(', ')}: ${w.code}`).join(' · ')||'No cadence warnings in the available publish metadata.';if(save)loadSafety();validated=input.value;result.textContent=save?'Import saved. Conflicts were preserved.':'Validation passed. Review the rows before committing.';}catch(e){result.textContent=e.message;}finally{busy=false;document.querySelector('#validate').disabled=false;commit.disabled=validated!==input.value||validated===null;}}
document.querySelector('#day').onchange=async()=>{try{const r=await fetch(planURL());if(!r.ok)throw Error('Could not load day');const items=await r.json();display(items.filter(x=>!document.querySelector('#day').value||(x.short.publish_at||'').slice(0,10)===document.querySelector('#day').value));}catch(e){result.textContent=e.message}};
document.querySelector('#produce').onclick=async e=>{const ids=[...document.querySelectorAll('.batch-select:checked')].map(x=>x.value);if(!ids.length){result.textContent='Select at least one short.';return}e.currentTarget.disabled=true;try{const csrf=decodeURIComponent((document.cookie.match(/(?:^|; )tubeforge_csrf=([^;]+)/)||[])[1]||'');const r=await fetch('/api/batch-plans/produce',{method:'POST',headers:{'content-type':'application/json','x-csrf-token':csrf},body:JSON.stringify({ids})});if(!r.ok)throw Error(await r.text());result.textContent='Jobs queued. Script and preview approvals remain required in Generations.';document.querySelector('#day').onchange();}catch(e){result.textContent=e.message}finally{document.querySelector('#produce').disabled=false}};
setInterval(async()=>{try{const response=await fetch(planURL());if(!response.ok)return;const items=await response.json();for(const row of rows.querySelectorAll('[data-short]')){const item=items.find(x=>x.short.id===row.dataset.short);if(item){const state=item.action||item.status,stateEl=row.querySelector('.batch-state'),qaEl=row.querySelector('.batch-qa');stateEl.textContent=state;stateEl.className='badge batch-state '+stateBadgeClass(state);row.querySelector('.stages').innerHTML=stagesHTML(item.stage);const thumb=row.querySelector('.thumb');if(item.thumbnail_url&&!thumb.querySelector('img'))thumb.innerHTML=thumbHTML(item);qaEl.textContent=qaText(item.qa);qaEl.className='badge batch-qa '+qaBadgeClass(item.qa);}}const p=items[0]?.progress;if(p)document.querySelector('#progress').textContent=`${p.finished} / ${p.total} finished · ${p.eta_seconds===null?'ETA unavailable while awaiting measured work or approvals':`About ${Math.ceil(p.eta_seconds/60)} minutes remaining`}`;}catch(_){/* Keep the visible rows and selection during background refresh. */}},10000);
const pretty=t=>String(t).split('_').join(' ');
async function loadSafety(){try{const r=await fetch('/api/batch-plans/safety-report');if(!r.ok)throw Error('Channel checks unavailable.');const rep=await r.json(),out=[];for(const pair of rep.similar_and_close||[])out.push(`<li>Similar and planned ${Math.round(pair.minutes_apart??pair.minutes??0)} min apart (minimum ${esc(pair.minimum_minutes)}): ${esc(pair.ids.join(' + '))} - ${esc((pair.reasons||[]).map(pretty).join(', '))}</li>`);for(const w of [...(rep.repetition?.warnings||[]),...(rep.cadence?.warnings||[])])out.push(`<li>${esc((w.ids||[]).join(', '))}: ${esc(w.code?pretty(w.code):(w.reasons||[]).map(x=>pretty(x.code)).join(', '))}</li>`);const warned=out.length>0;if(!out.length)out.push('<li class="info">No repetition or cadence warnings in the available plan and render evidence. Warnings never block production.</li>');const n=out.length-(warned?0:1);setting('safetySummary').textContent=warned?`${n} cadence/repetition warning${n===1?'':'s'} across all plans (advisory, never blocks production)`:'No repetition or cadence warnings';setting('safetyWarnings').innerHTML=out.join('');}catch(e){setting('safetyWarnings').innerHTML=`<li class="info">${esc(e.message)}</li>`;}}
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
