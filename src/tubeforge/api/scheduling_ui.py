"""Account-first Scheduling controls backed by the existing local APIs."""

SCHEDULING_CSS = r"""
.studio-page>.channel-scheduling{max-width:none}
.channel-scheduling{padding:24px}
.channel-scheduling h2{font-size:17px}
.channel-intro{display:flex;justify-content:space-between;align-items:start;gap:16px;margin-bottom:18px}
.channel-intro p{margin-top:5px}
.channel-intro a,.channel-link{color:var(--cyan);font-weight:650;text-decoration:none}
.channel-intro a:hover,.channel-link:hover{text-decoration:underline}
.channel-account-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,205px),1fr));gap:10px;margin-bottom:23px}
.channel-account-card{width:100%;min-height:104px;margin:0;padding:15px;text-align:left;background:var(--studio-input);color:#edf3fb;border:1px solid var(--line);border-radius:12px;display:flex;flex-direction:column;align-items:flex-start;gap:4px}
.channel-account-card:hover:not(:disabled){background:var(--studio-panel-alt);border-color:#688071;transform:none}
.channel-account-card[aria-pressed=true]{background:#20382f;border-color:#80cfa6;box-shadow:inset 0 0 0 1px #80cfa6}
.channel-account-card strong{font-size:14px;line-height:1.25;overflow-wrap:anywhere}
.channel-account-card span{color:var(--muted);font-size:11px;overflow-wrap:anywhere}
.channel-account-card[aria-pressed=true] span{color:#c7e7d4}
.channel-account-card .channel-platform{color:var(--cyan);font-size:10px;font-weight:750;letter-spacing:.08em;text-transform:uppercase}
.channel-head{padding:20px;border:1px solid var(--line);border-radius:12px;background:var(--studio-panel-alt);margin-bottom:18px}
.channel-head h2{font-size:21px}
.channel-head p{margin-top:4px;overflow-wrap:anywhere}
.channel-columns{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(300px,.85fr);gap:18px;align-items:start}
.channel-card{min-width:0;padding:20px;border:1px solid var(--line);border-radius:12px;background:var(--studio-input)}
.channel-card h3{font-size:15px;margin:0 0 5px}
.channel-card .sub{font-size:12px}
.channel-card textarea{min-height:110px}
.channel-card button{margin-top:12px}
.channel-list{display:grid;gap:8px;margin-top:16px}
.channel-list-row{min-width:0;padding:12px 13px;border:1px solid var(--line);border-radius:9px;background:var(--panel)}
.channel-list-row strong{display:block;font-size:13px;overflow-wrap:anywhere}
.channel-list-row span{display:block;margin-top:3px;color:var(--muted);font-size:11px;overflow-wrap:anywhere}
.channel-list-row a{display:inline-block;margin-top:7px;color:var(--cyan);font-size:12px;font-weight:650}
.channel-queue-summary{margin:0 0 12px;color:var(--cyan);font-size:12px;font-weight:650}
.channel-empty{padding:17px;border:1px dashed #43566c;border-radius:9px;color:var(--muted);font-size:12px}
.channel-form-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 12px}
.channel-form-grid .channel-wide{grid-column:1/-1}
.channel-status{min-height:20px;margin-top:9px;color:var(--good);font-size:12px}
@media(max-width:1030px){.channel-columns{grid-template-columns:1fr}}
@media(max-width:760px){.channel-scheduling{padding:17px}.channel-intro{flex-direction:column}.channel-account-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.channel-card{padding:16px}}
@media(max-width:440px){.channel-account-grid,.channel-form-grid{grid-template-columns:1fr}.channel-account-card{min-height:84px}}
"""

