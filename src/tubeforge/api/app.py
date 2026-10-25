"""Application factory and operational endpoints."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from pathlib import Path
from datetime import UTC, datetime
import hashlib
import html
import json
import subprocess
import os
import secrets
import shlex
import shutil
import threading
import wave
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from tubeforge.core.config import Settings, load_settings, validate_selected_provider
from tubeforge.api.scene_ui import SCENE_CONTROLS
from tubeforge.api.studio_shell import STUDIO_CSS, STUDIO_SCRIPT
from tubeforge.api.generation_ui import GENERATION_CSS, GENERATION_CONTROLS
from tubeforge.api.scheduling_ui import SCHEDULING_CSS, SCHEDULING_SCRIPT
from tubeforge.core.runtime import Runtime, create_runtime
from tubeforge.domain.contracts import ContentPackage, ContentRequest, SourceReference, VoiceRequest, video_plan_from_package
from tubeforge.core.errors import ProviderValidationError, RetryableProviderError
from tubeforge.domain.states import ApprovalGate, ApprovalStatus, JobState
from tubeforge.scheduling.service import next_run, schedule_destination_options
from tubeforge.providers.content.prompts import validate_video_package
from tubeforge.pipeline.manual_publish import ManualPublishService
from tubeforge.pipeline.scene_revisions import StaleSceneRevision, create_scene_revision
from tubeforge.pipeline.diagnostics import summarize_stage_events
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


class RetryApprovedValidationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_script_identity: str = Field(pattern=r"^[a-f0-9]{64}$")


class ScriptRevisionRequest(BaseModel):
    """Operator-authored narration changes for a script awaiting review."""

    model_config = ConfigDict(extra="forbid")
    narrations: tuple[str, ...] = Field(min_length=1, max_length=500)
    actor: str = Field(default="local-dashboard", min_length=1, max_length=200)


class SceneRevisionRequest(BaseModel):
    """One scene edit forked into a new manually reviewed job."""

    model_config = ConfigDict(extra="forbid")
    scene_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    expected_content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    narration: str | None = Field(default=None, min_length=1, max_length=12_000)
    visual_type: str | None = Field(default=None, min_length=1, max_length=100)
    visual_subject: str | None = Field(default=None, min_length=1, max_length=200)
    visual_purpose: str | None = Field(default=None, min_length=1, max_length=300)
    composition: str | None = Field(default=None, min_length=1, max_length=200)
    on_screen_text: str | None = Field(default=None, max_length=500)
    visual_elements: tuple[str, ...] | None = Field(default=None, max_length=4)
    actor: str = Field(default="local-dashboard", min_length=1, max_length=200)

class ScriptRevisionPromptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instruction: str = Field(min_length=1, max_length=4000)


_RETRY_AS_NEW_STATES = frozenset({JobState.FAILED_VALIDATION, JobState.FAILED_EXHAUSTED, JobState.FAILED_RETRYABLE, JobState.CANCELLED})


class RetryJobRequest(BaseModel):
    """Optional edited ContentRequest JSON; omitted means retry with the saved request."""
    model_config = ConfigDict(extra="forbid")
    request: dict[str, object] | None = None


class VideoBriefRequest(BaseModel):
    """User-facing shorthand expanded into the durable provider-neutral request."""
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=500)
    notes: tuple[str, ...] = Field(min_length=1, max_length=30)
    angle: str | None = Field(default=None, max_length=4_000)
    sources: tuple[SourceReference, ...] | None = Field(default=None, min_length=1, max_length=8)
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
    destination_account_ids: tuple[str, ...] = Field(default=(), max_length=20)
    description: str | None = Field(default=None, min_length=1, max_length=5000)
    source_title: str | None = Field(default=None, max_length=500)
    source_excerpt: str | None = Field(default=None, max_length=24_000)
    show_source_credit: bool = False
    show_mascot: bool = False
    channel_watermark: str | None = Field(default=None, max_length=40)
    script_owner: str | None = Field(default=None, pattern=r"^(codex|claude)$")
    # Studio's single "script writer" choice. Omitted = the configured default (Sonnet, medium effort).
    script_model: str | None = Field(default=None, pattern=r"^(sonnet-medium|opus|gpt-sol)$")


# id -> (script owner, Claude model choice). Sonnet is the default for testing.
SCRIPT_MODELS = {"sonnet-medium": ("claude", "sonnet-medium"), "opus": ("claude", "opus"), "gpt-sol": ("codex", None)}
DEFAULT_SCRIPT_MODEL = "sonnet-medium"


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
    account_id: str | None = Field(default=None, min_length=1, max_length=64)


class TopicBulkCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    titles: tuple[str, ...] = Field(min_length=1, max_length=200)
    priority: int = Field(default=0, ge=-1000, le=1000)
    account_id: str | None = Field(default=None, min_length=1, max_length=64)


class ScheduleCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    cron: str = Field(min_length=1, max_length=120)
    timezone: str = Field(default="UTC", min_length=1, max_length=100)
    options: dict[str, object] = Field(default_factory=dict)
    account_id: str | None = Field(default=None, min_length=1, max_length=64)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=1024)


class SocialAccountCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    platform: str = Field(pattern=r"^(youtube|instagram|facebook|snapchat|x)$")
    display_name: str = Field(min_length=1, max_length=200)
    category: str = Field(default="general", min_length=1, max_length=100)
    default_description: str = Field(default="", max_length=5000)
    auth_type: str = Field(default="oauth", pattern=r"^(oauth|manual_handoff)$")


class SocialAccountProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=100)
    default_description: str = Field(default="", max_length=5000)


class OAuthStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: str | None = Field(default=None, max_length=64)


class OAuthConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: str = Field(min_length=1, max_length=200)


class ThumbnailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str | None = Field(default=None, max_length=48)
    frame_time: float | None = Field(default=None, ge=0, le=7200)
    logo: str | None = Field(default=None, max_length=40)


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

def _watermark(value: str | None) -> str | None:
    """Optional small channel name: trimmed, single line, no markup; empty means none."""
    text = " ".join((value or "").split())
    if not text:
        return None
    if len(text) > 40 or any(ord(c) < 32 or c in "<>" for c in text):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="channel name must be at most 40 characters without angle brackets")
    return text


def _with_page_text(source: SourceReference) -> SourceReference:
    """Fill a blank title/excerpt from the source page itself (HTTPS, public hosts, no redirects)."""
    from urllib.parse import urlparse
    from tubeforge.core.errors import ProviderValidationError, RetryableProviderError
    from tubeforge.pipeline.sources import SourceIngestor
    host = (urlparse(str(source.url)).hostname or "").casefold()
    title = (source.title or "").strip() or host
    excerpt = (source.excerpt or "").strip()
    if not excerpt and host and host != "local.invalid":
        try:
            excerpt = SourceIngestor(frozenset({host})).ingest(source.model_copy(update={"title": title})).excerpt
        except (ProviderValidationError, RetryableProviderError, ValueError) as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"could not read the source page {source.url} ({error}); paste the passage into its excerpt field instead") from error
    return source.model_copy(update={"title": title, "excerpt": excerpt})


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
    if value.sources is not None:
        if value.source_url or value.source_title or value.source_excerpt:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="use either the multi-source packet or the single source fields, not both")
        source_ids = [source.source_id for source in value.sources]
        if len(set(source_ids)) != len(source_ids):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="approved source packet must have unique source IDs")
        sources = [_with_page_text(source) for source in value.sources]
        if any(not source.title.strip() or not source.excerpt or not source.excerpt.strip() for source in sources):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="each approved source needs a title and exact excerpt")
    else:
        sources = [SourceReference(source_id="operator-notes", url="https://local.invalid/operator-notes", title=("Brief notes (unverified)" if settings.pipeline.sources.research_enabled else "Operator-approved source notes"), excerpt="\n".join(notes))]
        if value.source_url:
            from urllib.parse import urlparse
            try:
                sources.append(_with_page_text(SourceReference(source_id="approved-source-1", url=value.source_url, title=(value.source_title or "").strip() or (urlparse(value.source_url).hostname or value.source_url), excerpt=(value.source_excerpt or "").strip())))
            except ValueError as error:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="source URL must be an absolute HTTP(S) URL") from error
        elif value.source_title or value.source_excerpt:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="source title and excerpt require a source URL")
    from tubeforge.providers.content.youtube_skills import voice_for
    choice = value.script_model or ("gpt-sol" if value.script_owner == "codex" else DEFAULT_SCRIPT_MODEL)
    if choice != "gpt-sol" and not settings.pipeline.claude.enabled:
        if value.script_model is None and value.script_owner is None:
            choice = "gpt-sol"  # Claude not configured: fall back to the Codex default
        else:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Claude script writers are not enabled in this TubeForge configuration")
    owner, claude_model = SCRIPT_MODELS[choice]
    channel, profile = voice_for(settings.pipeline.codex, value.channel_identity)
    return ContentRequest(
        script_owner=owner, script_model=claude_model,
        show_source_credit=value.show_source_credit, show_mascot=value.show_mascot, channel_watermark=_watermark(value.channel_watermark),
        channel_identity=channel, channel_voice_profile=profile,
        topic=value.title, angle=value.angle.strip() if value.angle and value.angle.strip() else "\n".join(notes), target_duration_seconds=duration,
        language="en", audience=value.audience, prompt_version=preset.prompt_version or settings.pipeline.codex.prompt_template_version,
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
        "attempt_count": job.attempt_count,
        "next_retry_at": _as_ist(job.next_retry_at) if job.next_retry_at is not None else None,
        "created_at": _as_ist(job.created_at),
    }


def _artifact_file_matches(artifact: object) -> bool:
    try:
        digest = hashlib.sha256()
        with Path(artifact.path).open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest() == artifact.checksum_sha256
    except OSError:
        return False


def _can_retry_approved_asset_validation(runtime: Runtime, job: object) -> tuple[bool, str | None]:
    refresh = job.state is JobState.PREVIEW_READY
    retry = job.state is JobState.FAILED_VALIDATION and job.resume_state in {JobState.ASSET_ACQUISITION, JobState.PREVIEW_RENDERING}
    if not (refresh or retry) or job.claim_owner is not None:
        return False, None
    if refresh and runtime.approvals.approved(job.id, ApprovalGate.PREVIEW) is not None:
        return False, None
    if not refresh and job.resume_state is JobState.PREVIEW_RENDERING and runtime.artifacts.get(job.id, JobState.PREVIEW_RENDERING, "preview") is not None:
        return False, None
    package = runtime.artifacts.get(job.id, JobState.CONTENT_GENERATING, "content_package")
    packet = runtime.artifacts.get(job.id, JobState.CONTENT_GENERATING, "source_packet")
    if package is None or packet is None or not _artifact_file_matches(package) or not _artifact_file_matches(packet):
        return False, None
    if runtime.approvals.approved(job.id, ApprovalGate.SCRIPT, reviewed_identity=package.checksum_sha256) is None:
        return False, None
    try:
        from tubeforge.pipeline.scene_contracts import compile_scene_contract

        compile_scene_contract(
            Path(package.path).read_bytes(),
            Path(packet.path).read_bytes(),
            accepted_script_identity=package.checksum_sha256,
        )
    except (OSError, ValueError, ValidationError):
        return False, None
    return True, package.checksum_sha256


DASHBOARD_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TubeForge Studio</title><style>
:root{color-scheme:dark;--bg:#080d1a;--panel:#111a2e;--muted:#8ea0bd;--line:#253451;--cyan:#5ee8ff;--good:#70e1a1;--warn:#ffd36a;--bad:#ff8492}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at top,#162544,#080d1a 45%);color:#f3f7ff;font:15px/1.5 Inter,ui-sans-serif,system-ui,sans-serif;min-height:100vh}.shell{max-width:1180px;margin:auto;padding:22px 16px 48px}.top{display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:22px}.brand{font-size:22px;font-weight:800;letter-spacing:-.5px}.brand i{font-style:normal;color:var(--cyan)}.sub{color:var(--muted);font-size:13px}.grid{display:grid;grid-template-columns:minmax(270px,350px) 1fr;gap:18px}.panel,.job{background:linear-gradient(145deg,#131f37,#0e1729);border:1px solid var(--line);border-radius:16px;box-shadow:0 12px 32px #0003}.panel{padding:18px}h1,h2,h3,p{margin:0}h2{font-size:17px}label{display:block;margin:13px 0 0;color:#cbd7eb;font-size:13px}input:not([type=checkbox]),textarea,select,button{font:inherit;width:100%;margin-top:5px;border-radius:9px;border:1px solid #31415f;padding:10px;background:#0a1222;color:#f5f8ff}textarea{min-height:106px;resize:vertical}input[type=checkbox]{accent-color:var(--cyan)}button{border:0;background:linear-gradient(100deg,#53d6f1,#8099ff);color:#07111e;font-weight:800;cursor:pointer}button.secondary{background:#223452;color:#eaf4ff;border:1px solid #3b5076}button.danger{background:#4b2634;color:#ffdce1;border:1px solid #864454}button.small{width:auto;margin:0;padding:7px 10px;font-size:12px}.checkbox{display:flex;gap:8px;align-items:center;margin-top:15px}.checkbox input{width:auto}.toolbar{display:flex;justify-content:space-between;gap:10px;align-items:center;margin-bottom:12px}.toolbar select{width:auto;margin:0;padding:7px}.jobs{display:grid;gap:11px}.job{padding:15px;overflow-wrap:anywhere}.jobhead{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}.title{font-weight:800;font-size:16px}.badge{display:inline-flex;align-items:center;border-radius:99px;padding:4px 8px;background:#223654;color:#b7ebff;font-size:11px;font-weight:800;white-space:nowrap}.badge.failed{background:#4a2631;color:#ffc0c8}.badge.ready{background:#1c4038;color:#adf4ce}.badge.pending{background:#4a3c1d;color:#ffe5a1}.muted{color:var(--muted);font-size:13px}.failure{margin-top:10px;border-left:3px solid var(--bad);padding:8px 10px;background:#2b1720;color:#ffdce1;border-radius:6px;font-size:13px}.failure.pending{border-color:var(--warn);background:#2b2617;color:#ffecad}.actions{display:flex;flex-wrap:wrap;gap:7px;margin-top:13px}.empty,.loading,.error{padding:25px;text-align:center;color:var(--muted)}.error{color:#ffc0c8}.notice{min-height:20px;margin-top:10px;color:var(--good);font-size:13px}dialog{width:min(680px,calc(100% - 24px));max-height:86vh;color:#f4f7ff;background:#101a2d;border:1px solid #3b4d70;border-radius:16px;padding:0;box-shadow:0 24px 80px #000b}dialog::backdrop{background:#020714bb}.modal-head{display:flex;justify-content:space-between;gap:8px;align-items:center;padding:15px 16px;border-bottom:1px solid var(--line)}.modal-body{padding:16px;overflow:auto;max-height:70vh}.close{width:auto;background:transparent;color:#dbe8ff;font-size:20px;padding:0 6px}.video{width:100%;border-radius:10px;background:#000}.timeline{display:grid;gap:11px}.event{border-left:2px solid #406392;padding-left:10px}.event-time{color:var(--muted);font-size:12px}.event-type{font-weight:750}.event-detail{font-size:13px;color:#cbd7eb;white-space:pre-wrap;overflow-wrap:anywhere}@media(max-width:780px){.shell{padding:14px 12px}.grid{grid-template-columns:1fr}.top{align-items:flex-start}.panel{padding:15px}.jobhead{flex-direction:column}.badge{white-space:normal}.toolbar{align-items:flex-start;flex-direction:column}.toolbar select{width:100%}}</style></head>
<body><main class="shell"><header class="top"><div><div class="brand">Tube<i>Forge</i> Studio</div><div class="sub">Local video creation, review, and activity</div></div><div class="sub" id="connection">Connecting…</div></header><div class="grid"><section class="panel"><h2>New generation</h2><p class="sub">Give a title and the key points. You stay in control of review.</p><form id="createForm"><label>Title<input name="title" maxlength="500" required placeholder="e.g. Bare minimum for software engineers"></label><label>Notes<textarea name="notes" required placeholder="One point per line"></textarea></label><label>Target duration (seconds)<input name="duration_seconds" type="number" value="60" min="30" max="7200" required></label><label>Review mode<select name="review_mode"><option value="manual">Manual review</option><option value="auto">Automatic render</option></select></label><label class="checkbox"><input name="captions_enabled" type="checkbox" checked> Include captions</label><button type="submit">Create video</button><div class="notice" id="notice" role="status"></div></form></section><section><div class="toolbar"><div><h2>Generations</h2><div class="sub">Updates in place every 30 seconds</div></div><select id="filter" aria-label="Filter generations"><option value="all">All generations</option><option value="active">In progress</option><option value="needs_review">Needs review</option><option value="failed">Failed</option><option value="complete">Video ready</option></select><button type="button" class="secondary" id="refreshJobs">Refresh</button></div><div id="jobs" class="jobs"><div class="loading">Loading generations…</div></div></section></div></main><dialog id="videoDialog" aria-labelledby="videoTitle"><div class="modal-head"><h2 id="videoTitle">Video</h2><button class="close" type="button" data-close="videoDialog" aria-label="Close video">×</button></div><div class="modal-body"><video id="player" class="video" controls preload="metadata" playsinline></video></div></dialog><dialog id="activityDialog" aria-labelledby="activityTitle"><div class="modal-head"><h2 id="activityTitle">Activity</h2><button class="close" type="button" data-close="activityDialog" aria-label="Close activity">×</button></div><div class="modal-body"><div id="timeline" class="timeline"><div class="loading">Loading activity…</div></div></div></dialog><script>
const jobsRoot=document.querySelector('#jobs'),filter=document.querySelector('#filter'),notice=document.querySelector('#notice'),cards=new Map();const esc=v=>String(v??'');const ready=s=>['preview_ready','final_ready','publication_approval_required','publication_ready','published'].includes(s),failed=s=>['failed_validation','failed_exhausted'].includes(s);const needs=s=>['script_approval_required','preview_ready','publication_approval_required'].includes(s);function matches(j){return filter.value==='all'||filter.value==='active'&&(!ready(j.state)&&!failed(j.state)&&!needs(j.state))||filter.value==='needs_review'&&needs(j.state)||filter.value==='failed'&&failed(j.state)||filter.value==='complete'&&j.artifacts.includes('final')}function badgeClass(j){return j.state==='failed_retryable'?'pending':failed(j.state)?'failed':j.artifacts.includes('final')?'ready':''}function button(label,cls,fn){let b=document.createElement('button');b.type='button';b.className='small '+(cls||'secondary');b.textContent=label;b.onclick=fn;return b}function renderCard(card,j){card.replaceChildren();card.className='job';let head=document.createElement('div');head.className='jobhead';let name=document.createElement('div');name.className='title';name.textContent=j.topic;let badge=document.createElement('span');badge.className='badge '+badgeClass(j);badge.textContent=j.blocked_reason==='insufficient_sources'?'Blocked: insufficient sources':j.state==='failed_retryable'?(j.next_retry_at?'Retry scheduled':'Retry pending'):j.state.replaceAll('_',' ');head.append(name,badge);card.append(head);if(j.failure_message){let msg=document.createElement('div');msg.className='failure'+(j.state==='failed_retryable'?' pending':'');msg.textContent=j.failure_message;card.append(msg)}let meta=document.createElement('div');meta.className='muted';meta.textContent=`${j.artifacts.length} saved artifacts · ${j.event_count} activity events`;if(j.state==='failed_retryable'&&j.next_retry_at)meta.textContent+=` · Next attempt ${new Date(j.next_retry_at).toLocaleString()} (attempt ${j.attempt_count})`;card.append(meta);let actions=document.createElement('div');actions.className='actions';if(j.artifacts.includes('preview'))actions.append(button('Preview','secondary',()=>openVideo(j,'preview','Preview')));if(j.artifacts.includes('final'))actions.append(button('Watch final','',()=>openVideo(j,'final','Final video')));for(const clip of j.artifacts.filter(name=>name.startsWith('clip_')))actions.append(button(clip.replace('_',' '),'secondary',()=>openVideo(j,clip,clip.replace('_',' '))));actions.append(button('Activity','secondary',()=>openActivity(j)));if(j.state==='script_approval_required')actions.append(button('Approve script','',()=>approve(j.id,'script')));if(j.state==='preview_ready')actions.append(button('Approve preview','',()=>approve(j.id,'preview')));if(j.can_retry_validation)actions.append(button('Retry approved media stages','secondary',()=>retryValidation(j)));if(j.deletable)actions.append(button('Delete','danger',()=>removeJob(j.id)));card.append(actions)}async function refresh(){try{let r=await fetch('/api/jobs');if(!r.ok)throw Error('Could not load generations');let data=await r.json(),visible=data.filter(matches),seen=new Set;for(const job of visible){let card=cards.get(job.id);if(!card){card=document.createElement('article');cards.set(job.id,card);jobsRoot.append(card)}renderCard(card,job);seen.add(job.id)}for(const [id,card]of cards)if(!seen.has(id)){card.remove();cards.delete(id)}if(!visible.length)jobsRoot.innerHTML='<div class="empty">No matching generations yet.</div>';else if(jobsRoot.querySelector('.empty'))jobsRoot.querySelector('.empty').remove();document.querySelector('#connection').textContent='Dashboard connected'}catch(e){if(!cards.size)jobsRoot.innerHTML='<div class="error">Unable to load generations. Retrying…</div>';document.querySelector('#connection').textContent='Reconnecting…'}}async function openVideo(job,name,label){let dialog=document.querySelector('#videoDialog'),player=document.querySelector('#player');document.querySelector('#videoTitle').textContent=`${label}: ${job.topic}`;player.pause();player.removeAttribute('src');player.load();player.src=`/api/jobs/${job.id}/artifacts/${name}`;player.autoplay=false;dialog.showModal()}async function openActivity(job){let dialog=document.querySelector('#activityDialog'),timeline=document.querySelector('#timeline');document.querySelector('#activityTitle').textContent=`Activity: ${job.topic}`;timeline.replaceChildren(Object.assign(document.createElement('div'),{className:'loading',textContent:'Loading activity…'}));dialog.showModal();let r=await fetch(`/api/jobs/${job.id}/events`);let events=await r.json();timeline.replaceChildren();let diagnostic=document.createElement('div');diagnostic.className='event';diagnostic.textContent='Diagnostics loading…';timeline.append(diagnostic);try{let response=await fetch(`/api/jobs/${job.id}/diagnostics`);if(!response.ok)throw Error('unavailable');let report=await response.json();const dur=ms=>ms<1000?ms+' ms':ms<60000?(ms/1000).toFixed(1)+' s':Math.floor(ms/60000)+' min '+Math.round(ms%60000/1000)+' s',mem=b=>b==null?'n/a':b>=1073741824?(b/1073741824).toFixed(2)+' GiB':(b/1048576).toFixed(0)+' MiB';let stages=Object.entries(report.stage_metrics).filter(([,value])=>value.elapsed_ms>=1000||value.executions>1).map(([stage,value])=>`${stage.replaceAll('_',' ')} — ${dur(value.elapsed_ms)}${value.executions>1?' ('+value.executions+' runs)':''}, memory peak ${mem(value.cgroup_peak_bytes)}`).join(' · ');diagnostic.textContent=(stages||'No measured stages yet.')+(report.failure_reason?' · Failure: '+report.failure_reason:'');let note=document.createElement('div');note.className='sub';note.textContent=report.memory_note;diagnostic.append(note);let download=document.createElement('a');download.href=`/api/jobs/${job.id}/diagnostics.jsonl`;download.textContent='Download diagnostics JSONL';diagnostic.append(download)}catch(_){diagnostic.textContent='Diagnostics unavailable; activity remains visible.'}if(!events.length){timeline.append(Object.assign(document.createElement('div'),{textContent:'No activity was recorded before the dashboard timeline was enabled.'}));return}for(const event of events){let node=document.createElement('div');node.className='event';let type=document.createElement('div');type.className='event-type';type.textContent=event.event_type.replaceAll('_',' ');let time=document.createElement('div');time.className='event-time';time.textContent=new Date(event.created_at).toLocaleString();let detail=document.createElement('div');detail.className='event-detail';detail.textContent=Object.entries(event.details).map(([k,v])=>`${k}: ${typeof v==='string'?v:JSON.stringify(v)}`).join('\n');node.append(type,time,detail);timeline.append(node)}}async function retryValidation(job){if(!window.confirm('Retry local media stages from the saved, approved script and source packet? This resumes local media work; it will not regenerate narration.'))return;notice.textContent='Requesting checkpoint recovery…';const response=await fetch(`/api/jobs/${job.id}/retry-validation`,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({expected_script_identity:job.retry_script_identity})});if(!response.ok){notice.textContent='Recovery was not queued: '+await response.text();await refresh();return}notice.textContent='Approved checkpoint queued at asset acquisition.';await refresh()}async function approve(id,gate){let r=await fetch(`/api/jobs/${id}/approvals/${gate}`,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({status:'approved',actor:'local-dashboard'})});if(!r.ok)alert(await r.text());refresh()}async function removeJob(id){if(confirm('Delete this local generation and its saved files?')){let r=await fetch(`/api/jobs/${id}`,{method:'DELETE'});if(!r.ok)alert(await r.text());refresh()}}document.querySelectorAll('[data-close]').forEach(b=>b.onclick=()=>{let d=document.querySelector('#'+b.dataset.close);if(d.id==='videoDialog'){let p=document.querySelector('#player');p.pause();p.removeAttribute('src');p.load()}d.close()});document.querySelector('#createForm').onsubmit=async e=>{e.preventDefault();let d=new FormData(e.currentTarget),body={title:d.get('title'),notes:d.get('notes').split('\n').map(x=>x.trim()).filter(Boolean),duration_seconds:Number(d.get('duration_seconds')),review_mode:d.get('review_mode'),captions_enabled:d.has('captions_enabled')};let r=await fetch('/api/videos',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)});if(!r.ok){notice.textContent='Could not create video: '+await r.text();return}notice.textContent='Generation created. It will appear in the list shortly.';e.currentTarget.reset();e.currentTarget.querySelector('[name=duration_seconds]').value=60;e.currentTarget.querySelector('[name=captions_enabled]').checked=true;refresh()};filter.onchange=refresh;document.querySelector('#refreshJobs').onclick=async ev=>{const b=ev.currentTarget;b.disabled=true;b.textContent='Refreshing…';try{await refresh()}finally{b.disabled=false;b.textContent='Refresh'}};refresh();setInterval(refresh,30000);</script></body></html>"""


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
        try:
            topic = runtime.topics.create(uuid4().hex, title=value.title, notes=value.notes, priority=value.priority, options=value.options, account_id=value.account_id)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return {"id": topic.id, "title": topic.title, "status": topic.status, "priority": topic.priority, "account_id": topic.account_id}

    @app.post("/api/topics/bulk", status_code=status.HTTP_201_CREATED, tags=["topics"])
    def create_topics_bulk(value: TopicBulkCreateRequest) -> list[dict[str, object]]:
        try:
            topics = runtime.topics.create_many(tuple((uuid4().hex, title) for title in value.titles), priority=value.priority, account_id=value.account_id)
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
        return [{"id": item.id, "title": item.title, "status": item.status, "priority": item.priority, "account_id": item.account_id} for item in topics]

    @app.get("/api/social-accounts", tags=["social accounts"])
    def list_social_accounts() -> list[dict[str, object]]:
        return [{"id": item.id, "platform": item.platform, "display_name": item.display_name, "category": item.category, "default_description": item.default_description, "external_account_id": item.external_account_id, "auth_type": item.auth_type, "scopes": item.scopes, "status": item.status, "capabilities": item.capabilities, "is_default": item.is_default, "disabled": item.disabled, "token_expires_at": item.token_expires_at, "last_validated_at": item.last_validated_at} for item in runtime.accounts.list()]

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
                ready.append({"job_id": job.id, "title": job.request.topic, "state": job.state.value, "video_description": runtime.jobs.video_description(job.id), "destination_intents": runtime.jobs.destination_intents(job.id)})
        return ready

    @app.get("/api/jobs/{job_id}/destination-intents", tags=["jobs"])
    def job_destination_intents(job_id: str) -> list[dict[str, str]]:
        try:
            runtime.jobs.get(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="job not found") from error
        return runtime.jobs.destination_intents(job_id)

    # -- upload-ready title / description / thumbnail for the Publishing page ---------------------------
    def _publishing_context(job_id: str):
        from tubeforge.pipeline.publishing_assets import READY_STATES
        try:
            job = runtime.jobs.get(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="job not found") from error
        final = runtime.artifacts.get(job_id, JobState.FINAL_RENDERING, "final")
        content = runtime.artifacts.get(job_id, JobState.CONTENT_GENERATING, "content_package")
        if job.state not in READY_STATES or final is None or content is None:
            raise HTTPException(status_code=409, detail="the final video is not ready")
        package = ContentPackage.model_validate_json(Path(content.path).read_text(encoding="utf-8"))
        folder = Path(final.path).parent / "publishing"
        return package, Path(final.path), folder

    def _thumbnail_state(job_id: str, *, text: str | None = None, frame_time: float | None = None, logo: str | None | bool = False, force: bool = False) -> dict[str, object]:
        """Current thumbnail for the job; (re)composed from the final video when asked or missing."""
        from tubeforge.pipeline import thumbnail as thumbs
        from tubeforge.pipeline.publication_suggest import suggest
        package, video, folder = _publishing_context(job_id)
        meta_path = folder / "thumbnail.json"
        meta: dict[str, object] = json.loads(meta_path.read_text()) if meta_path.is_file() else {}
        ffmpeg = application_settings.pipeline.voice.ffmpeg_executable
        duration = float(meta["duration"]) if meta.get("duration") else float(runtime.orchestrator.ffprobe.inspect(video)["duration_seconds"])
        wants_portrait = package.request.aspect_ratio == "9:16"
        stale_shape = bool(meta) and not meta.get("custom") and bool(meta.get("portrait", False)) != wants_portrait
        if force or stale_shape or not meta or not (folder / str(meta.get("file", "-"))).is_file():
            options = suggest(package)["thumbnail_text_options"]
            scenes = package.reference_short.scenes if package.reference_short is not None else ()
            default_logo = next((scene.logo for scene in scenes if scene.logo), None)
            new = {"text": text if text is not None else str(meta.get("text") or (options[0] if options else package.request.topic)),
                   "frame_time": frame_time if frame_time is not None else float(meta.get("frame_time") or thumbs.best_time(ffmpeg, video, duration)),
                   "logo": (logo if logo is not False else meta.get("logo", default_logo)), "custom": False}
            frame = thumbs.grab_frame(ffmpeg, video, float(new["frame_time"]))
            if package.request.aspect_ratio == "9:16":
                shorts = application_settings.pipeline.shorts_thumbnail
                image, _ = thumbs.compose_portrait(frame, str(new["text"]), new["logo"], config=shorts, brand=Path(shorts.brand_logo_path) if shorts.brand_logo_path else thumbs.BRAND_LOGO)
            else:
                image = thumbs.compose(frame, str(new["text"]), new["logo"])
            temporary = folder / "thumbnail.tmp.jpg"
            digest = thumbs.save(image, temporary)
            target = folder / f"thumbnail-{digest[:12]}.jpg"
            temporary.replace(target)
            meta = {**new, "file": target.name, "sha256": digest, "portrait": wants_portrait, "duration": duration}
            meta_path.write_text(json.dumps(meta, indent=1))
            for stale in folder.glob("thumbnail-*.jpg"):
                if stale != target:
                    stale.unlink(missing_ok=True)
        portrait = package.request.aspect_ratio == "9:16"
        return {"url": f"/api/publishing/jobs/{job_id}/thumbnail.jpg?v={str(meta['sha256'])[:12]}", "sha256": meta["sha256"], "text": meta.get("text"), "portrait": portrait,
                "frame_time": meta.get("frame_time"), "logo": meta.get("logo"), "custom": bool(meta.get("custom")),
                "frame_times": thumbs.candidate_times(duration), "logos": list(thumbs.LOGO_NAMES)}

    @app.get("/api/publishing/jobs/{job_id}/suggestion", tags=["publishing"])
    def publishing_suggestion(job_id: str) -> dict[str, object]:
        from tubeforge.pipeline.publication_suggest import suggest
        package, _, _ = _publishing_context(job_id)
        try:
            thumbnail = _thumbnail_state(job_id)
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            raise HTTPException(status_code=500, detail="thumbnail could not be composed from the video") from error
        return {**suggest(package), "thumbnail": thumbnail}

    @app.post("/api/publishing/jobs/{job_id}/thumbnail", tags=["publishing"])
    def regenerate_thumbnail(job_id: str, value: ThumbnailRequest) -> dict[str, object]:
        try:
            return _thumbnail_state(job_id, text=value.text, frame_time=value.frame_time, logo=value.logo if "logo" in value.model_fields_set else False, force=True)
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            raise HTTPException(status_code=422, detail="thumbnail could not be composed from the video") from error

    @app.post("/api/publishing/jobs/{job_id}/thumbnail/upload", tags=["publishing"])
    async def upload_thumbnail(job_id: str, request: Request) -> dict[str, object]:
        from io import BytesIO
        from PIL import Image
        from tubeforge.pipeline import thumbnail as thumbs
        _, _, folder = _publishing_context(job_id)
        data = await request.body()
        if not data or len(data) > 10_000_000:
            raise HTTPException(status_code=413, detail="thumbnail must be an image up to 10 MB")
        try:
            image = Image.open(BytesIO(data)).convert("RGB")
        except Exception as error:
            raise HTTPException(status_code=422, detail="thumbnail must be a PNG or JPEG image") from error
        if image.width < 640 or image.height < 360:
            raise HTTPException(status_code=422, detail="thumbnail must be at least 640×360")
        from PIL import ImageOps
        shorts = application_settings.pipeline.shorts_thumbnail
        package, _, _ = _publishing_context(job_id)
        image = ImageOps.fit(image, (shorts.width, shorts.height) if package.request.aspect_ratio == "9:16" else thumbs.SIZE, Image.Resampling.LANCZOS)
        temporary = folder / "thumbnail.tmp.jpg"
        digest = thumbs.save(image, temporary)
        target = folder / f"thumbnail-{digest[:12]}.jpg"
        temporary.replace(target)
        for stale in folder.glob("thumbnail-*.jpg"):
            if stale != target:
                stale.unlink(missing_ok=True)
        (folder / "thumbnail.json").write_text(json.dumps({"file": target.name, "sha256": digest, "text": None, "frame_time": None, "logo": None, "custom": True}, indent=1))
        return _thumbnail_state(job_id)

    @app.get("/api/publishing/jobs/{job_id}/thumbnail.jpg", tags=["publishing"])
    def current_thumbnail(job_id: str, guides: int = 0) -> Response:
        package, _, folder = _publishing_context(job_id)
        meta_path = folder / "thumbnail.json"
        if not meta_path.is_file():
            raise HTTPException(status_code=404, detail="no thumbnail yet")
        path = folder / json.loads(meta_path.read_text())["file"]
        if not path.is_file():
            raise HTTPException(status_code=404, detail="thumbnail file is missing")
        if guides and package.request.aspect_ratio == "9:16":
            from io import BytesIO
            from PIL import Image
            from tubeforge.pipeline import thumbnail as thumbs
            buffer = BytesIO()
            thumbs.draw_guides(Image.open(path).convert("RGB"), application_settings.pipeline.shorts_thumbnail).save(buffer, "JPEG", quality=85)
            return Response(buffer.getvalue(), media_type="image/jpeg", headers={"Cache-Control": "no-cache"})
        return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "no-cache", "Content-Disposition": f'inline; filename="thumbnail-{job_id[:8]}.jpg"'})

    @app.get("/api/publishing/status", tags=["publishing"])
    def publishing_worker_status() -> dict[str, object]:
        platforms = sorted(publisher_presence.live_platforms())
        return {"worker_online": bool(platforms), "platforms": platforms, "manual_submission_enabled": bool(runtime.token_cipher and "youtube" in platforms)}

    @app.post("/api/publishing/drafts", status_code=status.HTTP_201_CREATED, tags=["publishing"])
    def create_manual_publish_draft(value: ManualPublishDraftRequest) -> dict[str, object]:
        try:
            staged_thumbnails: dict[str, Path] = {}
            for metadata in value.destinations.values():
                digest = metadata.get("thumbnail_sha256")
                if digest is not None and digest not in staged_thumbnails:
                    _, _, folder = _publishing_context(value.job_id)
                    meta_path = folder / "thumbnail.json"
                    current = json.loads(meta_path.read_text()) if meta_path.is_file() else {}
                    if current.get("sha256") != digest or not (folder / str(current.get("file"))).is_file():
                        raise ValueError("the thumbnail changed since it was reviewed; reload the Publishing page")
                    target = publishing_assets.stage_root / "thumbnails" / f"{digest}.jpg"
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if not target.is_file():
                        shutil.copyfile(folder / str(current["file"]), target)
                    staged_thumbnails[digest] = target
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
        try:
            account = runtime.accounts.create(uuid4().hex, platform=value.platform, display_name=value.display_name, external_account_id=None, auth_type=value.auth_type, credential_ciphertext=None, scopes=(), capabilities=(), category=value.category, default_description=value.default_description)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return {"id": account.id, "platform": account.platform, "display_name": account.display_name, "category": account.category, "default_description": account.default_description, "status": account.status, "capabilities": account.capabilities}

    @app.put("/api/social-accounts/{account_id}/profile", tags=["social accounts"])
    def update_social_account_profile(account_id: str, value: SocialAccountProfileRequest) -> dict[str, object]:
        try:
            account = runtime.accounts.update_profile(account_id, display_name=value.display_name, category=value.category, default_description=value.default_description)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="account not found") from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return {"id": account.id, "platform": account.platform, "display_name": account.display_name, "category": account.category, "default_description": account.default_description, "status": account.status}

    @app.put("/api/social-accounts/{account_id}/default", tags=["social accounts"])
    def set_default_social_account(account_id: str) -> dict[str, object]:
        try:
            account = runtime.accounts.set_default(account_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="account not found") from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return {"id": account.id, "is_default": account.is_default}

    @app.post("/api/social-accounts/{account_id}/disable", tags=["social accounts"])
    def disable_social_account(account_id: str) -> Response:
        try: runtime.accounts.disable(account_id)
        except KeyError as error: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="account not found") from error
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get("/api/topics", tags=["topics"])
    def list_topics(status_filter: str | None = None, account_id: str | None = None, unassigned: bool = False) -> list[dict[str, object]]:
        if account_id is not None and unassigned:
            raise HTTPException(status_code=422, detail="choose an account or unassigned topics")
        topics = runtime.topics.list(status=status_filter, **({"account_id": None if unassigned else account_id} if unassigned or account_id is not None else {}))
        return [{"id": item.id, "title": item.title, "notes": item.notes, "priority": item.priority, "status": item.status, "generation_job_id": item.generation_job_id, "attempts": item.attempts, "account_id": item.account_id} for item in topics]

    @app.post("/api/schedules", status_code=status.HTTP_201_CREATED, tags=["schedules"])
    def create_schedule(value: ScheduleCreateRequest) -> dict[str, object]:
        try:
            destination_ids, _ = schedule_destination_options(value.options)
            options = dict(value.options)
            if value.account_id is not None:
                if destination_ids and destination_ids != (value.account_id,):
                    raise ValueError("account schedule must target only its own account")
                options["destination_account_ids"] = [value.account_id]
                destination_ids = (value.account_id,)
            available = {account.id for account in runtime.accounts.list() if not account.disabled}
            if any(account_id not in available for account_id in destination_ids):
                raise ValueError("selected destination account is missing or disabled")
            schedule = runtime.schedules.create(uuid4().hex, name=value.name, cron=value.cron, timezone=value.timezone, next_run_at=next_run(value.cron, value.timezone, datetime.now(UTC)), options=options, account_id=value.account_id)
        except (ValueError, KeyError) as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"invalid schedule: {error}") from error
        return {"id": schedule.id, "name": schedule.name, "next_run_at": schedule.next_run_at, "account_id": schedule.account_id}

    @app.get("/api/schedules", tags=["schedules"])
    def list_schedules(account_id: str | None = None, unassigned: bool = False) -> list[dict[str, object]]:
        if account_id is not None and unassigned:
            raise HTTPException(status_code=422, detail="choose an account or unassigned schedules")
        schedules = runtime.schedules.list()
        if unassigned or account_id is not None:
            schedules = [item for item in schedules if item.account_id == (None if unassigned else account_id)]
        return [{"id": item.id, "name": item.name, "cron": item.cron, "timezone": item.timezone, "enabled": item.enabled, "next_run_at": item.next_run_at, "last_run_at": item.last_run_at, "options": item.options, "account_id": item.account_id} for item in schedules]

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
        try:
            job = runtime.jobs.create(uuid4().hex, _video_request(brief, application_settings, available_music=available_music), destination_account_ids=brief.destination_account_ids, video_description=brief.description)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        runtime.events.append(job.id, "job_created", topic=job.request.topic, review_mode=job.request.review_mode)
        return {**_job_payload(job), "video_description": runtime.jobs.video_description(job.id), "destination_intents": runtime.jobs.destination_intents(job.id), "watch_url": f"/api/jobs/{job.id}/artifacts/final"}

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
          const ownerLabel=document.createElement('label');ownerLabel.textContent='Script writer (AI model)';
          const ownerSelect=document.createElement('select');ownerSelect.name='script_model';ownerSelect.id='scriptModel';
          ownerSelect.append(Object.assign(document.createElement('option'),{value:'',textContent:'Loading models…'}));ownerLabel.append(ownerSelect);form.insertBefore(ownerLabel,presetLabel);
          fetch('/api/content-profiles').then(r=>r.ok?r.json():null).then(data=>{if(!data||!data.script_models)return;ownerSelect.replaceChildren();data.script_models.forEach(o=>ownerSelect.append(Object.assign(document.createElement('option'),{value:o.id,textContent:o.label,disabled:!o.enabled})));ownerSelect.value=data.default_script_model;}).catch(()=>{ownerSelect.replaceChildren(Object.assign(document.createElement('option'),{value:'',textContent:'Server default'}));});
          const intentField=document.createElement('fieldset');intentField.id='videoDestinationIntent';intentField.style.marginTop='18px';
          intentField.style.minWidth='0';intentField.style.border='1px solid #31415f';intentField.style.borderRadius='9px';intentField.style.padding='14px';
          const intentLegend=document.createElement('legend');intentLegend.textContent='Where this video should go';
          const intentHelp=document.createElement('p');intentHelp.className='sub';intentHelp.textContent='Choose exact local account profiles. This saves a plan with the video; no upload or online connection starts.';
          const intentAccounts=document.createElement('div');intentAccounts.id='videoIntentAccounts';intentAccounts.textContent='Loading account profiles…';
          const descriptionLabel=document.createElement('label');descriptionLabel.textContent='Video description (optional)';
          const descriptionInput=document.createElement('textarea');descriptionInput.id='videoDescription';descriptionInput.maxLength=5000;descriptionInput.placeholder='Leave blank to use each selected account’s default description';descriptionLabel.append(descriptionInput);
          intentField.append(intentLegend,intentHelp,intentAccounts,descriptionLabel);
          form.querySelector('button[type="submit"]').before(intentField);
          let accountChoicesLoaded=false;
          async function loadIntentAccounts(){const selected=new Set([...intentAccounts.querySelectorAll('input[type="checkbox"]:checked')].map(item=>item.value));try{const response=await fetch('/api/social-accounts');if(!response.ok)throw Error();const accounts=(await response.json()).filter(account=>!account.disabled);intentAccounts.replaceChildren();if(!accounts.length){intentAccounts.textContent='No account profiles yet. Add one in Accounts, or create this video without a destination.';return;}for(const account of accounts){const label=document.createElement('label');label.className='checkbox';const check=document.createElement('input');check.type='checkbox';check.value=account.id;check.checked=accountChoicesLoaded?selected.has(account.id):account.is_default;check.defaultChecked=check.checked;check.setAttribute('aria-label','Plan for '+account.platform+' account '+account.display_name);const details=document.createElement('span');details.textContent=account.platform+' · '+account.display_name+' · '+account.category+' ('+account.status.replaceAll('_',' ')+')'+(account.is_default?' · default':'');label.append(check,details);intentAccounts.append(label);}accountChoicesLoaded=true;}catch(_){if(intentAccounts.textContent==='Loading account profiles…')intentAccounts.textContent='Could not load account profiles. Reload before selecting destinations.';}}
          window.addEventListener('tubeforge:default-changed',()=>{accountChoicesLoaded=false;});window.addEventListener('tubeforge:accounts-changed',loadIntentAccounts);loadIntentAccounts();
          const originalFetch=window.fetch;
          window.fetch=(url, init={})=>{if(String(url)==='/api/videos'&&init.body){try{const body=JSON.parse(init.body);body.script_model=ownerSelect.value||null;body.visual_source=visualSelect.value;body.preset=presetSelect.value;body.channel_identity=channelSelect.value||null;body.music_track=document.querySelector('#musicSelect')?.value||null;body.destination_account_ids=[...intentAccounts.querySelectorAll('input[type="checkbox"]:checked')].map(item=>item.value);body.description=descriptionInput.value.trim()||null;init={...init,body:JSON.stringify(body)};}catch(_){}}return originalFetch(url,init);};
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
        operations_controls = SCHEDULING_SCRIPT
        account_controls = """<script>
        (() => {
          const shell=document.querySelector('.shell'); if(!shell)return;
          const panel=document.createElement('section');panel.className='panel';panel.style.marginTop='18px';
          const title=document.createElement('h2');title.textContent='Publishing accounts';
          const note=document.createElement('p');note.className='sub';note.textContent='Set up local account profiles for destination planning. A profile is not a platform connection. Connections require verified platform authorization.';
          const profileForm=document.createElement('form');profileForm.id='accountProfileForm';
          profileForm.innerHTML='<fieldset><legend>Add account profile</legend><label>Platform<select name="platform"><option value="youtube">YouTube</option><option value="instagram">Instagram</option><option value="snapchat">Snapchat</option><option value="x">X / Twitter</option></select></label><label>Account name<input name="display_name" maxlength="200" required placeholder="Virtual World Master"></label><label>Category<input name="category" maxlength="100" required placeholder="Tech"></label><label>Default video description<textarea name="default_description" maxlength="5000" placeholder="Used when a video has no custom description"></textarea></label><button type="submit" class="small secondary">Save account profile</button><div id="accountProfileStatus" role="status" aria-live="polite"></div></fieldset>';
          const profileField=profileForm.querySelector('fieldset');profileField.style.minWidth='0';profileField.style.marginTop='14px';profileField.style.border='1px solid #31415f';profileField.style.borderRadius='9px';profileField.style.padding='14px';
          const connect=document.createElement('button');connect.type='button';connect.className='small secondary';connect.textContent='Connect YouTube';connect.disabled=true;connect.style.marginTop='12px';
          const connectStatus=document.createElement('div');connectStatus.className='sub';connectStatus.setAttribute('role','status');connectStatus.textContent='Checking YouTube connection setup…';
          const list=document.createElement('div');list.className='muted';list.setAttribute('aria-live','polite');list.textContent='Loading accounts…';
          panel.append(title,note,profileForm,connect,connectStatus,list);shell.append(panel);
          let youtubeReady=false;
          fetch('/api/oauth/youtube/status').then(response=>response.json()).then(result=>{youtubeReady=Boolean(result.configured);connect.disabled=!youtubeReady;connectStatus.textContent=youtubeReady?'YouTube authorization is ready. Google will ask you to choose a channel.':result.reason;}).catch(()=>{connectStatus.textContent='Could not check YouTube connection setup.';});
          async function start(accountId){if(!youtubeReady)return;connect.disabled=true;connectStatus.textContent='Starting Google authorization…';try{const response=await fetch('/api/oauth/youtube/start',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({account_id:accountId||null})});if(!response.ok)throw Error(await response.text());const result=await response.json();location.assign(result.authorization_url);}catch(_){connectStatus.textContent='Could not start Google authorization. Check the app configuration and retry.';connect.disabled=false;}}
          connect.onclick=()=>start(null);
          async function loadAccounts(){try{const response=await fetch('/api/social-accounts');if(!response.ok)throw Error();const accounts=await response.json();list.replaceChildren();if(!accounts.length){list.textContent='No account profiles yet.';return;}for(const account of accounts){const row=document.createElement('div');row.className='event';row.style.marginTop='12px';const name=document.createElement('strong');name.textContent=account.display_name+' · '+account.platform+' · '+account.category;const state=document.createElement('div');state.textContent=account.status==='connected'&&account.external_account_id?'Connected · '+account.external_account_id:account.status.replaceAll('_',' ');const edit=document.createElement('button');edit.type='button';edit.className='small secondary';edit.textContent='Edit profile';edit.onclick=()=>{const editor=document.createElement('form');editor.innerHTML='<label>Account name<input name="display_name" maxlength="200" required></label><label>Category<input name="category" maxlength="100" required></label><label>Default video description<textarea name="default_description" maxlength="5000"></textarea></label><button type="submit" class="small secondary">Save changes</button><div role="status"></div>';editor.elements.display_name.value=account.display_name;editor.elements.category.value=account.category;editor.elements.default_description.value=account.default_description;editor.onsubmit=async event=>{event.preventDefault();const button=editor.querySelector('button'),feedback=editor.querySelector('[role="status"]');button.disabled=true;feedback.textContent='Saving…';try{const response=await fetch('/api/social-accounts/'+encodeURIComponent(account.id)+'/profile',{method:'PUT',headers:{'content-type':'application/json'},body:JSON.stringify(Object.fromEntries(new FormData(editor)))});if(!response.ok)throw Error(await response.text());feedback.textContent='Profile saved.';window.dispatchEvent(new Event('tubeforge:accounts-changed'));await loadAccounts();}catch(error){feedback.textContent='Could not save profile: '+error.message;button.disabled=false;}};row.append(editor);edit.remove();};row.append(name,state,edit);const defaultButton=document.createElement('button');defaultButton.type='button';defaultButton.className='small secondary';defaultButton.textContent=account.is_default?'Default account':'Set as default';defaultButton.disabled=account.is_default||account.disabled;defaultButton.onclick=async()=>{defaultButton.disabled=true;defaultButton.textContent='Saving…';try{const response=await fetch('/api/social-accounts/'+encodeURIComponent(account.id)+'/default',{method:'PUT'});if(!response.ok)throw Error(await response.text());window.dispatchEvent(new Event('tubeforge:default-changed'));window.dispatchEvent(new Event('tubeforge:accounts-changed'));await loadAccounts();}catch(error){defaultButton.textContent='Could not save default: '+error.message;defaultButton.disabled=false;}};row.append(defaultButton);if(account.platform==='youtube'&&account.external_account_id){const reconnect=document.createElement('button');reconnect.type='button';reconnect.className='small secondary';reconnect.textContent='Reconnect this channel';reconnect.disabled=!youtubeReady;reconnect.onclick=()=>start(account.id);row.append(reconnect);}list.append(row);}}catch(_){if(list.textContent==='Loading accounts…')list.textContent='Could not load account profiles. Reload to retry.';}}
          profileForm.onsubmit=async event=>{event.preventDefault();const button=profileForm.querySelector('button[type="submit"]'),feedback=document.querySelector('#accountProfileStatus');button.disabled=true;feedback.textContent='Saving profile…';try{const response=await fetch('/api/social-accounts',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(Object.fromEntries(new FormData(profileForm)))});if(!response.ok)throw Error(await response.text());feedback.textContent='Account profile saved. Connection is still required before online delivery.';profileForm.reset();window.dispatchEvent(new Event('tubeforge:accounts-changed'));await loadAccounts();}catch(error){feedback.textContent='Could not save profile: '+error.message;}finally{button.disabled=false;}};
          loadAccounts();
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
          const planned=document.createElement('div');planned.id='plannedVideoDestinations';planned.className='sub';planned.style.marginTop='10px';planned.setAttribute('role','status');
          const destinations=document.createElement('div');destinations.id='publishDestinations';destinations.textContent='Loading connected accounts…';
          const save=document.createElement('button');save.type='button';save.id='savePublishDraft';save.textContent='Save publishing draft';save.disabled=true;
          const status=document.createElement('div');status.className='notice';status.id='publishDraftStatus';status.setAttribute('role','status');
          const historyHeading=document.createElement('h3');historyHeading.textContent='Publishing drafts';historyHeading.style.marginTop='20px';
          const refreshHistory=document.createElement('button');refreshHistory.type='button';refreshHistory.className='small secondary';refreshHistory.textContent='Refresh publishing activity';refreshHistory.style.marginBottom='12px';
          const history=document.createElement('div');history.id='publishDraftHistory';history.className='muted';history.textContent='Loading drafts…';
          panel.append(heading,help,workerState,videoLabel,preview,destinationLabel,planned,destinations,save,status,historyHeading,refreshHistory,history);shell.append(panel);
          const rows=new Map(),videosById=new Map(),accountsById=new Map();let workerReady=false;

          const pkgBox=document.createElement('fieldset');pkgBox.style.cssText='border:1px solid #31415f;border-radius:9px;margin-top:14px';
          pkgBox.innerHTML='<legend>Upload-ready package — title, description and thumbnail are prefilled and fully editable</legend><div class="sub" id="pkgStatus" role="status">Select a finished video to prepare its title, two-line description and thumbnail.</div><label>Video title<input id="pkgTitle" maxlength="100"></label><label>Description (two lines)<textarea id="pkgDesc" rows="3" maxlength="5000"></textarea></label><label>Keyword tags, comma separated<input id="pkgTags"></label><div class="actions"><button type="button" class="small secondary" id="pkgCopyTitle">Copy title</button><button type="button" class="small secondary" id="pkgCopyDesc">Copy description</button></div><label class="checkbox" id="pkgGuidesRow" style="display:none"><input type="checkbox" id="pkgGuides"> Show Shorts safe-area guides (review only; not in the file)</label><img id="pkgThumb" alt="Thumbnail preview" style="display:none;width:100%;max-width:480px;border-radius:10px;margin-top:10px;border:1px solid #31415f"><label>Thumbnail text (2–3 punchy words)<input id="pkgText" maxlength="48"></label><label>Video moment<select id="pkgFrame"></select></label><label>Logo badge<select id="pkgLogo"></select></label><label>Title ideas<select id="pkgTitles"></select></label><div class="actions"><button type="button" class="small" id="pkgUpdate">Update thumbnail</button><label class="small secondary" style="display:inline-block;cursor:pointer;padding:8px 12px">Upload my own image<input id="pkgFile" type="file" accept="image/png,image/jpeg" hidden></label><a id="pkgDownload" class="small secondary" style="display:none;padding:8px 12px" download>Download thumbnail</a></div>';
          preview.after(pkgBox);const pkg=id=>pkgBox.querySelector('#'+id);let currentThumb=null;
          function renderThumb(t){currentThumb=t;const img=pkg('pkgThumb');img.dataset.url=t.url;pkg('pkgGuidesRow').style.display=t.portrait?'block':'none';img.style.maxWidth=t.portrait?'300px':'480px';img.src=t.url+(t.portrait&&pkg('pkgGuides').checked?'&guides=1':'');img.style.display='block';pkg('pkgText').value=t.text||'';pkg('pkgText').disabled=t.custom;
            const frame=pkg('pkgFrame');frame.replaceChildren();(t.frame_times||[]).forEach(sec=>frame.append(Object.assign(document.createElement('option'),{value:sec,textContent:sec.toFixed(1)+' s'})));if(t.frame_time!=null)frame.value=String((t.frame_times||[]).reduce((a,b)=>Math.abs(b-t.frame_time)<Math.abs(a-t.frame_time)?b:a));
            const logo=pkg('pkgLogo');logo.replaceChildren(Object.assign(document.createElement('option'),{value:'',textContent:'No logo'}));(t.logos||[]).forEach(name=>logo.append(Object.assign(document.createElement('option'),{value:name,textContent:name})));logo.value=t.logo||'';
            const link=pkg('pkgDownload');link.href=t.url;link.style.display='inline-block';pkg('pkgUpdate').disabled=false;}
          function propagate(){for(const row of rows.values()){const yt=row.account.platform==='youtube';if(yt&&row.title&&!row.title.dataset.edited)row.title.value=pkg('pkgTitle').value;if(!row.caption.dataset.edited)row.caption.value=pkg('pkgDesc').value;if(yt&&row.tags&&!row.tags.dataset.edited)row.tags.value=pkg('pkgTags').value;}}
          for(const id of ['pkgTitle','pkgDesc','pkgTags'])pkg(id).addEventListener('input',event=>{event.target.dataset.edited='1';propagate();});
          for(const [id,source] of [['pkgCopyTitle','pkgTitle'],['pkgCopyDesc','pkgDesc']])pkg(id).onclick=async()=>{try{await navigator.clipboard.writeText(pkg(source).value);pkg(id).textContent='Copied';}catch(_){pkg(source).select();}setTimeout(()=>{pkg(id).textContent=id==='pkgCopyTitle'?'Copy title':'Copy description';},1800);};
          async function applySuggestion(){const id=videoSelect.value;if(!id||videoSelect.disabled)return;const note=pkg('pkgStatus');note.textContent='Preparing title, description and thumbnail from the finished video…';
            try{const response=await fetch('/api/publishing/jobs/'+encodeURIComponent(id)+'/suggestion');if(!response.ok)throw Error((await response.json().catch(()=>({}))).detail||response.status);const s=await response.json();if(videoSelect.value!==id)return;
              if(!pkg('pkgTitle').dataset.edited)pkg('pkgTitle').value=s.title;if(!pkg('pkgDesc').dataset.edited)pkg('pkgDesc').value=s.description;if(!pkg('pkgTags').dataset.edited)pkg('pkgTags').value=s.tags.join(', ');propagate();
              const titles=pkg('pkgTitles');titles.replaceChildren(Object.assign(document.createElement('option'),{value:'',textContent:'Suggested: '+s.title}));s.title_options.forEach(t=>titles.append(Object.assign(document.createElement('option'),{value:t,textContent:t})));
              renderThumb(s.thumbnail);note.textContent='Review and edit anything below, then save the draft. The thumbnail is attached to the YouTube upload.';}
            catch(error){note.textContent='Could not prepare the package: '+error.message+'. You can still type the title and description yourself.';}}
          pkg('pkgGuides').onchange=()=>{const img=pkg('pkgThumb');img.src=img.dataset.url+(pkg('pkgGuides').checked?'&guides=1':'');};
          pkg('pkgTitles').onchange=event=>{if(!event.target.value)return;pkg('pkgTitle').value=event.target.value;pkg('pkgTitle').dataset.edited='1';propagate();};
          pkg('pkgUpdate').onclick=async()=>{const id=videoSelect.value,button=pkg('pkgUpdate');button.disabled=true;button.textContent='Composing…';try{const body={text:pkg('pkgText').value.trim()||null,frame_time:Number(pkg('pkgFrame').value),logo:pkg('pkgLogo').value||null};const response=await fetch('/api/publishing/jobs/'+encodeURIComponent(id)+'/thumbnail',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)});if(!response.ok)throw Error((await response.json().catch(()=>({}))).detail||response.status);renderThumb(await response.json());}catch(error){pkg('pkgStatus').textContent='Thumbnail not updated: '+error.message;}finally{button.disabled=false;button.textContent='Update thumbnail';}};
          pkg('pkgFile').onchange=async event=>{const file=event.target.files[0];if(!file)return;try{const response=await fetch('/api/publishing/jobs/'+encodeURIComponent(videoSelect.value)+'/thumbnail/upload',{method:'POST',headers:{'content-type':file.type||'image/jpeg'},body:file});if(!response.ok)throw Error((await response.json().catch(()=>({}))).detail||response.status);renderThumb(await response.json());pkg('pkgStatus').textContent='Your image is the thumbnail (cropped to 16:9).';}catch(error){pkg('pkgStatus').textContent='Image not used: '+error.message;}event.target.value='';};
          destinations.addEventListener('input',event=>{event.target.dataset.edited='1';});videoSelect.addEventListener('change',()=>{for(const id of ['pkgTitle','pkgDesc','pkgTags'])delete pkg(id).dataset.edited;for(const row of rows.values())for(const f of [row.title,row.caption,row.tags])if(f)delete f.dataset.edited;applySuggestion();});
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
          function applyVideoIntent(){const video=videosById.get(videoSelect.value);planned.replaceChildren();for(const row of rows.values()){row.check.checked=false;row.caption.value='';if(row.title)row.title.value='';if(row.tags)row.tags.value='';}if(!video)return;const intents=video.destination_intents||[];if(!intents.length){planned.textContent='This video has no saved destination plan. Choose a connected account below to prepare a draft.';for(const row of rows.values()){if(video.video_description&&video.video_description.length<=row.caption.maxLength)row.caption.value=video.video_description;if(row.title)row.title.value=video.title.slice(0,100);}return;}const heading=document.createElement('strong');heading.textContent='Saved creation plan';planned.append(heading);for(const intent of intents){const account=accountsById.get(intent.account_id),row=rows.get(intent.account_id),fits=row&&intent.description.length<=row.caption.maxLength;const line=document.createElement('p');line.textContent=intent.platform+' · '+intent.account_name+' · '+intent.category+(fits?' — ready for draft review':row?' — description exceeds this platform’s limit; shorten it before selecting':' — '+(account?.status||'account unavailable')+'; connection or platform draft support required');planned.append(line);if(row){row.check.checked=Boolean(fits);row.caption.value=fits?intent.description:'';if(row.title)row.title.value=video.title.slice(0,100);}}}
          videoSelect.onchange=applyVideoIntent;
          async function loadChoices(){try{const [videosResponse,accountsResponse]=await Promise.all([fetch('/api/publishing/ready-videos'),fetch('/api/social-accounts')]);if(!videosResponse.ok||!accountsResponse.ok)throw Error();const videos=await videosResponse.json(),allAccounts=await accountsResponse.json(),accounts=allAccounts.filter(item=>item.status==='connected'&&!item.disabled&&item.external_account_id&&['youtube','instagram'].includes(item.platform));videosById.clear();accountsById.clear();rows.clear();for(const video of videos)videosById.set(video.job_id,video);for(const account of allAccounts)accountsById.set(account.id,account);videoSelect.replaceChildren();if(!videos.length){videoSelect.append(Object.assign(document.createElement('option'),{textContent:'No finished videos available'}));planned.textContent='Saved destination plans appear when a final video is ready.';}else{for(const video of videos)videoSelect.append(Object.assign(document.createElement('option'),{value:video.job_id,textContent:video.title+' · '+video.state.replaceAll('_',' ')}));videoSelect.disabled=false;preview.disabled=false;}destinations.replaceChildren();if(!accounts.length){destinations.textContent='No verified YouTube or Instagram accounts available for a manual publishing draft. Planned accounts remain visible above.';}for(const account of accounts){const card=document.createElement('fieldset');card.style.border='1px solid #31415f';card.style.borderRadius='9px';card.style.marginTop='10px';const legend=document.createElement('legend');const check=document.createElement('input');check.type='checkbox';check.setAttribute('aria-label','Publish to '+account.display_name);legend.append(check,document.createTextNode(' '+account.platform+' · '+account.display_name+' · '+account.external_account_id));card.append(legend);const caption=inputField(account.platform==='youtube'?'YouTube description':'Instagram caption','textarea');caption.input.maxLength=account.platform==='youtube'?5000:2200;card.append(caption.label);let title=null,tags=null;if(account.platform==='youtube'){title=inputField('YouTube title','input');title.input.maxLength=100;tags=inputField('YouTube keyword tags, comma separated','input');card.append(title.label,tags.label);}destinations.append(card);rows.set(account.id,{account,check,caption:caption.input,title:title?.input,tags:tags?.input});}save.disabled=!videos.length||!accounts.length;applyVideoIntent();applySuggestion();}catch(_){videoSelect.replaceChildren();destinations.textContent='Could not load videos or accounts. Reload to retry.';preview.disabled=true;save.disabled=true;}}
          save.onclick=async()=>{const selected=[...rows.values()].filter(row=>row.check.checked);if(!selected.length){status.textContent='Select at least one destination account.';return;}const destinationData={};for(const row of selected){const metadata={caption:row.caption.value.trim()};if(row.account.platform==='youtube'){metadata.title=row.title.value.trim();metadata.tags=row.tags.value.split(',').map(value=>value.trim()).filter(Boolean);if(currentThumb)metadata.thumbnail_sha256=currentThumb.sha256;}destinationData[row.account.id]=metadata;}save.disabled=true;save.textContent='Saving draft…';status.textContent='Validating and copying the selected video…';try{const response=await fetch('/api/publishing/drafts',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({job_id:videoSelect.value,destinations:destinationData})});if(!response.ok)throw Error(await response.text());const draft=await response.json();status.textContent='Draft '+draft.id.slice(0,8)+' saved for '+draft.destinations.length+' destination(s). No upload was started.';await loadDrafts();}catch(error){status.textContent='Could not save draft: '+error.message;}finally{save.disabled=false;save.textContent='Save publishing draft';}};
          loadChoices();loadDrafts();loadWorkerState();setInterval(loadWorkerState,20000);
        })();
        </script>"""
        reviewer_controls = """<dialog id="scriptDialog" aria-labelledby="scriptTitle"><div class="modal-head"><h2 id="scriptTitle">Review script and sources</h2><button class="close" type="button" id="scriptClose" aria-label="Close script">×</button></div><form id="scriptForm"><div class="modal-body"><p class="sub">Review the exact source packet and narration. Saving creates a new exact script revision and requires a fresh approval.</p><h3>Approved sources</h3><div id="scriptSources"></div><h3>Hook and title checks</h3><div id="creativeChecks" aria-live="polite"></div><details><summary>Scene, packaging and technical details</summary><pre id="skillReview" style="white-space:pre-wrap;overflow-wrap:anywhere"></pre></details><h3>Narration</h3><div id="scriptSections"></div><label>Codex revision instruction<textarea id="codexInstruction" placeholder="e.g. Make the hook sharper, use a practical senior-engineer tone, and keep all claims accurate."></textarea></label><button id="copyCodexPrompt" class="secondary" type="button">Copy Codex prompt</button><div id="scriptNotice" class="notice"></div><div class="actions"><button class="small secondary" type="button" id="scriptCancel">Cancel</button><button class="small" type="submit">Save revision</button></div></div></form></dialog><script>
        (() => {
          let currentJob=null, currentPackage=null, scriptEditable=false;
          const dialog=document.querySelector('#scriptDialog'), sections=document.querySelector('#scriptSections'), sources=document.querySelector('#scriptSources'), creativeChecks=document.querySelector('#creativeChecks'), scriptNotice=document.querySelector('#scriptNotice');
          document.addEventListener('click', event=>{const button=event.target.closest('button');if(button&&(button.textContent==='Approve script'||button.textContent==='Approve preview')&&!button.disabled){button.disabled=true;button.textContent='Saving approval…';}},true);
          const makeButton=(label, cls, handler)=>{const b=document.createElement('button');b.type='button';b.className='small '+(cls||'secondary');b.textContent=label;b.onclick=handler;return b;};
          const textNode=(parent,tag,className,text)=>{const node=document.createElement(tag);if(className)node.className=className;node.textContent=text;parent.append(node);return node;};
          function renderCreativeChecks(pkg,checks){
            creativeChecks.replaceChildren();
            textNode(creativeChecks,'p','sub','Hook and title scores are heuristic review signals, not predictions of views. They do not replace source or creative review.');
            if(!checks||!Array.isArray(checks.hooks)||!Array.isArray(checks.titles)){
              textNode(creativeChecks,'p','failure pending',checks?.reason||'Automated creative checks are unavailable. Review the hook and packaging manually; no approval was applied.');
              return;
            }
            const hookTitle=textNode(creativeChecks,'h4','','Hook options');hookTitle.style.margin='12px 0 4px';
            const hooks=document.createElement('ol');hooks.className='creative-list';creativeChecks.append(hooks);
            const chosen=pkg.script_sections?.[0]?.narration?.match(/^.*?[.!?…](?:\\s|$)/)?.[0]?.trim();
            const selectedIndex=checks.hooks.findIndex(item=>item.selected||item.hook===chosen);
            checks.hooks.forEach((item,index)=>{
              const row=textNode(hooks,'li','creative-row','');
              textNode(row,'span','creative-score',`${item.verdict}/100 · ${item.band||'unrated'}`);
              textNode(row,'span','',`${item.selected||item.hook===chosen?'Selected opening · ':''}${item.hook}`);
              if(index===selectedIndex&&selectedIndex>1)textNode(row,'p','sub','This selected opening ranks below the two highest heuristic scores.');
            });
            const thumbnailOptions=pkg.thumbnail_brief?.text_options||[];
            textNode(creativeChecks,'p','sub',thumbnailOptions.length?`No title/thumbnail pair is selected. Title scores below compare against the first thumbnail option: “${thumbnailOptions[0]}”. Other thumbnail text options: ${thumbnailOptions.slice(1).map(value=>`“${value}”`).join(', ')||'none'}.`:'No thumbnail text options are available, so review the title choices manually.');
            const titleTitle=textNode(creativeChecks,'h4','','Top title checks');titleTitle.style.margin='12px 0 4px';
            const sortedTitles=[...checks.titles].sort((a,b)=>(b.score||0)-(a.score||0));
            const showTitle=(parent,item,index)=>{
              const row=textNode(parent,'li','creative-row','');
              textNode(row,'span','creative-score',`${item.score}/100`);
              textNode(row,'span','',`${item.title} · ${item.chars} characters`);
              const issues=Array.isArray(item.issues)?item.issues:[];
              if(issues.length){const list=document.createElement('ul');list.className='sub';issues.slice(0,2).forEach(issue=>textNode(list,'li','',Array.isArray(issue)?`${issue[0]}: ${issue[1]}`:String(issue)));row.append(list);}
            };
            const topTitles=document.createElement('ol');topTitles.className='creative-list';sortedTitles.slice(0,3).forEach((item,index)=>showTitle(topTitles,item,index));creativeChecks.append(topTitles);
            if(sortedTitles.length>3){const more=document.createElement('details');textNode(more,'summary','','Show all title checks');const all=document.createElement('ol');all.className='creative-list';sortedTitles.slice(3).forEach((item,index)=>showTitle(all,item,index+3));more.append(all);creativeChecks.append(more);}
          }
          async function review(jobId, editable){
            document.querySelector('#skillReview').textContent='';
            currentJob=jobId; scriptNotice.textContent='Loading script…'; sections.replaceChildren(); sources.replaceChildren(); creativeChecks.replaceChildren(); dialog.showModal();
            const response=await fetch(`/api/jobs/${jobId}/script`);
            if(!response.ok){scriptNotice.textContent='Could not load script: '+await response.text();return;}
            scriptEditable=Boolean(editable); const reviewData=await response.json();currentPackage=reviewData.package;renderCreativeChecks(currentPackage,reviewData.skill_checks);document.querySelector('#skillReview').textContent=JSON.stringify({channel:currentPackage.request.channel_identity,voice:currentPackage.request.channel_voice_profile,scenes:currentPackage.scene_plans,metadata:currentPackage.metadata,thumbnail:currentPackage.thumbnail_brief,skill_checks:reviewData.skill_checks},null,2); scriptNotice.textContent=scriptEditable?'Review the sources, creative checks and narration, then save or approve it.':'This saved script and its source packet are read-only because this generation has already moved past script review.';
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
        reviewer_controls += SCENE_CONTROLS
        dashboard = DASHBOARD_HTML.replace(
            "</style>",
            ".creative-list{margin:6px 0 14px;padding-inline-start:1.4rem}.creative-row{padding:7px 2px 10px;overflow-wrap:anywhere;border-bottom:1px solid var(--line)}.creative-score{display:inline-block;margin-right:8px;padding:2px 7px;border-radius:999px;background:#223654;color:#b7ebff;font-size:12px;font-weight:700}.creative-row ul{margin:5px 0 0;padding-inline-start:1.2rem}.creative-row li+li{margin-top:3px}#creativeChecks{overflow-wrap:anywhere}#scriptDialog details summary{cursor:pointer}@media(max-width:600px){.creative-row{padding-inline-start:2px}}"
            "</style>",
            1,
        )
        research_enabled = application_settings.pipeline.sources.research_enabled
        dashboard = dashboard.replace(
            "Give a title and the key points.",
            ("Give a title and brief notes. Codex researches primary sources before writing; unsupported angles are qualified. Supplied source packets keep their exact evidence."
             if research_enabled else "Give a title, brief notes, and approved sources. You approve the exact script and preview before rendering."),
        )
        dashboard = dashboard.replace(
            '<label>Notes<textarea name="notes" required placeholder="One point per line"></textarea></label>',
            '<label>Brief notes / key points<textarea name="notes" required placeholder="One point per line"></textarea></label>',
        )
        source_fields = """<label>Audience<input name="audience" maxlength="200" required value="general"></label>
        <label>Creative angle<textarea name="angle" maxlength="4000" placeholder="What should the viewer understand or be able to do?"></textarea><span class="sub">This guides the story. It stays separate from source evidence.</span></label>
        <label class="checkbox"><input name="show_source_credit" type="checkbox"> Show the source name on screen in the middle of the video (9:16 Shorts; off by default)</label>
        <label class="checkbox"><input name="show_mascot" type="checkbox"> Add the Chip mascot in a free corner (9:16 Shorts; off by default)</label>
        <label>Channel name on the video (optional)<input name="channel_watermark" maxlength="40" placeholder="Leave empty for none — shown very small at the top"></label>
