"""Configurable deterministic providers used exclusively for local development and tests."""

from __future__ import annotations

import hashlib
import io
import struct
import wave
import zlib
from datetime import UTC, datetime
from pathlib import Path
import math
import re

from tubeforge.core.config import FakeProviderConfig
from tubeforge.core.errors import ProviderAuthenticationError, ProviderCancellation, ProviderValidationError, RetryableProviderError
from tubeforge.domain.contracts import (AssetCandidate, AssetSearchRequest, CitedClaim, ClaimReviewStatus, ConfidenceLevel, ContentPackage, ContentRequest, PublishRequest, PublishResult, ScenePlan, ScriptSection, ThumbnailBrief, VideoMetadata, VoiceRequest, VoiceResult)


class FakeContentProvider:
    """Return a stable valid package and expose injectable failure modes."""

    def __init__(self, failure: Exception | None = None) -> None:
        self.calls = 0
        self.failure = failure

    def generate_package(self, request: ContentRequest) -> ContentPackage:
        self.calls += 1
        if self.failure:
            raise self.failure
        points = request.notes or tuple(item.strip() for item in request.angle.splitlines() if item.strip()) or (request.angle,)
        # The offline/local provider must still produce a useful storyboard.
        # Its former single repeated "context" sentence was only a test fixture
        # and made every deployed video look broken.
        scene_count = min(6, max(3, len(points) + 2))
        scene_topics = ("Why this matters", *points, "What to do next")[:scene_count]
        # Piper's measured local pace is roughly 3.3 words/second for these
        # concise lines. Shorts use complete sentences and a slightly lower
        # planning rate so the final narration remains inside 30–55 seconds.
        words_per_second = 3.1 if request.aspect_ratio == "9:16" else 2.15
        target_words = max(18, round(request.target_duration_seconds * words_per_second / scene_count))
        sections = tuple(
            ScriptSection(
                section_id=f"section-{index}",
                scene_id=f"scene-{index}",
                narration=_local_scene_narration(request.topic, point, index, scene_count, target_words, shorts=request.aspect_ratio == "9:16"),
                claim_ids=(),
                contains_factual_claims=False,
            )
            for index, point in enumerate(scene_topics, 1)
        )
        scenes = tuple(
            ScenePlan(
                scene_id=f"scene-{index}",
                visual_type="illustration",
                search_queries=(f"{request.visual_style} {request.topic} {point}",),
                on_screen_text=point[:120],
                fallback_visual="local_scene_illustration",
            )
            for index, point in enumerate(scene_topics, 1)
        )
        claim = CitedClaim(claim_id="operator-brief", text=f"Operator-provided brief for {request.topic}.", source_ids=(request.sources[0].source_id,), confidence=ConfidenceLevel.HIGH, review_status=ClaimReviewStatus.VERIFIED, human_review_required=False)
        return ContentPackage(schema_version="1.0", request=request, claims=(claim,), script_sections=sections, scene_plans=scenes, metadata=VideoMetadata(title_options=(request.topic,), description=request.angle), thumbnail_brief=ThumbnailBrief(text_options=(request.topic[:40],), visual_direction=f"Cinematic local illustration for {request.topic}", accessibility_description=f"Scene-specific illustration for {request.topic}"))


