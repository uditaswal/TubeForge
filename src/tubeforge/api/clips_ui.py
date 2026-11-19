"""Clips page and API: turn a long video into vertical clips, review them, send the good ones to publishing.

Authentication and CSRF come from the application middleware, like every other /api route. A clip job is a
normal TubeForge job (``production_mode=source_clip``): its own video is the best-ranked clip and it follows
the usual Day review and Publishing flow. Every other clip can be approved here, which creates a small job
bound to that exact file's checksum.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, Request, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

from tubeforge.api.studio_shell import STUDIO_CSS, STUDIO_STATIC_MENU_SCRIPT, wrap_studio_page
from tubeforge.core import runtime_settings as runtime_values
from tubeforge.db.repositories import PAUSABLE_STATES
from tubeforge.domain.states import JobState

# Where each state sits on the progress bar. Clip work is dominated by analysis and rendering.
STAGE_PERCENT = {
    JobState.TOPIC_CREATED: 2, JobState.SOURCE_INSPECTING: 8, JobState.SOURCE_ACQUIRING: 15, JobState.SOURCE_ANALYZING: 40,
    JobState.CLIP_RENDERING: 75, JobState.FINAL_RENDERING: 92, JobState.FINAL_READY: 100,
}
STAGE_LABEL = {
    JobState.TOPIC_CREATED: "Queued", JobState.SOURCE_INSPECTING: "Checking the video", JobState.SOURCE_ACQUIRING: "Preparing",
    JobState.SOURCE_ANALYZING: "Downloading and choosing moments", JobState.CLIP_RENDERING: "Rendering clips",
    JobState.FINAL_RENDERING: "Finishing", JobState.FINAL_READY: "Clips ready",
}


class ClipJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_url: str = Field(min_length=8, max_length=2_000)
    clip_count: int = Field(default=3, ge=1, le=12)
    max_duration_seconds: int = Field(default=60, ge=10, le=900)
    captions_enabled: bool = True
    start_seconds: int | None = Field(default=None, ge=0, le=172_800)
    length_minutes: int | None = Field(default=None, ge=1, le=2_880)
    guidance: str | None = Field(default=None, max_length=1_000)


class ClipApproval(BaseModel):
    model_config = ConfigDict(extra="forbid")
    checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def _meminfo_mb() -> int | None:
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) // 1024
    except (OSError, ValueError):
        return None
    return None


def _disk_bytes(folder: Path) -> int:
    """Bytes a job has written so far (download, cache and clips); a cheap activity signal for long downloads."""
    total = 0
    try:
        for root, _dirs, files in os.walk(folder):
            for name in files:
                try:
                    total += os.stat(os.path.join(root, name)).st_size
                except OSError:
                    continue
    except OSError:
        return 0
    return total


def _file_checksum(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


_MAIN_HTML = '''<main>
<div class="studio-page-head"><div><h1>Clips</h1><p class="sub">Paste a long video. TubeForge reads the transcript, picks the best standalone moments and renders each as a vertical clip.</p></div></div>
<section class="panel" aria-labelledby="engineTitle"><h2 id="engineTitle">Engine</h2>
<ul class="engine" id="engineStrip" aria-live="polite"><li>Checking…</li></ul></section>
<section class="panel" aria-labelledby="createTitle"><h2 id="createTitle">New clips</h2>
<form id="clipForm" class="clip-form">
<label>Video link<input id="clipUrl" type="url" required maxlength="2000" placeholder="https://www.youtube.com/watch?v=…" autocomplete="off"></label>
<div class="row"><label>Clips<input id="clipCount" type="number" min="1" max="12" value="3" required></label>
<label>Longest clip (seconds)<input id="clipLength" type="number" min="10" max="900" value="60" required></label>
<label class="checkbox"><input id="clipCaptions" type="checkbox" checked> Captions</label></div>
<div class="row"><label>Start at (optional)<input id="clipStart" type="text" inputmode="numeric" placeholder="1:05:00" pattern="[0-9]+(:[0-5]?[0-9]){0,2}" autocomplete="off"></label>
<label>Use at most (minutes, optional)<input id="clipMinutes" type="number" min="1" max="2880" placeholder="all"></label></div>
<label>What should the AI look for? (optional)<textarea id="clipGuidance" rows="2" maxlength="1000" placeholder="e.g. find scenes where the guest explains the argument, skip sponsor reads"></textarea></label>
<p class="sub" id="clipLimitNote">A video longer than the limit is trimmed to its first stretch instead of refused. Pick a start time to use a different part.</p>
<p class="sub">One run uses about six AI calls from a separate daily limit (a very long video uses more). It needs the Claude runner.</p>
<div class="row"><button id="clipSubmit" type="submit">Make clips</button><span id="clipState" class="state" role="status" aria-live="polite"></span></div>
</form></section>
<section class="panel" aria-labelledby="jobsTitle"><h2 id="jobsTitle">Clip jobs</h2>
<p id="jobsEmpty" class="sub">Loading…</p><div id="clipJobs"></div></section>
</main>'''

_PAGE_HEAD = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Clips — TubeForge</title><style>''' + STUDIO_CSS + '''
main{max-width:1000px;margin:32px auto;padding:0 20px;display:flex;flex-direction:column;gap:22px}
.panel h2{margin:0 0 12px}
.engine{list-style:none;padding:0;margin:0;display:flex;flex-wrap:wrap;gap:8px 18px;font-size:13px}.engine .ok{color:#9fd9b6}.engine .bad{color:#ffb3bf}
.clip-form{display:grid;gap:12px}.clip-form .row{display:flex;flex-wrap:wrap;align-items:flex-end;gap:12px}.clip-form input[type=number]{width:140px}.clip-form input[type=text]{width:140px}.clip-form input[type=url]{width:100%}.clip-form textarea{width:100%;min-height:64px;resize:vertical}
.state{font-size:12px;min-height:1.2em}.state.bad{color:#ffb3bf}.state.good{color:#9fd9b6}
.job{border-top:1px solid var(--line);padding:16px 0;display:grid;gap:10px}.job:first-child{border-top:0;padding-top:0}
.job-head{display:flex;flex-wrap:wrap;gap:8px 12px;align-items:center;justify-content:space-between}.job-head strong{overflow-wrap:anywhere}
.bar{height:8px;border-radius:99px;background:rgba(255,255,255,.1);overflow:hidden}.bar span{display:block;height:100%;background:#38bdf8}
.meta{color:var(--muted);font-size:12px}.actions{display:flex;flex-wrap:wrap;gap:8px}
.clips{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:14px}
.clip{display:grid;gap:8px;align-content:start}.clip video{width:100%;aspect-ratio:9/16;background:#000;border-radius:8px}
.clip h3{font-size:14px;margin:0;overflow-wrap:anywhere}.mono{font-family:ui-monospace,monospace}.timings{font-size:12px}.timings summary{cursor:pointer;color:var(--muted)}.timings table{width:100%;border-collapse:collapse;margin-top:6px}.timings td{padding:3px 6px;border-top:1px solid var(--line)}.timings td.t{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}.timings .bar2{height:5px;border-radius:9px;background:#38bdf8;min-width:2px}.live{display:grid;gap:4px;font-size:13px}.live strong{font-weight:600}.warn{color:#ffd58a}.why{font-size:12px}.why summary{cursor:pointer;color:var(--muted)}.why h4{margin:8px 0 2px;font-size:12px}.why ul{margin:0;padding-left:16px}.why li{margin:2px 0}.why .no{color:#ffd58a}.why .ok{color:#8fe3a3}.clip .meta{display:flex;flex-wrap:wrap;gap:4px 10px}
@media(max-width:640px){main{margin:16px auto;padding:0 14px}.clip-form input[type=number]{width:100%}.clips{grid-template-columns:repeat(auto-fill,minmax(150px,1fr))}}</style>
'''

_SCRIPT = r'''
<script>
const csrf=()=>decodeURIComponent((document.cookie.match(/(?:^|; )tubeforge_csrf=([^;]+)/)||[])[1]||'');
function el(tag,text,cls){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e}
async function call(method,path,body){const r=await fetch(path,{method,headers:{'content-type':'application/json','x-csrf-token':csrf()},body:body===undefined?undefined:JSON.stringify(body)});const text=await r.text();let data={};try{data=text?JSON.parse(text):{}}catch(_){data={detail:text}}if(!r.ok){const d=data.detail;throw new Error(typeof d==='string'?d:(d&&d.message)||'Request failed ('+r.status+')')}return data}
const mmss=s=>{s=Math.round(s||0);return Math.floor(s/60)+':'+String(s%60).padStart(2,'0')};
let engine={can_create:false,reason:'Checking…'};
function renderEngine(e){engine=e;const strip=document.querySelector('#engineStrip');strip.replaceChildren();
  const add=(text,ok)=>strip.append(el('li',text,ok?'ok':'bad'));
  add(e.enabled?'Clipping enabled':'Clipping is turned off in config',e.enabled);
  add(e.runner_reachable?'Claude runner answers':'Claude runner is not reachable',e.runner_reachable);
  strip.append(el('li',e.youtube_cookies?'YouTube cookies found':'No YouTube cookies (only needed if YouTube asks to confirm you are not a bot)',e.youtube_cookies?'ok':''));
  if(e.max_source_minutes){document.querySelector('#clipLimitNote').textContent='A video longer than '+e.max_source_minutes+' minutes is trimmed to its first '+e.max_source_minutes+' minutes instead of refused. Pick a start time to use a different part, or raise the limit in Settings.'}
  if(e.free_ram_mb!==null)strip.append(el('li','Free memory '+e.free_ram_mb+' MB'));
  strip.append(el('li',e.running+' running · '+e.queued+' queued'));
  const submit=document.querySelector('#clipSubmit');submit.disabled=!e.can_create;submit.title=e.can_create?'':e.reason}
async function loadEngine(){try{renderEngine(await call('GET','/api/clips/engine/status'))}catch(error){renderEngine({enabled:false,runner_reachable:false,free_ram_mb:null,running:0,queued:0,can_create:false,reason:error.message})}}
function button(label,cls,handler){const b=el('button',label,cls||'secondary');b.type='button';b.onclick=async()=>{b.disabled=true;try{await handler()}catch(error){window.alert(error.message)}b.disabled=false;await loadJobs()};return b}
function clipCard(job,clip){const card=el('article',undefined,'clip');
  const video=document.createElement('video');video.controls=true;video.preload='none';video.muted=false;video.src=clip.video_url;video.setAttribute('aria-label','Clip '+clip.index);card.append(video);
  card.append(el('h3','Clip '+clip.index+' · '+(clip.hook_title||'Untitled'),'clip-title'));card.append(el('div',clip.name+' · '+job.short_id,'meta mono'));
  const meta=el('div',undefined,'meta');meta.append(el('span',mmss(clip.duration)+' long'));if(clip.virality_score!=null)meta.append(el('span','Score '+clip.virality_score));if(clip.start_time)meta.append(el('span','From '+clip.start_time));card.append(meta);
  const actions=el('div',undefined,'actions');
  const link=el('a','Download');link.href=clip.video_url;link.download='clip-'+clip.index+'.mp4';link.className='button secondary';actions.append(link);
  if(clip.own_video){actions.append(el('span','This job’s own video — review it in Generations','meta'))}
  else if(clip.approved_job_id){actions.append(el('span','Sent to publishing','badge ready'))}
  else if(clip.can_approve){actions.append(button('Approve for publishing','',async()=>{if(!window.confirm('Approve this exact clip for publishing? It becomes its own job and goes through review.'))return;await call('POST','/api/clip-jobs/'+job.id+'/clips/'+clip.name+'/approve',{checksum_sha256:clip.checksum_sha256})}))}
  card.append(actions);return card}
const gb=b=>b>=1e9?(b/1e9).toFixed(2)+' GB':Math.round(b/1e6)+' MB';
const lastSeen={};
function liveBlock(job){const box=el('div',undefined,'live');
  const p=job.progress,parts=[el('strong',job.percent+'% · '+job.stage)];
  if(p&&p.message)parts.push(el('span','Now: '+p.message+(p.seconds_since_update!=null?' (reported '+p.seconds_since_update+' s ago)':'')));
  if(p&&p.disk_bytes){parts.push(el('span','On disk: '+gb(p.disk_bytes)));
    const key=job.id,prev=lastSeen[key],now=Date.now();
    if(!prev||prev.bytes!==p.disk_bytes||prev.message!==p.message)lastSeen[key]={bytes:p.disk_bytes,message:p.message,at:now};
    else if(now-prev.at>300000&&job.claimed)parts.push(el('span','No change for '+Math.round((now-prev.at)/60000)+' minutes. It may be busy on one long step (a very large download, a copy or a transcription); check the worker log if this keeps growing.','warn'))}
  if(job.claimed===false&&job.percent<100&&!job.failure_message)parts.push(el('span','Waiting for a worker to pick this up.'));
  box.append(...parts);return box}
const clock=s=>{s=Math.round(s);return Math.floor(s/60)+':'+String(s%60).padStart(2,'0')};
const openTimings=new Set();
function timingsBlock(t,id){const box=document.createElement('details');box.className='timings';box.open=openTimings.has(id);box.ontoggle=()=>{if(box.open)openTimings.add(id);else openTimings.delete(id)};const sum=document.createElement('summary');sum.textContent='Where the time went · '+clock(t.total_seconds)+' total';box.append(sum);
  const table=document.createElement('table');const longest=Math.max(...t.rows.map(r=>r.seconds),1);
  for(const row of t.rows){const tr=document.createElement('tr');const name=document.createElement('td');name.textContent=row.label+(row.running?' (running)':'');
    const bar=document.createElement('td');bar.style.width='38%';const fill=document.createElement('div');fill.className='bar2';fill.style.width=Math.max(2,Math.round(100*row.seconds/longest))+'%';bar.append(fill);
    const time=document.createElement('td');time.className='t';time.textContent=clock(row.seconds);tr.append(name,bar,time);table.append(tr)}
  box.append(table);return box}
const openWhy=new Set();
const WHY_AREAS=[['signals','What viewers and captions told us'],['windows','Parts that were listened to'],['candidates','How the moments were picked'],['faces','Faces'],['layout','Framing'],['captions','Captions'],['render','Render']];
const WHY_BAD=new Set(['none-found','analysis-failed','captions-missing','unavailable','skipped','dropped','default-centre','default-crop','whole-video','fallback-window','speaker-cuts-skipped','opening-penalised','left-out']);
function whyLine(d){const f=d.facts||{};const bits=Object.entries(f).filter(([k,v])=>v!==null&&v!==''&&typeof v!=='object').map(([k,v])=>k.replace(/_/g,' ')+' '+v);
  const li=document.createElement('li');li.className=WHY_BAD.has(d.outcome)?'no':'';const head=document.createElement('strong');head.textContent=(d.clip?'Clip '+d.clip+' · ':'')+d.outcome.replace(/-/g,' ');li.append(head);
  if(d.reason)li.append(' — '+d.reason);if(bits.length)li.append(document.createTextNode(' ('+bits.join(', ')+')'));return li}
function whyBlock(list,id){const box=document.createElement('details');box.className='why';box.open=openWhy.has(id);box.ontoggle=()=>{if(box.open)openWhy.add(id);else openWhy.delete(id)};
  const sum=document.createElement('summary');sum.textContent='Why these clips · '+list.length+' decisions';box.append(sum);
  for(const [area,label] of WHY_AREAS){const rows=list.filter(d=>d.area===area);if(!rows.length)continue;const h=document.createElement('h4');h.textContent=label;const ul=document.createElement('ul');for(const d of rows)ul.append(whyLine(d));box.append(h,ul)}
  return box}
function renderJob(job){const box=el('div',undefined,'job');box.dataset.id=job.id;
  const head=el('div',undefined,'job-head');head.append(el('strong',job.title));head.append(el('span',job.stage+(job.failure_message?' — failed':''),'badge '+(job.failure_message?'danger':job.percent>=100?'ready':'pending')));box.append(head);
  const bar=el('div',undefined,'bar');bar.setAttribute('role','progressbar');bar.setAttribute('aria-valuenow',job.percent);bar.setAttribute('aria-valuemin',0);bar.setAttribute('aria-valuemax',100);const fill=el('span');fill.style.width=job.percent+'%';bar.append(fill);box.append(bar);
  box.append(el('div',(job.parent?'Approved clip · ':'')+'Job '+job.short_id+' · '+job.state.replace(/_/g,' ')+' · started '+(job.created_at?new Date(job.created_at).toLocaleString():''),'meta'));
  if(job.progress||job.percent<100){box.append(liveBlock(job))}
  if(job.note)box.append(el('div',job.note,'meta'));
  if(job.failure_message)box.append(el('div',job.failure_message,'state bad'));
  const actions=el('div',undefined,'actions');
  if(job.can_pause)actions.append(button('Pause','',()=>call('POST','/api/jobs/'+job.id+'/pause')));
  if(job.can_resume)actions.append(button('Resume','',()=>call('POST','/api/jobs/'+job.id+'/resume')));
  if(job.can_retry_as_new)actions.append(button('Retry','',()=>call('POST','/api/jobs/'+job.id+'/retry',{})));
  if(job.cancellable)actions.append(button('Cancel','',async()=>{if(window.confirm('Cancel this job? Finished clips are kept.'))await call('POST','/api/jobs/'+job.id+'/pause')}));
  if(job.deletable)actions.append(button('Delete','danger',async()=>{if(window.confirm('Delete this job and its files?'))await call('DELETE','/api/jobs/'+job.id)}));
  box.append(actions);
  if(job.timings&&job.timings.rows.length)box.append(timingsBlock(job.timings,job.id));
  if(job.decisions&&job.decisions.length)box.append(whyBlock(job.decisions,job.id));
  if(job.clips.length){const grid=el('div',undefined,'clips');for(const clip of job.clips)grid.append(clipCard(job,clip));box.append(grid)}
  return box}
async function loadJobs(){try{const data=await call('GET','/api/clip-jobs');const holder=document.querySelector('#clipJobs');holder.replaceChildren(...data.jobs.map(renderJob));document.querySelector('#jobsEmpty').textContent=data.jobs.length?'':'No clip jobs yet.'}catch(error){document.querySelector('#jobsEmpty').textContent='Could not load clip jobs: '+error.message}}
const parseTime=text=>{text=text.trim();if(!text)return null;const parts=text.split(':').map(Number);if(parts.some(n=>!Number.isFinite(n)||n<0)||parts.length>3)throw new Error('Start time must look like 1:05:00, 12:30 or 90.');return parts.reduce((total,n)=>total*60+n,0)};
document.querySelector('#clipForm').onsubmit=async event=>{event.preventDefault();const state=document.querySelector('#clipState'),submit=document.querySelector('#clipSubmit');
  submit.disabled=true;state.className='state';state.textContent='Creating…';
  try{await call('POST','/api/clip-jobs',{source_url:document.querySelector('#clipUrl').value.trim(),clip_count:Number(document.querySelector('#clipCount').value),max_duration_seconds:Number(document.querySelector('#clipLength').value),captions_enabled:document.querySelector('#clipCaptions').checked,start_seconds:parseTime(document.querySelector('#clipStart').value),length_minutes:document.querySelector('#clipMinutes').value?Number(document.querySelector('#clipMinutes').value):null,guidance:document.querySelector('#clipGuidance').value.trim()||null});state.className='state good';state.textContent='Queued. The worker picks it up next.';document.querySelector('#clipUrl').value='';document.querySelector('#clipStart').value='';document.querySelector('#clipMinutes').value='';document.querySelector('#clipGuidance').value='';await loadJobs()}
  catch(error){state.className='state bad';state.textContent=error.message}
  await loadEngine()};
loadEngine();loadJobs();setInterval(()=>{loadEngine();loadJobs()},5000);
''' + STUDIO_STATIC_MENU_SCRIPT + '''
</script>'''


def render_clips_html(username: str | None = None) -> str:
    return _PAGE_HEAD + wrap_studio_page("clips", username, "Workspace / Clips", _MAIN_HTML) + _SCRIPT + "</html>"


def register_clips_routes(app, runtime, create_clip_job):
    """Mount the Clips page. ``create_clip_job(ClipJobRequest)`` is the application's existing job creator."""
    def clip_jobs():
        return [job for job in runtime.jobs.list_recent(limit=100) if job.request.production_mode == "source_clip"]

    def manifest(job_id: str):
        artifact = runtime.artifacts.get(job_id, JobState.CLIP_RENDERING, "clip_manifest")
        if artifact is None or not Path(artifact.path).is_file():
            return None
        try:
            return json.loads(Path(artifact.path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def source_title(job) -> str:
        artifact = runtime.artifacts.get(job.id, JobState.SOURCE_INSPECTING, "source_metadata")
        try:
            data = json.loads(Path(artifact.path).read_text(encoding="utf-8")) if artifact else {}
        except (OSError, ValueError):
            data = {}
        return str(data.get("title") or job.request.topic)

    def hms(seconds) -> str:
        seconds = int(seconds or 0)
        return f"{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"

    def part_note(job_id: str) -> str | None:
        artifact = runtime.artifacts.get(job_id, JobState.SOURCE_ACQUIRING, "clip_plan")
        try:
            plan = json.loads(Path(artifact.path).read_text(encoding="utf-8")) if artifact else {}
        except (OSError, ValueError):
            return None
        window = plan.get("source_window")
        if not window:
            return None
        text = f"Using {hms(window[0])} to {hms(window[1])}"
        if plan.get("source_duration_seconds"):
            text += f" of {hms(plan['source_duration_seconds'])}"
        return text + (" (the video is longer than the limit, so the first stretch is used)" if plan.get("source_trimmed") else "")

    def live_progress(job):
        """What the engine reports right now, plus how much the job has written to disk."""
        work = Path(app.state.settings.pipeline.voice.artifact_root) / job.id / "clip-work"
        try:
            info = json.loads((work / "progress.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            info = {}
        if not info and not work.exists():
            return None
        return {"stage": info.get("stage"), "percent": info.get("percent"), "message": info.get("message"),
                "seconds_since_update": round(time.time() - info["updated_at"]) if info.get("updated_at") else None,
                "disk_bytes": _disk_bytes(work)}

    def timings(job):
        """Where this job's time went, stage by stage (a running stage counts up to now)."""
        from tubeforge.clips.stage_clock import StageClock, TIMINGS_FILE, summarize
        path = Path(app.state.settings.pipeline.voice.artifact_root) / job.id / "clip-work" / TIMINGS_FILE
        stages = StageClock(path).stages
        return summarize(stages) if stages else None

    def decision_log(job):
        """Why the clips were picked and how each was framed and captioned (a short, plain-language audit)."""
        from tubeforge.clips import decisions
        return decisions.read(Path(app.state.settings.pipeline.voice.artifact_root) / job.id / "clip-work")[-400:]

    def payload(job, all_jobs):
        children = {item.request.clip_of: item.id for item in all_jobs if item.request.clip_of}
        clips = []
        entries = (manifest(job.id) or {}).get("clips", []) if not job.request.clip_of else []
        for number, entry in enumerate(entries, 1):
            candidate = entry.get("candidate") or {}
            key = f"{job.id}:{entry['name']}:{entry['checksum_sha256']}"
            clips.append({
                "index": number, "name": entry["name"], "checksum_sha256": entry["checksum_sha256"],
                "video_url": f"/api/jobs/{job.id}/artifacts/{entry['name']}", "duration": candidate.get("duration"),
                "hook_title": candidate.get("hook_title"), "virality_score": candidate.get("virality_score"), "start_time": candidate.get("start_time"),
                "own_video": number == 1, "approved_job_id": children.get(key),
                "can_approve": number > 1 and children.get(key) is None and job.state is not JobState.CANCELLED,
            })
        percent = STAGE_PERCENT.get(job.state, 100 if job.state.value.startswith("publication") or job.state is JobState.PUBLISHED else 0)
        running = job.state in {JobState.SOURCE_ANALYZING, JobState.CLIP_RENDERING}
        progress = live_progress(job) if running else None
        if progress and progress.get("percent") is not None:
            percent = max(percent if job.state is JobState.CLIP_RENDERING else 12, min(int(progress["percent"]), 99))
        return {
            "id": job.id, "title": source_title(job), "state": job.state.value, "stage": STAGE_LABEL.get(job.state, job.state.value.replace("_", " ").capitalize()),
            "percent": percent, "failure_message": job.failure_message, "created_at": job.created_at.isoformat() if job.created_at else None,
            "short_id": job.id[:8], "progress": progress, "timings": timings(job), "decisions": decision_log(job), "claimed": job.claim_owner is not None, "note": part_note(job.id), "parent": bool(job.request.clip_of), "clips": clips, "clip_of": job.request.clip_of,
            "can_pause": job.state in PAUSABLE_STATES and job.cancellation_requested_at is None,
            "can_resume": job.state is JobState.CANCELLED and job.resume_state is not None and job.claim_owner is None,
            "cancellable": job.state in STAGE_PERCENT and job.state is not JobState.FINAL_READY and job.cancellation_requested_at is None,
            "can_retry_as_new": job.claim_owner is None and job.state in {JobState.FAILED_VALIDATION, JobState.FAILED_EXHAUSTED},
            "deletable": job.claim_owner is None and job.state in {JobState.FINAL_READY, JobState.FAILED_VALIDATION, JobState.FAILED_EXHAUSTED, JobState.FAILED_RETRYABLE, JobState.PUBLICATION_APPROVAL_REQUIRED, JobState.CANCELLED},
        }

    @app.get("/api/clips/engine/status", tags=["clips"])
    def engine_status():
        settings = app.state.settings
        enabled = bool(settings.pipeline.source_clips.enabled)
        claude = settings.pipeline.claude
        reachable = bool(claude.enabled and Path(claude.socket_path).exists())
        jobs = clip_jobs()
        running = sum(1 for job in jobs if job.claim_owner is not None)
        queued = sum(1 for job in jobs if job.claim_owner is None and job.state in {JobState.TOPIC_CREATED, JobState.SOURCE_INSPECTING, JobState.SOURCE_ACQUIRING, JobState.SOURCE_ANALYZING, JobState.CLIP_RENDERING})
        reason = "" if enabled and reachable else ("Clipping is turned off in config/production.yaml." if not enabled else "The Claude runner does not answer; start it with scripts/run_claude_runner.sh.")
        from tubeforge.pipeline.orchestrator import artifacts_cookies
        cookies = artifacts_cookies(settings.pipeline.voice.artifact_root).is_file()
        return {"enabled": enabled, "runner_reachable": reachable, "youtube_cookies": cookies, "free_ram_mb": _meminfo_mb(), "running": running, "queued": queued,
                "can_create": enabled and reachable, "reason": reason,
                "max_source_minutes": int(runtime_values.shared().value("clips.max_source_minutes", settings.pipeline.source_clips.max_source_duration_seconds // 60))}

    @app.get("/api/clip-jobs", tags=["clips"])
    def list_clip_jobs():
        jobs = clip_jobs()
        return {"jobs": [payload(job, jobs) for job in jobs]}

    @app.get("/api/clip-jobs/{job_id}", tags=["clips"])
    def get_clip_job(job_id: str):
        jobs = clip_jobs()
        job = next((item for item in jobs if item.id == job_id), None)
        if job is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="clip job not found")
        return payload(job, jobs)

    @app.post("/api/clip-jobs", status_code=status.HTTP_201_CREATED, tags=["clips"])
    def create_clip_job_route(body: ClipJobRequest):
        return create_clip_job(body)

    @app.post("/api/clip-jobs/{job_id}/clips/{name}/approve", status_code=status.HTTP_201_CREATED, tags=["clips"])
    def approve_clip(job_id: str, name: str, body: ClipApproval, request: Request):
        jobs = clip_jobs()
        parent = next((item for item in jobs if item.id == job_id), None)
        if parent is None or parent.request.clip_of:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="clip job not found")
        entries = (manifest(job_id) or {}).get("clips", [])
        entry = next((item for item in entries if item["name"] == name), None)
        if entry is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="clip not found")
        if entries and entries[0]["name"] == name:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This clip is the job's own video: review it in Generations.")
        if entry["checksum_sha256"] != body.checksum_sha256:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The clip changed since you reviewed it; reload the page.")
        if _file_checksum(Path(entry["path"])) != body.checksum_sha256:
            raise HTTPException(status_code=status.HTTP_410_GONE, detail="The clip file is missing or no longer matches the approved checksum.")
        key = f"{job_id}:{name}:{body.checksum_sha256}"
        existing = next((item for item in jobs if item.request.clip_of == key), None)
        if existing is not None:
            return {"id": existing.id, "state": existing.state.value, "already_approved": True}
        title = (entry.get("candidate") or {}).get("hook_title") or source_title(parent)
        child_request = parent.request.model_copy(update={"clip_of": key, "clip_count": 1, "topic": str(title)[:500]})
        child_id = uuid4().hex
        job = runtime.jobs.create(child_id, child_request)
        session = runtime.auth.session(request.cookies.get("tubeforge_session"))
        actor = (runtime.auth.username_for(session.user_id) if session else None) or "operator"
        runtime.events.append(job.id, "clip_approved_for_publishing", parent_job_id=job_id, clip=name, checksum_sha256=body.checksum_sha256, actor=actor)
        runtime.events.append(job_id, "clip_approved", clip=name, child_job_id=job.id, checksum_sha256=body.checksum_sha256, actor=actor)
        return {"id": job.id, "state": job.state.value, "already_approved": False}

    @app.get("/clips", response_class=HTMLResponse, include_in_schema=False)
    def clips_page(request: Request):
        session = runtime.auth.session(request.cookies.get("tubeforge_session"))
        return render_clips_html(runtime.auth.username_for(session.user_id) if session else None)