<fieldset class="sources" id="sourceRows"><legend>Sources (optional)</legend><p class="sub">Add the pages the script should be based on. Give a URL and we read the whole page for you, or paste an exact passage to use only that. Up to 8.</p><div id="sourceList"></div><button type="button" class="secondary" id="addSource">+ Add source</button></fieldset>
        <script>(()=>{const list=document.querySelector('#sourceList'),add=document.querySelector('#addSource');if(!list||!add)return;
        const row=()=>{const r=document.createElement('div');r.className='source-row';r.innerHTML='<label>Page URL<input class="src-url" type="url" maxlength="2000" placeholder="https://…"></label><label>Title <span class="sub">(optional)</span><input class="src-title" maxlength="500" placeholder="Defaults to the site name"></label><label>Exact passage <span class="sub">(optional — leave empty to read the whole page)</span><textarea class="src-excerpt" maxlength="24000" placeholder="Paste only the part you want the script to rely on"></textarea></label><button type="button" class="small secondary src-remove">Remove source</button>';r.querySelector('.src-remove').onclick=()=>{r.remove();add.disabled=false;};list.append(r);add.disabled=list.children.length>=8;};
        add.onclick=row;row();window.collectSources=()=>[...list.querySelectorAll('.source-row')].map((r,i)=>{const url=r.querySelector('.src-url').value.trim();if(!url)return null;let host=url;try{host=new URL(url).hostname}catch(_){}return {source_id:'source-'+(i+1),url,title:r.querySelector('.src-title').value.trim()||host,excerpt:r.querySelector('.src-excerpt').value.trim()||null};}).filter(Boolean);})();</script>"""
        dashboard = dashboard.replace(
            "</label><label>Target duration (seconds)",
            "</label>" + source_fields + "<label>Target duration (seconds)",
        )
        dashboard = dashboard.replace(
            "textarea{min-height:106px;resize:vertical}",
            "textarea{min-height:106px;resize:vertical}fieldset.sources{margin:14px 0;padding:10px 12px;border:1px solid var(--line);border-radius:9px}fieldset.sources legend{color:#cbd7eb;font-size:13px;font-weight:700}.source-row{margin:10px 0;padding:10px;border:1px solid var(--line);border-radius:8px}",
        )
        dashboard = dashboard.replace("join('\n')", r"join('\n')").replace("split('\n')", r"split('\n')")
        dashboard = dashboard.replace(
            "cards.set(job.id,card);jobsRoot.append(card)",
            "cards.set(job.id,card);card.dataset.jobId=job.id;jobsRoot.append(card)",
        )
        old_brief_submit = r"let d=new FormData(e.currentTarget),body={title:d.get('title'),notes:d.get('notes').split('\n').map(x=>x.trim()).filter(Boolean),duration_seconds:Number(d.get('duration_seconds')),review_mode:d.get('review_mode'),captions_enabled:d.has('captions_enabled')};let r=await fetch('/api/videos'"
        new_brief_submit = r"let d=new FormData(e.currentTarget),sources=(window.collectSources?window.collectSources():[]);if(!sources.length)sources=null;let body={title:d.get('title'),notes:d.get('notes').split('\n').map(x=>x.trim()).filter(Boolean),angle:String(d.get('angle')||'').trim()||null,audience:String(d.get('audience')||'general').trim()||'general',sources,duration_seconds:Number(d.get('duration_seconds')),review_mode:d.get('review_mode'),captions_enabled:d.has('captions_enabled'),voice_id:d.get('voice_id')||null,show_source_credit:d.has('show_source_credit'),show_mascot:d.has('show_mascot'),channel_watermark:String(d.get('channel_watermark')||'').trim()||null};let r=await fetch('/api/videos'"
        assert dashboard.count(old_brief_submit) == 1, dashboard.count(old_brief_submit)
        dashboard = dashboard.replace(old_brief_submit, new_brief_submit)
        dashboard = dashboard.replace(
            "if(j.artifacts.includes('preview'))actions.append(button('Preview','secondary',()=>openVideo(j,'preview','Preview')));if(j.artifacts.includes('final'))actions.append(button('Watch final','',()=>openVideo(j,'final','Final video')))",
            "if(j.artifacts.includes('final'))actions.append(button('Watch video','',()=>openVideo(j,'final','Final video')));else if(j.artifacts.includes('preview'))actions.append(button('Watch preview','secondary',()=>openVideo(j,'preview','Preview')))",
        )
        dashboard = dashboard.replace(
            "${j.artifacts.length} saved artifacts · ${j.event_count} activity events",
            "${j.artifacts.length} saved artifacts · ${j.event_count} activity events · Job ${j.id.slice(0,8)} · Script: ${j.script_model||j.script_owner||'codex'} · Created ${j.created_at?new Date(j.created_at).toLocaleString():'unknown'}",
        )
        dashboard = dashboard.replace(
            "card.append(actions)}async function refresh()",
            "actions.append(button('Inputs & script','secondary',()=>window.openStudioRecord(j.id)));if(j.can_retry_as_new)actions.append(button('Retry…','',()=>window.openRetryJob(j.id)));actions.append(button('Copy job ID','secondary',async ev=>{const b=ev.currentTarget;try{await navigator.clipboard.writeText(j.id);b.textContent='Copied '+j.id.slice(0,8);}catch(_){window.prompt('Job ID',j.id);}setTimeout(()=>{b.textContent='Copy job ID'},2500);}));let format=document.createElement('div');format.className='generation-format';const kind=j.format.production_mode==='source_clip'?'Source clips':j.format.aspect_ratio==='9:16'&&j.format.duration_seconds<=120?'Shorts':j.format.aspect_ratio==='9:16'?'Vertical video':'Landscape video';format.textContent=kind+' · '+j.format.preset+' · '+j.format.duration_seconds+'s · '+(j.destinations.length?j.destinations.map(item=>item.platform+' / '+item.account_name+' / '+item.category).join(', '):'No destination selected');card.append(format,actions)}async function refresh()",
        )
        dashboard = dashboard.replace(
            "const meta=card.querySelector('.muted');if(meta&&!meta.dataset.created){const created=job.created_at?new Date(job.created_at).toLocaleString():'unknown';meta.textContent+=' · Created '+created;meta.dataset.created='true';}",
            "",
        )
        dashboard = dashboard.replace("</head>", f"<style>{STUDIO_CSS}{SCHEDULING_CSS}{GENERATION_CSS}</style></head>")
        return dashboard.replace("</body>", source_controls + operations_controls + account_controls + publishing_controls + reviewer_controls + GENERATION_CONTROLS + STUDIO_SCRIPT + "</body>")

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> Response:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get("/api/jobs", tags=["jobs"])
    def list_jobs() -> list[dict[str, object]]:
        deletable = {JobState.SCRIPT_APPROVAL_REQUIRED, JobState.PREVIEW_READY, JobState.FINAL_READY, JobState.PUBLICATION_APPROVAL_REQUIRED, JobState.FAILED_RETRYABLE, JobState.FAILED_VALIDATION, JobState.FAILED_EXHAUSTED, JobState.CANCELLED}
        payloads = []
        for job in runtime.jobs.list_recent():
            can_retry_validation, retry_identity = _can_retry_approved_asset_validation(runtime, job)
            events = runtime.events.list_for_job(job.id)
            payloads.append({
                **_job_payload(job), "topic": job.request.topic, "script_owner": job.request.script_owner, "script_model": job.request.script_model,
                "artifacts": [artifact.name for artifact in runtime.artifacts.list_for_job(job.id)],
                "event_count": len(events),
                "latest_event": {"event_type": events[-1].event_type, "stage": events[-1].details.get("stage") if isinstance(events[-1].details.get("stage"), str) else None, "created_at": _as_ist(events[-1].created_at)} if events else None,
                "destinations": runtime.jobs.destination_intents(job.id),
                "format": {"preset": job.request.preset_name, "aspect_ratio": job.request.aspect_ratio, "duration_seconds": job.request.target_duration_seconds, "production_mode": job.request.production_mode},
                "deletable": job.claim_owner is None and job.state in deletable,
                "artifact_cleanup_eligible": job.claim_owner is None and job.state is JobState.PUBLISHED,
                "can_retry_validation": can_retry_validation,
                "can_retry_as_new": job.claim_owner is None and job.state in _RETRY_AS_NEW_STATES,
                "retry_script_identity": retry_identity,
            })
        return payloads

    @app.get("/api/jobs/{job_id}/studio-record", tags=["jobs"])
    def get_studio_record(job_id: str) -> dict[str, object]:
        """Return saved operator inputs and durable Codex invocation evidence."""
        try:
            job = runtime.jobs.get(job_id)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found") from error
        commands: list[str] = []
        generation: dict[str, object] | None = None
        evidence = runtime.artifacts.get(job_id, JobState.CONTENT_GENERATING, "content_generation_evidence")
        if evidence is not None:
            try:
                saved = json.loads(Path(evidence.path).read_text(encoding="utf-8"))
                provenance, usage = saved.get("provenance") or {}, saved.get("usage") or {}
                if provenance.get("provider") == "codex-cli":
                    commands = [shlex.join(args) for args in provenance.get("commands", []) if isinstance(args, list) and all(isinstance(arg, str) for arg in args)]
                    generation = {"owner": "codex", "model": provenance.get("model")}
                elif provenance.get("provider") == "host-claude-runner":
                    # argv is not stored per call; this is the fixed shape the runner builds (prompt on stdin, schema omitted)
                    flags = ["claude", "-p", "--model", str(provenance.get("model")), "--output-format", "json", "--json-schema", "<schema>", "--no-session-persistence", "--system-prompt", "<system prompt>", "--tools", ""]
                    if provenance.get("effort"):
                        flags += ["--effort", str(provenance["effort"])]
                    commands = [shlex.join(flags) + "  # prompt via stdin; reconstructed, schema/prompt omitted"] * int(usage.get("attempts") or 1)
                    generation = {"owner": "claude", "model": provenance.get("model"), "effort": provenance.get("effort"), "choice": provenance.get("choice")}
                if generation is not None:
                    keys = ("attempts", "input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "total_cost_usd", "web_search_requests")
                    generation.update({key: usage[key] for key in keys if key in usage})
                    generation["elapsed_seconds"] = provenance.get("elapsed_seconds")
            except (OSError, ValueError, TypeError):
                pass
        return {"job_id": job_id, "request": job.request.model_dump(mode="json"), "destinations": runtime.jobs.destination_intents(job_id), "video_description": runtime.jobs.video_description(job_id), "codex_commands": commands, "generation": generation, "command_status": "recorded" if commands else "not_recorded"}

    @app.post("/api/jobs/{job_id}/retry", status_code=status.HTTP_201_CREATED, tags=["jobs"])
    def retry_job_as_new(job_id: str, retry: RetryJobRequest) -> dict[str, object]:
        """Start a fresh job from a failed one, optionally with an edited request; the failed job and its allowances stay untouched."""
        try:
            job = runtime.jobs.get(job_id)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found") from error
        if job.claim_owner is not None or job.state not in _RETRY_AS_NEW_STATES:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="only an idle failed or cancelled job can be retried")
        try:
            new_request = ContentRequest.model_validate(retry.request) if retry.request is not None else job.request
        except ValidationError as error:
            detail = "; ".join(f"{'.'.join(str(part) for part in item['loc']) or 'request'}: {item['msg']}" for item in error.errors())
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail) from error
        destinations = tuple(item["account_id"] for item in runtime.jobs.destination_intents(job_id))
        try:
            created = runtime.jobs.create(uuid4().hex, new_request, destination_account_ids=destinations, video_description=runtime.jobs.video_description(job_id))
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        runtime.events.append(created.id, "job_created", topic=created.request.topic, review_mode=created.request.review_mode)
        runtime.events.append(created.id, "job_retried_from", source_job_id=job_id, request_edited=new_request != job.request)
        runtime.events.append(job_id, "job_retry_started", new_job_id=created.id)
        return {**_job_payload(created), "retried_from": job_id, "request_edited": new_request != job.request}

    @app.post("/api/jobs/{job_id}/retry-validation", tags=["jobs"])
    def retry_approved_validation(job_id: str, decision: RetryApprovedValidationRequest, request: Request) -> dict[str, object]:
        """Resume only an intact, exact-approved asset checkpoint after validation code is repaired."""
        try:
            job = runtime.jobs.get(job_id)
            can_retry, identity = _can_retry_approved_asset_validation(runtime, job)
            if not can_retry or identity is None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="job is not eligible for approved asset-checkpoint recovery")
            if decision.expected_script_identity != identity:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="approved script identity changed; reload Studio before retrying")
            auth_session = runtime.auth.session(request.cookies.get("tubeforge_session"))
            actor = f"admin:{auth_session.user_id}" if auth_session is not None else "local-dashboard"
            resumed = runtime.jobs.retry_approved_asset_validation(
                job_id, package_identity=identity, actor=actor,
            )
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found") from error
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
        return {"job_id": job_id, "state": resumed.state.value, "resumed_from": JobState.ASSET_ACQUISITION.value, "script_identity": identity}

    @app.get("/api/content-profiles", tags=["videos"])
    def content_profiles() -> dict[str, object]:
        config = application_settings.pipeline.codex
        identities = sorted(set(config.voice_profiles) | {config.default_channel_identity})
        claude = application_settings.pipeline.claude
        suffix = "" if claude.enabled else " — not enabled"
        models = [
            {"id": "sonnet-medium", "label": "Claude Sonnet 5.5 · medium effort (default)" + suffix, "enabled": claude.enabled},
            {"id": "opus", "label": "Claude Opus 5.5 · high effort" + suffix, "enabled": claude.enabled},
            {"id": "gpt-sol", "label": "Codex · " + config.model, "enabled": True},
        ]
        default_model = DEFAULT_SCRIPT_MODEL if claude.enabled else "gpt-sol"
        return {"default_identity": config.default_channel_identity, "script_models": models, "default_script_model": default_model, "profiles": [{"identity": name, "uses_default": name not in config.voice_profiles} for name in identities]}

    @app.get("/api/voices", tags=["voices"])
    def list_voices() -> list[dict[str, str]]:
        """Expose only configured local voices; no remote voice service is used."""
        pipeline = application_settings.pipeline
        options = [
            {"id": voice, "label": voice.replace("_", " ").title(), "provider": "kokoro"}
            for voice in pipeline.kokoro.voices
            if pipeline.kokoro.enabled and pipeline.voice_provider in {"kokoro", "hybrid", "hybrid-http"}
        ]
        if pipeline.voice_provider in {"piper", "piper-http", "hybrid", "hybrid-http"}:
            label = "Piper local voice" if pipeline.voice_provider == "piper-http" else "Piper reliable fallback"
            options.append({"id": "piper", "label": label, "provider": pipeline.voice_provider})
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

    @app.get("/api/jobs/{job_id}/diagnostics", tags=["jobs"])
    def get_job_diagnostics(job_id: str) -> dict[str, object]:
        try:
            job = runtime.jobs.get(job_id)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found") from error
        events = runtime.events.list_for_job(job_id, limit=2_000)
        return {"job_id": job_id, **summarize_stage_events(events, attempt_count=job.attempt_count, failure_message=job.failure_message)}

    @app.get("/api/jobs/{job_id}/diagnostics.jsonl", tags=["jobs"])
    def download_job_diagnostics(job_id: str) -> Response:
        try:
            runtime.jobs.get(job_id)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found") from error
        rows = [
            json.dumps({"event_type": event.event_type, "created_at": _as_ist(event.created_at).isoformat(), **event.details}, sort_keys=True)
            for event in runtime.events.list_for_job(job_id, limit=2_000)
            if event.event_type in {"stage_started", "stage_execution", "job_retry_scheduled", "job_error", "job_claimed", "job_claim_released"}
        ]
        return Response("\n".join(rows) + ("\n" if rows else ""), media_type="application/x-ndjson", headers={"Content-Disposition": f'attachment; filename="{job_id}-diagnostics.jsonl"'})

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
            if gate is ApprovalGate.SCRIPT:
                package = runtime.artifacts.get(job_id, JobState.CONTENT_GENERATING, "content_package")
                if package is None:
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="script is unavailable")
                if reviewed_identity is not None and reviewed_identity != package.checksum_sha256:
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="script changed; reload before approving")
                reviewed_identity = package.checksum_sha256
            if gate is ApprovalGate.PREVIEW:
                manifest = runtime.artifacts.get(job_id, JobState.PREVIEW_RENDERING, "preview_manifest")
                if manifest is None:
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="preview manifest is unavailable")
                import json
                preview_identity = str(json.loads(Path(manifest.path).read_text(encoding="utf-8"))["render_identity"])
                if reviewed_identity is not None and reviewed_identity != preview_identity:
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="preview changed; reload before approving")
                reviewed_identity = preview_identity
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

    @app.post("/api/jobs/{job_id}/scene-revisions", status_code=status.HTTP_201_CREATED, tags=["jobs"])
    def revise_scene(job_id: str, revision: SceneRevisionRequest) -> dict[str, object]:
        """Fork one scene into a paused draft; the original job stays immutable."""
        changes = revision.model_dump(exclude_none=True, exclude={"scene_id", "expected_content_sha256", "actor"})
        try:
            child_id, identity = create_scene_revision(
                runtime, job_id, scene_id=revision.scene_id,
                expected_content_sha256=revision.expected_content_sha256,
                actor=revision.actor, changes=changes,
            )
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found") from error
        except StaleSceneRevision as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
        except (ValueError, ValidationError, ProviderValidationError) as error:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
        return {"job_id": child_id, "parent_job_id": job_id, "scene_id": revision.scene_id, "reviewed_identity": identity, "state": JobState.SCRIPT_APPROVAL_REQUIRED.value}

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
        media_type = {
            ".mp4": "video/mp4", ".png": "image/png", ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg", ".wav": "audio/wav",
        }.get(path.suffix.lower(), "application/json")
        return FileResponse(path, media_type=media_type)

    return app