class FixedScriptContentProvider:
    """Deterministic six-scene package for offline and real-media smoke jobs."""

    _SCENES = (
        ("A question appears: how can one idea become a finished narrated video, entirely on a local machine? This demonstration follows every practical step from the opening prompt to the final file.", "A glowing question mark above a compact home server at dawn"),
        ("TubeForge begins with a structured plan, dividing the story into clear scenes with a visual purpose for each one. The ordered plan keeps narration, evidence, and pictures connected while the job moves forward.", "A storyboard wall with six distinct cinematic frames"),
        ("Next, local speech synthesis turns every line into real narration, without sending the script to a paid voice service. Piper writes ordinary wave audio that the pipeline can measure and validate directly.", "Sound waves flowing from a small computer into studio headphones"),
        ("The measured audio duration becomes the clock, so every image stays on screen for exactly the scene it explains. Timing comes from the produced sound itself, rather than from a hopeful estimate.", "A precise editing timeline aligned with an audio waveform"),
        ("Each scene receives its own validated visual, while checksums and atomic promotion protect incomplete files from becoming artifacts. Distinct colors and compositions make every transition visible, even when the system is offline.", "Six colorful image cards passing through a validation checkpoint"),
        ("Finally, FFmpeg joins the visuals, captions, and narration into a playable video that can safely resume after interruption. The completed file contains real audio and video streams, ready for inspection before publication.", "A finished video frame emerging from gears labeled audio visuals captions"),
    )
    _MINIMUM_ENGINEER_SCENES = (
        ("Want to become useful as a software engineer now? Ignore the endless tool list. Build a compact foundation you can use to ship, debug, and explain a real project.", "A focused software engineer at a desk, surrounded by only five clear skill cards"),
        ("First, choose one language and go deep. Python, JavaScript, Java, or Go can work. Learn functions, testing, debugging, packages, and clean interfaces before chasing another language.", "One programming language card becoming a working application with tests and a debugger"),
        ("Second, learn Linux well enough to live in the terminal. Navigate files, manage processes, read logs, use permissions, environment variables, SSH, and simple shell pipelines.", "A dark Linux terminal showing files, process logs, permissions, and an SSH connection"),
        ("Third, learn Git and Docker together. Git protects your changes. Docker makes your application run consistently on your laptop, a teammate's machine, and a server.", "A Git branch merging into a Docker container that runs identically on laptop and cloud server"),
        ("Fourth, understand practical AWS basics: IAM, compute, storage, networking, logs, and costs. Deploy one small service, then trace a request from browser to logs and back.", "A simple AWS cloud diagram with IAM, compute, storage, networking, and CloudWatch-style logs"),
        ("Finally, use data structures and algorithms as problem-solving practice, not a memorization contest. Arrays, hash maps, stacks, queues, trees, sorting, and Big O are enough to start. Build projects, explain tradeoffs, and repeat.", "A roadmap ending in a deployed project, with DSA building blocks feeding into a confident engineer"),
    )

    def __init__(self) -> None:
        self.calls = 0

    def generate_package(self, request: ContentRequest) -> ContentPackage:
        self.calls += 1
        scenes_source = self._MINIMUM_ENGINEER_SCENES if request.prompt_version == "minimum-engineer-v1" else self._SCENES
        claim = CitedClaim(claim_id="claim-1", text=f"This deterministic demonstration explains {request.topic}.", source_ids=(request.sources[0].source_id,), confidence=ConfidenceLevel.HIGH, review_status=ClaimReviewStatus.VERIFIED, human_review_required=False)
        sections = tuple(ScriptSection(section_id=f"section-{index}", narration=narration, scene_id=f"scene-{index}", claim_ids=("claim-1",), contains_factual_claims=True) for index, (narration, _) in enumerate(scenes_source, 1))
        scenes = tuple(ScenePlan(scene_id=f"scene-{index}", visual_type="illustration", search_queries=(visual,), fallback_visual="synthetic_illustration") for index, (_, visual) in enumerate(scenes_source, 1))
        description = "A focused one-minute roadmap for the practical modern software-engineering baseline." if scenes_source is self._MINIMUM_ENGINEER_SCENES else "A deterministic local TubeForge pipeline demonstration."
        thumbnail = ("ENGINEER MINIMUM", "A focused software engineering toolkit") if scenes_source is self._MINIMUM_ENGINEER_SCENES else ("LOCAL VIDEO", "Six-scene local video pipeline")
        return ContentPackage(schema_version="1.0", request=request, claims=(claim,), script_sections=sections, scene_plans=scenes, metadata=VideoMetadata(title_options=(request.topic,), description=description, tags=("software engineering", "AWS", "Linux", "Docker", "DSA")), thumbnail_brief=ThumbnailBrief(text_options=(thumbnail[0],), visual_direction=thumbnail[1], accessibility_description=thumbnail[1]))


