"""Local review surface. Preserve the open player during silent refresh."""
from tubeforge.api.studio_shell import STUDIO_CSS, STUDIO_STATIC_MENU_SCRIPT, wrap_studio_page

_MAIN_HTML = r'''<main>
<div class="studio-page-head"><div><h1>Day review</h1><p class="sub">Review the exact local video. Ready means staged for later publishing.</p></div></div>
<section class="panel">
<div class="day-row"><div><label for="day">Day (publish metadata; leave blank for all)</label><input id="day" type="date"></div><button id="refresh" type="button" class="secondary">Refresh</button></div>
<p id="notice" class="sub" role="status" aria-live="polite">Loading review queue…</p>
</section>
<div class="review-layout">
<section class="panel" aria-label="Day videos"><ul id="reviewList"></ul></section>
<section class="panel" id="detail" aria-label="Selected video"><p>Select a short to review its video, QA, and script.</p></section>
</div>
</main>'''

_PAGE_HEAD = r'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Day review — TubeForge</title><style>''' + STUDIO_CSS + r'''
main{max-width:1160px;margin:32px auto;padding:0 20px;display:flex;flex-direction:column;gap:22px}
.panel h2,.panel h3:first-child{margin-top:0}
.day-row{display:flex;align-items:flex-end;flex-wrap:wrap;gap:12px}
.day-row label{margin:0 0 6px}
.review-layout{display:grid;grid-template-columns:minmax(220px,1fr) minmax(0,2fr);gap:20px;align-items:start}
#reviewList{list-style:none;padding:0;margin:0}#reviewList button{display:block;text-align:left;width:100%;background:var(--studio-panel-alt);border:1px solid var(--line);border-radius:9px;color:inherit;margin:0 0 8px;padding:10px 12px}#reviewList li:last-child button{margin-bottom:0}
video{display:block;width:100%;max-height:65vh;background:#000;border-radius:10px}img{max-width:240px;width:100%;height:auto;border-radius:8px;margin-top:10px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:var(--studio-input);border:1px solid var(--line);border-radius:9px;padding:12px;font-size:12px;max-height:50vh;overflow:auto}
.qa-list{list-style:none;padding:0;margin:0 0 14px;display:grid;gap:6px}.qa-list li{display:flex;align-items:flex-start;gap:8px;font-size:13px;line-height:1.5}.qa-list .badge{flex:none;margin-top:1px}
#actions{display:flex;flex-wrap:wrap;gap:8px;margin:16px 0}#actions button{min-height:44px}
label{display:block;margin:14px 0 6px}
@media(max-width:760px){.review-layout{grid-template-columns:1fr}main{margin:16px auto;padding:0 14px}}</style>
'''


