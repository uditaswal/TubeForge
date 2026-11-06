"""Reference-only video contracts; never permission to reuse source footage."""
from __future__ import annotations

from datetime import datetime
import re
from typing import Literal
from urllib.parse import parse_qs, urlsplit

from pydantic import Field, field_validator, model_validator

from tubeforge.domain.contracts import DomainModel

VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


def canonical_reference_url(value: str) -> str:
    """Normalize an allowlisted YouTube video link without making a request.

    Actual fetching must still enforce public DNS/redirect rules. Normalization
    alone cannot establish network safety, access, captions or reuse rights.
    """
    if not isinstance(value, str) or len(value) > 2000 or any(ord(c) < 33 for c in value):
        raise ValueError("reference requires a public HTTPS YouTube video URL")
    url = urlsplit(value)
    if url.scheme != "https" or url.username or url.password or url.port not in {None, 443}:
        raise ValueError("reference requires HTTPS without credentials or a custom port")
    host = (url.hostname or "").lower()
    if host == "youtu.be":
        video_id = url.path.removeprefix('/')
    elif host in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        if url.path == '/watch':
            values = parse_qs(url.query, keep_blank_values=True).get('v', [])
            if len(values) != 1:
                raise ValueError("reference must identify exactly one video")
            video_id = values[0]
        else:
            match = re.fullmatch(r"/(?:shorts|embed|live)/([^/]+)", url.path)
            video_id = match[1] if match else ''
    else:
        raise ValueError("reference host must be YouTube")
    if not VIDEO_ID.fullmatch(video_id):
        raise ValueError("reference video ID is invalid")
    return f'https://www.youtube.com/watch?v={video_id}'


class TranscriptCue(DomainModel):
    start_seconds: float = Field(ge=0, allow_inf_nan=False)
    end_seconds: float = Field(gt=0, allow_inf_nan=False)
    text: str = Field(min_length=1, max_length=4000)

    @model_validator(mode='after')
    def meaningful_interval(self):
        if self.end_seconds <= self.start_seconds or not self.text.strip():
            raise ValueError('transcript cues require nonblank text and positive intervals')
        return self


class ReferenceSnapshot(DomainModel):
    schema_version: Literal['reference-video-v1'] = 'reference-video-v1'
    extractor_version: str = Field(min_length=1, max_length=100)
    reference_url: str = Field(max_length=2000)
    video_id: str = Field(pattern=r'^[A-Za-z0-9_-]{11}$')
    title: str = Field(min_length=1, max_length=500)
    creator: str = Field(min_length=1, max_length=300)
    duration_seconds: float = Field(gt=0, le=21600, allow_inf_nan=False)
    captured_at: datetime
    language: str = Field(pattern=r'^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$')
    transcript_origin: Literal['captions', 'supplied', 'local_transcription', 'unavailable']
    cues: tuple[TranscriptCue, ...] = Field(default=(), max_length=10000)
    limitations: tuple[str, ...] = Field(default=(), max_length=20)

    @field_validator('reference_url')
    @classmethod
    def normalize_url(cls, value):
        return canonical_reference_url(value)

    @model_validator(mode='after')
    def truthful_transcript(self):
        if self.reference_url != f'https://www.youtube.com/watch?v={self.video_id}':
            raise ValueError('snapshot video ID differs from reference URL')
        if not self.title.strip() or not self.creator.strip() or not self.extractor_version.strip():
            raise ValueError('snapshot metadata must be nonblank')
        if self.captured_at.utcoffset() is None:
            raise ValueError('capture time requires a timezone')
        if self.transcript_origin == 'unavailable':
            if self.cues or not self.limitations:
                raise ValueError('unavailable transcript requires a limitation and no cues')
        elif not self.cues:
            raise ValueError('available transcript requires timestamped cues')
        starts = tuple(c.start_seconds for c in self.cues)
        if starts != tuple(sorted(starts)) or any(c.end_seconds > self.duration_seconds for c in self.cues):
            raise ValueError('transcript cues must be ordered and inside source duration')
        if any(not item.strip() or len(item) > 500 for item in self.limitations):
            raise ValueError('limitations must be bounded nonblank observations')
        if sum(len(c.text.encode('utf-8')) for c in self.cues) > 1_000_000:
            raise ValueError('transcript exceeds snapshot byte budget')
        return self


class ReferenceIntakeRequest(DomainModel):
    """Proposed request shape, not an enabled endpoint or generation request."""
    reference_url: str = Field(max_length=2000)
    target_duration_seconds: int = Field(ge=600, le=900)
    channel_identity: str = Field(default='default', pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$')
    language: str = Field(default='en', pattern=r'^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$')

    supplied_cues: tuple[TranscriptCue, ...] = Field(default=(), max_length=10000)

    @field_validator('reference_url')
    @classmethod
    def normalize_url(cls, value):
        return canonical_reference_url(value)

    @model_validator(mode='after')
    def bounded_supplied_transcript(self):
        starts = tuple(c.start_seconds for c in self.supplied_cues)
        if starts != tuple(sorted(starts)) or sum(len(c.text.encode('utf-8')) for c in self.supplied_cues) > 1_000_000:
            raise ValueError('supplied transcript must be ordered and within the byte budget')
        return self


class ReferenceIntakeView(DomainModel):
    """Truthful read projection for a future durable intake service."""
    intake_id: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$')
    revision: int = Field(ge=1)
    request: ReferenceIntakeRequest
    state: Literal['pending', 'ready', 'needs_input', 'failed']
    snapshot: ReferenceSnapshot | None = None
    failure_code: Literal['unavailable', 'captions_unavailable', 'retrieval_failed', 'oversized', 'language_mismatch'] | None = None
    message: str | None = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode='after')
    def truthful_state(self):
        if self.snapshot is not None:
            if self.snapshot.reference_url != self.request.reference_url:
                raise ValueError('intake snapshot belongs to a different reference')
        if self.state == 'ready':
            if self.snapshot is None or self.snapshot.transcript_origin == 'unavailable' or self.failure_code or self.message:
                raise ValueError('ready intake requires a usable transcript without failure')
            if self.snapshot.language.casefold() != self.request.language.casefold():
                raise ValueError('ready intake transcript language differs from request')
        elif self.state == 'pending':
            if self.snapshot is not None or self.failure_code or self.message:
                raise ValueError('pending intake cannot claim captured metadata or failure')
        elif not self.failure_code or not self.message or not self.message.strip():
            raise ValueError('failed or needs-input intake requires an actionable failure')
        return self
