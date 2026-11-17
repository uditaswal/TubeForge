"""Saved generation details and truthful copy controls for Studio."""

GENERATION_CSS = r"""
#generationRecord .record-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}
#generationRecord textarea{width:100%;min-height:180px;resize:vertical;font:12px/1.5 ui-monospace,monospace}
#generationRecord .record-wide{grid-column:1/-1}
#generationRecord .record-copy{width:auto;margin-top:8px}
#generationRecord .record-state{min-height:20px;margin:8px 0;color:var(--cyan);font-size:12px}
#generationRecord .record-audio{white-space:pre-wrap;line-height:1.5}
#retryJob textarea{width:100%;min-height:340px;resize:vertical;font:12px/1.5 ui-monospace,monospace}
#retryJob .retry-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
#retryJob .retry-state{min-height:20px;margin:8px 0;font-size:12px;color:var(--cyan);white-space:pre-wrap}
#retryJob .retry-state.error{color:#fda4af}
@media(max-width:680px){#generationRecord .record-grid{grid-template-columns:1fr}#generationRecord .record-wide{grid-column:auto}}
"""

GENERATION_CONTROLS = r"""<dialog id="retryJob" aria-labelledby="retryJobTitle"><div class="modal-head"><h2 id="retryJobTitle">Retry generation</h2><button class="close" type="button" id="retryJobClose" aria-label="Close retry">×</button></div><div class="modal-body"><p class="sub">Starts a new job with the same destinations. The failed job and its script-attempt allowance stay as they are. Edit the request JSON below, or leave it unchanged; an identical request reuses the same allowance and may fail the same way.</p><div id="retryJobState" class="retry-state" role="status"></div><textarea id="retryJobJson" spellcheck="false" aria-label="Request JSON" disabled></textarea><div class="retry-actions"><button id="retryJobReset" class="secondary" type="button" disabled>Reset to saved</button><button id="retryJobSubmit" type="button" disabled>Start new job</button></div></div></dialog><script>
(() => {
  const dialog=document.querySelector('#retryJob'),area=dialog.querySelector('#retryJobJson'),state=dialog.querySelector('#retryJobState'),submit=dialog.querySelector('#retryJobSubmit'),reset=dialog.querySelector('#retryJobReset');
  let jobId=null,saved='';
  const say=(text,error)=>{state.textContent=text;state.classList.toggle('error',!!error);};
  dialog.querySelector('#retryJobClose').onclick=()=>dialog.close();
  reset.onclick=()=>{area.value=saved;say('Restored the saved request.');};
  async function open(id){jobId=id;area.value='';area.disabled=submit.disabled=reset.disabled=true;say('Loading saved request…');dialog.showModal();try{const response=await fetch('/api/jobs/'+encodeURIComponent(id)+'/studio-record');if(!response.ok)throw new Error(await response.text());saved=JSON.stringify((await response.json()).request,null,2);area.value=saved;area.disabled=submit.disabled=reset.disabled=false;say('');}catch(error){say('Could not load the saved request: '+error.message,true);}}
  submit.onclick=async()=>{let parsed;try{parsed=JSON.parse(area.value);}catch(error){say('Invalid JSON: '+error.message,true);return;}
    if(parsed===null||typeof parsed!=='object'||Array.isArray(parsed)){say('The request must be a JSON object.',true);return;}
    const edited=area.value!==saved;submit.disabled=true;say('Creating the new job…');
    try{const response=await fetch('/api/jobs/'+encodeURIComponent(jobId)+'/retry',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(edited?{request:parsed}:{})});
      if(!response.ok){let detail=await response.text();try{const body=JSON.parse(detail);detail=typeof body.detail==='string'?body.detail:JSON.stringify(body.detail);}catch(_){}say('Not started: '+detail,true);return;}
      const created=await response.json();say('Started new job '+created.id.slice(0,8)+'.');dialog.close();
    }catch(error){say('Could not reach the dashboard: '+error.message,true);}finally{submit.disabled=false;}};
  window.openRetryJob=open;
})();
</script><dialog id="generationRecord" aria-labelledby="generationRecordTitle"><div class="modal-head"><h2 id="generationRecordTitle">Generation record</h2><button class="close" type="button" id="generationRecordClose" aria-label="Close generation record">×</button></div><div class="modal-body"><p class="sub">These are the inputs saved with this job, the script-writer command that ran and its token usage.</p><div id="generationRecordState" class="record-state" role="status"></div><div class="record-grid"><section><h3>Inputs, links and descriptions</h3><textarea id="generationInputs" readonly aria-label="Saved generation inputs"></textarea><button id="copyGenerationInputs" class="secondary record-copy" type="button" disabled>Copy inputs</button></section><section><h3>Narration used</h3><textarea id="generationScript" readonly aria-label="Saved narration"></textarea><button id="copyGenerationScript" class="secondary record-copy" type="button" disabled>Copy script</button></section><section class="record-wide"><h3 id="generationCommandTitle">Script command executed</h3><p id="generationUsage" class="sub"></p><textarea id="generationCommand" readonly aria-label="Recorded script-writer commands"></textarea><button id="copyGenerationCommand" class="secondary record-copy" type="button" disabled>Copy command</button></section><section class="record-wide"><h3>Audio diagnostics</h3><p id="generationAudio" class="sub record-audio" role="status">Open a rendered generation to see signal warnings.</p><a id="generationAudioReport" hidden>Open full audio report</a></section><section class="record-wide"><h3>Video diagnostics</h3><p id="generationVideo" class="sub record-audio" role="status">Video report pending until a reference Short is rendered.</p><a id="generationVideoReport" hidden>Open full video report</a></section></div></div></dialog><script>
(() => {
  const dialog=document.querySelector('#generationRecord'),status=dialog.querySelector('#generationRecordState');
  const fields={inputs:dialog.querySelector('#generationInputs'),script:dialog.querySelector('#generationScript'),command:dialog.querySelector('#generationCommand')};
  const buttons={inputs:dialog.querySelector('#copyGenerationInputs'),script:dialog.querySelector('#copyGenerationScript'),command:dialog.querySelector('#copyGenerationCommand')};
  for(const key of Object.keys(fields))buttons[key].onclick=async()=>{if(!fields[key].value)return;buttons[key].disabled=true;try{await navigator.clipboard.writeText(fields[key].value);status.textContent=(key==='command'?'Recorded command':key==='script'?'Script':'Inputs')+' copied.';}catch(error){status.textContent='Could not copy: '+error.message;}finally{buttons[key].disabled=false;}};
  dialog.querySelector('#generationRecordClose').onclick=()=>dialog.close();
  async function loadAudio(jobId){const summary=dialog.querySelector('#generationAudio'),link=dialog.querySelector('#generationAudioReport');summary.textContent='Audio report pending until a reference Short is rendered.';link.hidden=true;for(const name of ['final_qa','preview_qa']){try{const url='/api/jobs/'+encodeURIComponent(jobId)+'/artifacts/'+name;const response=await fetch(url);if(response.status===404)continue;if(!response.ok)throw Error('HTTP '+response.status);const report=await response.json();if(!report.audio_health||!report.narration_health){summary.textContent='This render has no audio health report.';return;}const sources=[['Narration',report.narration_health],['Encoded video',report.audio_health]];summary.textContent=sources.map(([label,health])=>{const warnings=health.warnings||[];return label+': '+warnings.length+' signal warning(s)'+(health.truncated?' (report capped)':'')+(warnings.length?'\n'+warnings.slice(0,8).map(w=>'  '+w.kind+' at '+w.start.toFixed(1)+'–'+w.end.toFixed(1)+'s'+(w.scene_index==null?'':' · scene '+(w.scene_index+1))).join('\n'):'');}).join('\n');link.href=url;link.hidden=false;return;}catch(error){summary.textContent='Could not load audio report: '+error.message;return;}}summary.textContent='No audio report is available for this generation yet.';}
  async function loadVideo(jobId){const summary=dialog.querySelector('#generationVideo'),link=dialog.querySelector('#generationVideoReport');summary.textContent='Video report pending until a reference Short is rendered.';link.hidden=true;for(const name of ['final_qa','preview_qa']){try{const url='/api/jobs/'+encodeURIComponent(jobId)+'/artifacts/'+name;const response=await fetch(url);if(response.status===404)continue;if(!response.ok)throw Error('HTTP '+response.status);const report=await response.json();if(!report.temporal_qa){summary.textContent='This render has no temporal video report.';return;}const qa=report.temporal_qa;const format=rows=>rows.length?rows.slice(0,8).map(row=>row.start.toFixed(1)+'–'+row.end.toFixed(1)+'s · scene '+(row.scene_index+1)).join(', '):'none';summary.textContent='Black frames: '+format(qa.black_intervals||[])+'\nFrozen frames: '+format(qa.freeze_intervals||[])+'\nFrame signal only; static cards may be intentional.';link.href=url;link.hidden=false;return;}catch(error){summary.textContent='Could not load video report: '+error.message;return;}}summary.textContent='No video report is available for this generation yet.';}
  async function open(jobId){for(const key of Object.keys(fields)){fields[key].value='';buttons[key].disabled=true;}status.textContent='Loading saved record…';dialog.querySelector('#generationAudio').textContent='Loading audio report…';dialog.querySelector('#generationAudioReport').hidden=true;dialog.querySelector('#generationVideo').textContent='Loading video report…';dialog.querySelector('#generationVideoReport').hidden=true;dialog.showModal();try{const response=await fetch('/api/jobs/'+encodeURIComponent(jobId)+'/studio-record');if(!response.ok)throw Error(await response.text());const record=await response.json();dialog.querySelector('#generationRecordTitle').textContent='Generation record · '+record.request.topic;fields.inputs.value=JSON.stringify({request:record.request,destinations:record.destinations,video_description:record.video_description},null,2);buttons.inputs.disabled=false;fields.command.value=record.codex_commands.length?record.codex_commands.join('\n'):'No command was recorded for this job.';buttons.command.disabled=!record.codex_commands.length;const scriptResponse=await fetch('/api/jobs/'+encodeURIComponent(jobId)+'/script');if(scriptResponse.ok){const data=await scriptResponse.json();fields.script.value=(data.package.script_sections||[]).map(section=>section.narration).join('\n\n');buttons.script.disabled=!fields.script.value;}else{fields.script.value='Narration is not available yet for this job.';}const g=record.generation,n=v=>Number(v||0).toLocaleString();dialog.querySelector('#generationCommandTitle').textContent=g?(g.owner==='claude'?'Claude command executed':'Codex command executed'):'Script command executed';dialog.querySelector('#generationUsage').textContent=g&&g.input_tokens!=null?[(g.owner==='claude'?'Claude ':'Codex ')+(g.model||''),g.effort?'effort '+g.effort:null,g.attempts+' call(s)','input '+n(g.input_tokens)+' tokens','output '+n(g.output_tokens)+' tokens','cache read '+n(g.cache_read_input_tokens)+' · cache write '+n(g.cache_creation_input_tokens),g.total_cost_usd!=null?'list price $'+Number(g.total_cost_usd).toFixed(2):null,g.elapsed_seconds!=null?Math.round(g.elapsed_seconds)+' s':null].filter(Boolean).join(' · '):'';status.textContent='Saved inputs loaded'+(record.codex_commands.length?' · script command recorded':' · script command unavailable')+'.';await Promise.all([loadAudio(jobId),loadVideo(jobId)]);}catch(error){status.textContent='Could not load generation record: '+error.message;dialog.querySelector('#generationAudio').textContent='Audio report unavailable.';dialog.querySelector('#generationVideo').textContent='Video report unavailable.';}}
  window.openStudioRecord=open;
  function openFocused(){if(location.hash!=='#generations')return;const id=sessionStorage.getItem('tubeforge:focus-job');if(id){sessionStorage.removeItem('tubeforge:focus-job');open(id);}}
  window.addEventListener('hashchange',openFocused);setTimeout(openFocused,0);
})();
</script>"""


