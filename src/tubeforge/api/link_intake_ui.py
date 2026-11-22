"""One front door on the Studio page: paste a public link, choose what to make.

It only calls the existing, tested intake APIs (source clips and reference intake) and never posts anything:
every later step (capture, script, review, approval, upload) keeps its own gate.
"""

LINK_INTAKE_SCRIPT = r"""<script>
(() => {
  const page=document.querySelector('#studio-studio'); if(!page)return;
  const panel=document.createElement('section');panel.className='panel';panel.id='linkIntake';panel.setAttribute('aria-label','Start from a link');
  panel.innerHTML='<h2>Start from a link</h2><p class="sub">Paste a public YouTube link, then choose what to make. Nothing is posted: every later step still waits for your approval.</p>'
    +'<label for="linkUrl">Public YouTube link</label><input id="linkUrl" type="url" inputmode="url" maxlength="2000" placeholder="https://www.youtube.com/watch?v=…" autocomplete="off">'
    +'<label for="linkNotes">What should it focus on? (optional)</label><textarea id="linkNotes" maxlength="500" rows="2" style="min-height:64px;height:64px" placeholder="For example: the claim that it is 8x faster, and what it costs you."></textarea>'
    +'<div class="actions" style="margin-top:12px;display:flex;flex-wrap:wrap;gap:8px">'
    +'<button type="button" id="linkClip" class="small secondary">Clip it</button>'
    +'<button type="button" id="linkShort" class="small secondary">Reference Short</button>'
    +'<button type="button" id="linkLong" class="small secondary">Long video</button></div>'
    +'<p class="sub" style="margin-top:10px"><b>Clip it</b> cuts highlights from the video (use only sources you may reuse). <b>Reference Short</b> captures its transcript and lets you write an original 60-second Short. <b>Long video</b> does the same for a 10-minute script.</p>'
    +'<div id="linkStatus" role="status" aria-live="polite"></div>';
  page.prepend(panel);
  const $=id=>panel.querySelector('#'+id), buttons=['linkClip','linkShort','linkLong'].map($);
  const csrf=()=>decodeURIComponent((document.cookie.match(/(?:^|; )tubeforge_csrf=([^;]+)/)||[])[1]||'');
  const say=(text,error=false)=>{const el=$('linkStatus');el.textContent=text;el.style.color=error?'#ffb8c2':'';};
  async function post(path,body){const response=await fetch(path,{method:'POST',headers:{'content-type':'application/json','x-csrf-token':csrf()},body:JSON.stringify(body)});if(response.status===401){location.assign('/login');throw Error('Sign in again.');}let data={};try{data=await response.json();}catch(_){}if(!response.ok){const detail=data.detail;throw Error(typeof detail==='string'?detail:(Array.isArray(detail)?'Check the link and notes.':'Request failed ('+response.status+').'));}return data;}
  function link(){const value=$('linkUrl').value.trim();if(!value){say('Paste a public YouTube link first.',true);$('linkUrl').focus();return null;}return value;}
  async function run(kind){
    const url=link();if(!url)return;const notes=$('linkNotes').value.trim();buttons.forEach(b=>b.disabled=true);say(kind==='clip'?'Queuing the clip job…':'Saving the reference…');
    try{
      if(kind==='clip'){const body={source_url:url};if(notes)body.guidance=notes;const job=await post('/api/source-clips',body);say('Clip job queued. Follow it in Generations; you review the clips before anything is published.');const a=document.createElement('a');a.href='/#generations';a.textContent=' Open Generations';$('linkStatus').append(a);}
      else{const body={reference_url:url,target_duration_seconds:kind==='long'?600:60,language:'en',channel_identity:'default'};if(notes)body.focus=notes;const intake=await post('/api/reference-intakes',body);say('Reference saved. Opening it…');location.assign('/references?intake='+encodeURIComponent(intake.intake.intake_id));return;}
    }catch(error){say('Could not start: '+error.message,true);}
    buttons.forEach(b=>b.disabled=false);
  }
  $('linkClip').onclick=()=>run('clip');$('linkShort').onclick=()=>run('short');$('linkLong').onclick=()=>run('long');
})();
</script>"""