class FakeVoiceProvider:
    """Write synthetic audio bytes atomically and return their checksum."""

    def __init__(self, settings: FakeProviderConfig, failure: Exception | None = None) -> None:
        self.settings, self.failure, self.calls = settings, failure, 0

    def synthesize(self, request: VoiceRequest) -> VoiceResult:
        self.calls += 1
        if self.failure:
            raise self.failure
        # Match a conservative narration rate so fake E2E videos exercise the
        # requested duration contract rather than rendering a sub-second clip.
        words = max(1, len(re.findall(r"\b\w+\b", request.text)))
        frames = max(800, round(words / _FAKE_WORDS_PER_SECOND * 8_000))
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as stream:
            stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(8_000)
            stream.writeframes(b"\x00\x00" * frames)
        payload = buffer.getvalue()
        destination = Path(request.output_path) if request.output_path else self.settings.artifact_root / "voice" / f"{request.phrase_id or request.section_id}.wav"
        _atomic_write(destination, payload)
        return VoiceResult(artifact_path=str(destination), duration_seconds=frames / 8_000, checksum_sha256=_checksum(payload), provider_name="fake-voice")


class FakeMediaProvider:
    """Return a rights-bearing synthetic media candidate without downloading."""

    def __init__(self, settings: FakeProviderConfig, failure: Exception | None = None) -> None:
        self.settings, self.failure, self.calls = settings, failure, 0

    def search(self, request: AssetSearchRequest) -> list[AssetCandidate]:
        self.calls += 1
        if self.failure:
            raise self.failure
        digest = _checksum("|".join(request.queries).encode())[:12]
        path = self.settings.artifact_root / "media" / f"{digest}.png"
        # Derive a stable, high-contrast colour from the scene query. Different
        # scene descriptions therefore produce visibly different local assets.
        rgb = tuple(48 + int(digest[offset : offset + 2], 16) % 176 for offset in (0, 2, 4))
        # These are production-safe local fallbacks, not one-pixel test
        # fixtures.  Render at HD so the final profile does not have to enlarge
        # a 640px source into a noticeably soft 1080p frame.
        _atomic_write(path, _scene_png(1280, 720, rgb, digest))
        return [AssetCandidate(provider_asset_id=f"fake-{digest}", source_url=f"https://example.invalid/assets/{digest}", download_url=f"https://example.invalid/assets/{digest}.png", local_path=str(path), media_type="image", width=1280, height=720, author="TubeForge fake", license_name=self.settings.media_license, attribution_text="Synthetic local illustration", retrieved_at=datetime.now(UTC))]


class FakePublisher:
    """Deterministically maps idempotency keys to receipts without network activity."""

    def __init__(self, failure: Exception | None = None) -> None:
        self.failure, self.calls, self._results = failure, 0, {}

    def upload(self, request: PublishRequest) -> PublishResult:
        self.calls += 1
        if self.failure:
            raise self.failure
        if request.idempotency_key not in self._results:
            digest = _checksum(request.idempotency_key.encode())[:16]
            self._results[request.idempotency_key] = PublishResult(platform=request.platform, remote_id=f"fake-{digest}", privacy=request.privacy, receipt_id=f"receipt-{digest}")
        return self._results[request.idempotency_key]