JOB_EXTRAS_CSS = r"""
.job-thumb{display:block;width:100%;max-width:240px;aspect-ratio:16/9;object-fit:cover;border-radius:8px;margin:8px 0;border:1px solid var(--line,#31415f);background:#000}
.job-thumb[src*="thumbnail"]{max-height:420px}
.focus-banner{display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin:0 0 14px;padding:10px 14px;border:1px solid #6c5a1e;border-radius:10px;background:#2a2410;color:#ffe9a6;font-size:13px}
.focus-banner button{margin:0}
"""

JOB_EXTRAS_SCRIPT = r"""<script>
(() => {
  // One job alone: the worker takes only the chosen job until it rests or the focus is released.
  window.focusedJobId=null;
  const csrf=()=>decodeURIComponent((document.cookie.match(/(?:^|; )tubeforge_csrf=([^;]+)/)||[])[1]||'');
  const send=(method,path)=>fetch(path,{method,headers:{'x-csrf-token':csrf(),'content-type':'application/json'}});
  function banner(state,title){let box=document.querySelector('#focusBanner');const jobs=document.querySelector('#jobs');if(!jobs)return;
    if(!state.active){if(box)box.remove();return}
    if(!box){box=document.createElement('div');box.id='focusBanner';box.className='focus-banner';box.setAttribute('role','status');jobs.before(box)}
    box.replaceChildren();const text=document.createElement('span');text.textContent='Running only '+(title||('job '+String(state.job_id).slice(0,8)))+'. Every other job waits until it finishes or you release this.';
    const release=document.createElement('button');release.type='button';release.className='small secondary';release.textContent='Run everything again';release.onclick=window.releaseFocus;box.append(text,release)}
  async function sync(){try{const r=await fetch('/api/job-focus');if(!r.ok)return;const state=await r.json();const changed=window.focusedJobId!==(state.job_id||null);window.focusedJobId=state.job_id||null;
      let title=null;if(state.active){const card=[...document.querySelectorAll('#jobs .job')].find(c=>c.textContent.includes(String(state.job_id).slice(0,8)));title=card&&card.querySelector('.title')?card.querySelector('.title').textContent:null}
      banner(state,title);if(changed&&typeof refresh==='function')refresh()}catch(_){}}
  window.focusJob=async id=>{const r=await send('POST','/api/jobs/'+encodeURIComponent(id)+'/focus');if(!r.ok){let d='';try{d=(await r.json()).detail}catch(_){}window.alert(d||'Could not focus this job.');return}await sync()};
  window.releaseFocus=async()=>{await send('DELETE','/api/job-focus');await sync()};
  sync();setInterval(sync,5000);
  // Studio: guidance for the thumbnail, sent with every new brief.
  (function(){const form=document.querySelector('#createForm');if(!form||document.querySelector('#thumbnailGuidance'))return;
    const label=document.createElement('label');label.setAttribute('for','thumbnailGuidance');label.textContent='Thumbnail guidance (optional)';
    const area=document.createElement('textarea');area.id='thumbnailGuidance';area.maxLength=1000;area.rows=2;area.placeholder='What should the thumbnail say and show? For example: the number 8x in big yellow type, the host looking shocked.';
    const hint=document.createElement('p');hint.className='sub';hint.textContent='The writer shapes the thumbnail text options and the hook around this. A markdown plan can set it per short with thumbnail: {text, visual}.';
    const submit=form.querySelector('button[type=submit],button:not([type])');(submit||form.lastElementChild).before(label,area,hint);
    const original=window.fetch;window.fetch=(url,init={})=>{if(String(url)==='/api/videos'&&init.body){try{const body=JSON.parse(init.body);const value=area.value.trim();if(value)body.thumbnail_guidance=value;init={...init,body:JSON.stringify(body)}}catch(_){}}return original(url,init)}})();
  // "Publish…" on a generation opens the Publishing page with that video chosen.
  function preselect(){let id=null;try{id=sessionStorage.getItem('tubeforge:publish-job')}catch(_){}if(!id||location.hash!=='#publishing')return;
    let tries=0;const timer=setInterval(()=>{const select=document.querySelector('#publishVideo');tries++;
      if(select&&[...select.options].some(o=>o.value===id)){select.value=id;select.dispatchEvent(new Event('change'));select.scrollIntoView({block:'center'});try{sessionStorage.removeItem('tubeforge:publish-job')}catch(_){}clearInterval(timer)}
      else if(tries>40){clearInterval(timer)}},250)}
  window.addEventListener('hashchange',preselect);setTimeout(preselect,0);
})();
</script>"""
