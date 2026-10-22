"""Saved generation details and truthful copy controls for Studio."""

GENERATION_CSS = r"""
#generationRecord .record-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}
#generationRecord textarea{width:100%;min-height:180px;resize:vertical;font:12px/1.5 ui-monospace,monospace}
#generationRecord .record-wide{grid-column:1/-1}
#generationRecord .record-copy{width:auto;margin-top:8px}
#generationRecord .record-state{min-height:20px;margin:8px 0;color:var(--cyan);font-size:12px}
@media(max-width:680px){#generationRecord .record-grid{grid-template-columns:1fr}#generationRecord .record-wide{grid-column:auto}}
"""

GENERATION_CONTROLS = r"""<dialog id="generationRecord" aria-labelledby="generationRecordTitle"><div class="modal-head"><h2 id="generationRecordTitle">Generation record</h2><button class="close" type="button" id="generationRecordClose" aria-label="Close generation record">×</button></div><div class="modal-body"><p class="sub">These are the inputs saved with this job. Codex commands appear only when an exact invocation was recorded.</p><div id="generationRecordState" class="record-state" role="status"></div><div class="record-grid"><section><h3>Inputs, links and descriptions</h3><textarea id="generationInputs" readonly aria-label="Saved generation inputs"></textarea><button id="copyGenerationInputs" class="secondary record-copy" type="button" disabled>Copy inputs</button></section><section><h3>Narration used</h3><textarea id="generationScript" readonly aria-label="Saved narration"></textarea><button id="copyGenerationScript" class="secondary record-copy" type="button" disabled>Copy script</button></section><section class="record-wide"><h3>Codex command executed</h3><textarea id="generationCommand" readonly aria-label="Recorded Codex commands"></textarea><button id="copyGenerationCommand" class="secondary record-copy" type="button" disabled>Copy recorded command</button></section></div></div></dialog><script>
(() => {
  const dialog=document.querySelector('#generationRecord'),status=dialog.querySelector('#generationRecordState');
  const fields={inputs:dialog.querySelector('#generationInputs'),script:dialog.querySelector('#generationScript'),command:dialog.querySelector('#generationCommand')};
  const buttons={inputs:dialog.querySelector('#copyGenerationInputs'),script:dialog.querySelector('#copyGenerationScript'),command:dialog.querySelector('#copyGenerationCommand')};
  for(const key of Object.keys(fields))buttons[key].onclick=async()=>{if(!fields[key].value)return;buttons[key].disabled=true;try{await navigator.clipboard.writeText(fields[key].value);status.textContent=(key==='command'?'Recorded command':key==='script'?'Script':'Inputs')+' copied.';}catch(error){status.textContent='Could not copy: '+error.message;}finally{buttons[key].disabled=false;}};
  dialog.querySelector('#generationRecordClose').onclick=()=>dialog.close();
  async function open(jobId){for(const key of Object.keys(fields)){fields[key].value='';buttons[key].disabled=true;}status.textContent='Loading saved record…';dialog.showModal();try{const response=await fetch('/api/jobs/'+encodeURIComponent(jobId)+'/studio-record');if(!response.ok)throw Error(await response.text());const record=await response.json();dialog.querySelector('#generationRecordTitle').textContent='Generation record · '+record.request.topic;fields.inputs.value=JSON.stringify({request:record.request,destinations:record.destinations,video_description:record.video_description},null,2);buttons.inputs.disabled=false;fields.command.value=record.codex_commands.length?record.codex_commands.join('\n'):'No exact Codex command was recorded for this job.';buttons.command.disabled=!record.codex_commands.length;const scriptResponse=await fetch('/api/jobs/'+encodeURIComponent(jobId)+'/script');if(scriptResponse.ok){const data=await scriptResponse.json();fields.script.value=(data.package.script_sections||[]).map(section=>section.narration).join('\n\n');buttons.script.disabled=!fields.script.value;}else{fields.script.value='Narration is not available yet for this job.';}status.textContent='Saved inputs loaded'+(record.codex_commands.length?' · exact Codex command recorded':' · exact Codex command unavailable')+'.';}catch(error){status.textContent='Could not load generation record: '+error.message;}}
  window.openStudioRecord=open;
  function openFocused(){if(location.hash!=='#generations')return;const id=sessionStorage.getItem('tubeforge:focus-job');if(id){sessionStorage.removeItem('tubeforge:focus-job');open(id);}}
  window.addEventListener('hashchange',openFocused);setTimeout(openFocused,0);
})();
</script>"""