class FakeYouTubePublisher:
    """Deterministic in-memory M13 fake; it never contacts YouTube."""
    def __init__(self, channel_id: str = "fake-channel", failure: Exception | None = None, *, outcomes: dict[str, list[Exception | None]] | None = None) -> None:
        self.channel_id, self.failure, self.creates, self.create_calls, self.metadata_calls, self.thumbnail_calls, self.reconcile_calls, self.channel_lookup_calls, self.analytics_calls = channel_id, failure, 0, 0, 0, 0, 0, 0, 0
        self.outcomes = outcomes or {}; self.videos: dict[str, dict[str, object]] = {}
    def _outcome(self, operation: str) -> None:
        values = self.outcomes.get(operation, [])
        if values:
            failure = values.pop(0)
            if failure: raise failure
        if self.failure: raise self.failure
    def authenticated_channel_id(self) -> str:
        self.channel_lookup_calls += 1; self._outcome("channel_lookup"); return self.channel_id
    def create_or_resume_video(self, request: PublishRequest, *, resume_token: str | None = None, cancellation_requested=None) -> str:
        self.create_calls += 1
        self._outcome("create")
        if cancellation_requested and cancellation_requested(): raise ProviderCancellation("fake upload cancelled")
        key = request.idempotency_key; remote_id = f"fake-{_checksum(key.encode())[:16]}"
        if remote_id not in self.videos: self.creates += 1; self.videos[remote_id] = {"privacy": request.privacy.value}
        return remote_id
    def apply_metadata(self, remote_video_id: str, request: PublishRequest) -> None:
        self.metadata_calls += 1
        self._outcome("metadata")
        self.videos[remote_video_id]["metadata"] = request.metadata.model_dump(mode="json")
    def set_thumbnail(self, remote_video_id: str, thumbnail_path: str) -> None:
        self.thumbnail_calls += 1
        self._outcome("thumbnail")
        self.videos[remote_video_id]["thumbnail"] = thumbnail_path
    def fetch_video(self, remote_video_id: str) -> dict[str, object] | None:
        self.reconcile_calls += 1; self._outcome("reconcile"); return self.videos.get(remote_video_id)
    def fetch_publication_snapshot(self, remote_video_id: str):
        from tubeforge.domain.contracts import RemotePublicationSnapshot
        value = self.fetch_video(remote_video_id)
        if value is None: return RemotePublicationSnapshot(video_id=remote_video_id, exists=False)
        return RemotePublicationSnapshot(video_id=remote_video_id, exists=True, processing=value.get("processing", "succeeded"), privacy=value.get("privacy"), title=(value.get("metadata") or {}).get("title_options", [value.get("title")])[0], description=(value.get("metadata") or {}).get("description", value.get("description")), tags=tuple((value.get("metadata") or {}).get("tags", value.get("tags", ()))) if value.get("tags") is not None or value.get("metadata") else None, thumbnail_present=bool(value.get("thumbnail")) if "thumbnail" in value else None)

    def fetch_video_analytics(self, remote_video_id, channel_id, report_start, report_end):
        from datetime import UTC, datetime
        from tubeforge.domain.contracts import AnalyticsMetric, AnalyticsSnapshotData
        self.analytics_calls += 1; self._outcome("analytics")
        scripted = self.videos.get(remote_video_id, {}).get("analytics", {})
        metrics = {name: AnalyticsMetric.model_validate(value) for name, value in scripted.items()}
        return AnalyticsSnapshotData(video_id=remote_video_id, channel_id=channel_id, report_start=report_start, report_end=report_end, observed_at=datetime.now(UTC), metrics=metrics, completeness="complete" if metrics else "unavailable")


