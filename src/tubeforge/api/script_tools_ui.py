"""Own-script tools shared by Studio and Batch plans: copy the plan format / an AI-agent guide, and a live length-fit meter.

The script is raw JavaScript (never an f-string); every control calls a real API (`/api/script-guide`, `/api/script-fit`).
"""

SCRIPT_TOOLS_CSS = """
.st-bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:10px 0}.st-bar select{width:auto;margin:0;padding:7px}
.st-bar button{width:auto;margin:0;padding:7px 10px;font-size:12px}.st-meter{margin:8px 0;padding:9px 11px;border-radius:9px;border:1px solid #31415f;background:#0a1222;font-size:13px}
.st-meter.ok{border-color:#2f6b52}.st-meter.warn{border-color:#8a6d2b}.st-meter.bad{border-color:#864454}.st-meter ul{margin:6px 0 0 18px;padding:0;color:#cbd7eb}
"""

SCRIPT_TOOLS_SCRIPT = r"""<script>
(() => {
  async function copy(text){
    try{ if(navigator.clipboard&&navigator.clipboard.writeText){await navigator.clipboard.writeText(text);return true;}}catch(_){}
    try{const t=document.createElement('textarea');t.value=text;t.style.cssText='position:fixed;opacity:0';document.body.append(t);t.focus();t.select();const ok=document.execCommand('copy');t.remove();return ok;}catch(_){return false;}
  }
  function toolbar(getLength){
    const bar=document.createElement('div');bar.className='st-bar';
    const sel=document.createElement('select');sel.setAttribute('aria-label','Video length for the guide');
    [30,45,60,75,90].forEach(n=>sel.append(Object.assign(document.createElement('option'),{value:n,textContent:n+' s'})));sel.value='60';
    const status=document.createElement('span');status.className='sub';status.setAttribute('role','status');status.setAttribute('aria-live','polite');
    const make=(label,kind,done)=>{const b=document.createElement('button');b.type='button';b.className='small secondary';b.textContent=label;
      b.onclick=async()=>{b.disabled=true;status.textContent='Preparing…';try{const length=(getLength&&getLength())||sel.value;const r=await fetch('/api/script-guide?kind='+kind+'&length_s='+encodeURIComponent(length));if(!r.ok)throw Error(await r.text());const d=await r.json();status.textContent=(await copy(d.markdown))?done+' ('+d.length_s+' s)':'Could not copy; use a browser that allows clipboard access.';}catch(e){status.textContent='Could not load: '+e.message;}finally{b.disabled=false;setTimeout(()=>{status.textContent='';},6000);}};return b;};
    const lengthLabel=document.createElement('span');lengthLabel.className='sub';lengthLabel.textContent='Length:';
    bar.append(lengthLabel,sel,make('Copy markdown format','format','Copied the markdown format'),make('Copy AI script guide','guide','Copied the guide for other AI agents'),status);
    return bar;
  }
  function meter(){
    const box=document.createElement('div');box.className='st-meter';box.setAttribute('role','status');box.setAttribute('aria-live','polite');box.hidden=true;return box;
  }
  let timer=null,seq=0;
  function fit(box,payload){
    clearTimeout(timer);
    timer=setTimeout(async()=>{
      const mine=++seq;
      try{
        const csrf=decodeURIComponent((document.cookie.match(/(?:^|; )tubeforge_csrf=([^;]+)/)||[])[1]||'');const r=await fetch('/api/script-fit',{method:'POST',headers:{'content-type':'application/json','x-csrf-token':csrf},body:JSON.stringify(payload())});
        if(!r.ok)throw Error(await r.text());const d=await r.json();if(mine!==seq)return;
        if(!d.words){box.hidden=true;return;}
        box.hidden=false;box.className='st-meter '+(d.status==='ok'?'ok':(d.status==='short'?'warn':'bad'));box.replaceChildren();
        const head=document.createElement('div');head.textContent=d.words+' words ≈ '+d.estimated_seconds+' s of speech · aim '+d.aim_low+'–'+d.aim_high+' words, maximum '+d.max_words+' for '+d.length_s+' s · '+d.section_count+' scenes (target '+d.scenes_low+'–'+d.scenes_high+'). '+d.suggestion;
        box.append(head);
        const notes=d.sections.filter(s=>s.note);
        if(notes.length){const ul=document.createElement('ul');notes.slice(0,12).forEach(s=>{const li=document.createElement('li');li.textContent='Scene '+s.index+' ('+s.words+' words): '+s.note;ul.append(li);});if(notes.length>12){const li=document.createElement('li');li.textContent='…and '+(notes.length-12)+' more.';ul.append(li);}box.append(ul);}
      }catch(e){box.hidden=false;box.className='st-meter bad';box.textContent='Could not check the length: '+e.message;}
    },350);
  }
  window.tubeforgeScriptTools={toolbar,meter,fit};

  // Studio: structured form gets an optional own-script field; markdown mode gets the copy tools.
  const form=document.querySelector('#createForm');
  if(form){
    const label=document.createElement('label');label.textContent='Your own script (optional)';
    const area=document.createElement('textarea');area.id='operatorScript';area.maxLength=12000;
    area.placeholder='Paste your narration. Blank lines separate scenes. Leave empty to let the AI write it. The writer keeps your wording and only splits, trims or fills it to fit; you review it before anything renders.';
    label.append(area);
    const box=meter();
    const lengthOf=()=>Number(form.querySelector('[name=duration_seconds]')?.value)||60;
    const bar=toolbar(lengthOf);
    const submit=form.querySelector('button[type="submit"]');
    (submit?submit.before.bind(submit):form.append.bind(form))(label,box,bar);
    const refit=()=>{if(!area.value.trim()){box.hidden=true;return;}fit(box,()=>({text:area.value,length_s:Math.min(90,Math.max(30,lengthOf()))}));};
    area.addEventListener('input',refit);form.querySelector('[name=duration_seconds]')?.addEventListener('input',refit);
    const previous=window.fetch;
    window.fetch=(url,init={})=>{if(String(url)==='/api/videos'&&init.body&&area.value.trim()){try{const body=JSON.parse(init.body);body.operator_script=area.value.trim();init={...init,body:JSON.stringify(body)};}catch(_){}}return previous(url,init);};
    form.addEventListener('reset',()=>{setTimeout(()=>{box.hidden=true;},0);});
  }
  const mdPanel=document.querySelector('#markdownModePanel');
  if(mdPanel){mdPanel.querySelector('p.sub')?.after(toolbar(null));}

  // Batch plans page.
  const batchText=document.querySelector('#batchText');
  if(batchText&&!form){batchText.closest('form').before(toolbar(null));}

  // Script review dialog: live fit of the edited narration.
  const sections=document.querySelector('#scriptSections');
  if(sections){
    const box=meter();sections.before(box);
    const run=()=>{const areas=[...sections.querySelectorAll('.script-narration')];if(!areas.length){box.hidden=true;return;}fit(box,()=>({sections:areas.map(a=>a.value),length_s:Math.min(90,Math.max(30,Number(window.__scriptTargetSeconds)||60))}));};
    sections.addEventListener('input',run);document.addEventListener('tubeforge:script-loaded',run);
  }
})();
</script>"""
