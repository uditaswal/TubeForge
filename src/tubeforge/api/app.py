"""Application factory and operational endpoints."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from pathlib import Path
from datetime import UTC, datetime
import hashlib
import html
import json
import os
import secrets
import shutil
import threading
import wave
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from tubeforge.core.config import Settings, load_settings, validate_selected_provider
from tubeforge.core.runtime import Runtime, create_runtime
from tubeforge.domain.contracts import ContentPackage, ContentRequest, SourceReference, VoiceRequest, video_plan_from_package
from tubeforge.core.errors import ProviderValidationError, RetryableProviderError
from tubeforge.domain.states import ApprovalGate, ApprovalStatus, JobState
from tubeforge.scheduling.service import next_run
from tubeforge.providers.content.prompts import validate_video_package
from tubeforge.pipeline.manual_publish import ManualPublishService
from tubeforge.pipeline.delivery_queue import DeliveryQueue
from tubeforge.pipeline.publishing_assets import PublishingAssetRegistry, READY_STATES
from tubeforge.db.models import DeliveryAttemptRecord, PublishingAssetRecord, SocialAccountRecord
from tubeforge.publishing_worker.presence import PublisherWorkerPresence
from tubeforge.security.google_oauth import GoogleAccountOAuth
from tubeforge.security.oauth_state import OAuthStateStore


class ApprovalRequest(BaseModel):
    """An explicit, audit-friendly human decision from the private dashboard."""

    model_config = ConfigDict(extra="forbid")

    status: ApprovalStatus
    actor: str = Field(min_length=1, max_length=200)
    reviewed_identity: str | None = Field(default=None, min_length=1, max_length=128)


class ScriptRevisionRequest(BaseModel):
    """Operator-authored narration changes for a script awaiting review."""

    model_config = ConfigDict(extra="forbid")
    narrations: tuple[str, ...] = Field(min_length=1, max_length=500)
    actor: str = Field(default="local-dashboard", min_length=1, max_length=200)

class ScriptRevisionPromptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instruction: str = Field(min_length=1, max_length=4000)


class VideoBriefRequest(BaseModel):
    """User-facing shorthand expanded into the durable provider-neutral request."""
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=500)
    notes: tuple[str, ...] = Field(min_length=1, max_length=30)
    preset: str | None = Field(default=None, max_length=100)
    duration_seconds: int | None = Field(default=None, ge=30, le=7_200)
    captions_enabled: bool | None = None
    music_track: str | None = Field(default=None, max_length=200)
    visual_style: str | None = Field(default=None, max_length=100)
    visual_source: str = Field(default="generated", pattern=r"^(generated|stock)$")
    review_mode: str | None = Field(default=None, pattern=r"^(manual|auto)$")
    mcp_servers: tuple[str, ...] | None = None
    audience: str = Field(default="general", min_length=1, max_length=200)
    voice_id: str | None = Field(default=None, min_length=1, max_length=200)
    source_url: str | None = Field(default=None, max_length=2_000)
    channel_identity: str | None = Field(default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    source_title: str | None = Field(default=None, max_length=500)
    source_excerpt: str | None = Field(default=None, max_length=24_000)


class SourceClipRequest(BaseModel):
    """URL intake for the worker-owned source clip path."""
    model_config = ConfigDict(extra="forbid")
    source_url: str = Field(min_length=8, max_length=2_000)
    title: str | None = Field(default=None, min_length=1, max_length=500)
    clip_count: int = Field(default=1, ge=1, le=12)
    max_duration_seconds: int = Field(default=60, ge=10, le=900)
    captions_enabled: bool = False


class TopicCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=500)
    notes: str = Field(default="", max_length=24_000)
    priority: int = Field(default=0, ge=-1000, le=1000)
    options: dict[str, object] = Field(default_factory=dict)


class TopicBulkCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    titles: tuple[str, ...] = Field(min_length=1, max_length=200)
    priority: int = Field(default=0, ge=-1000, le=1000)


class ScheduleCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    cron: str = Field(min_length=1, max_length=120)
    timezone: str = Field(default="UTC", min_length=1, max_length=100)
    options: dict[str, object] = Field(default_factory=dict)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=1024)


class SocialAccountCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    platform: str = Field(pattern=r"^(youtube|instagram|facebook|snapchat)$")
    display_name: str = Field(min_length=1, max_length=200)
    auth_type: str = Field(default="oauth", pattern=r"^(oauth|manual_handoff)$")


class OAuthStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: str | None = Field(default=None, max_length=64)


class OAuthConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: str = Field(min_length=1, max_length=200)


class ManualPublishDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: str = Field(min_length=1, max_length=64)
    destinations: dict[str, dict[str, object]] = Field(min_length=1, max_length=20)


class ManualPublishSubmitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reviewed_identity: str = Field(pattern=r"^[0-9a-f]{64}$")


class DeliveryActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str = Field(pattern=r"^(inspect|resume|retry_after_reconnect)$")

def _video_request(value: VideoBriefRequest, settings: Settings, *, available_music: set[str] | None = None) -> ContentRequest:
    generation = settings.pipeline.video_generation
    name = value.preset or generation.default_preset
    try:
        preset = generation.presets[name]
    except KeyError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"unknown video preset: {name}") from error
    duration = value.duration_seconds or preset.duration_seconds
    if not preset.minimum_duration_seconds <= duration <= preset.maximum_duration_seconds:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"{name} duration must be between {preset.minimum_duration_seconds} and {preset.maximum_duration_seconds} seconds")
    music = value.music_track if value.music_track is not None else preset.music_track
    catalog = available_music if available_music is not None else {track.name for track in generation.music_catalog}
    if music is not None and music not in catalog:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"unknown approved music track: {music}")
    mcp = value.mcp_servers if value.mcp_servers is not None else preset.mcp_servers
    # The Codex CLI remains the authority for actual configured MCP servers;
    # reject only malformed selections here and preserve the selection durably.
    if len(set(mcp)) != len(mcp) or any(not server.strip() for server in mcp):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="mcp_servers must be unique and nonblank")
    notes = tuple(note.strip() for note in value.notes if note.strip())
    if not notes:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="at least one nonblank note is required")
    if value.visual_source == "stock" and settings.pipeline.media.provider not in {"wikimedia", "hybrid"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="rights-safe stock is not enabled in this TubeForge configuration")
    if value.visual_source == "generated" and settings.pipeline.media.provider == "wikimedia":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="local generated scene art is not enabled in this TubeForge configuration")
    sources = [SourceReference(source_id="operator-notes", url="https://local.invalid/operator-notes", title="Operator-approved source notes", excerpt="\n".join(notes))]
    if value.source_url:
        if not value.source_title or not value.source_title.strip() or not value.source_excerpt or not value.source_excerpt.strip():
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="source URL requires a source title and approved excerpt")
        try:
            sources.append(SourceReference(source_id="approved-source-1", url=value.source_url, title=value.source_title.strip(), excerpt=value.source_excerpt.strip()))
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="source URL must be an absolute HTTP(S) URL") from error
    elif value.source_title or value.source_excerpt:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="source title and excerpt require a source URL")
    from tubeforge.providers.content.youtube_skills import voice_for
    channel, profile = voice_for(settings.pipeline.codex, value.channel_identity)
    return ContentRequest(
        channel_identity=channel, channel_voice_profile=profile,
        topic=value.title, angle="\n".join(notes), target_duration_seconds=duration,
        language="en", audience=value.audience, prompt_version=settings.pipeline.codex.prompt_template_version,
        sources=tuple(sources),
        notes=notes, review_mode=value.review_mode or preset.review_mode,
        captions_enabled=preset.captions_enabled if value.captions_enabled is None else value.captions_enabled,
        music_track=music, visual_style=value.visual_style or preset.visual_style, visual_source=value.visual_source, mcp_servers=tuple(mcp), voice_id=value.voice_id,
        preset_name=name, aspect_ratio=preset.aspect_ratio,
    )


def _source_clip_request(value: SourceClipRequest) -> ContentRequest:
    from tubeforge.clipping.source import validate_source_url

    source_url = validate_source_url(value.source_url)
    title = value.title or "Source video highlights"
    return ContentRequest(
        topic=title, angle="Find self-contained, high-energy moments in the source video.",
        # A source can be shorter than the normal generated-video floor.  The
        # requested maximum controls source acquisition/rendering; the shared
        # ContentRequest duration remains a valid planning hint for the durable
        # job contract.
        target_duration_seconds=max(30, value.max_duration_seconds), language="en", audience="general",
        prompt_version="source-clip-v1", sources=(SourceReference(source_id="source-video", url=source_url, title=title),),
        review_mode="auto", captions_enabled=value.captions_enabled, production_mode="source_clip", source_url=source_url,
        clip_count=value.clip_count,
    )


IST = ZoneInfo("Asia/Kolkata")


def _as_ist(value: datetime) -> datetime:
    """Present UTC-persisted timestamps to Studio operators in IST."""
    return (value.replace(tzinfo=UTC) if value.tzinfo is None else value).astimezone(IST)


def _job_payload(job: object) -> dict[str, object]:
    return {
        "id": job.id,
        "state": job.state,
        "failure_message": job.failure_message,
        "blocked_reason": "insufficient_sources" if (job.failure_message or "").startswith("insufficient_sources:") else None,
        "created_at": _as_ist(job.created_at),
    }


DASHBOARD_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TubeForge Studio</title><style>
:root{color-scheme:dark;--bg:#080d1a;--panel:#111a2e;--muted:#8ea0bd;--line:#253451;--cyan:#5ee8ff;--good:#70e1a1;--warn:#ffd36a;--bad:#ff8492}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at top,#162544,#080d1a 45%);color:#f3f7ff;font:15px/1.5 Inter,ui-sans-serif,system-ui,sans-serif;min-height:100vh}.shell{max-width:1180px;margin:auto;padding:22px 16px 48px}.top{display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:22px}.brand{font-size:22px;font-weight:800;letter-spacing:-.5px}.brand i{font-style:normal;color:var(--cyan)}.sub{color:var(--muted);font-size:13px}.grid{display:grid;grid-template-columns:minmax(270px,350px) 1fr;gap:18px}.panel,.job{background:linear-gradient(145deg,#131f37,#0e1729);border:1px solid var(--line);border-radius:16px;box-shadow:0 12px 32px #0003}.panel{padding:18px}h1,h2,h3,p{margin:0}h2{font-size:17px}label{display:block;margin:13px 0 0;color:#cbd7eb;font-size:13px}input:not([type=checkbox]),textarea,select,button{font:inherit;width:100%;margin-top:5px;border-radius:9px;border:1px solid #31415f;padding:10px;background:#0a1222;color:#f5f8ff}textarea{min-height:106px;resize:vertical}input[type=checkbox]{accent-color:var(--cyan)}button{border:0;background:linear-gradient(100deg,#53d6f1,#8099ff);color:#07111e;font-weight:800;cursor:pointer}button.secondary{background:#223452;color:#eaf4ff;border:1px solid #3b5076}button.danger{background:#4b2634;color:#ffdce1;border:1px solid #864454}button.small{width:auto;margin:0;padding:7px 10px;font-size:12px}.checkbox{display:flex;gap:8px;align-items:center;margin-top:15px}.checkbox input{width:auto}.toolbar{display:flex;justify-content:space-between;gap:10px;align-items:center;margin-bottom:12px}.toolbar select{width:auto;margin:0;padding:7px}.jobs{display:grid;gap:11px}.job{padding:15px;overflow-wrap:anywhere}.jobhead{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}.title{font-weight:800;font-size:16px}.badge{display:inline-flex;align-items:center;border-radius:99px;padding:4px 8px;background:#223654;color:#b7ebff;font-size:11px;font-weight:800;white-space:nowrap}.badge.failed{background:#4a2631;color:#ffc0c8}.badge.ready{background:#1c4038;color:#adf4ce}.muted{color:var(--muted);font-size:13px}.failure{margin-top:10px;border-left:3px solid var(--bad);padding:8px 10px;background:#2b1720;color:#ffdce1;border-radius:6px;font-size:13px}.actions{display:flex;flex-wrap:wrap;gap:7px;margin-top:13px}.empty,.loading,.error{padding:25px;text-align:center;color:var(--muted)}.error{color:#ffc0c8}.notice{min-height:20px;margin-top:10px;color:var(--good);font-size:13px}dialog{width:min(680px,calc(100% - 24px));max-height:86vh;color:#f4f7ff;background:#101a2d;border:1px solid #3b4d70;border-radius:16px;padding:0;box-shadow:0 24px 80px #000b}dialog::backdrop{background:#020714bb}.modal-head{display:flex;justify-content:space-between;gap:8px;align-items:center;padding:15px 16px;border-bottom:1px solid var(--line)}.modal-body{padding:16px;overflow:auto;max-height:70vh}.close{width:auto;background:transparent;color:#dbe8ff;font-size:20px;padding:0 6px}.video{width:100%;border-radius:10px;background:#000}.timeline{display:grid;gap:11px}.event{border-left:2px solid #406392;padding-left:10px}.event-time{color:var(--muted);font-size:12px}.event-type{font-weight:750}.event-detail{font-size:13px;color:#cbd7eb;white-space:pre-wrap;overflow-wrap:anywhere}@media(max-width:780px){.shell{padding:14px 12px}.grid{grid-template-columns:1fr}.top{align-items:flex-start}.panel{padding:15px}.jobhead{flex-direction:column}.badge{white-space:normal}.toolbar{align-items:flex-start;flex-direction:column}.toolbar select{width:100%}}</style></head>
<body><main class="shell"><header class="top"><div><div class="brand">Tube<i>Forge</i> Studio</div><div class="sub">Local video creation, review, and activity</div></div><div class="sub" id="connection">Connecting…</div></header><div class="grid"><section class="panel"><h2>New generation</h2><p class="sub">Give a title and the key points. You stay in control of review.</p><form id="createForm"><label>Title<input name="title" maxlength="500" required placeholder="e.g. Bare minimum for software engineers"></label><label>Notes<textarea name="notes" required placeholder="One point per line"></textarea></label><label>Duration<input name="duration_seconds" type="number" value="60" min="30" max="7200" required></label><label>Review mode<select name="review_mode"><option value="manual">Manual review</option><option value="auto">Automatic render</option></select></label><label class="checkbox"><input name="captions_enabled" type="checkbox" checked> Include captions</label><button type="submit">Create video</button><div class="notice" id="notice" role="status"></div></form></section><section><div class="toolbar"><div><h2>Generations</h2><div class="sub">Updates in place every 4 seconds</div></div><select id="filter" aria-label="Filter generations"><option value="all">All generations</option><option value="active">In progress</option><option value="needs_review">Needs review</option><option value="failed">Failed</option><option value="complete">Video ready</option></select></div><div id="jobs" class="jobs"><div class="loading">Loading generations…</div></div></section></div></main><dialog id="videoDialog" aria-labelledby="videoTitle"><div class="modal-head"><h2 id="videoTitle">Video</h2><button class="close" type="button" data-close="videoDialog" aria-label="Close video">×</button></div><div class="modal-body"><video id="player" class="video" controls preload="metadata" playsinline></video></div></dialog><dialog id="activityDialog" aria-labelledby="activityTitle"><div class="modal-head"><h2 id="activityTitle">Activity</h2><button class="close" type="button" data-close="activityDialog" aria-label="Close activity">×</button></div><div class="modal-body"><div id="timeline" class="timeline"><div class="loading">Loading activity…</div></div></div></dialog><script>
const jobsRoot=document.querySelector('#jobs'),filter=document.querySelector('#filter'),notice=document.querySelector('#notice'),cards=new Map();const esc=v=>String(v??'');const ready=s=>['preview_ready','final_ready','publication_approval_required','publication_ready','published'].includes(s),failed=s=>s.startsWith('failed_');const needs=s=>['script_approval_required','preview_ready','publication_approval_required'].includes(s);function matches(j){return filter.value==='all'||filter.value==='active'&&(!ready(j.state)&&!failed(j.state)&&!needs(j.state))||filter.value==='needs_review'&&needs(j.state)||filter.value==='failed'&&failed(j.state)||filter.value==='complete'&&j.artifacts.includes('final')}function badgeClass(j){return failed(j.state)?'failed':j.artifacts.includes('final')?'ready':''}function button(label,cls,fn){let b=document.createElement('button');b.type='button';b.className='small '+(cls||'secondary');b.textContent=label;b.onclick=fn;return b}function renderCard(card,j){card.replaceChildren();card.className='job';let head=document.createElement('div');head.className='jobhead';let name=document.createElement('div');name.className='title';name.textContent=j.topic;let badge=document.createElement('span');badge.className='badge '+badgeClass(j);badge.textContent=j.blocked_reason==='insufficient_sources'?'Blocked: insufficient sources':j.state.replaceAll('_',' ');head.append(name,badge);card.append(head);if(j.failure_message){let msg=document.createElement('div');msg.className='failure';msg.textContent=j.failure_message;card.append(msg)}let meta=document.createElement('div');meta.className='muted';meta.textContent=`${j.artifacts.length} saved artifacts · ${j.event_count} activity events`;card.append(meta);let actions=document.createElement('div');actions.className='actions';if(j.artifacts.includes('preview'))actions.append(button('Preview','secondary',()=>openVideo(j,'preview','Preview')));if(j.artifacts.includes('final'))actions.append(button('Watch final','',()=>openVideo(j,'final','Final video')));for(const clip of j.artifacts.filter(name=>name.startsWith('clip_')))actions.append(button(clip.replace('_',' '),'secondary',()=>openVideo(j,clip,clip.replace('_',' '))));actions.append(button('Activity','secondary',()=>openActivity(j)));if(j.state==='script_approval_required')actions.append(button('Approve script','',()=>approve(j.id,'script')));if(j.state==='preview_ready')actions.append(button('Approve preview','',()=>approve(j.id,'preview')));if(j.deletable)actions.append(button('Delete','danger',()=>removeJob(j.id)));card.append(actions)}async function refresh(){try{let r=await fetch('/api/jobs');if(!r.ok)throw Error('Could not load generations');let data=await r.json(),visible=data.filter(matches),seen=new Set;for(const job of visible){let card=cards.get(job.id);if(!card){card=document.createElement('article');cards.set(job.id,card);jobsRoot.append(card)}renderCard(card,job);seen.add(job.id)}for(const [id,card]of cards)if(!seen.has(id)){card.remove();cards.delete(id)}if(!visible.length)jobsRoot.innerHTML='<div class="empty">No matching generations yet.</div>';else if(jobsRoot.querySelector('.empty'))jobsRoot.querySelector('.empty').remove();document.querySelector('#connection').textContent='Dashboard connected'}catch(e){if(!cards.size)jobsRoot.innerHTML='<div class="error">Unable to load generations. Retrying…</div>';document.querySelector('#connection').textContent='Reconnecting…'}}async function openVideo(job,name,label){let dialog=document.querySelector('#videoDialog'),player=document.querySelector('#player');document.querySelector('#videoTitle').textContent=`${label}: ${job.topic}`;player.pause();player.removeAttribute('src');player.load();player.src=`/api/jobs/${job.id}/artifacts/${name}`;player.autoplay=false;dialog.showModal()}async function openActivity(job){let dialog=document.querySelector('#activityDialog'),timeline=document.querySelector('#timeline');document.querySelector('#activityTitle').textContent=`Activity: ${job.topic}`;timeline.replaceChildren(Object.assign(document.createElement('div'),{className:'loading',textContent:'Loading activity…'}));dialog.showModal();let r=await fetch(`/api/jobs/${job.id}/events`);let events=await r.json();timeline.replaceChildren();if(!events.length){timeline.textContent='No activity was recorded before the dashboard timeline was enabled.';return}for(const event of events){let node=document.createElement('div');node.className='event';let type=document.createElement('div');type.className='event-type';type.textContent=event.event_type.replaceAll('_',' ');let time=document.createElement('div');time.className='event-time';time.textContent=new Date(event.created_at).toLocaleString();let detail=document.createElement('div');detail.className='event-detail';detail.textContent=Object.entries(event.details).map(([k,v])=>`${k}: ${typeof v==='string'?v:JSON.stringify(v)}`).join('\n');node.append(type,time,detail);timeline.append(node)}}async function approve(id,gate){let r=await fetch(`/api/jobs/${id}/approvals/${gate}`,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({status:'approved',actor:'local-dashboard'})});if(!r.ok)alert(await r.text());refresh()}async function removeJob(id){if(confirm('Delete this local generation and its saved files?')){let r=await fetch(`/api/jobs/${id}`,{method:'DELETE'});if(!r.ok)alert(await r.text());refresh()}}document.querySelectorAll('[data-close]').forEach(b=>b.onclick=()=>{let d=document.querySelector('#'+b.dataset.close);if(d.id==='videoDialog'){let p=document.querySelector('#player');p.pause();p.removeAttribute('src');p.load()}d.close()});document.querySelector('#createForm').onsubmit=async e=>{e.preventDefault();let d=new FormData(e.currentTarget),body={title:d.get('title'),notes:d.get('notes').split('\n').map(x=>x.trim()).filter(Boolean),duration_seconds:Number(d.get('duration_seconds')),review_mode:d.get('review_mode'),captions_enabled:d.has('captions_enabled')};let r=await fetch('/api/videos',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)});if(!r.ok){notice.textContent='Could not create video: '+await r.text();return}notice.textContent='Generation created. It will appear in the list shortly.';e.currentTarget.reset();e.currentTarget.querySelector('[name=duration_seconds]').value=60;e.currentTarget.querySelector('[name=captions_enabled]').checked=true;refresh()};filter.onchange=refresh;refresh();setInterval(refresh,4000);</script></body></html>"""


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create the HTTP application using explicit settings when supplied."""
    application_settings = settings or load_settings()
    validate_selected_provider(application_settings)
    runtime: Runtime = create_runtime(application_settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
        try:
            yield
        finally:
            runtime.database.dispose()

    app = FastAPI(title=application_settings.app.name, lifespan=lifespan)
    app.state.settings = application_settings
    app.state.database = runtime.database
    app.state.runtime = runtime
    publishing_assets = PublishingAssetRegistry(
        runtime.database.session_factory, runtime.jobs, runtime.artifacts,
        application_settings.pipeline.voice.artifact_root,
        ffprobe=str(application_settings.pipeline.voice.ffprobe_executable),
    )
    manual_posts = ManualPublishService(runtime.database.session_factory)
    delivery_queue = DeliveryQueue(runtime.database.session_factory)
    publisher_presence = PublisherWorkerPresence(runtime.database.session_factory)

    oauth_store = OAuthStateStore(runtime.database.session_factory, runtime.token_cipher) if runtime.token_cipher else None
    google_oauth: GoogleAccountOAuth | None = None
    google_oauth_values = tuple(os.environ.get(name, "") for name in (
        "TUBEFORGE_GOOGLE_OAUTH_CLIENT_ID",
        "TUBEFORGE_GOOGLE_OAUTH_CLIENT_SECRET",
        "TUBEFORGE_GOOGLE_OAUTH_REDIRECT_URI",
    ))
    if oauth_store and all(google_oauth_values):
        try:
            google_oauth = GoogleAccountOAuth(*google_oauth_values)
        except ValueError:
            pass

    @app.exception_handler(RequestValidationError)
    async def redacted_validation_error(_: Request, error: RequestValidationError) -> JSONResponse:
        # Pydantic's default response includes the rejected input. A token
        # sent to a legacy account endpoint must not be echoed in the body.
        details = [{key: value for key, value in item.items() if key not in {"input", "ctx"}} for item in error.errors()]
        return JSONResponse({"detail": details}, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)

    attempts: dict[str, list[datetime]] = {}
    # A voice sample is a fixed, public-to-the-local-dashboard phrase. Keep it
    # outside individual job artifacts so selecting a narrator never launches
    # synthesis again after the first successful request. The lock also avoids
    # duplicate work when two browser tabs request the same new sample at once.
    voice_preview_lock = threading.Lock()
    voice_preview_text = "Welcome to TubeForge Studio. This is a local voice preview."

    def cached_voice_preview_path(voice_id: str) -> Path:
        key = hashlib.sha256(
            f"voice-preview-v1\\0{voice_id}\\0{voice_preview_text}".encode("utf-8")
        ).hexdigest()
        return Path(runtime.orchestrator.artifact_root) / "voice-previews" / f"{key}.wav"

    def valid_voice_preview(path: Path) -> bool:
        try:
            if not path.is_file() or path.stat().st_size <= 44:
                return False
            with wave.open(str(path), "rb") as stream:
                return (
                    stream.getnframes() > 0
                    and stream.getnchannels() > 0
                    and stream.getsampwidth() > 0
                    and stream.getframerate() > 0
                    and stream.getcomptype() == "NONE"
                )
        except (wave.Error, OSError, EOFError):
            return False

    @app.middleware("http")
    async def require_dashboard_auth(request: Request, call_next):
        if not application_settings.auth.enabled or request.url.path in {"/healthz", "/login", "/logout", "/favicon.ico", "/docs", "/openapi.json"}:
            return await call_next(request)
        session = runtime.auth.session(request.cookies.get("tubeforge_session"))
        if session is None:
            if request.url.path.startswith("/api/"):
                return JSONResponse({"detail": "authentication required"}, status_code=status.HTTP_401_UNAUTHORIZED)
            return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
        if request.method not in {"GET", "HEAD", "OPTIONS"} and request.headers.get("x-csrf-token") != session.csrf_token:
            return JSONResponse({"detail": "CSRF validation failed"}, status_code=status.HTTP_403_FORBIDDEN)
        return await call_next(request)

    @app.get("/login", response_class=HTMLResponse, include_in_schema=False)
    def login_form() -> str:
        return """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Sign in — TubeForge Studio</title><style>:root{color-scheme:dark}*{box-sizing:border-box}body{min-height:100vh;margin:0;display:grid;place-items:center;padding:20px;background:radial-gradient(circle at 25% 0,#1b3157,#080d1a 55%);color:#f4f7ff;font:15px/1.5 Inter,ui-sans-serif,system-ui,sans-serif}.card{width:min(100%,410px);padding:30px;border:1px solid #2c4167;border-radius:18px;background:linear-gradient(145deg,#15213a,#0e1729);box-shadow:0 24px 80px #0008}.eyebrow{color:#67dff5;font-size:12px;font-weight:800;letter-spacing:.12em;text-transform:uppercase}.brand{margin:5px 0;font-size:29px;letter-spacing:-1px}.brand b{color:#5ee8ff}.sub{margin:0;color:#a9b9d3}label{display:block;margin-top:18px;color:#d5e0f2;font-size:13px}input,button{width:100%;font:inherit;border-radius:9px;padding:11px}input{margin-top:6px;background:#091221;color:#f4f7ff;border:1px solid #344767}button{margin-top:22px;border:0;background:linear-gradient(100deg,#53d6f1,#8099ff);color:#07111e;font-weight:800;cursor:pointer}button:disabled{opacity:.65;cursor:wait}.password{position:relative}.password input{padding-right:80px}.toggle{position:absolute;right:6px;bottom:6px;width:auto;margin:0;padding:5px 8px;background:#243755;color:#e8f1ff;border:1px solid #405779;font-size:12px}.error{min-height:22px;margin:14px 0 0;color:#ffb8c2;font-size:13px}</style><main class="card"><div class="eyebrow">Private workspace</div><h1 class="brand">Tube<b>Forge</b> Studio</h1><p class="sub">Sign in to create, review, and publish your local video work.</p><form id="loginForm"><label>Username<input name="username" autocomplete="username" required autofocus></label><label>Password<span class="password"><input id="password" name="password" type="password" autocomplete="current-password" required><button id="toggle" class="toggle" type="button" aria-controls="password">Show</button></span></label><div id="error" class="error" role="alert" aria-live="polite"></div><button id="submit" type="submit">Sign in</button></form></main><script>const form=document.querySelector('#loginForm'),submit=document.querySelector('#submit'),error=document.querySelector('#error'),password=document.querySelector('#password');document.querySelector('#toggle').onclick=()=>{const visible=password.type==='text';password.type=visible?'password':'text';document.querySelector('#toggle').textContent=visible?'Show':'Hide'};form.onsubmit=async event=>{event.preventDefault();error.textContent='';submit.disabled=true;submit.textContent='Signing in…';try{const data=new FormData(form),response=await fetch('/login',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({username:data.get('username'),password:data.get('password')})});if(response.ok){location.assign('/');return}error.textContent=response.status===429?'Too many attempts. Please wait and try again.':'The username or password is incorrect.'}catch(_){error.textContent='Could not reach the local dashboard. Please retry.'}finally{submit.disabled=false;submit.textContent='Sign in'}}</script></html>"""

    @app.post("/login", include_in_schema=False)
    def login(value: LoginRequest, request: Request) -> Response:
        now = datetime.now(UTC); key = request.client.host if request.client else "unknown"
        recent = [at for at in attempts.get(key, []) if (now - at).total_seconds() < application_settings.auth.login_window_seconds]
        attempts[key] = recent
        if len(recent) >= application_settings.auth.login_attempt_limit:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="too many login attempts")
        issued = runtime.auth.authenticate(value.username, value.password, session_hours=application_settings.auth.session_hours)
        if issued is None:
            attempts[key].append(now)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
        attempts.pop(key, None)
        token, csrf = issued; response = JSONResponse({"status": "ok"})
        response.set_cookie("tubeforge_session", token, httponly=True, samesite="lax", secure=application_settings.auth.secure_cookies, max_age=application_settings.auth.session_hours * 3600)
        response.set_cookie("tubeforge_csrf", csrf, httponly=False, samesite="lax", secure=application_settings.auth.secure_cookies, max_age=application_settings.auth.session_hours * 3600)
        return response

    @app.post("/logout", include_in_schema=False)
    def logout(request: Request) -> Response:
        runtime.auth.logout(request.cookies.get("tubeforge_session")); response = JSONResponse({"status": "ok"})
        response.delete_cookie("tubeforge_session"); response.delete_cookie("tubeforge_csrf"); return response

    @app.get("/healthz", tags=["operations"])
    def healthz() -> dict[str, str]:
        """Report process and database reachability without exposing settings."""
        try:
            with runtime.database.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="database unavailable",
            ) from error
        return {"status": "ok", "database": "ok"}

    @app.post("/api/topics", status_code=status.HTTP_201_CREATED, tags=["topics"])
    def create_topic(value: TopicCreateRequest) -> dict[str, object]:
        topic = runtime.topics.create(uuid4().hex, title=value.title, notes=value.notes, priority=value.priority, options=value.options)
        return {"id": topic.id, "title": topic.title, "status": topic.status, "priority": topic.priority}

    @app.post("/api/topics/bulk", status_code=status.HTTP_201_CREATED, tags=["topics"])
    def create_topics_bulk(value: TopicBulkCreateRequest) -> list[dict[str, object]]:
        try:
            topics = runtime.topics.create_many(tuple((uuid4().hex, title) for title in value.titles), priority=value.priority)
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
        return [{"id": item.id, "title": item.title, "status": item.status, "priority": item.priority} for item in topics]

    @app.get("/api/social-accounts", tags=["social accounts"])
    def list_social_accounts() -> list[dict[str, object]]:
        return [{"id": item.id, "platform": item.platform, "display_name": item.display_name, "external_account_id": item.external_account_id, "auth_type": item.auth_type, "scopes": item.scopes, "status": item.status, "capabilities": item.capabilities, "is_default": item.is_default, "disabled": item.disabled, "token_expires_at": item.token_expires_at, "last_validated_at": item.last_validated_at} for item in runtime.accounts.list()]

    @app.get("/api/oauth/youtube/status", tags=["social accounts"])
    def youtube_oauth_status() -> dict[str, object]:
        configured = application_settings.auth.enabled and google_oauth is not None and oauth_store is not None
        return {"configured": configured, "reason": None if configured else "Google application, HTTPS callback, account encryption key, and Studio login are required"}

    @app.post("/api/oauth/youtube/start", tags=["social accounts"])
    def start_youtube_oauth(value: OAuthStartRequest, request: Request) -> dict[str, str]:
        if not application_settings.auth.enabled or google_oauth is None or oauth_store is None:
            raise HTTPException(status_code=503, detail="YouTube connection is not configured")
        login_session = runtime.auth.session(request.cookies.get("tubeforge_session"))
        if login_session is None:
            raise HTTPException(status_code=401, detail="Studio sign-in is required")
        if value.account_id:
            account = next((item for item in runtime.accounts.list() if item.id == value.account_id), None)
            if account is None or account.platform != "youtube":
                raise HTTPException(status_code=404, detail="YouTube account not found")
        verifier = secrets.token_urlsafe(64)
        state = oauth_store.begin(platform="youtube", account_id=value.account_id, session_id=login_session.id, redirect_uri=google_oauth.redirect_uri, code_verifier=verifier)
        try:
            url = google_oauth.authorization_url(state, verifier)
        except Exception as error:
            raise HTTPException(status_code=502, detail="Could not start Google authorization") from error
        return {"authorization_url": url}

    @app.get("/oauth/youtube/callback", response_class=HTMLResponse, include_in_schema=False)
    def youtube_oauth_callback(request: Request, state: str = "", code: str = "", error: str = "") -> str:
        if google_oauth is None or oauth_store is None:
            raise HTTPException(status_code=503, detail="YouTube connection is not configured")
        login_session = runtime.auth.session(request.cookies.get("tubeforge_session"))
        if login_session is None:
            raise HTTPException(status_code=401, detail="Studio sign-in is required")
        pending = oauth_store.consume(state, platform="youtube", session_id=login_session.id)
        if pending is None:
            raise HTTPException(status_code=400, detail="Google authorization state is expired or invalid")
        if error or not code or not pending.code_verifier:
            raise HTTPException(status_code=400, detail="Google authorization was declined or incomplete")
        try:
            verified = google_oauth.exchange_and_discover(code=code, state=state, code_verifier=pending.code_verifier)
            candidate = oauth_store.stage_verified(state, session_id=login_session.id, external_id=verified.channel_id, label=verified.label, credential=verified.credential, scopes=verified.scopes, expires_at=verified.expires_at)
        except Exception as failure:
            raise HTTPException(status_code=400, detail="Google channel verification failed; reconnect and try again") from failure
        return f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Confirm YouTube channel — TubeForge</title><style>body{{background:#080d1a;color:#f3f7ff;font:16px system-ui;max-width:520px;margin:10vh auto;padding:20px}}main{{background:#111a2e;border:1px solid #253451;border-radius:16px;padding:24px}}button{{background:#5ee8ff;color:#07111e;border:0;border-radius:9px;padding:12px;font:inherit;font-weight:700;cursor:pointer}}button:disabled{{opacity:.6}}a{{color:#5ee8ff}}</style><main><h1>Confirm YouTube channel</h1><p>TubeForge found <strong>{html.escape(candidate.label)}</strong>.</p><p>Channel ID: <code>{html.escape(candidate.external_id)}</code></p><p>Confirm this exact destination before saving the encrypted connection.</p><input id="oauthState" type="hidden" value="{html.escape(state)}"><button id="confirm" type="button">Connect this channel</button><p id="result" role="status" aria-live="polite"></p><a href="/">Return to Studio</a></main><script>document.querySelector('#confirm').onclick=async()=>{{const button=document.querySelector('#confirm'),result=document.querySelector('#result');button.disabled=true;button.textContent='Saving connection…';const csrf=(document.cookie.match(/(?:^|; )tubeforge_csrf=([^;]+)/)||[])[1];try{{const response=await fetch('/api/oauth/youtube/confirm',{{method:'POST',headers:{{'content-type':'application/json','x-csrf-token':decodeURIComponent(csrf||'')}},body:JSON.stringify({{state:document.querySelector('#oauthState').value}})}});if(!response.ok)throw Error(await response.text());result.textContent='Channel connected. Returning to Studio…';location.assign('/');}}catch(_){{result.textContent='Could not save this connection. Start authorization again.';button.disabled=false;button.textContent='Connect this channel';}}}};</script></html>"""

    @app.post("/api/oauth/youtube/confirm", tags=["social accounts"])
    def confirm_youtube_oauth(value: OAuthConfirmRequest, request: Request) -> dict[str, object]:
        if oauth_store is None:
            raise HTTPException(status_code=503, detail="YouTube connection is not configured")
        login_session = runtime.auth.session(request.cookies.get("tubeforge_session"))
        if login_session is None:
            raise HTTPException(status_code=401, detail="Studio sign-in is required")
        try:
            account_id = oauth_store.confirm(value.state, session_id=login_session.id)
        except ValueError as failure:
            raise HTTPException(status_code=409, detail=str(failure)) from failure
        account = next(item for item in runtime.accounts.list() if item.id == account_id)
        return {"id": account.id, "platform": account.platform, "display_name": account.display_name, "external_account_id": account.external_account_id, "status": account.status}

    @app.get("/api/publishing/ready-videos", tags=["publishing"])
    def list_ready_videos() -> list[dict[str, object]]:
        ready: list[dict[str, object]] = []
        for job in runtime.jobs.list_recent(limit=200):
            if job.state in READY_STATES and job.claim_owner is None and runtime.artifacts.get(job.id, JobState.FINAL_RENDERING, "final") is not None:
                ready.append({"job_id": job.id, "title": job.request.topic, "state": job.state.value})
        return ready

    @app.get("/api/publishing/status", tags=["publishing"])
    def publishing_worker_status() -> dict[str, object]:
        platforms = sorted(publisher_presence.live_platforms())
        return {"worker_online": bool(platforms), "platforms": platforms, "manual_submission_enabled": bool(runtime.token_cipher and "youtube" in platforms)}

    @app.post("/api/publishing/drafts", status_code=status.HTTP_201_CREATED, tags=["publishing"])
    def create_manual_publish_draft(value: ManualPublishDraftRequest) -> dict[str, object]:
        try:
            asset = publishing_assets.register_final(value.job_id)
            post = manual_posts.create_draft(asset.id, value.destinations)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="generation not found") from error
        except ValueError as error:
            detail = str(error)
            code = 409 if "already reserved" in detail or "not available" in detail or "stable final" in detail else 422
            raise HTTPException(status_code=code, detail=detail) from error
        except OSError as error:
            raise HTTPException(status_code=409, detail="final video file is unavailable") from error
        return {"id": post.id, "state": post.state, "asset_id": asset.id, "asset_sha256": asset.sha256, "destinations": [{"account_id": item.account_id, "platform": item.platform, "external_account_id": item.external_account_id, "state": item.state} for item in manual_posts.deliveries(post.id)]}

    @app.get("/api/publishing/drafts", tags=["publishing"])
    def list_manual_publish_drafts() -> list[dict[str, object]]:
        posts = []
        for post in manual_posts.list_recent():
            deliveries = manual_posts.deliveries(post.id)
            with runtime.database.session_factory() as session:
                asset = session.get(PublishingAssetRecord, post.asset_id)
                recent_attempts = list(session.scalars(select(DeliveryAttemptRecord).where(
                    DeliveryAttemptRecord.delivery_id.in_([item.id for item in deliveries]),
                ).order_by(DeliveryAttemptRecord.started_at.desc(), DeliveryAttemptRecord.id.desc()).limit(100))) if deliveries else []
                account_rows = list(session.scalars(select(SocialAccountRecord).where(
                    SocialAccountRecord.id.in_([item.account_id for item in deliveries]),
                ))) if deliveries else []
            accounts_by_id = {item.id: item for item in account_rows}
            attempts_by_delivery: dict[str, list[dict[str, object]]] = {item.id: [] for item in deliveries}
            for attempt in recent_attempts:
                attempts_by_delivery[attempt.delivery_id].append({
                    "kind": attempt.kind, "state": attempt.state,
                    "remote_id": attempt.remote_id, "error_message": attempt.error_message,
                    "started_at": _as_ist(attempt.started_at),
                    "finished_at": _as_ist(attempt.finished_at) if attempt.finished_at else None,
                })
            posts.append({
                "id": post.id, "state": post.state, "asset_id": post.asset_id,
                "asset_sha256": asset.sha256 if asset else None,
                "video_url": f"/api/publishing/assets/{post.asset_id}/video",
                "reviewed_identity": manual_posts.review_identity(post.id),
                "created_at": _as_ist(post.created_at),
                "submitted_at": _as_ist(post.submitted_at) if post.submitted_at else None,
                "destinations": [{
                    "id": item.id, "account_id": item.account_id, "platform": item.platform,
                    "external_account_id": item.external_account_id, "state": item.state,
                    "metadata": json.loads(item.metadata_json), "attempt_count": item.attempt_count,
                    "error_message": item.error_message, "remote_id": item.remote_id,
                    "remote_url": item.remote_url,
                    "requested_action": item.requested_action,
                    "requested_by": item.requested_by,
                    "requested_at": _as_ist(item.requested_at) if item.requested_at else None,
                    "attempts": attempts_by_delivery[item.id],
                    "can_inspect": item.platform == "youtube" and item.state == "unknown_outcome" and bool(item.remote_session_id) and not item.remote_id and not item.requested_action,
                    "can_resume": item.platform == "youtube" and item.state == "unknown_outcome" and bool(item.remote_session_id) and not item.remote_id and not item.requested_action and bool(item.error_message and item.error_message.startswith("remote upload is incomplete")),
                    "can_retry_after_reconnect": item.state == "auth_required" and not item.claim_owner and bool(accounts_by_id.get(item.account_id) and not accounts_by_id[item.account_id].disabled and accounts_by_id[item.account_id].status == "connected" and accounts_by_id[item.account_id].external_account_id == item.external_account_id and accounts_by_id[item.account_id].credential_ciphertext),
                } for item in deliveries],
            })
        return posts

    @app.get("/api/publishing/assets/{asset_id}/video", tags=["publishing"])
    def preview_publishing_asset(asset_id: str) -> FileResponse:
        try:
            path = publishing_assets.preview_path(asset_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="publishing video not found") from error
        except (OSError, ValueError) as error:
            raise HTTPException(status_code=410, detail="publishing video is unavailable or changed") from error
        return FileResponse(path, media_type="video/mp4")

    @app.post("/api/publishing/drafts/{post_id}/submit", tags=["publishing"])
    def submit_manual_publish_draft(post_id: str, value: ManualPublishSubmitRequest, request: Request) -> dict[str, object]:
        login_session = runtime.auth.session(request.cookies.get("tubeforge_session"))
        if login_session is None:
            raise HTTPException(status_code=401, detail="Studio sign-in is required")
        supported = publisher_presence.live_platforms() & {"youtube"} if runtime.token_cipher else set()
        if not supported:
            raise HTTPException(status_code=503, detail="private YouTube publisher worker is unavailable")
        try:
            post = manual_posts.submit(post_id, reviewed_identity=value.reviewed_identity, actor=login_session.user_id, supported_platforms=supported)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="publishing draft not found") from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return {"id": post.id, "state": post.state, "reviewed_identity": post.reviewed_identity, "destinations": [{"account_id": item.account_id, "state": item.state} for item in manual_posts.deliveries(post.id)]}

    @app.post("/api/publishing/deliveries/{delivery_id}/actions", tags=["publishing"])
    def request_delivery_action(delivery_id: str, value: DeliveryActionRequest, request: Request) -> dict[str, str]:
        login_session = runtime.auth.session(request.cookies.get("tubeforge_session"))
        if login_session is None:
            raise HTTPException(status_code=401, detail="Studio sign-in is required")
        if not runtime.token_cipher or "youtube" not in publisher_presence.live_platforms():
            raise HTTPException(status_code=503, detail="YouTube publisher worker is unavailable")
        try:
            if value.action == "retry_after_reconnect":
                resulting_state = delivery_queue.retry_after_reconnect(delivery_id, login_session.user_id)
            else:
                delivery_queue.request_action(delivery_id, value.action, login_session.user_id)
                resulting_state = "pending"
        except KeyError as error:
            raise HTTPException(status_code=404, detail="publishing destination not found") from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return {"delivery_id": delivery_id, "action": value.action, "state": resulting_state}

    @app.post("/api/social-accounts", status_code=status.HTTP_201_CREATED, tags=["social accounts"])
    def create_social_account(value: SocialAccountCreateRequest) -> dict[str, object]:
        # This endpoint creates a visible placeholder only. A browser-supplied
        # token or claimed remote ID cannot prove account ownership and must
        # never create a "connected" publishing destination.
        account = runtime.accounts.create(uuid4().hex, platform=value.platform, display_name=value.display_name, external_account_id=None, auth_type=value.auth_type, credential_ciphertext=None, scopes=(), capabilities=())
        return {"id": account.id, "platform": account.platform, "display_name": account.display_name, "status": account.status, "capabilities": account.capabilities}

    @app.post("/api/social-accounts/{account_id}/disable", tags=["social accounts"])
    def disable_social_account(account_id: str) -> Response:
        try: runtime.accounts.disable(account_id)
        except KeyError as error: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="account not found") from error
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get("/api/topics", tags=["topics"])
    def list_topics(status_filter: str | None = None) -> list[dict[str, object]]:
        return [{"id": item.id, "title": item.title, "notes": item.notes, "priority": item.priority, "status": item.status, "generation_job_id": item.generation_job_id, "attempts": item.attempts} for item in runtime.topics.list(status=status_filter)]

    @app.post("/api/schedules", status_code=status.HTTP_201_CREATED, tags=["schedules"])
    def create_schedule(value: ScheduleCreateRequest) -> dict[str, object]:
        try:
            schedule = runtime.schedules.create(uuid4().hex, name=value.name, cron=value.cron, timezone=value.timezone, next_run_at=next_run(value.cron, value.timezone, datetime.now(UTC)), options=value.options)
        except (ValueError, KeyError) as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"invalid cron schedule: {error}") from error
        return {"id": schedule.id, "name": schedule.name, "next_run_at": schedule.next_run_at}

    @app.get("/api/schedules", tags=["schedules"])
    def list_schedules() -> list[dict[str, object]]:
        return [{"id": item.id, "name": item.name, "cron": item.cron, "timezone": item.timezone, "enabled": item.enabled, "next_run_at": item.next_run_at, "last_run_at": item.last_run_at, "options": item.options} for item in runtime.schedules.list()]

    @app.post("/api/schedules/{schedule_id}/run", tags=["schedules"])
    def run_schedule(schedule_id: str) -> dict[str, object]:
        schedule = next((item for item in runtime.schedules.list() if item.id == schedule_id), None)
        if schedule is None: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="schedule not found")
        return runtime.scheduler.run(schedule, run_key=f"manual-{uuid4().hex}")

    @app.post("/api/jobs", status_code=status.HTTP_201_CREATED, tags=["jobs"])
    def create_job(request: ContentRequest) -> dict[str, object]:
        """Create a durable job; a separate worker advances it."""
        job = runtime.jobs.create(uuid4().hex, request)
        runtime.events.append(job.id, "job_created", topic=job.request.topic, review_mode=job.request.review_mode)
        return _job_payload(job)

    @app.post("/api/videos", status_code=status.HTTP_201_CREATED, tags=["videos"])
    def create_video(brief: VideoBriefRequest) -> dict[str, object]:
        available_music = runtime.orchestrator.music_catalog.names() if runtime.orchestrator.music_catalog else set()
        job = runtime.jobs.create(uuid4().hex, _video_request(brief, application_settings, available_music=available_music))
        runtime.events.append(job.id, "job_created", topic=job.request.topic, review_mode=job.request.review_mode)
        return {**_job_payload(job), "watch_url": f"/api/jobs/{job.id}/artifacts/final"}

    @app.post("/api/source-clips", status_code=status.HTTP_201_CREATED, tags=["videos"])
    def create_source_clips(brief: SourceClipRequest) -> dict[str, object]:
        if not application_settings.pipeline.source_clips.enabled:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="source clipping is disabled")
        job = runtime.jobs.create(uuid4().hex, _source_clip_request(brief))
        runtime.events.append(job.id, "source_clip_job_created", source_url=str(job.request.source_url), clip_count=job.request.clip_count)
        return {**_job_payload(job), "watch_url": f"/api/jobs/{job.id}/artifacts/final"}

    def legacy_video_form() -> str:
        return """<!doctype html><meta name=viewport content='width=device-width,initial-scale=1'><title>TubeForge</title><style>*{box-sizing:border-box}body{font:16px system-ui;max-width:760px;margin:20px auto;padding:0 14px;background:#101827;color:#e6edf3;overflow-x:hidden}label{display:block;margin:10px 0}input:not([type=checkbox]),textarea,select,button{font:inherit;padding:9px;margin-top:4px;width:100%;max-width:100%;border-radius:6px;border:1px solid #334155;background:#fff;color:#0f172a}textarea{min-height:88px;resize:vertical}input[type=checkbox]{width:auto;margin-right:7px}button{background:#38bdf8;border:0;color:#06233a;font-weight:700;cursor:pointer}.job{background:#172033;margin:10px 0;padding:12px;border-radius:8px;overflow-wrap:anywhere}.state{color:#7dd3fc}.actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:9px}.actions button{width:auto;margin:0;padding:7px 10px}.danger{background:#fda4af}a{color:#7dd3fc}video{display:block;width:100%;max-width:100%;margin-top:10px;border-radius:6px;background:#000}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><h1>TubeForge</h1><p>Create, review, and track local video generations.</p><form id=f><label>Title<input name=title required></label><label>Notes<textarea name=notes required placeholder='One point per line'></textarea></label><label>Duration (seconds)<input name=duration_seconds type=number value=60 min=30></label><label><input name=captions_enabled type=checkbox checked> Captions</label><label>Review<select name=review_mode><option value=manual>Manual: approve script and preview</option><option value=auto>Auto render</option></select></label><button>Create video</button></form><pre id=o></pre><h2>Generations</h2><div id=jobs>Loading…</div><script>const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));async function refresh(){let r=await fetch('/api/jobs');let j=await r.json();jobs.innerHTML=j.map(x=>{let a=x.artifacts||[],preview=a.includes('preview'),final=a.includes('final'),actions=(x.state==='script_approval_required'?`<button onclick=approve('${x.id}','script')>Approve script</button>`:'')+(x.state==='preview_ready'?`<button onclick=approve('${x.id}','preview')>Approve preview</button>`:'')+(x.deletable?`<button class=danger onclick=removeJob('${x.id}')>Delete</button>`:'');let media=final?`<video controls preload=metadata src='/api/jobs/${x.id}/artifacts/final'></video>`:preview?`<video controls preload=metadata src='/api/jobs/${x.id}/artifacts/preview'></video>`:'';return `<div class=job><b>${esc(x.topic)}</b><br><span class=state>${esc(x.state)}</span>${x.failure_message?'<br>'+esc(x.failure_message):''}${media}<div class=actions>${actions}</div></div>`}).join('')||'No generations yet.'}async function approve(id,gate){await fetch(`/api/jobs/${id}/approvals/${gate}`,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({status:'approved',actor:'local-dashboard'})});refresh()}async function removeJob(id){if(confirm('Delete this generation and its local files?')){let r=await fetch(`/api/jobs/${id}`,{method:'DELETE'});if(!r.ok)alert(await r.text());refresh()}}f.onsubmit=async e=>{e.preventDefault();let d=new FormData(f),b={title:d.get('title'),notes:d.get('notes').split('\\n').filter(Boolean),duration_seconds:+d.get('duration_seconds'),captions_enabled:d.has('captions_enabled'),review_mode:d.get('review_mode')};let r=await fetch('/api/videos',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(b)});o.textContent=await r.text();refresh()};refresh();setInterval(refresh,3000)</script>"""

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def video_form() -> str:
        # Keep JavaScript newline escapes literal inside the Python HTML string.
        # Without this normalization Python turns them into raw line breaks in
        # quoted JavaScript strings, which prevents the whole script from parsing.
        source_controls = """<script>
        (() => {
          // Persisted timestamps are serialized as IST; format them explicitly
          // too, so every browser shows the same operator-facing timezone.
          Date.prototype.toLocaleString = function(){return new Intl.DateTimeFormat('en-IN',{timeZone:'Asia/Kolkata',year:'numeric',month:'short',day:'numeric',hour:'numeric',minute:'2-digit',second:'2-digit',hour12:true}).format(this)+' IST';};
          const form = document.querySelector('#createForm');
          if (!form) return;
          const presetLabel=document.createElement('label'); presetLabel.textContent='Format preset';
          const presetSelect=document.createElement('select'); presetSelect.name='preset'; presetSelect.id='presetSelect';
          presetSelect.append(Object.assign(document.createElement('option'),{value:'default',textContent:'Default — 16:9'}));
          presetLabel.append(presetSelect); form.insertBefore(presetLabel,form.querySelector('[name=duration_seconds]').closest('label'));
          fetch('/api/presets').then(response=>response.ok?response.json():[]).then(presets=>{presetSelect.replaceChildren();presets.forEach(preset=>{const option=document.createElement('option');option.value=preset.name;option.textContent=preset.label;Object.assign(option.dataset,{duration:preset.duration_seconds,min:preset.minimum_duration_seconds,max:preset.maximum_duration_seconds,aspect:preset.aspect_ratio});presetSelect.append(option);});presetSelect.value=presets.some(value=>value.name==='default')?'default':presets[0]?.name||'default';presetSelect.onchange=()=>{const option=presetSelect.selectedOptions[0],duration=form.querySelector('[name=duration_seconds]');if(!option)return;duration.value=option.dataset.duration;duration.min=option.dataset.min;duration.max=option.dataset.max;};presetSelect.onchange();});
          const visualLabel=document.createElement('label'); visualLabel.textContent='Visuals';
          const visualSelect=document.createElement('select'); visualSelect.name='visual_source'; visualSelect.id='visualSource';
          visualSelect.append(Object.assign(document.createElement('option'),{value:'generated',textContent:'Generate local scene art'}),Object.assign(document.createElement('option'),{value:'stock',textContent:'Rights-safe stock (Wikimedia Commons; local fallback if unavailable)'}));
          const visualHelp=document.createElement('span'); visualHelp.className='sub'; visualHelp.textContent='Google Image results are not used: a search result does not prove reuse rights.'; visualLabel.append(visualSelect,visualHelp);
          form.insertBefore(visualLabel, form.querySelector('[name=duration_seconds]').closest('label'));
          const channelLabel=document.createElement('label');channelLabel.textContent='Channel voice profile';
          const channelSelect=document.createElement('select');channelSelect.name='channel_identity';channelSelect.disabled=true;
          channelSelect.append(Object.assign(document.createElement('option'),{value:'',textContent:'Loading profiles…'}));channelLabel.append(channelSelect);form.insertBefore(channelLabel,presetLabel);
          fetch('/api/content-profiles').then(async response=>{if(!response.ok)throw Error();const data=await response.json();channelSelect.replaceChildren();data.profiles.forEach(profile=>channelSelect.append(Object.assign(document.createElement('option'),{value:profile.identity,textContent:profile.identity+(profile.uses_default?' (default voice)':'')})));channelSelect.value=data.default_identity;channelSelect.disabled=false;}).catch(()=>{channelSelect.replaceChildren(Object.assign(document.createElement('option'),{value:'',textContent:'Configured default (profile list unavailable)'}));});
          const originalFetch=window.fetch;
          window.fetch=(url, init={})=>{if(String(url)==='/api/videos'&&init.body){try{const body=JSON.parse(init.body);body.visual_source=visualSelect.value;body.preset=presetSelect.value;body.channel_identity=channelSelect.value||null;body.music_track=document.querySelector('#musicSelect')?.value||null;init={...init,body:JSON.stringify(body)};}catch(_){}}return originalFetch(url,init);};
          const panel = document.createElement('fieldset');
          panel.style.marginTop = '18px'; panel.style.border = '1px solid #31415f'; panel.style.borderRadius = '9px';
          panel.innerHTML = '<legend>Clip existing video / stream</legend><label>Source URL<input id="sourceClipUrl" type="url" placeholder="https://…"></label><label>Number of clips<input id="sourceClipCount" type="number" value="1" min="1" max="12"></label><label class="checkbox"><input id="sourceClipCaptions" type="checkbox"> Burn available captions</label><button id="sourceClipCreate" type="button" class="secondary">Create clip job</button>';
          form.append(panel);
          const voiceLabel=document.createElement('label'); voiceLabel.textContent='Narrator voice';
          const voiceSelect=document.createElement('select'); voiceSelect.name='voice_id'; voiceSelect.id='voiceSelect';
          const voicePreview=document.createElement('button'); voicePreview.type='button'; voicePreview.className='small secondary'; voicePreview.textContent='Preview voice'; voicePreview.style.marginTop='8px';
          const previewStatus=document.createElement('span'); previewStatus.className='sub'; previewStatus.style.marginLeft='8px'; previewStatus.setAttribute('aria-live','polite');
          voiceSelect.append(Object.assign(document.createElement('option'),{value:'',textContent:'Default local voice'})); voiceLabel.append(voiceSelect,voicePreview,previewStatus);
          form.querySelector('button[type="submit"]').before(voiceLabel);
          fetch('/api/voices').then(response=>response.ok?response.json():[]).then(voices=>voices.forEach(voice=>voiceSelect.append(Object.assign(document.createElement('option'),{value:voice.id,textContent:voice.label+(voice.provider==='kokoro'?' — natural':'')}))));
          const musicLabel=document.createElement('label');musicLabel.textContent='Background music';const musicSelect=document.createElement('select');musicSelect.name='music_track';musicSelect.id='musicSelect';musicLabel.append(musicSelect);form.querySelector('button[type="submit"]').before(musicLabel);
          async function loadMusic(){const response=await fetch('/api/music');if(!response.ok)return;const selected=musicSelect.value;musicSelect.replaceChildren(Object.assign(document.createElement('option'),{value:'',textContent:'No background music'}));(await response.json()).forEach(track=>musicSelect.append(Object.assign(document.createElement('option'),{value:track.name,textContent:track.name+' — '+track.license_name+(track.attribution_required?' (credit required)':'')})));musicSelect.value=selected;}
          loadMusic();
          const musicPanel=document.createElement('fieldset');musicPanel.style.marginTop='18px';musicPanel.style.border='1px solid #31415f';musicPanel.style.borderRadius='9px';musicPanel.innerHTML='<legend>Add licensed music</legend><p class="sub">Upload only a track whose actual licence permits this publishing use. “Royalty-free” alone is not a licence.</p><label>Track name<input id="musicName" maxlength="200"></label><label>Audio file<input id="musicFile" type="file" accept="audio/*"></label><label>Source URL<input id="musicSource" type="url" placeholder="https://…"></label><label>Actual licence name<input id="musicLicenseName" placeholder="e.g. CC BY 4.0"></label><label>Licence terms URL<input id="musicLicenseUrl" type="url" placeholder="https://…"></label><label class="checkbox"><input id="musicPublishingAllowed" type="checkbox"> I verified these terms permit the intended YouTube publishing use</label><label class="checkbox"><input id="musicAttributionRequired" type="checkbox"> Attribution is required</label><label>Attribution text<textarea id="musicAttribution" placeholder="Creator and required credit line"></textarea></label><button id="musicUpload" type="button" class="secondary">Upload approved track</button><div id="musicStatus" class="notice" role="status"></div>';
          form.append(musicPanel);
          document.querySelector('#musicUpload').onclick=async()=>{const file=document.querySelector('#musicFile').files[0],status=document.querySelector('#musicStatus');if(!file){status.textContent='Choose an audio file.';return;}const query=new URLSearchParams({name:document.querySelector('#musicName').value,filename:file.name,source_url:document.querySelector('#musicSource').value,license_name:document.querySelector('#musicLicenseName').value,license_url:document.querySelector('#musicLicenseUrl').value,attribution_required:String(document.querySelector('#musicAttributionRequired').checked),attribution:document.querySelector('#musicAttribution').value,publishing_allowed:String(document.querySelector('#musicPublishingAllowed').checked)});status.textContent='Validating and uploading…';const response=await fetch('/api/music?'+query,{method:'POST',headers:{'content-type':'application/octet-stream'},body:file});const data=response.ok?await response.json():null;status.textContent=response.ok?'Approved track added to the catalog.':'Could not add track: '+await response.text();if(data){await loadMusic();musicSelect.value=data.name;}};
          voicePreview.onclick=async()=>{const voice=voiceSelect.value;if(!voice){previewStatus.textContent='Choose a voice first.';return;}voicePreview.disabled=true;voicePreview.textContent='Loading preview…';previewStatus.textContent='';try{const audio=new Audio(`/api/voices/${encodeURIComponent(voice)}/preview`);await audio.play();previewStatus.textContent='Playing local sample.';audio.onended=()=>previewStatus.textContent='';audio.onerror=()=>previewStatus.textContent='Voice preview could not be played.';}catch(_){previewStatus.textContent='Voice preview could not be loaded.';}finally{voicePreview.disabled=false;voicePreview.textContent='Preview voice';}};
          document.querySelector('#sourceClipCreate').addEventListener('click', async () => {
            const notice = document.querySelector('#notice');
            const sourceUrl = document.querySelector('#sourceClipUrl').value.trim();
            const clipCount = Number(document.querySelector('#sourceClipCount').value);
            if (!sourceUrl) { notice.textContent = 'Enter a public source URL first.'; return; }
            const response = await fetch('/api/source-clips', {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({source_url: sourceUrl, clip_count: clipCount, captions_enabled: document.querySelector('#sourceClipCaptions').checked})});
            notice.textContent = response.ok ? 'Source clip job created. It will appear in the list shortly.' : 'Could not create clip job: ' + await response.text();
          });
        })();
        </script>"""
        operations_controls = """<script>
        (() => {
          const csrf=(document.cookie.match(/(?:^|; )tubeforge_csrf=([^;]+)/)||[])[1];
          if (csrf) { const original=window.fetch; window.fetch=(url, init={}) => { const method=(init.method||'GET').toUpperCase(); if (!['GET','HEAD','OPTIONS'].includes(method)) init.headers={...(init.headers||{}),'x-csrf-token':decodeURIComponent(csrf)}; return original(url,init); }; }
          const shell=document.querySelector('.shell'); if (!shell) return;
          const panel=document.createElement('section'); panel.className='panel'; panel.style.marginTop='18px';
          panel.innerHTML='<h2>Topic queue</h2><p class=sub>Paste one topic per line. Notes can be added from the API today.</p><textarea id=bulkTopics placeholder="Topic one&#10;Topic two"></textarea><button id=bulkTopicsButton type=button>Add topics</button><div id=topicStatus class=notice></div><h2 style="margin-top:22px">Schedule</h2><p class=sub>New schedules use the channel voice, format and duration selected above. Scheduled review policy is unchanged.</p><label>Name<input id=scheduleName value="Twice daily"></label><label>Cron<input id=scheduleCron value="0 9,18 * * *"></label><label>Timezone<input id=scheduleTimezone value="UTC"></label><button id=scheduleButton type=button>Create schedule</button><div id=scheduleStatus class=notice></div><div id=operationsList class=muted style="margin-top:12px"></div>';
          shell.append(panel);
          async function listOps(){ const [topics,schedules]=await Promise.all([fetch('/api/topics').then(r=>r.json()),fetch('/api/schedules').then(r=>r.json())]); document.querySelector('#operationsList').textContent=`${topics.length} topics · ${schedules.length} schedules`; }
          document.querySelector('#bulkTopicsButton').onclick=async()=>{const titles=document.querySelector('#bulkTopics').value.split('\\n').map(v=>v.trim()).filter(Boolean);const r=await fetch('/api/topics/bulk',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({titles})});document.querySelector('#topicStatus').textContent=r.ok?`Added ${(await r.json()).length} topics.`:'Could not add topics: '+await r.text();if(r.ok){document.querySelector('#bulkTopics').value='';listOps();}};
          document.querySelector('#scheduleButton').onclick=async()=>{const button=document.querySelector('#scheduleButton'),status=document.querySelector('#scheduleStatus'),duration=form.querySelector('[name=duration_seconds]');if(!duration.reportValidity())return;const body={name:document.querySelector('#scheduleName').value,cron:document.querySelector('#scheduleCron').value,timezone:document.querySelector('#scheduleTimezone').value,options:{channel_identity:channelSelect.value||null,preset_name:presetSelect.value,aspect_ratio:presetSelect.selectedOptions[0]?.dataset.aspect||'16:9',duration_seconds:Number(duration.value)}};button.disabled=true;status.textContent='Saving schedule…';try{const r=await fetch('/api/schedules',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)});if(!r.ok)throw Error(await r.text());status.textContent='Schedule created.';await listOps();}catch(error){status.textContent='Could not create schedule: '+error.message;}finally{button.disabled=false;}}; listOps();
        })();
        </script>"""
        account_controls = """<script>
        (() => {
          const shell=document.querySelector('.shell'); if(!shell)return;
          const panel=document.createElement('section');panel.className='panel';panel.style.marginTop='18px';
          const title=document.createElement('h2');title.textContent='Publishing accounts';
          const note=document.createElement('p');note.className='sub';note.textContent='Connections require verified platform authorization. Instagram connection is not available yet.';
          const connect=document.createElement('button');connect.type='button';connect.className='small secondary';connect.textContent='Connect YouTube';connect.disabled=true;connect.style.marginTop='12px';
          const connectStatus=document.createElement('div');connectStatus.className='sub';connectStatus.setAttribute('role','status');connectStatus.textContent='Checking YouTube connection setup…';
          const list=document.createElement('div');list.className='muted';list.setAttribute('aria-live','polite');list.textContent='Loading accounts…';
          panel.append(title,note,connect,connectStatus,list);shell.append(panel);
          let youtubeReady=false;
          fetch('/api/oauth/youtube/status').then(response=>response.json()).then(result=>{youtubeReady=Boolean(result.configured);connect.disabled=!youtubeReady;connectStatus.textContent=youtubeReady?'YouTube authorization is ready. Google will ask you to choose a channel.':result.reason;}).catch(()=>{connectStatus.textContent='Could not check YouTube connection setup.';});
          async function start(accountId){if(!youtubeReady)return;connect.disabled=true;connectStatus.textContent='Starting Google authorization…';try{const response=await fetch('/api/oauth/youtube/start',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({account_id:accountId||null})});if(!response.ok)throw Error(await response.text());const result=await response.json();location.assign(result.authorization_url);}catch(_){connectStatus.textContent='Could not start Google authorization. Check the app configuration and retry.';connect.disabled=false;}}
          connect.onclick=()=>start(null);
          fetch('/api/social-accounts').then(async response=>{if(!response.ok)throw Error('Account list unavailable');const accounts=await response.json();list.replaceChildren();if(!accounts.length){list.textContent='No publishing accounts configured.';return;}for(const account of accounts){const row=document.createElement('div');row.className='event';row.style.marginTop='12px';const name=document.createElement('strong');name.textContent=account.display_name+' · '+account.platform;const state=document.createElement('div');state.textContent=account.status==='connected'&&account.external_account_id?'Connected · '+account.external_account_id:account.status.replaceAll('_',' ');row.append(name,state);if(account.platform==='youtube'&&account.external_account_id){const reconnect=document.createElement('button');reconnect.type='button';reconnect.className='small secondary';reconnect.textContent='Reconnect this channel';reconnect.disabled=!youtubeReady;reconnect.onclick=()=>start(account.id);row.append(reconnect);fetch('/api/oauth/youtube/status').then(r=>r.json()).then(v=>reconnect.disabled=!v.configured).catch(()=>{});}list.append(row);}}).catch(()=>{list.textContent='Could not load publishing accounts. Reload to retry.';});
        })();
        </script>"""
        publishing_controls = """<script>
        (() => {
          const shell=document.querySelector('.shell');if(!shell)return;
          const panel=document.createElement('section');panel.className='panel';panel.style.marginTop='18px';
          const heading=document.createElement('h2');heading.textContent='Compose manual post';
          const help=document.createElement('p');help.className='sub';help.textContent='Choose a finished video and exact connected accounts. Saving creates a durable draft; nothing is uploaded.';
          const workerState=document.createElement('p');workerState.className='sub';workerState.style.marginTop='8px';workerState.textContent='Checking publisher worker…';
          const videoLabel=document.createElement('label');videoLabel.textContent='Finished video';
          const videoSelect=document.createElement('select');videoSelect.id='publishVideo';videoSelect.disabled=true;videoLabel.append(videoSelect);
          const preview=document.createElement('button');preview.type='button';preview.className='small secondary';preview.textContent='Preview selected video';preview.disabled=true;preview.onclick=()=>{const dialog=document.querySelector('#videoDialog'),player=document.querySelector('#player');if(!dialog||!player||!videoSelect.value)return;document.querySelector('#videoTitle').textContent='Publishing preview: '+videoSelect.selectedOptions[0].textContent;player.pause();player.src='/api/jobs/'+encodeURIComponent(videoSelect.value)+'/artifacts/final';player.autoplay=false;dialog.showModal();};
          const destinationLabel=document.createElement('div');destinationLabel.className='sub';destinationLabel.style.marginTop='14px';destinationLabel.textContent='Destinations and individual post details';
          const destinations=document.createElement('div');destinations.id='publishDestinations';destinations.textContent='Loading connected accounts…';
          const save=document.createElement('button');save.type='button';save.id='savePublishDraft';save.textContent='Save publishing draft';save.disabled=true;
          const status=document.createElement('div');status.className='notice';status.id='publishDraftStatus';status.setAttribute('role','status');
          const historyHeading=document.createElement('h3');historyHeading.textContent='Publishing drafts';historyHeading.style.marginTop='20px';
          const refreshHistory=document.createElement('button');refreshHistory.type='button';refreshHistory.className='small secondary';refreshHistory.textContent='Refresh publishing activity';refreshHistory.style.marginBottom='12px';
          const history=document.createElement('div');history.id='publishDraftHistory';history.className='muted';history.textContent='Loading drafts…';
          panel.append(heading,help,workerState,videoLabel,preview,destinationLabel,destinations,save,status,historyHeading,refreshHistory,history);shell.append(panel);
          const rows=new Map();let workerReady=false;
          function inputField(labelText,kind){const label=document.createElement('label');label.textContent=labelText;const input=document.createElement(kind);input.maxLength=kind==='textarea'?5000:500;label.append(input);return {label,input};}
          async function requestDeliveryAction(item,action,button){if(action==='resume'&&!window.confirm('Continue only this saved remote upload session? No new session will be opened.'))return;button.disabled=true;status.textContent=action==='inspect'?'Requesting read-only remote inspection…':action==='resume'?'Requesting saved-session continuation…':'Checking the reconnected destination…';try{const response=await fetch('/api/publishing/deliveries/'+encodeURIComponent(item.id)+'/actions',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({action})});if(!response.ok)throw Error(await response.text());const result=await response.json();status.textContent=action==='retry_after_reconnect'?'Destination moved to '+result.state.replaceAll('_',' ')+'. Refresh activity for the worker result.':'Action queued. Refresh publishing activity to see the durable result.';await loadDrafts();}catch(error){status.textContent='Could not request action: '+error.message;button.disabled=false;}}
          async function loadDrafts(){try{
            const response=await fetch('/api/publishing/drafts');if(!response.ok)throw Error();const drafts=await response.json();history.replaceChildren();
            if(!drafts.length){history.textContent='No publishing drafts yet.';return;}
            for(const draft of drafts){
              const row=document.createElement('div');row.className='event';row.style.marginTop='12px';
              const title=document.createElement('strong');title.textContent='Post '+draft.id.slice(0,8)+' · '+draft.state.replaceAll('_',' ');row.append(title);
              if(draft.submitted_at){const submittedAt=document.createElement('div');submittedAt.className='sub';submittedAt.textContent='Submitted '+draft.submitted_at;row.append(submittedAt);}
              const details=document.createElement('details');const summary=document.createElement('summary');summary.textContent='Review exact video, destinations and activity';details.append(summary);
              const video=document.createElement('video');video.controls=true;video.preload='metadata';video.playsInline=true;video.className='video';video.src=draft.video_url;video.style.maxWidth='280px';details.append(video);
              const identity=document.createElement('p');identity.className='sub';identity.textContent='Video SHA-256: '+draft.asset_sha256;details.append(identity);
              for(const item of draft.destinations){
                const account=document.createElement('p');account.textContent=item.platform+' · '+item.external_account_id+' · '+item.state.replaceAll('_',' ')+' · '+item.attempt_count+' attempt(s)';details.append(account);
                const metadata=document.createElement('pre');metadata.style.whiteSpace='pre-wrap';metadata.style.overflowWrap='anywhere';metadata.textContent=JSON.stringify(item.metadata,null,2);details.append(metadata);
                if(item.error_message){const error=document.createElement('p');error.className='failure';error.textContent=item.error_message;details.append(error);}
                if(item.remote_id){const remote=document.createElement('p');remote.className='sub';remote.textContent='Remote ID: '+item.remote_id;details.append(remote);}
                if(item.remote_url){try{const url=new URL(item.remote_url);if(url.protocol==='https:'){const link=document.createElement('a');link.href=url.href;link.rel='noopener noreferrer';link.target='_blank';link.textContent='View remote post';details.append(link);}}catch(_){}}
                if(item.attempts.length){const activity=document.createElement('details');const activityLabel=document.createElement('summary');activityLabel.textContent='Destination attempt history ('+item.attempts.length+')';activity.append(activityLabel);for(const attempt of item.attempts){const event=document.createElement('p');event.className='sub';event.textContent=attempt.started_at+' · '+attempt.kind+' · '+attempt.state+(attempt.finished_at?' · ended '+attempt.finished_at:'')+(attempt.error_message?' · '+attempt.error_message:'')+(attempt.remote_id?' · remote '+attempt.remote_id:'');activity.append(event);}details.append(activity);}
                if(item.requested_action){const pending=document.createElement('p');pending.className='sub';pending.textContent=(item.requested_action==='inspect'?'Remote inspection':'Saved-session continuation')+' requested; waiting for the publisher worker.';details.append(pending);}
                if(item.can_inspect){const inspect=document.createElement('button');inspect.type='button';inspect.className='small secondary';inspect.textContent='Inspect saved remote session';inspect.dataset.reconcile='true';inspect.disabled=!workerReady;inspect.onclick=()=>requestDeliveryAction(item,'inspect',inspect);details.append(inspect);}
                if(item.can_resume){const resume=document.createElement('button');resume.type='button';resume.className='small secondary';resume.textContent='Continue saved upload session';resume.dataset.reconcile='true';resume.disabled=!workerReady;resume.onclick=()=>requestDeliveryAction(item,'resume',resume);details.append(resume);}
                if(item.can_retry_after_reconnect){const retry=document.createElement('button');retry.type='button';retry.className='small secondary';retry.textContent='Resume after account reconnect';retry.dataset.reconcile='true';retry.disabled=!workerReady;retry.onclick=()=>requestDeliveryAction(item,'retry_after_reconnect',retry);details.append(retry);}
                else if(item.state==='auth_required'){const reconnectNote=document.createElement('p');reconnectNote.className='sub';reconnectNote.textContent='Reconnect this exact account before resuming its destination.';details.append(reconnectNote);}
              }
              const supported=draft.destinations.length>0&&draft.destinations.every(item=>item.platform==='youtube'&&(item.metadata.visibility||'private')==='private');
              if(draft.state==='draft'&&supported){
                const reviewLabel=document.createElement('label');reviewLabel.className='checkbox';const reviewed=document.createElement('input');reviewed.type='checkbox';reviewLabel.append(reviewed,document.createTextNode(' I reviewed this exact video and every destination detail'));details.append(reviewLabel);
                const submit=document.createElement('button');submit.type='button';submit.className='small';submit.textContent='Submit private YouTube post';submit.dataset.submitDraft='true';submit.disabled=true;details.append(submit);
                reviewed.onchange=()=>{submit.dataset.reviewed=reviewed.checked?'true':'false';submit.disabled=!reviewed.checked||!workerReady;};
                submit.onclick=async()=>{submit.disabled=true;submit.textContent='Submitting…';status.textContent='Queueing the exact reviewed private post…';try{const result=await fetch('/api/publishing/drafts/'+encodeURIComponent(draft.id)+'/submit',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({reviewed_identity:draft.reviewed_identity})});if(!result.ok)throw Error(await result.text());status.textContent='Post queued. Waiting for durable destination results.';await loadDrafts();}catch(error){status.textContent='Could not submit post: '+error.message;submit.disabled=!reviewed.checked||!workerReady;}finally{submit.textContent='Submit private YouTube post';}};
              }else if(draft.state==='draft'){const unavailable=document.createElement('p');unavailable.className='sub';unavailable.textContent='Submission is unavailable for this destination selection.';details.append(unavailable);}
              row.append(details);history.append(row);
            }
          }catch(_){if(history.textContent==='Loading drafts…')history.textContent='Could not load publishing drafts.';}}
          async function loadWorkerState(){try{const response=await fetch('/api/publishing/status');if(!response.ok)throw Error();const result=await response.json();workerReady=Boolean(result.manual_submission_enabled);workerState.textContent=workerReady?'Publisher worker online for private YouTube submission.':'Publisher worker unavailable. Drafts can be saved; submission is disabled.';}catch(_){workerReady=false;workerState.textContent='Publisher worker status is unavailable. Drafts can be saved; submission is disabled.';}for(const button of history.querySelectorAll('[data-submit-draft]'))button.disabled=!workerReady||button.dataset.reviewed!=='true';for(const button of history.querySelectorAll('[data-reconcile]'))button.disabled=!workerReady;}
          refreshHistory.onclick=async()=>{refreshHistory.disabled=true;refreshHistory.textContent='Refreshing activity…';await loadDrafts();refreshHistory.disabled=false;refreshHistory.textContent='Refresh publishing activity';};
          async function loadChoices(){try{const [videosResponse,accountsResponse]=await Promise.all([fetch('/api/publishing/ready-videos'),fetch('/api/social-accounts')]);if(!videosResponse.ok||!accountsResponse.ok)throw Error();const videos=await videosResponse.json(),accounts=(await accountsResponse.json()).filter(item=>item.status==='connected'&&!item.disabled&&item.external_account_id&&['youtube','instagram'].includes(item.platform));videoSelect.replaceChildren();if(!videos.length){videoSelect.append(Object.assign(document.createElement('option'),{textContent:'No finished videos available'}));}else{for(const video of videos)videoSelect.append(Object.assign(document.createElement('option'),{value:video.job_id,textContent:video.title+' · '+video.state.replaceAll('_',' ')}));videoSelect.disabled=false;preview.disabled=false;}destinations.replaceChildren();if(!accounts.length){destinations.textContent='No verified publishing accounts. Connect an account above first.';}for(const account of accounts){const card=document.createElement('fieldset');card.style.border='1px solid #31415f';card.style.borderRadius='9px';card.style.marginTop='10px';const legend=document.createElement('legend');const check=document.createElement('input');check.type='checkbox';check.setAttribute('aria-label','Publish to '+account.display_name);legend.append(check,document.createTextNode(' '+account.platform+' · '+account.display_name+' · '+account.external_account_id));card.append(legend);const caption=inputField(account.platform==='youtube'?'YouTube description':'Instagram caption','textarea');caption.input.maxLength=account.platform==='youtube'?5000:2200;card.append(caption.label);let title=null,tags=null;if(account.platform==='youtube'){title=inputField('YouTube title','input');title.input.maxLength=100;tags=inputField('YouTube keyword tags, comma separated','input');card.append(title.label,tags.label);}destinations.append(card);rows.set(account.id,{account,check,caption:caption.input,title:title?.input,tags:tags?.input});}save.disabled=!videos.length||!accounts.length;}catch(_){videoSelect.replaceChildren();destinations.textContent='Could not load videos or accounts. Reload to retry.';preview.disabled=true;save.disabled=true;}}
          save.onclick=async()=>{const selected=[...rows.values()].filter(row=>row.check.checked);if(!selected.length){status.textContent='Select at least one destination account.';return;}const destinationData={};for(const row of selected){const metadata={caption:row.caption.value.trim()};if(row.account.platform==='youtube'){metadata.title=row.title.value.trim();metadata.tags=row.tags.value.split(',').map(value=>value.trim()).filter(Boolean);}destinationData[row.account.id]=metadata;}save.disabled=true;save.textContent='Saving draft…';status.textContent='Validating and copying the selected video…';try{const response=await fetch('/api/publishing/drafts',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({job_id:videoSelect.value,destinations:destinationData})});if(!response.ok)throw Error(await response.text());const draft=await response.json();status.textContent='Draft '+draft.id.slice(0,8)+' saved for '+draft.destinations.length+' destination(s). No upload was started.';await loadDrafts();}catch(error){status.textContent='Could not save draft: '+error.message;}finally{save.disabled=false;save.textContent='Save publishing draft';}};
          loadChoices();loadDrafts();loadWorkerState();setInterval(loadWorkerState,20000);
        })();
        </script>"""
        reviewer_controls = """<dialog id="scriptDialog" aria-labelledby="scriptTitle"><div class="modal-head"><h2 id="scriptTitle">Review script and sources</h2><button class="close" type="button" id="scriptClose" aria-label="Close script">×</button></div><form id="scriptForm"><div class="modal-body"><p class="sub">Review the exact source packet and narration. Saving creates a new exact script revision and requires a fresh approval.</p><h3>Approved sources</h3><div id="scriptSources"></div><h3>Scenes, packaging and skill checks</h3><pre id="skillReview" style="white-space:pre-wrap;overflow-wrap:anywhere"></pre><h3>Narration</h3><div id="scriptSections"></div><label>Codex revision instruction<textarea id="codexInstruction" placeholder="e.g. Make the hook sharper, use a practical senior-engineer tone, and keep all claims accurate."></textarea></label><button id="copyCodexPrompt" class="secondary" type="button">Copy Codex prompt</button><div id="scriptNotice" class="notice"></div><div class="actions"><button class="small secondary" type="button" id="scriptCancel">Cancel</button><button class="small" type="submit">Save revision</button></div></div></form></dialog><script>
        (() => {
          let currentJob=null, currentPackage=null, scriptEditable=false;
          const dialog=document.querySelector('#scriptDialog'), sections=document.querySelector('#scriptSections'), sources=document.querySelector('#scriptSources'), scriptNotice=document.querySelector('#scriptNotice');
          document.addEventListener('click', event=>{const button=event.target.closest('button');if(button&&(button.textContent==='Approve script'||button.textContent==='Approve preview')&&!button.disabled){button.disabled=true;button.textContent='Saving approval…';}},true);
          const makeButton=(label, cls, handler)=>{const b=document.createElement('button');b.type='button';b.className='small '+(cls||'secondary');b.textContent=label;b.onclick=handler;return b;};
          async function review(jobId, editable){
            document.querySelector('#skillReview').textContent='';
            currentJob=jobId; scriptNotice.textContent='Loading script…'; sections.replaceChildren(); sources.replaceChildren(); dialog.showModal();
            const response=await fetch(`/api/jobs/${jobId}/script`);
            if(!response.ok){scriptNotice.textContent='Could not load script: '+await response.text();return;}
            scriptEditable=Boolean(editable); const reviewData=await response.json();currentPackage=reviewData.package;document.querySelector('#skillReview').textContent=JSON.stringify({channel:currentPackage.request.channel_identity,voice:currentPackage.request.channel_voice_profile,scenes:currentPackage.scene_plans,metadata:currentPackage.metadata,thumbnail:currentPackage.thumbnail_brief,skill_checks:reviewData.skill_checks},null,2); scriptNotice.textContent=scriptEditable?'Review the sources and narration, then save or approve it.':'This saved script and its source packet are read-only because this generation has already moved past script review.';
            currentPackage.request.sources.forEach(source=>{const card=document.createElement('div');card.className='event';const title=document.createElement('div');title.className='event-type';title.textContent=source.title;const link=document.createElement('a');link.href=source.url;link.target='_blank';link.rel='noopener noreferrer';link.textContent=source.url;const excerpt=document.createElement('div');excerpt.className='event-detail';excerpt.textContent=source.excerpt||'No excerpt was stored.';card.append(title,link,excerpt);if(source.content_sha256){const checksum=document.createElement('div');checksum.className='sub';checksum.textContent='SHA-256 '+source.content_sha256;card.append(checksum);}sources.append(card);});
            currentPackage.script_sections.forEach((section,index)=>{const label=document.createElement('label');label.textContent=`Section ${index+1}`;const area=document.createElement('textarea');area.className='script-narration';area.value=section.narration;area.dataset.index=index;area.disabled=!scriptEditable;area.style.minHeight='130px';label.append(area);sections.append(label);});
            document.querySelector('#scriptForm button[type="submit"]').hidden=!scriptEditable;
          }
          async function removeLocalArtifacts(job){
            if(!confirm(`Remove the local files for "${job.topic}"? The published-video audit will be kept.`))return;
            const response=await fetch(`/api/jobs/${job.id}/artifacts`,{method:'DELETE'});
            if(!response.ok){alert('Could not remove local files: '+await response.text());return;}
            document.querySelector('#notice').textContent='Local files removed. The publication record and activity history were kept.';
          }
          async function decorate(){
            let response; try{response=await fetch('/api/jobs');if(!response.ok)return;}catch(_){return;}
            const jobs=new Map((await response.json()).map(job=>[job.id,job]));
            document.querySelectorAll('.job[data-job-id]').forEach(card=>{const job=jobs.get(card.dataset.jobId);if(!job)return;const meta=card.querySelector('.muted');if(meta&&!meta.dataset.created){const created=job.created_at?new Date(job.created_at).toLocaleString():'unknown';meta.textContent+=' · Created '+created;meta.dataset.created='true';}const actions=card.querySelector('.actions');if(!actions)return;if(job.artifacts.includes('content_package')&&!card.querySelector('.script-review')){const editable=job.state==='script_approval_required';const button=makeButton(editable?'View / edit script':'View script','secondary',()=>review(job.id,editable));button.classList.add('script-review');actions.prepend(button);}if(job.artifact_cleanup_eligible&&!card.querySelector('.artifact-cleanup')){const button=makeButton('Remove local files','danger',()=>removeLocalArtifacts(job));button.classList.add('artifact-cleanup');actions.append(button);}});
          }
          document.querySelector('#scriptClose').onclick=()=>dialog.close(); document.querySelector('#scriptCancel').onclick=()=>dialog.close();
          document.querySelector('#scriptForm').onsubmit=async event=>{event.preventDefault();if(!scriptEditable||!currentJob||!currentPackage)return;const narrations=[...document.querySelectorAll('.script-narration')].map(area=>area.value.trim());if(narrations.some(value=>!value)){scriptNotice.textContent='Every script section needs narration.';return;}scriptNotice.textContent='Saving revision…';const response=await fetch(`/api/jobs/${currentJob}/script-revision`,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({narrations,actor:'local-dashboard'})});scriptNotice.textContent=response.ok?'Revision saved. Approve the updated script to continue.':'Could not save: '+await response.text();if(response.ok){currentPackage.script_sections.forEach((section,index)=>section.narration=narrations[index]);setTimeout(()=>dialog.close(),700);}};
          document.querySelector('#copyCodexPrompt').onclick=async()=>{if(!currentPackage||!currentJob){scriptNotice.textContent='Load a script first.';return;}const button=document.querySelector('#copyCodexPrompt');button.disabled=true;scriptNotice.textContent='Preparing revision prompt…';try{const response=await fetch(`/api/jobs/${currentJob}/script-revision-prompt`,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({instruction:document.querySelector('#codexInstruction').value.trim()||'Improve clarity and pacing while preserving the source-supported payoff.'})});if(!response.ok)throw new Error(await response.text());const data=await response.json();await navigator.clipboard.writeText(data.prompt);scriptNotice.textContent='Revision prompt copied with the writing skill and approved sources. Review the returned narration, save it, and approve the new revision.';}catch(error){scriptNotice.textContent='Could not copy revision prompt: '+error.message;}finally{button.disabled=false;}};
          const originalRefresh=window.setInterval; decorate(); originalRefresh(decorate,1000);
        })();
        </script>"""
        return DASHBOARD_HTML.replace("Give a title and the key points.", "Give a title, approved source notes, and optionally one cited source.").replace("<label>Notes<textarea name=\"notes\" required placeholder=\"One point per line\"></textarea></label>", "<label>Approved source notes<textarea name=\"notes\" required placeholder=\"One source-backed point per line\"></textarea></label><label>Source URL (optional)<input name=\"source_url\" type=\"url\" maxlength=\"2000\" placeholder=\"https://…\"></label><label>Source title<input name=\"source_title\" maxlength=\"500\" placeholder=\"Required with a source URL\"></label><label>Approved source excerpt<textarea name=\"source_excerpt\" maxlength=\"24000\" placeholder=\"Paste the exact supporting passage; pages are not silently scraped\"></textarea></label>").replace("join('\n')", r"join('\n')").replace("split('\n')", r"split('\n')").replace("cards.set(job.id,card);jobsRoot.append(card)", "cards.set(job.id,card);card.dataset.jobId=job.id;jobsRoot.append(card)").replace("captions_enabled:d.has('captions_enabled')};let r", "captions_enabled:d.has('captions_enabled'),voice_id:d.get('voice_id')||null,source_url:d.get('source_url')||null,source_title:d.get('source_title')||null,source_excerpt:d.get('source_excerpt')||null};let r").replace("if(j.artifacts.includes('preview'))actions.append(button('Preview','secondary',()=>openVideo(j,'preview','Preview')));if(j.artifacts.includes('final'))actions.append(button('Watch final','',()=>openVideo(j,'final','Final video')))", "if(j.artifacts.includes('final'))actions.append(button('Watch video','',()=>openVideo(j,'final','Final video')));else if(j.artifacts.includes('preview'))actions.append(button('Watch preview','secondary',()=>openVideo(j,'preview','Preview')))").replace("${j.artifacts.length} saved artifacts · ${j.event_count} activity events", "${j.artifacts.length} saved artifacts · ${j.event_count} activity events · Created ${j.created_at?new Date(j.created_at).toLocaleString():'unknown'}").replace("const meta=card.querySelector('.muted');if(meta&&!meta.dataset.created){const created=job.created_at?new Date(job.created_at).toLocaleString():'unknown';meta.textContent+=' · Created '+created;meta.dataset.created='true';}", "").replace("</body>", source_controls + operations_controls + account_controls + publishing_controls + reviewer_controls + "</body>")

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> Response:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get("/api/jobs", tags=["jobs"])
    def list_jobs() -> list[dict[str, object]]:
        deletable = {JobState.SCRIPT_APPROVAL_REQUIRED, JobState.PREVIEW_READY, JobState.FINAL_READY, JobState.PUBLICATION_APPROVAL_REQUIRED, JobState.FAILED_RETRYABLE, JobState.FAILED_VALIDATION, JobState.FAILED_EXHAUSTED, JobState.CANCELLED}
        return [
            {
                **_job_payload(job), "topic": job.request.topic,
                "artifacts": [artifact.name for artifact in runtime.artifacts.list_for_job(job.id)],
                "event_count": len(runtime.events.list_for_job(job.id)),
                "deletable": job.claim_owner is None and job.state in deletable,
                "artifact_cleanup_eligible": job.claim_owner is None and job.state is JobState.PUBLISHED,
            }
            for job in runtime.jobs.list_recent()
        ]

    @app.get("/api/content-profiles", tags=["videos"])
    def content_profiles() -> dict[str, object]:
        config = application_settings.pipeline.codex
        identities = sorted(set(config.voice_profiles) | {config.default_channel_identity})
        return {"default_identity": config.default_channel_identity, "profiles": [{"identity": name, "uses_default": name not in config.voice_profiles} for name in identities]}

    @app.get("/api/voices", tags=["voices"])
    def list_voices() -> list[dict[str, str]]:
        """Expose only configured local voices; no remote voice service is used."""
        pipeline = application_settings.pipeline
        options = [
            {"id": voice, "label": voice.replace("_", " ").title(), "provider": "kokoro"}
            for voice in pipeline.kokoro.voices
            if pipeline.kokoro.enabled and pipeline.voice_provider in {"kokoro", "hybrid"}
        ]
        if pipeline.voice_provider in {"piper", "hybrid"}:
            options.append({"id": "piper", "label": "Piper reliable fallback", "provider": "piper"})
        return options

    @app.get("/api/presets", tags=["videos"])
    def list_video_presets() -> list[dict[str, object]]:
        return [
            {
                "name": name,
                "label": ("Shorts" if preset.aspect_ratio == "9:16" else name.replace("-", " ").title()) + f" — {preset.aspect_ratio}, {preset.minimum_duration_seconds}–{preset.maximum_duration_seconds}s",
                "duration_seconds": preset.duration_seconds,
                "minimum_duration_seconds": preset.minimum_duration_seconds,
                "maximum_duration_seconds": preset.maximum_duration_seconds,
                "aspect_ratio": preset.aspect_ratio,
            }
            for name, preset in application_settings.pipeline.video_generation.presets.items()
        ]

    @app.get("/api/music", tags=["music"])
    def list_music() -> list[dict[str, object]]:
        catalog = runtime.orchestrator.music_catalog
        if catalog is None:
            return []
        return [
            track.model_dump(mode="json", exclude={"path"})
            for track in catalog.list()
        ]

    @app.post("/api/music", status_code=status.HTTP_201_CREATED, tags=["music"])
    async def upload_music(
        request: Request,
        name: str,
        filename: str,
        source_url: str,
        license_name: str,
        license_url: str,
        attribution_required: bool = False,
        attribution: str = "",
        publishing_allowed: bool = False,
    ) -> dict[str, object]:
        catalog = runtime.orchestrator.music_catalog
        if catalog is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="music catalog is not configured")
        payload = bytearray()
        async for chunk in request.stream():
            payload.extend(chunk)
            if len(payload) > catalog.max_bytes:
                raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="music upload exceeds the 50 MB limit")
        try:
            record = catalog.upload(
                name=name,
                filename=filename,
                payload=bytes(payload),
                source_url=source_url,
                license_name=license_name,
                license_url=license_url,
                attribution_required=attribution_required,
                attribution=attribution,
                publishing_allowed=publishing_allowed,
            )
        except ProviderValidationError as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
        return record.model_dump(mode="json", exclude={"path"})

    @app.get("/api/voices/{voice_id}/preview", tags=["voices"])
    def preview_voice(voice_id: str) -> FileResponse:
        """Return one persistent local sample for the selected configured voice."""
        available = {item["id"] for item in list_voices()}
        if voice_id not in available:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="voice is not available")
        path = cached_voice_preview_path(voice_id)
        with voice_preview_lock:
            if not valid_voice_preview(path):
                try:
                    runtime.orchestrator.voice.synthesize(
                        VoiceRequest(
                            text=voice_preview_text,
                            language="en",
                            voice_id=voice_id,
                            section_id="dashboard-preview",
                            phrase_id="dashboard-preview-v1",
                            output_path=str(path),
                        )
                    )
                except (ProviderValidationError, RetryableProviderError) as error:
                    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"voice preview is unavailable: {error}") from error
        if not valid_voice_preview(path):
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="voice preview was not created")
        return FileResponse(path, media_type="audio/wav", filename=f"{voice_id}-preview.wav", headers={"Cache-Control": "private, max-age=31536000, immutable"})

    @app.get("/api/jobs/{job_id}/events", tags=["jobs"])
    def get_job_events(job_id: str) -> list[dict[str, object]]:
        try:
            runtime.jobs.get(job_id)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found") from error
        return [
            {"id": event.id, "event_type": event.event_type, "details": event.details, "created_at": _as_ist(event.created_at)}
            for event in runtime.events.list_for_job(job_id)
        ]

    @app.get("/api/jobs/{job_id}", tags=["jobs"])
    def get_job(job_id: str) -> dict[str, object]:
        try:
            return _job_payload(runtime.jobs.get(job_id))
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found") from error

    @app.delete("/api/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["jobs"])
    def delete_job(job_id: str) -> None:
        """Delete a paused/completed local generation and only its own artifacts."""
        try:
            runtime.events.append(job_id, "delete_requested", actor="local-dashboard")
            artifacts = runtime.jobs.delete_completed_or_paused(job_id)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found") from error
        except ValueError as error:
            runtime.events.append(job_id, "delete_rejected", reason=str(error))
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
        root = Path(runtime.orchestrator.artifact_root).resolve()
        for artifact in artifacts:
            path = Path(artifact.path).resolve()
            if path.is_relative_to(root) and path.is_file():
                path.unlink()
        job_directory = root / job_id
        if job_directory.is_dir():
            # The directory is a fully resolved child of the configured
            # artifact root and the DB deletion above only permits this job.
            # Remove empty nested source/analysis/clip directories as well.
            shutil.rmtree(job_directory)
        runtime.events.append(job_id, "delete_completed", artifact_count=len(artifacts))

    @app.delete("/api/jobs/{job_id}/artifacts", status_code=status.HTTP_204_NO_CONTENT, tags=["artifacts"])
    def delete_published_local_artifacts(job_id: str) -> None:
        """Reclaim published media without deleting the durable publication audit."""
        try:
            job = runtime.jobs.get(job_id)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found") from error
        if job.claim_owner is not None or job.state is not JobState.PUBLISHED:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="local artifact cleanup is available only after publication is complete")
        artifacts = runtime.artifacts.remove_for_job(job_id)
        root = Path(runtime.orchestrator.artifact_root).resolve()
        for artifact in artifacts:
            path = Path(artifact.path).resolve()
            if path.is_relative_to(root) and path.is_file():
                path.unlink()
        job_directory = root / job_id
        if job_directory.is_dir():
            shutil.rmtree(job_directory)
        runtime.events.append(job_id, "local_artifacts_removed", actor="local-dashboard", artifact_count=len(artifacts))

    @app.post("/api/jobs/{job_id}/approvals/{gate}", tags=["approvals"])
    def decide(job_id: str, gate: ApprovalGate, decision: ApprovalRequest) -> dict[str, object]:
        """Record one immutable approval; the worker validates identities before use."""
        try:
            runtime.jobs.get(job_id)
            reviewed_identity = decision.reviewed_identity
            if gate is ApprovalGate.SCRIPT and reviewed_identity is None:
                package = runtime.artifacts.get(job_id, JobState.CONTENT_GENERATING, "content_package")
                if package is None:
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="script is unavailable")
                reviewed_identity = package.checksum_sha256
            if gate is ApprovalGate.PREVIEW and reviewed_identity is None:
                manifest = runtime.artifacts.get(job_id, JobState.PREVIEW_RENDERING, "preview_manifest")
                if manifest is None:
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="preview manifest is unavailable")
                import json
                reviewed_identity = str(json.loads(Path(manifest.path).read_text(encoding="utf-8"))["render_identity"])
            runtime.approvals.record(
                uuid4().hex,
                job_id,
                gate,
                decision.status,
                actor=decision.actor,
                reviewed_identity=reviewed_identity,
            )
            runtime.events.append(job_id, "approval_recorded", gate=gate.value, status=decision.status.value, actor=decision.actor, reviewed_identity=reviewed_identity)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found") from error
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
        return {"job_id": job_id, "gate": gate, "status": decision.status}

    @app.get("/api/jobs/{job_id}/script", tags=["jobs"])
    def get_script(job_id: str) -> dict[str, object]:
        """Return the current immutable content package for human review."""
        try:
            runtime.jobs.get(job_id)
            artifact = runtime.artifacts.get(job_id, JobState.CONTENT_GENERATING, "content_package")
            if artifact is None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="script is unavailable")
            package = ContentPackage.model_validate_json(Path(artifact.path).read_text(encoding="utf-8"))
            checks = None
            if package.hook_options:
                from tubeforge.providers.content.youtube_skills import evaluate
                try:
                    checks = evaluate(package)
                except ValueError as failure:
                    checks = {"status": "review_needed", "reason": str(failure)}
                except Exception as failure:
                    checks = {"status": "unavailable", "reason": str(failure)}
            return {"package": package.model_dump(mode="json"), "reviewed_identity": artifact.checksum_sha256, "skill_checks": checks}
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found") from error

    @app.post("/api/jobs/{job_id}/script-revision-prompt", tags=["jobs"])
    def script_revision_prompt(job_id: str, revision: ScriptRevisionPromptRequest) -> dict[str, object]:
        """Prepare explicit skill/context for an operator's external Codex revision."""
        try:
            job = runtime.jobs.get(job_id)
            if job.state is not JobState.SCRIPT_APPROVAL_REQUIRED or job.claim_owner is not None:
                raise HTTPException(status_code=409, detail="revision requires an unclaimed pending script review")
            package = ContentPackage.model_validate(runtime.orchestrator._required_json(job_id, JobState.CONTENT_GENERATING, "content_package"))
            from tubeforge.providers.content.prompts import build_revision_prompt, prompt_evidence
            prompt = build_revision_prompt(package, revision.instruction, max_chars=settings.pipeline.codex.max_prompt_chars)
            evidence = prompt_evidence(prompt)
            runtime.events.append(job_id, "script_revision_prompt_prepared", **evidence)
            return {"prompt": prompt, "reviewed_identity": runtime.artifacts.get(job_id, JobState.CONTENT_GENERATING, "content_package").checksum_sha256, "evidence": evidence}
        except KeyError as error:
            raise HTTPException(status_code=404, detail="job not found") from error
        except (ValueError, ProviderValidationError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.post("/api/jobs/{job_id}/script-revision", tags=["jobs"])
    def revise_script(job_id: str, revision: ScriptRevisionRequest) -> dict[str, object]:
        """Save a local narration revision and require approval of its exact bytes."""
        try:
            job = runtime.jobs.get(job_id)
            if job.state is not JobState.SCRIPT_APPROVAL_REQUIRED or job.claim_owner is not None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="script revisions are allowed only while an unclaimed script approval is pending")
            current = runtime.orchestrator._required_json(job_id, JobState.CONTENT_GENERATING, "content_package")
            package = ContentPackage.model_validate(current)
            if len(revision.narrations) != len(package.script_sections):
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="revision must include one narration for every script section")
            sections = tuple(section.model_copy(update={"narration": narration.strip()}) for section, narration in zip(package.script_sections, revision.narrations, strict=True))
            package = ContentPackage.model_validate({**package.model_dump(mode="json"), "script_sections": [section.model_dump(mode="json") for section in sections]})
            if job.request.aspect_ratio == "9:16":
                validate_video_package(package, job.request, provider_name="Revised")
            artifact = runtime.orchestrator._replace_json(
                job_id,
                JobState.CONTENT_GENERATING,
                "content_package",
                package.model_dump(mode="json"),
            )
            runtime.orchestrator._replace_json(
                job_id,
                JobState.CONTENT_GENERATING,
                "video_plan",
                video_plan_from_package(package, aspect_ratio=job.request.aspect_ratio).model_dump(mode="json"),
            )
            runtime.orchestrator._replace_json(
                job_id,
                JobState.CONTENT_GENERATING,
                "script_revision",
                {"actor": revision.actor, "content_package_checksum": artifact.checksum_sha256},
            )
            runtime.events.append(job_id, "script_revised", actor=revision.actor, content_package_checksum=artifact.checksum_sha256)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found") from error
        except ProviderValidationError as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
        return {"job_id": job_id, "reviewed_identity": artifact.checksum_sha256}

    @app.get("/api/jobs/{job_id}/artifacts/{name}", tags=["artifacts"])
    def get_artifact(job_id: str, name: str) -> FileResponse:
        """Serve a registered logical artifact name or its exact file name."""
        artifact = next(
            (
                item
                for item in runtime.artifacts.list_for_job(job_id)
                if item.name == name or Path(item.path).name == name
            ),
            None,
        )
        if artifact is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="artifact not found")
        path = Path(artifact.path)
        if not path.is_file():
            raise HTTPException(status_code=status.HTTP_410_GONE, detail="artifact is unavailable")
        media_type = "video/mp4" if path.suffix.lower() == ".mp4" else "application/json"
        return FileResponse(path, media_type=media_type)

    return app