def _atomic_write(destination: Path, payload: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(destination)


_FAKE_WORDS_PER_SECOND = 2.4


def _local_scene_narration(topic: str, point: str, index: int, total: int, target_words: int, *, shorts: bool = False) -> str:
    """Create concise readable local narration from the operator's own brief."""
    lead = (f"Stop scrolling. {topic} has one practical lesson you can use now. " if shorts and index == 1 else f"{topic}. " if index == 1 else "")
    core = f"{lead}{point}. Focus on the practical meaning, then connect it to one decision you can make in a real project. "
    closing = "Keep the explanation concrete, test the result, and move to the next step with confidence."
    if shorts:
        sentences = [core.strip(), closing]
        filler = "Use one clear example, show the result, and keep the pace moving."
        while len(" ".join(sentences).split()) < target_words:
            sentences.append(filler)
        return " ".join(sentences)
    words = (core + closing).split()
    filler = ["Use", "small", "examples", "and", "clear", "tradeoffs", "so", "the", "idea", "remains", "useful", "when", "you", "build", "and", "debug", "software."]
    while len(words) < target_words:
        words.extend(filler)
    return " ".join(words[:target_words])


def _checksum(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _solid_png(width: int, height: int, color: tuple[int, int, int]) -> bytes:
    """Build a valid, dependency-free RGB PNG for offline media tests."""
    raw = b"".join(b"\x00" + bytes(color) * width for _ in range(height))

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def _scene_png(width: int, height: int, color: tuple[int, int, int], seed: str) -> bytes:
    """Build a scene-specific HD illustration without embedded unreadable text."""
    value = int(seed, 16)
    raw = bytearray()
    accent = tuple(min(255, component + 58) for component in color)
    for y in range(height):
        for x in range(width):
            wave = ((x * (value % 7 + 2) + y * (value % 11 + 3)) // 36) % 26
            vignette = int(44 * (((x - width / 2) / width) ** 2 + ((y - height / 2) / height) ** 2))
            raw.extend((
                max(0, min(255, color[0] - vignette + wave // 3)),
                max(0, min(255, color[1] - vignette + wave)),
                max(0, min(255, color[2] - vignette + wave * 2)),
            ))
    # Add stable circuit-like paths, nodes, and an asymmetric focal glow; each
    # scene has a distinct seed. Captions remain the only rendered text, which
    # avoids low-quality synthetic text baked into source art.
    pixels = bytearray()
    for y in range(height):
        pixels.append(0)
        row = y * width * 3
        pixels.extend(raw[row:row + width * 3])
    for index in range(10):
        x = 38 + (value >> (index * 3)) % (width - 76)
        y = 32 + (value >> (index * 5)) % (height - 64)
        for dx in range(-5, 6):
            for dy in range(-5, 6):
                px, py = x + dx, y + dy
                if 0 <= px < width and 0 <= py < height and dx * dx + dy * dy <= 25:
                    offset = py * (width * 3 + 1) + 1 + px * 3
                    pixels[offset:offset + 3] = bytes(accent)
        for step in range(48):
            px = min(width - 1, x + step)
            py = min(height - 1, y + (step if index % 2 else 0))
            offset = py * (width * 3 + 1) + 1 + px * 3
            pixels[offset:offset + 3] = bytes(accent)
    focus_x = width // 3 + value % (width // 3)
    focus_y = height // 3 + (value >> 7) % (height // 3)
    for y in range(max(0, focus_y - 110), min(height, focus_y + 110)):
        for x in range(max(0, focus_x - 110), min(width, focus_x + 110)):
            distance = ((x - focus_x) ** 2 + (y - focus_y) ** 2) ** 0.5
            if distance > 110:
                continue
            strength = int((1 - distance / 110) * 72)
            offset = y * (width * 3 + 1) + 1 + x * 3
            pixels[offset] = min(255, pixels[offset] + strength)
            pixels[offset + 1] = min(255, pixels[offset + 1] + strength)
            pixels[offset + 2] = min(255, pixels[offset + 2] + strength)
    def chunk(kind: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(bytes(pixels), level=6)) + chunk(b"IEND", b"")


__all__ = ["FakeContentProvider", "FixedScriptContentProvider", "FakeMediaProvider", "FakePublisher", "FakeVoiceProvider", "ProviderAuthenticationError", "ProviderValidationError", "RetryableProviderError"]
