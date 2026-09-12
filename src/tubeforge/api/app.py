"""Application factory and operational endpoints."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from pathlib import Path
from datetime import UTC, datetime
import shutil
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from tubeforge.core.config import Settings, load_settings, validate_selected_provider
from tubeforge.core.runtime import Runtime, create_runtime
from tubeforge.domain.contracts import ContentPackage, ContentRequest, SourceReference, video_plan_from_package
from tubeforge.domain.states import ApprovalGate, ApprovalStatus, JobState
from tubeforge.scheduling.service import next_run


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
    review_mode: str | None = Field(default=None, pattern=r"^(manual|auto)$")
    mcp_servers: tuple[str, ...] | None = None
    audience: str = Field(default="general", min_length=1, max_length=200)


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
    external_account_id: str | None = Field(default=None, max_length=300)
    auth_type: str = Field(default="oauth", pattern=r"^(oauth|manual_handoff)$")
    scopes: tuple[str, ...] = Field(default=(), max_length=50)
    credential: dict[str, object] | None = None

def _video_request(value: VideoBriefRequest, settings: Settings) -> ContentRequest:
    generation = settings.pipeline.video_generation
    name = value.preset or generation.default_preset
    try:
        preset = generation.presets[name]
    except KeyError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"unknown video preset: {name}") from error
    music = value.music_track if value.music_track is not None else preset.music_track
    catalog = {track.name for track in generation.music_catalog}
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
    return ContentRequest(
        topic=value.title, angle="\n".join(notes), target_duration_seconds=value.duration_seconds or preset.duration_seconds,
        language="en", audience=value.audience, prompt_version="video-brief-v1",
        sources=(SourceReference(source_id="operator-notes", url="https://local.invalid/operator-notes", title="Operator-provided notes", excerpt="\n".join(notes)),),
        notes=notes, review_mode=value.review_mode or preset.review_mode,
        captions_enabled=preset.captions_enabled if value.captions_enabled is None else value.captions_enabled,
        music_track=music, visual_style=value.visual_style or preset.visual_style, mcp_servers=tuple(mcp),
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


def _job_payload(job: object) -> dict[str, object]:
    return {"id": job.id, "state": job.state, "failure_message": job.failure_message, "created_at": job.created_at}


DASHBOARD_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TubeForge Studio</title><style>
:root{color-scheme:dark;--bg:#080d1a;--panel:#111a2e;--muted:#8ea0bd;--line:#253451;--cyan:#5ee8ff;--good:#70e1a1;--warn:#ffd36a;--bad:#ff8492}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at top,#162544,#080d1a 45%);color:#f3f7ff;font:15px/1.5 Inter,ui-sans-serif,system-ui,sans-serif;min-height:100vh}.shell{max-width:1180px;margin:auto;padding:22px 16px 48px}.top{display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:22px}.brand{font-size:22px;font-weight:800;letter-spacing:-.5px}.brand i{font-style:normal;color:var(--cyan)}.sub{color:var(--muted);font-size:13px}.grid{display:grid;grid-template-columns:minmax(270px,350px) 1fr;gap:18px}.panel,.job{background:linear-gradient(145deg,#131f37,#0e1729);border:1px solid var(--line);border-radius:16px;box-shadow:0 12px 32px #0003}.panel{padding:18px}h1,h2,h3,p{margin:0}h2{font-size:17px}label{display:block;margin:13px 0 0;color:#cbd7eb;font-size:13px}input:not([type=checkbox]),textarea,select,button{font:inherit;width:100%;margin-top:5px;border-radius:9px;border:1px solid #31415f;padding:10px;background:#0a1222;color:#f5f8ff}textarea{min-height:106px;resize:vertical}input[type=checkbox]{accent-color:var(--cyan)}button{border:0;background:linear-gradient(100deg,#53d6f1,#8099ff);color:#07111e;font-weight:800;cursor:pointer}button.secondary{background:#223452;color:#eaf4ff;border:1px solid #3b5076}button.danger{background:#4b2634;color:#ffdce1;border:1px solid #864454}button.small{width:auto;margin:0;padding:7px 10px;font-size:12px}.checkbox{display:flex;gap:8px;align-items:center;margin-top:15px}.checkbox input{width:auto}.toolbar{display:flex;justify-content:space-between;gap:10px;align-items:center;margin-bottom:12px}.toolbar select{width:auto;margin:0;padding:7px}.jobs{display:grid;gap:11px}.job{padding:15px;overflow-wrap:anywhere}.jobhead{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}.title{font-weight:800;font-size:16px}.badge{display:inline-flex;align-items:center;border-radius:99px;padding:4px 8px;background:#223654;color:#b7ebff;font-size:11px;font-weight:800;white-space:nowrap}.badge.failed{background:#4a2631;color:#ffc0c8}.badge.ready{background:#1c4038;color:#adf4ce}.muted{color:var(--muted);font-size:13px}.failure{margin-top:10px;border-left:3px solid var(--bad);padding:8px 10px;background:#2b1720;color:#ffdce1;border-radius:6px;font-size:13px}.actions{display:flex;flex-wrap:wrap;gap:7px;margin-top:13px}.empty,.loading,.error{padding:25px;text-align:center;color:var(--muted)}.error{color:#ffc0c8}.notice{min-height:20px;margin-top:10px;color:var(--good);font-size:13px}dialog{width:min(680px,calc(100% - 24px));max-height:86vh;color:#f4f7ff;background:#101a2d;border:1px solid #3b4d70;border-radius:16px;padding:0;box-shadow:0 24px 80px #000b}dialog::backdrop{background:#020714bb}.modal-head{display:flex;justify-content:space-between;gap:8px;align-items:center;padding:15px 16px;border-bottom:1px solid var(--line)}.modal-body{padding:16px;overflow:auto;max-height:70vh}.close{width:auto;background:transparent;color:#dbe8ff;font-size:20px;padding:0 6px}.video{width:100%;border-radius:10px;background:#000}.timeline{display:grid;gap:11px}.event{border-left:2px solid #406392;padding-left:10px}.event-time{color:var(--muted);font-size:12px}.event-type{font-weight:750}.event-detail{font-size:13px;color:#cbd7eb;white-space:pre-wrap;overflow-wrap:anywhere}@media(max-width:780px){.shell{padding:14px 12px}.grid{grid-template-columns:1fr}.top{align-items:flex-start}.panel{padding:15px}.jobhead{flex-direction:column}.badge{white-space:normal}.toolbar{align-items:flex-start;flex-direction:column}.toolbar select{width:100%}}</style></head>
<body><main class="shell"><header class="top"><div><div class="brand">Tube<i>Forge</i> Studio</div><div class="sub">Local video creation, review, and activity</div></div><div class="sub" id="connection">Connecting…</div></header><div class="grid"><section class="panel"><h2>New generation</h2><p class="sub">Give a title and the key points. You stay in control of review.</p><form id="createForm"><label>Title<input name="title" maxlength="500" required placeholder="e.g. Bare minimum for software engineers"></label><label>Notes<textarea name="notes" required placeholder="One point per line"></textarea></label><label>Duration<input name="duration_seconds" type="number" value="60" min="30" max="7200" required></label><label>Review mode<select name="review_mode"><option value="manual">Manual review</option><option value="auto">Automatic render</option></select></label><label class="checkbox"><input name="captions_enabled" type="checkbox" checked> Include captions</label><button type="submit">Create video</button><div class="notice" id="notice" role="status"></div></form></section><section><div class="toolbar"><div><h2>Generations</h2><div class="sub">Updates in place every 4 seconds</div></div><select id="filter" aria-label="Filter generations"><option value="all">All generations</option><option value="active">In progress</option><option value="needs_review">Needs review</option><option value="failed">Failed</option><option value="complete">Video ready</option></select></div><div id="jobs" class="jobs"><div class="loading">Loading generations…</div></div></section></div></main><dialog id="videoDialog" aria-labelledby="videoTitle"><div class="modal-head"><h2 id="videoTitle">Video</h2><button class="close" type="button" data-close="videoDialog" aria-label="Close video">×</button></div><div class="modal-body"><video id="player" class="video" controls preload="metadata" playsinline></video></div></dialog><dialog id="activityDialog" aria-labelledby="activityTitle"><div class="modal-head"><h2 id="activityTitle">Activity</h2><button class="close" type="button" data-close="activityDialog" aria-label="Close activity">×</button></div><div class="modal-body"><div id="timeline" class="timeline"><div class="loading">Loading activity…</div></div></div></dialog><script>
const jobsRoot=document.querySelector('#jobs'),filter=document.querySelector('#filter'),notice=document.querySelector('#notice'),cards=new Map();const esc=v=>String(v??'');const ready=s=>['preview_ready','final_ready','publication_approval_required','publication_ready','published'].includes(s),failed=s=>s.startsWith('failed_');const needs=s=>['script_approval_required','preview_ready','publication_approval_required'].includes(s);function matches(j){return filter.value==='all'||filter.value==='active'&&(!ready(j.state)&&!failed(j.state)&&!needs(j.state))||filter.value==='needs_review'&&needs(j.state)||filter.value==='failed'&&failed(j.state)||filter.value==='complete'&&j.artifacts.includes('final')}function badgeClass(j){return failed(j.state)?'failed':j.artifacts.includes('final')?'ready':''}function button(label,cls,fn){let b=document.createElement('button');b.type='button';b.className='small '+(cls||'secondary');b.textContent=label;b.onclick=fn;return b}function renderCard(card,j){card.replaceChildren();card.className='job';let head=document.createElement('div');head.className='jobhead';let name=document.createElement('div');name.className='title';name.textContent=j.topic;let badge=document.createElement('span');badge.className='badge '+badgeClass(j);badge.textContent=j.state.replaceAll('_',' ');head.append(name,badge);card.append(head);if(j.failure_message){let msg=document.createElement('div');msg.className='failure';msg.textContent=j.failure_message;card.append(msg)}let meta=document.createElement('div');meta.className='muted';meta.textContent=`${j.artifacts.length} saved artifacts · ${j.event_count} activity events`;card.append(meta);let actions=document.createElement('div');actions.className='actions';if(j.artifacts.includes('preview'))actions.append(button('Preview','secondary',()=>openVideo(j,'preview','Preview')));if(j.artifacts.includes('final'))actions.append(button('Watch final','',()=>openVideo(j,'final','Final video')));for(const clip of j.artifacts.filter(name=>name.startsWith('clip_')))actions.append(button(clip.replace('_',' '),'secondary',()=>openVideo(j,clip,clip.replace('_',' '))));actions.append(button('Activity','secondary',()=>openActivity(j)));if(j.state==='script_approval_required')actions.append(button('Approve script','',()=>approve(j.id,'script')));if(j.state==='preview_ready')actions.append(button('Approve preview','',()=>approve(j.id,'preview')));if(j.deletable)actions.append(button('Delete','danger',()=>removeJob(j.id)));card.append(actions)}async function refresh(){try{let r=await fetch('/api/jobs');if(!r.ok)throw Error('Could not load generations');let data=await r.json(),visible=data.filter(matches),seen=new Set;for(const job of visible){let card=cards.get(job.id);if(!card){card=document.createElement('article');cards.set(job.id,card);jobsRoot.append(card)}renderCard(card,job);seen.add(job.id)}for(const [id,card]of cards)if(!seen.has(id)){card.remove();cards.delete(id)}if(!visible.length)jobsRoot.innerHTML='<div class="empty">No matching generations yet.</div>';else if(jobsRoot.querySelector('.empty'))jobsRoot.querySelector('.empty').remove();document.querySelector('#connection').textContent='Dashboard connected'}catch(e){if(!cards.size)jobsRoot.innerHTML='<div class="error">Unable to load generations. Retrying…</div>';document.querySelector('#connection').textContent='Reconnecting…'}}async function openVideo(job,name,label){let dialog=document.querySelector('#videoDialog'),player=document.querySelector('#player');document.querySelector('#videoTitle').textContent=`${label}: ${job.topic}`;player.pause();player.removeAttribute('src');player.load();player.src=`/api/jobs/${job.id}/artifacts/${name}`;player.autoplay=false;dialog.showModal()}async function openActivity(job){let dialog=document.querySelector('#activityDialog'),timeline=document.querySelector('#timeline');document.querySelector('#activityTitle').textContent=`Activity: ${job.topic}`;timeline.replaceChildren(Object.assign(document.createElement('div'),{className:'loading',textContent:'Loading activity…'}));dialog.showModal();let r=await fetch(`/api/jobs/${job.id}/events`);let events=await r.json();timeline.replaceChildren();if(!events.length){timeline.textContent='No activity was recorded before the dashboard timeline was enabled.';return}for(const event of events){let node=document.createElement('div');node.className='event';let type=document.createElement('div');type.className='event-type';type.textContent=event.event_type.replaceAll('_',' ');let time=document.createElement('div');time.className='event-time';time.textContent=new Date(event.created_at).toLocaleString();let detail=document.createElement('div');detail.className='event-detail';detail.textContent=Object.entries(event.details).map(([k,v])=>`${k}: ${typeof v==='string'?v:JSON.stringify(v)}`).join('\n');node.append(type,time,detail);timeline.append(node)}}async function approve(id,gate){let r=await fetch(`/api/jobs/${id}/approvals/${gate}`,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({status:'approved',actor:'local-dashboard'})});if(!r.ok)alert(await r.text());refresh()}async function removeJob(id){if(confirm('Delete this local generation and its saved files?')){let r=await fetch(`/api/jobs/${id}`,{method:'DELETE'});if(!r.ok)alert(await r.text());refresh()}}document.querySelectorAll('[data-close]').forEach(b=>b.onclick=()=>{let d=document.querySelector('#'+b.dataset.close);if(d.id==='videoDialog'){let p=document.querySelector('#player');p.pause();p.removeAttribute('src');p.load()}d.close()});document.querySelector('#createForm').onsubmit=async e=>{e.preventDefault();let d=new FormData(e.currentTarget),body={title:d.get('title'),notes:d.get('notes').split('\n').map(x=>x.trim()).filter(Boolean),duration_seconds:Number(d.get('duration_seconds')),review_mode:d.get('review_mode'),captions_enabled:d.has('captions_enabled')};let r=await fetch('/api/videos',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)});if(!r.ok){notice.textContent='Could not create video: '+await r.text();return}notice.textContent='Generation created. It will appear in the list shortly.';e.currentTarget.reset();e.currentTarget.querySelector('[name=duration_seconds]').value=60;e.currentTarget.querySelector('[name=captions_enabled]').checked=true;refresh()};filter.onchange=refresh;refresh();setInterval(refresh,4000);</script></body></html>"""


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

    attempts: dict[str, list[datetime]] = {}

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
        return """<!doctype html><title>TubeForge login</title><form id=f><h1>TubeForge</h1><input name=username autocomplete=username placeholder=Username required><input name=password type=password autocomplete=current-password placeholder=Password required><button>Log in</button><p id=e></p></form><script>f.onsubmit=async e=>{e.preventDefault();let d=new FormData(f),r=await fetch('/login',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({username:d.get('username'),password:d.get('password')})});if(r.ok)location='/';else document.querySelector('#e').textContent='Login failed.'}</script>"""

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

    @app.post("/api/social-accounts", status_code=status.HTTP_201_CREATED, tags=["social accounts"])
    def create_social_account(value: SocialAccountCreateRequest) -> dict[str, object]:
        if value.credential is not None and runtime.token_cipher is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="TUBEFORGE_ACCOUNT_ENCRYPTION_KEY is required before storing OAuth credentials")
        capabilities = {"youtube": ("upload_video",), "instagram": ("official_api_eligibility_required",), "facebook": ("official_page_api_eligibility_required",), "snapchat": ("manual_handoff_required",)}[value.platform]
        account = runtime.accounts.create(uuid4().hex, platform=value.platform, display_name=value.display_name, external_account_id=value.external_account_id, auth_type=value.auth_type, credential_ciphertext=runtime.token_cipher.encrypt(value.credential) if value.credential is not None and runtime.token_cipher else None, scopes=value.scopes, capabilities=capabilities)
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
        return [{"id": item.id, "name": item.name, "cron": item.cron, "timezone": item.timezone, "enabled": item.enabled, "next_run_at": item.next_run_at, "last_run_at": item.last_run_at} for item in runtime.schedules.list()]

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
        job = runtime.jobs.create(uuid4().hex, _video_request(brief, application_settings))
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
          const form = document.querySelector('#createForm');
          if (!form) return;
          const panel = document.createElement('fieldset');
          panel.style.marginTop = '18px'; panel.style.border = '1px solid #31415f'; panel.style.borderRadius = '9px';
          panel.innerHTML = '<legend>Clip existing video / stream</legend><label>Source URL<input id="sourceClipUrl" type="url" placeholder="https://…"></label><label>Number of clips<input id="sourceClipCount" type="number" value="1" min="1" max="12"></label><label class="checkbox"><input id="sourceClipCaptions" type="checkbox"> Burn available captions</label><button id="sourceClipCreate" type="button" class="secondary">Create clip job</button>';
          form.append(panel);
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
          panel.innerHTML='<h2>Topic queue</h2><p class=sub>Paste one topic per line. Notes can be added from the API today.</p><textarea id=bulkTopics placeholder="Topic one&#10;Topic two"></textarea><button id=bulkTopicsButton type=button>Add topics</button><div id=topicStatus class=notice></div><h2 style="margin-top:22px">Schedule</h2><label>Name<input id=scheduleName value="Twice daily"></label><label>Cron<input id=scheduleCron value="0 9,18 * * *"></label><label>Timezone<input id=scheduleTimezone value="UTC"></label><button id=scheduleButton type=button>Create schedule</button><div id=scheduleStatus class=notice></div><div id=operationsList class=muted style="margin-top:12px"></div>';
          shell.append(panel);
          async function listOps(){ const [topics,schedules]=await Promise.all([fetch('/api/topics').then(r=>r.json()),fetch('/api/schedules').then(r=>r.json())]); document.querySelector('#operationsList').textContent=`${topics.length} topics · ${schedules.length} schedules`; }
          document.querySelector('#bulkTopicsButton').onclick=async()=>{const titles=document.querySelector('#bulkTopics').value.split('\\n').map(v=>v.trim()).filter(Boolean);const r=await fetch('/api/topics/bulk',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({titles})});document.querySelector('#topicStatus').textContent=r.ok?`Added ${(await r.json()).length} topics.`:'Could not add topics: '+await r.text();if(r.ok){document.querySelector('#bulkTopics').value='';listOps();}};
          document.querySelector('#scheduleButton').onclick=async()=>{const body={name:document.querySelector('#scheduleName').value,cron:document.querySelector('#scheduleCron').value,timezone:document.querySelector('#scheduleTimezone').value};const r=await fetch('/api/schedules',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)});document.querySelector('#scheduleStatus').textContent=r.ok?'Schedule created.':'Could not create schedule: '+await r.text();if(r.ok)listOps();}; listOps();
        })();
        </script>"""
        reviewer_controls = """<dialog id="scriptDialog" aria-labelledby="scriptTitle"><div class="modal-head"><h2 id="scriptTitle">Review script</h2><button class="close" type="button" id="scriptClose" aria-label="Close script">×</button></div><form id="scriptForm"><div class="modal-body"><p class="sub">Edit narration, then save. Saving creates a new exact script revision and requires a fresh approval.</p><div id="scriptSections"></div><label>Codex revision instruction<textarea id="codexInstruction" placeholder="e.g. Make the hook sharper, use a practical senior-engineer tone, and keep all claims accurate."></textarea></label><button id="copyCodexPrompt" class="secondary" type="button">Copy Codex prompt</button><div id="scriptNotice" class="notice"></div><div class="actions"><button class="small secondary" type="button" id="scriptCancel">Cancel</button><button class="small" type="submit">Save revision</button></div></div></form></dialog><script>
        (() => {
          let currentJob=null, currentPackage=null;
          const dialog=document.querySelector('#scriptDialog'), sections=document.querySelector('#scriptSections'), scriptNotice=document.querySelector('#scriptNotice');
          document.addEventListener('click', event=>{const button=event.target.closest('button');if(button&&(button.textContent==='Approve script'||button.textContent==='Approve preview')&&!button.disabled){button.disabled=true;button.textContent='Saving approval…';}},true);
          const makeButton=(label, cls, handler)=>{const b=document.createElement('button');b.type='button';b.className='small '+(cls||'secondary');b.textContent=label;b.onclick=handler;return b;};
          async function review(jobId){
            currentJob=jobId; scriptNotice.textContent='Loading script…'; sections.replaceChildren(); dialog.showModal();
            const response=await fetch(`/api/jobs/${jobId}/script`);
            if(!response.ok){scriptNotice.textContent='Could not load script: '+await response.text();return;}
            currentPackage=(await response.json()).package; scriptNotice.textContent='Review the narration, then save or approve it.';
            currentPackage.script_sections.forEach((section,index)=>{const label=document.createElement('label');label.textContent=`Section ${index+1}`;const area=document.createElement('textarea');area.className='script-narration';area.value=section.narration;area.dataset.index=index;area.style.minHeight='130px';label.append(area);sections.append(label);});
          }
          async function decorate(){
            let response; try{response=await fetch('/api/jobs');if(!response.ok)return;}catch(_){return;}
            const jobs=new Map((await response.json()).map(job=>[job.id,job]));
            document.querySelectorAll('.job[data-job-id]').forEach(card=>{const job=jobs.get(card.dataset.jobId);if(!job)return;const meta=card.querySelector('.muted');if(meta&&!meta.dataset.created){const created=job.created_at?new Date(job.created_at).toLocaleString():'unknown';meta.textContent+=' · Created '+created;meta.dataset.created='true';}if(job.state==='script_approval_required'&&!card.querySelector('.script-review')){const actions=card.querySelector('.actions');if(actions){const button=makeButton('View / edit script','secondary',()=>review(job.id));button.classList.add('script-review');actions.prepend(button);}}});
          }
          document.querySelector('#scriptClose').onclick=()=>dialog.close(); document.querySelector('#scriptCancel').onclick=()=>dialog.close();
          document.querySelector('#scriptForm').onsubmit=async event=>{event.preventDefault();if(!currentJob||!currentPackage)return;const narrations=[...document.querySelectorAll('.script-narration')].map(area=>area.value.trim());if(narrations.some(value=>!value)){scriptNotice.textContent='Every script section needs narration.';return;}scriptNotice.textContent='Saving revision…';const response=await fetch(`/api/jobs/${currentJob}/script-revision`,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({narrations,actor:'local-dashboard'})});scriptNotice.textContent=response.ok?'Revision saved. Approve the updated script to continue.':'Could not save: '+await response.text();if(response.ok){currentPackage.script_sections.forEach((section,index)=>section.narration=narrations[index]);setTimeout(()=>dialog.close(),700);}};
          document.querySelector('#copyCodexPrompt').onclick=async()=>{if(!currentPackage){scriptNotice.textContent='Load a script first.';return;}const instruction=document.querySelector('#codexInstruction').value.trim()||'Improve clarity, pacing, and the hook while preserving factual accuracy.';const text=currentPackage.script_sections.map((section,index)=>`SECTION ${index+1}: ${section.narration}`).join('\n\n');const prompt=`Revise this TubeForge video script. ${instruction}\n\nKeep the same number and order of sections, return only the revised narration for each section, and do not add unsupported factual claims.\n\n${text}`;try{await navigator.clipboard.writeText(prompt);scriptNotice.textContent='Codex prompt copied to your clipboard.';}catch(_){scriptNotice.textContent='Clipboard access was blocked; copy the text from the sections manually.';}};
          const originalRefresh=window.setInterval; decorate(); originalRefresh(decorate,1000);
        })();
        </script>"""
        return DASHBOARD_HTML.replace("join('\n')", r"join('\n')").replace("split('\n')", r"split('\n')").replace("cards.set(job.id,card);jobsRoot.append(card)", "cards.set(job.id,card);card.dataset.jobId=job.id;jobsRoot.append(card)").replace("</body>", source_controls + operations_controls + reviewer_controls + "</body>")

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> Response:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get("/api/jobs", tags=["jobs"])
    def list_jobs() -> list[dict[str, object]]:
        deletable = {JobState.SCRIPT_APPROVAL_REQUIRED, JobState.PREVIEW_READY, JobState.FINAL_READY, JobState.FAILED_RETRYABLE, JobState.FAILED_VALIDATION, JobState.FAILED_EXHAUSTED, JobState.CANCELLED}
        return [
            {
                **_job_payload(job), "topic": job.request.topic,
                "artifacts": [artifact.name for artifact in runtime.artifacts.list_for_job(job.id)],
                "event_count": len(runtime.events.list_for_job(job.id)),
                "deletable": job.claim_owner is None and job.state in deletable,
            }
            for job in runtime.jobs.list_recent()
        ]

    @app.get("/api/jobs/{job_id}/events", tags=["jobs"])
    def get_job_events(job_id: str) -> list[dict[str, object]]:
        try:
            runtime.jobs.get(job_id)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found") from error
        return [
            {"id": event.id, "event_type": event.event_type, "details": event.details, "created_at": event.created_at}
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
        root = application_settings.pipeline.voice.artifact_root.resolve()
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
            return {"package": package.model_dump(mode="json"), "reviewed_identity": artifact.checksum_sha256}
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found") from error

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
                video_plan_from_package(package).model_dump(mode="json"),
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