def render_review_html(username: str | None = None) -> str:
    return (
        _PAGE_HEAD
        + wrap_studio_page('batch', username, 'Workspace / Batch plans / Day review', _MAIN_HTML)
        + r'''
<script>
const list=document.querySelector('#reviewList'),detail=document.querySelector('#detail'),notice=document.querySelector('#notice'),day=document.querySelector('#day');let selected=null,items=[],busy=false,signature='';
function node(tag,text){const el=document.createElement(tag);if(text!==undefined)el.textContent=text;return el;}
function qaChecks(qa){if(!qa||!qa.output)return null;try{const parsed=JSON.parse(qa.output);return Array.isArray(parsed)?parsed:null;}catch(_){return null;}}
function qaList(qa){
  const checks=qaChecks(qa);
  if(!qa)return node('p','No QA result recorded. Approval is disabled until checks pass for this video.');
  if(!checks){const fallback=node('pre',qa.error||qa.output||'QA did not record a readable result.');return fallback;}
  const list=node('ul');list.className='qa-list';
  for(const {level,check,detail} of checks){
    const item=node('li');
    const badge=node('span',level);badge.className='badge '+(level==='FAIL'?'failed':level==='WARN'?'pending':'ready');
    item.append(badge,node('span',' '+check+': '+detail));
    list.append(item);
  }
  if(!checks.length)list.append(node('li','No checks recorded.'));
  return list;
}
function show(item){selected=item;detail.replaceChildren();const stateLabel=node('p',`Review: ${item.state}${item.decision?' · '+item.decision:''} · Production: ${item.production_state}`);stateLabel.id='reviewStatus';detail.append(node('h2',item.short.title),stateLabel);if(item.preview_url){const video=node('video');video.controls=true;video.preload='metadata';video.src=item.preview_url;if(item.thumbnail_url)video.poster=item.thumbnail_url;detail.append(video);}else detail.append(node('p',item.error||'The final video is not available for review yet.'));
if(item.thumbnail_url){const image=node('img');image.src=item.thumbnail_url;image.alt=`Thumbnail for ${item.short.title}`;detail.append(image);}else detail.append(node('p',(item.thumbnail_result?.reason||'Thumbnail unavailable.')+' Brief: '+(item.short.thumbnail?.text||'No text')+' · '+(item.short.thumbnail?.visual||'No visual brief')));
detail.append(node('h3','QA result'),qaList(item.qa));
const actions=node('div');actions.id='actions';for(const [action,label] of [['approve','Approve'],['reject','Reject'],['regenerate','Regenerate'],['ready','Stage as ready']]){const button=node('button',label);button.type='button';button.dataset.action=action;button.disabled=!item.available||busy||(action==='approve'&&!item.qa_ok)||(action==='ready'&&(!item.qa_ok||item.state!=='approved'||!item.thumbnail_url));button.onclick=()=>decide(action);actions.append(button);}const exportLink=node('a','Open export');exportLink.id='exportLink';exportLink.href=item.export_url||'#';exportLink.hidden=!item.export_url;exportLink.target='_blank';exportLink.rel='noopener';detail.append(exportLink);const scriptSections=item.script&&Array.isArray(item.script.script_sections)?item.script.script_sections:null;const scriptSummary=scriptSections?{narration:scriptSections.map(s=>s.narration).filter(Boolean),hook:item.short.hook,beats:item.short.beats,cta:item.short.cta}:{narration:item.short.narration,hook:item.short.hook,beats:item.short.beats,cta:item.short.cta};detail.append(actions,node('h3','Script and beats'),node('pre',JSON.stringify(scriptSummary,null,2)));
}
async function refresh(explicit=false){try{const response=await fetch('/api/batch-plans/review'+(day.value?'?day='+encodeURIComponent(day.value):''));if(!response.ok)throw Error('Could not refresh review queue.');items=await response.json();const nextSignature=JSON.stringify(items.map(x=>[x.id,x.state,x.decision,x.production_state,x.reviewed_identity,x.qa_ok,x.export_url]));if(nextSignature!==signature){signature=nextSignature;list.replaceChildren();for(const item of items){const li=node('li'),button=node('button',`${item.short.title} · ${item.state} · ${item.production_state}`);button.type='button';button.onclick=()=>show(item);li.append(button);if(item.export_url){const link=node('a','Open export');link.href=item.export_url;link.target='_blank';link.rel='noopener';li.append(link);}list.append(li);}if(!items.length)list.append(node('li','No shorts for this day. Import a plan or choose another day.'));}if(selected){const current=items.find(x=>x.id===selected.id);if(explicit&&current)show(current);else if(!current||current.reviewed_identity!==selected.reviewed_identity){detail.querySelectorAll('#actions button').forEach(b=>b.disabled=true);const link=[...detail.children].find(x=>x.id==='exportLink');if(link)link.hidden=true;notice.textContent='The selected artifact changed. Select it again before reviewing.';}else{selected=current;const exportLink=[...detail.children].find(x=>x.id==='exportLink');if(exportLink){exportLink.hidden=!current.export_url;exportLink.href=current.export_url||'#';}const label=[...detail.children].find(x=>x.id==='reviewStatus');if(label)label.textContent=`Review: ${current.state}${current.decision?' · '+current.decision:''} · Production: ${current.production_state}`;detail.querySelectorAll('#actions button').forEach(b=>{const a=b.dataset.action;b.disabled=busy||!current.available||(a==='approve'&&!current.qa_ok)||(a==='ready'&&(!current.qa_ok||current.state!=='approved'||!current.thumbnail_url));});}}if(explicit||!selected)notice.textContent=items.length?`${items.length} shorts · select a video to review.`:'No videos to review.';}catch(e){notice.textContent=e.message+' Showing the last loaded data.';}}
async function decide(action){if(busy||!selected)return;busy=true;detail.querySelectorAll('#actions button').forEach(b=>b.disabled=true);notice.textContent=action==='regenerate'?'Creating a new generation…':'Saving review decision…';try{const csrf=decodeURIComponent((document.cookie.match(/(?:^|; )tubeforge_csrf=([^;]+)/)||[])[1]||'');const response=await fetch('/api/batch-plans/'+encodeURIComponent(selected.id)+'/review',{method:'POST',headers:{'content-type':'application/json','x-csrf-token':csrf},body:JSON.stringify({action,reviewed_identity:selected.reviewed_identity})});const data=await response.json();if(!response.ok)throw Error(data.detail||'Review action failed');busy=false;await refresh(true);notice.textContent=action==='regenerate'?'New job created. Fresh script and preview approvals are required in Generations.':`Saved: ${data.state}${data.decision?' · '+data.decision:''}`;}catch(e){notice.textContent=e.message;busy=false;if(selected)show(selected);}finally{busy=false;}}
day.onchange=()=>{selected=null;detail.replaceChildren(node('p','Select a short to review.'));refresh(true)};document.querySelector('#refresh').onclick=()=>refresh(true);refresh(true);setInterval(()=>{if(!busy)refresh(false)},10000);
''' + STUDIO_STATIC_MENU_SCRIPT + '''
</script></html>'''
    )


REVIEW_HTML = render_review_html(None)