SCHEDULING_SCRIPT = r"""<script>
(() => {
  const csrf=(document.cookie.match(/(?:^|; )tubeforge_csrf=([^;]+)/)||[])[1];
  if(csrf){const original=window.fetch;window.fetch=(url,init={})=>{const method=(init.method||'GET').toUpperCase();if(!['GET','HEAD','OPTIONS'].includes(method))init.headers={...(init.headers||{}),'x-csrf-token':decodeURIComponent(csrf)};return original(url,init);};}
  const shell=document.querySelector('.shell');if(!shell)return;
  const panel=document.createElement('section');panel.className='panel channel-scheduling';
  panel.innerHTML=`<div class="channel-intro"><div><h2>Choose a channel</h2><p class="sub">Each account has its own topic queue and generation schedule.</p></div><a href="#accounts">Manage accounts</a></div>
    <div id="channelAccountGrid" class="channel-account-grid" aria-label="Publishing accounts"></div>
    <div id="channelAccountStatus" class="channel-empty" role="status">Loading accounts…</div>
    <div id="channelWorkspace" hidden>
      <div class="channel-head"><h2 id="channelName"></h2><p id="channelMeta" class="sub"></p><p id="channelDefault" class="sub"></p></div>
      <div class="channel-columns">
        <section class="channel-card" aria-labelledby="queueHeading"><h3 id="queueHeading">Topic queue</h3><p class="sub">One topic per line. These topics belong only to this account.</p>
          <label>Topics to queue<textarea id="bulkTopics" placeholder="First topic&#10;Second topic"></textarea></label>
          <button id="bulkTopicsButton" type="button">Add topics to this account</button><div id="topicStatus" class="channel-status" role="status"></div>
          <p id="channelQueueSummary" class="channel-queue-summary" role="status"></p><div id="channelTopicList" class="channel-list" aria-live="polite"></div></section>
        <section class="channel-card" aria-labelledby="scheduleHeading"><h3 id="scheduleHeading">Schedules</h3><p class="sub">Runs take the next ready topic from this account only.</p>
          <div id="channelScheduleList" class="channel-list" aria-live="polite"></div>
          <form id="channelScheduleForm"><div class="channel-form-grid">
            <label class="channel-wide">Schedule name<input name="name" maxlength="200" required></label>
            <label>Cron<input name="cron" value="0 9 * * *" maxlength="120" required></label>
            <label>Timezone<input name="timezone" value="Asia/Kolkata" maxlength="100" required></label>
            <label>Format<select name="preset" id="schedulePreset" required></select></label>
            <label>Duration (seconds)<input name="duration_seconds" id="scheduleDuration" type="number" min="30" max="7200" value="60" required></label>
            <label class="channel-wide">Channel voice profile<select name="channel_identity" id="scheduleVoice" required></select></label>
            <label class="channel-wide">Video description (optional)<textarea name="video_description" maxlength="5000" placeholder="Leave blank to use this account’s default"></textarea></label>
          </div><button id="scheduleButton" type="submit" disabled>Create schedule for this account</button><div id="scheduleStatus" class="channel-status" role="status"></div></form>
        </section>
      </div>
    </div>`;
  shell.append(panel);
  const grid=panel.querySelector('#channelAccountGrid'),accountStatus=panel.querySelector('#channelAccountStatus'),workspace=panel.querySelector('#channelWorkspace');
  const topicList=panel.querySelector('#channelTopicList'),scheduleList=panel.querySelector('#channelScheduleList'),topicInput=panel.querySelector('#bulkTopics');
  const scheduleForm=panel.querySelector('#channelScheduleForm'),scheduleButton=panel.querySelector('#scheduleButton'),preset=panel.querySelector('#schedulePreset'),duration=panel.querySelector('#scheduleDuration'),voice=panel.querySelector('#scheduleVoice');
  const legacyId='__unassigned__';let accounts=[],selected=null,formReady=false;
  async function json(path,init){const response=await fetch(path,init);if(!response.ok)throw Error(await response.text());return response.json();}
  function empty(target,message){const box=document.createElement('div');box.className='channel-empty';box.textContent=message;target.replaceChildren(box);}
  function row(target,title,details){const item=document.createElement('div');item.className='channel-list-row';const strong=document.createElement('strong');strong.textContent=title;const meta=document.createElement('span');meta.textContent=details;item.append(strong,meta);target.append(item);}
  function renderAccounts(){grid.replaceChildren();for(const account of accounts){const button=document.createElement('button');button.type='button';button.className='channel-account-card';button.setAttribute('aria-pressed',String(account.id===selected));const platform=document.createElement('span');platform.className='channel-platform';platform.textContent=account.platform;const name=document.createElement('strong');name.textContent=account.display_name;const detail=document.createElement('span');detail.textContent=account.legacy?'Existing shared queue':account.category+' · '+(account.disabled?'disabled':account.status.replaceAll('_',' '));button.append(platform,name,detail);button.onclick=()=>choose(account.id);grid.append(button);}}
  async function loadSelected(silent=false){const account=accounts.find(item=>item.id===selected);if(!account)return;workspace.hidden=false;panel.querySelector('#channelName').textContent=account.display_name;panel.querySelector('#channelMeta').textContent=account.legacy?'Shared queue · read only':account.platform+' · '+account.category+' · '+(account.disabled?'disabled':account.status.replaceAll('_',' '));panel.querySelector('#channelDefault').textContent=account.legacy?'These older unassigned items cannot enter an account schedule. Add new topics under a channel above.':account.disabled?'This account is disabled. Existing topics and schedules remain visible; new work is blocked.':account.default_description?'Default description: '+account.default_description:'No default description set for this account.';panel.querySelector('#bulkTopicsButton').disabled=account.disabled;scheduleButton.disabled=account.disabled||!formReady;if(!silent){empty(topicList,'Loading topics…');empty(scheduleList,'Loading schedules…');}try{const id=encodeURIComponent(account.id),suffix=account.legacy?'unassigned=true':'account_id='+id,[topics,schedules,jobs]=await Promise.all([json('/api/topics?'+suffix),json('/api/schedules?'+suffix),json('/api/jobs')]);if(selected!==account.id)return;const byId=new Map(jobs.map(job=>[job.id,job]));topicList.replaceChildren();scheduleList.replaceChildren();const queued=topics.filter(topic=>topic.status==='ready').length,active=topics.filter(topic=>topic.status==='generating').length;panel.querySelector('#channelQueueSummary').textContent=queued+' queued · '+active+' generating · '+schedules.length+' schedule'+(schedules.length===1?'':'s');if(!topics.length)empty(topicList,'No topics queued for this account yet. Add the first topic above.');else for(const topic of topics){const job=byId.get(topic.generation_job_id),state=job?(job.state.replaceAll('_',' ')+(job.latest_event?' · '+(job.latest_event.stage||job.latest_event.event_type).replaceAll('_',' '):'')):(topic.status==='ready'?'Queued':topic.status.replaceAll('_',' '));row(topicList,topic.title,state+(topic.generation_job_id?' · Job '+topic.generation_job_id.slice(0,8):''));if(topic.generation_job_id){const link=document.createElement('a');link.href='#generations';link.textContent='Open generation';link.onclick=()=>sessionStorage.setItem('tubeforge:focus-job',topic.generation_job_id);topicList.lastElementChild.append(link);}}if(!schedules.length)empty(scheduleList,'No schedules for this account yet. Add one below.');else for(const schedule of schedules)row(scheduleList,schedule.name,schedule.cron+' · '+schedule.timezone+' · Next '+(schedule.next_run_at?new Date(schedule.next_run_at).toLocaleString():'not scheduled')+' · Last '+(schedule.last_run_at?new Date(schedule.last_run_at).toLocaleString():'never'));}catch(_){if(selected===account.id&&!silent){empty(topicList,'Could not load this account’s topics or job progress. Reload to retry.');empty(scheduleList,'Could not load this account’s schedules. Reload to retry.');}else if(selected===account.id)panel.querySelector('#channelQueueSummary').textContent='Could not refresh queue progress; showing last known data.';}}
  function choose(id){if(selected!==id){topicInput.value='';scheduleForm.elements.video_description.value='';const account=accounts.find(item=>item.id===id);scheduleForm.elements.name.value=account?account.display_name+' daily':'';}selected=id;renderAccounts();loadSelected();}
  async function loadAccounts(){try{const [profiles,legacyTopics,legacySchedules]=await Promise.all([json('/api/social-accounts'),json('/api/topics?unassigned=true'),json('/api/schedules?unassigned=true')]);accounts=profiles;if(legacyTopics.length||legacySchedules.length)accounts.push({id:legacyId,platform:'Legacy',display_name:'Unassigned items',category:'Shared',status:'unassigned',default_description:'',disabled:true,legacy:true});if(!accounts.length){grid.replaceChildren();workspace.hidden=true;accountStatus.hidden=false;accountStatus.textContent='No account profiles yet. Add one in Accounts to create a channel queue.';return;}accountStatus.hidden=true;choose(accounts.some(item=>item.id===selected)?selected:accounts[0].id);}catch(_){accountStatus.hidden=false;accountStatus.textContent='Could not load accounts or queues. Reload to retry.';}}
  async function loadScheduleOptions(){try{const [presets,profiles]=await Promise.all([json('/api/presets'),json('/api/content-profiles')]);preset.replaceChildren();for(const item of presets){const option=document.createElement('option');option.value=item.name;option.textContent=item.label;option.dataset.aspect=item.aspect_ratio;option.dataset.duration=item.duration_seconds;option.dataset.min=item.minimum_duration_seconds;option.dataset.max=item.maximum_duration_seconds;preset.append(option);}preset.value=presets.some(item=>item.name==='default')?'default':presets[0]?.name||'';preset.onchange=()=>{const item=preset.selectedOptions[0];if(item){duration.min=item.dataset.min;duration.max=item.dataset.max;duration.value=item.dataset.duration;}};preset.onchange();voice.replaceChildren();for(const item of profiles.profiles){const option=document.createElement('option');option.value=item.identity;option.textContent=item.identity+(item.uses_default?' (default voice)':'');voice.append(option);}voice.value=profiles.default_identity;formReady=Boolean(preset.value&&voice.value);scheduleButton.disabled=!formReady||Boolean(accounts.find(item=>item.id===selected)?.disabled);}catch(_){panel.querySelector('#scheduleStatus').textContent='Could not load format or voice options. Reload before scheduling.';scheduleButton.disabled=true;}}
  panel.querySelector('#bulkTopicsButton').onclick=async()=>{if(!selected)return;const titles=topicInput.value.split('\n').map(value=>value.trim()).filter(Boolean),status=panel.querySelector('#topicStatus'),button=panel.querySelector('#bulkTopicsButton');if(!titles.length){status.textContent='Enter at least one topic.';return;}button.disabled=true;status.textContent='Adding topics…';try{const created=await json('/api/topics/bulk',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({titles,account_id:selected})});status.textContent='Queued '+created.length+' topic'+(created.length===1?'':'s')+' for this account.';topicInput.value='';await loadSelected();}catch(error){status.textContent='Could not queue topics: '+error.message;}finally{button.disabled=Boolean(accounts.find(item=>item.id===selected)?.disabled);}};
  scheduleForm.onsubmit=async event=>{event.preventDefault();if(!selected||!formReady||!scheduleForm.reportValidity())return;const status=panel.querySelector('#scheduleStatus'),selectedPreset=preset.selectedOptions[0];const body={account_id:selected,name:scheduleForm.elements.name.value.trim(),cron:scheduleForm.elements.cron.value.trim(),timezone:scheduleForm.elements.timezone.value.trim(),options:{channel_identity:voice.value,preset_name:preset.value,aspect_ratio:selectedPreset.dataset.aspect||'16:9',duration_seconds:Number(duration.value),video_description:scheduleForm.elements.video_description.value.trim()||null}};scheduleButton.disabled=true;status.textContent='Saving schedule…';try{await json('/api/schedules',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)});status.textContent='Schedule saved for this account. No upload was queued.';await loadSelected();}catch(error){status.textContent='Could not save schedule: '+error.message;}finally{scheduleButton.disabled=!formReady||Boolean(accounts.find(item=>item.id===selected)?.disabled);}};
  window.addEventListener('tubeforge:accounts-changed',loadAccounts);loadScheduleOptions();loadAccounts();setInterval(()=>{if(selected)loadSelected(true);},10000);
})();
</script>"""
