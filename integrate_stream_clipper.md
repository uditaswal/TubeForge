# TubeForge — Integrate `stream-clipper` as Native Short-Form / Stream-Clipping Pipeline

You are working on my existing **TubeForge** project.

There are two codebases available on this machine:

* Current main project: `docker/tubeforge/Youtube_Video_Producer`
* Existing open-source donor project: `docker/stream-clipper`

Your job is to **integrate the useful functionality from `stream-clipper` into TubeForge**, rather than simply putting the second application inside the first repository.

## Product Goal

TubeForge is becoming a fully automated content-production and multi-platform publishing system.

It should eventually support two major content-generation modes:

### Mode A — AI-generated content

Existing TubeForge functionality:

topic / idea
→ research/content generation
→ script
→ narration
→ assets
→ video generation
→ metadata
→ thumbnail
→ publishing
→ analytics
→ learning

This existing functionality must continue working.

### Mode B — Stream / long-video clipping

New functionality being introduced from `stream-clipper`:

streamer/channel/video source
→ discover new stream/video
→ download/analyze content
→ identify interesting/high-engagement moments
→ select clips
→ convert them into vertical short-form videos
→ captions/subtitles/layout
→ metadata
→ publish to platforms
→ analytics / learning

Initially I want to manually provide a stream/video URL through the TubeForge dashboard.

Later, TubeForge should support configured creators/channels such as:

* YouTube creator/channel
* Kick streamer
* potentially Twitch
* other supported platforms

TubeForge will periodically check those sources and automatically process newly available content.

The architecture created now MUST make that future extension straightforward.

---

# IMPORTANT INTEGRATION PRINCIPLE

Do NOT treat `stream-clipper` as a second standalone application.

Do NOT simply:

* copy its entire folder into TubeForge
* run another independent web application
* create another unrelated database
* create another dashboard
* create an isolated "stream clipper service" unless there is a strong technical reason
* duplicate functionality already provided by TubeForge

Instead:

1. Inspect both repositories carefully.
2. Understand what functionality `stream-clipper` actually provides.
3. Identify reusable algorithms/modules.
4. Port/refactor those capabilities into TubeForge's existing architecture.
5. Reuse TubeForge infrastructure wherever practical:

   * configuration
   * database
   * job model
   * worker/orchestrator
   * leases/execution safety
   * artifact storage
   * FFmpeg abstraction
   * logging
   * publishing
   * dashboard/API
   * checkpoints/resume
   * analytics

The result should feel like TubeForge was designed from the beginning to support both AI-generated videos and source-content clipping.

---

# PHASE 0 — Repository Analysis FIRST

Before changing code, inspect BOTH repositories thoroughly.

For TubeForge determine:

* project/module structure
* FastAPI/API structure
* dashboard/UI implementation
* job models
* DB models/repositories
* migrations
* pipeline/orchestrator
* worker implementation
* execution leases
* checkpoints
* artifact handling
* FFmpeg/rendering functionality
* configuration system
* publishing architecture
* current tests
* Dockerfile/docker-compose setup

For `stream-clipper`, determine:

* how URLs/streams are accepted
* supported sources/platforms
* download mechanism
* yt-dlp or equivalent usage
* Twitch/Kick/YouTube handling if present
* transcript generation
* audio analysis
* scene detection
* highlight detection
* engagement/top-moment detection
* chat-based highlight detection if any
* LLM usage
* clip scoring/ranking
* FFmpeg clipping
* aspect-ratio transformation
* speaker/face tracking
* subtitles/captions
* vertical 9:16 rendering
* output format
* temporary file handling
* scheduling
* dependencies
* API/UI
* tests
* Docker/runtime requirements

Also identify license information for `stream-clipper`.

Do not blindly copy code whose license is incompatible with this project.

Create a concise integration assessment before implementation containing:

1. useful `stream-clipper` components
2. components that should NOT be imported
3. duplicated functionality
4. dependency impact
5. proposed TubeForge architecture
6. migration/database changes
7. implementation sequence
8. risks

Then proceed with implementation unless there is a genuine blocking issue.

---

# TARGET ARCHITECTURE

Introduce the concept of a **content source / ingestion mode** into TubeForge.

Avoid tightly coupling TubeForge to "stream clipping".

Prefer abstractions along these lines if they fit the existing codebase:

```text
ContentSource
    AI_GENERATED
    DIRECT_MEDIA
    YOUTUBE
    KICK
    TWITCH
    ...

SourceAsset / SourceMedia
    source URL
    provider
    external content ID
    creator/channel ID
    title
    published_at
    duration
    metadata
```

A job should then be capable of using a source mode such as:

```text
GENERATED_CONTENT
SOURCE_CLIP
```

Exact names may differ if better terminology fits the existing architecture.

Do not over-engineer the domain model, but establish the abstraction now so future providers do not require a major rewrite.

---

# FIRST USER-FACING FEATURE

Add a new option to the existing TubeForge dashboard for creating a job from a source URL.

The user should be able to choose something equivalent to:

```text
Create Video

[ AI Generated Video ]
[ Clip Existing Video / Stream ]
```

For the clipping mode, initially accept:

```text
Source URL: _______________________

Number of clips: [default sensible value]

[Create Job]
```

Optional clip settings may be exposed only if already useful, but avoid clutter.

For the first milestone, a pasted URL is sufficient.

Do NOT implement a separate dashboard from `stream-clipper`.

Use TubeForge's existing dashboard.

---

# SOURCE PROVIDER ABSTRACTION

Create a source/provider abstraction so TubeForge does not directly scatter `yt-dlp`, YouTube-specific logic, Kick-specific logic, etc. throughout the pipeline.

Something conceptually similar to:

```python
class SourceProvider(Protocol):
    def can_handle(url: str) -> bool:
        ...

    def inspect(url: str) -> SourceMetadata:
        ...

    def acquire(url: str, destination: Path) -> AcquiredMedia:
        ...
```

Providers could eventually include:

```text
YouTubeSourceProvider
KickSourceProvider
TwitchSourceProvider
DirectMediaSourceProvider
```

Use functionality from `stream-clipper` where appropriate.

Do not implement every future provider unless the donor project already provides reliable working support.

---

# CLIPPING PIPELINE

Create a native TubeForge clipping pipeline.

Conceptually:

```text
SOURCE_DISCOVERY / SOURCE_INSPECTION
        ↓
SOURCE_ACQUISITION
        ↓
TRANSCRIPT / SIGNAL EXTRACTION
        ↓
HIGHLIGHT DETECTION
        ↓
CLIP RANKING
        ↓
CLIP EXTRACTION
        ↓
VERTICAL / SHORT-FORM RENDERING
        ↓
CAPTIONS
        ↓
METADATA
        ↓
PUBLICATION PACKAGE
```

Use existing TubeForge checkpoint/restart semantics.

Each expensive stage should be durable/idempotent where appropriate.

A failed worker should not force the entire video to be downloaded/analyzed again if valid artifacts/checkpoints already exist.

Respect TubeForge's existing ownership/lease fencing before promoting artifacts or mutating job state.

---

# HIGHLIGHT DETECTION

This is one of the most important pieces to extract from `stream-clipper`.

Determine exactly how it identifies good moments.

Possible signals include:

* chat activity
* viewer engagement
* transcript semantics
* speech excitement
* audio peaks
* scene changes
* laughter
* sentiment
* LLM ranking
* comments
* stream markers
* platform engagement data

Do NOT replace existing working highlight-selection logic with a simplistic implementation.

Port the donor project's useful logic cleanly.

Create an abstraction such as:

```text
HighlightCandidate
    start_time
    end_time
    score
    reasons
    evidence
```

Keep score evidence/provenance so we can later improve learning/ranking.

Where multiple signals exist, preserve them independently instead of collapsing everything into an unexplained score.

---

# CLIP RANKING

The pipeline should be capable of producing multiple candidates and selecting the strongest N.

For example:

```text
Candidate 1: 0.91
Candidate 2: 0.87
Candidate 3: 0.73
...
```

Avoid heavily overlapping clips.

Store enough information so later TubeForge analytics can correlate:

```text
highlight prediction
vs
actual views
watch time
retention
likes
shares
```

This will eventually allow TubeForge to learn which predicted moments perform well.

Do NOT attempt to build the complete learning algorithm in this milestone.

Just preserve the necessary provenance.

---

# VIDEO OUTPUT

Short-form clips should preferably support:

```text
9:16
1080x1920 or configurable equivalent
H.264
AAC
platform-safe FPS
burned or selectable captions
```

Use TubeForge's existing FFmpeg infrastructure wherever possible.

If `stream-clipper` has substantially better FFmpeg logic for:

* crop/reframe
* subtitles
* speaker framing
* face tracking
* layouts
* zoom
* transitions

extract those capabilities into reusable renderer components.

Do not introduce duplicate FFmpeg wrappers unless necessary.

---

# ARTIFACT STORAGE

Clip artifacts must use TubeForge's normal artifact structure.

For one source video producing several clips, use a clear structure such as:

```text
job/
    source/
        source.mp4
        metadata.json

    analysis/
        transcript.json
        highlight_candidates.json

    clips/
        clip_001/
            raw.mp4
            final.mp4
            metadata.json

        clip_002/
            ...
```

Adapt naming to existing TubeForge artifact conventions.

Avoid storing large binaries in the database.

---

# DATA MODEL

Extend TubeForge's DB model minimally to represent source-based jobs.

Potential information:

```text
source_type
source_provider
source_url
source_external_id
source_creator_id
source_published_at
source_metadata

clip_index
clip_start
clip_end
clip_score
clip_score_details
```

Do not blindly add all fields if structured JSON or existing models make more sense.

Create proper Alembic migration(s).

Migration must work:

```text
existing DB → new schema
fresh DB → migration head
```

---

# FUTURE CREATOR MONITORING

DO NOT fully implement the scheduler unless it naturally falls out of existing donor functionality and remains small.

However, build the source model now so the following future feature does NOT require refactoring:

```text
CreatorSource

provider = youtube
creator_url = ...
enabled = true
check_interval = ...
last_checked_at = ...
last_seen_content_id = ...
```

Future workflow:

```text
every X minutes

        ↓

check configured creator

        ↓

new stream/video?

     no → finish
     yes

        ↓

create TubeForge source-clip job

        ↓

download / inspect

        ↓

find strongest moments

        ↓

produce shorts

        ↓

publish
```

The check must eventually be idempotent.

The same source video must not accidentally generate duplicate jobs unless explicitly requested.

Design for this now.

---

# PLATFORM PUBLISHING

Do not tightly couple clipping to YouTube Shorts.

A generated clip should become a normal TubeForge publication asset capable of eventually targeting:

```text
YouTube Shorts
Instagram Reels
Facebook Reels
TikTok
X
other platforms
```

If TubeForge's publisher architecture currently assumes YouTube only, make only the minimum safe abstraction changes necessary to stop the clipping pipeline from depending directly on YouTube.

Do NOT implement all social publishers in this milestone.

---

# DOCKER

TubeForge remains the primary Docker application.

Review dependencies required by `stream-clipper`.

Prefer incorporating them into the existing TubeForge worker image.

Likely examples:

```text
FFmpeg
ffprobe
yt-dlp
Python libraries
caption/transcription dependencies
```

Do NOT run the entire old `stream-clipper` container inside TubeForge unless there is a strong architectural reason.

If some component genuinely requires isolation, explain why before doing so.

The expected end state is still approximately:

```text
TubeForge web
TubeForge worker
TubeForge migrate
```

rather than a pile of independent containers.

---

# RESOURCE CONSTRAINT

This application runs on a relatively modest Debian home server.

Avoid architectures that require permanently running heavyweight ML models.

Where expensive AI functionality is required, keep providers configurable so TubeForge can use:

```text
local lightweight model
OR
external AI API
```

Heavy work must remain queue/worker-based.

Do not block the FastAPI web process while downloading, analyzing or rendering content.

---

# SECURITY

Treat pasted URLs as untrusted input.

Prevent obvious problems including:

* arbitrary local file reads
* `file://` input
* shell injection
* FFmpeg argument injection
* command interpolation
* unsafe output paths
* path traversal
* uncontrolled redirects where practical

Use subprocess argument arrays.

Do not use `shell=True` with user-controlled values.

Do not log secrets/cookies/authentication tokens.

---

# EXISTING TUBEFORGE RELIABILITY GUARANTEES

Do not regress existing TubeForge safety features.

In particular preserve:

* renewable job leases
* global heavy-work lease
* ownership fencing
* durable checkpoints
* stale-worker protection
* restart/resume
* atomic artifact promotion
* cancellation behavior
* DB migrations
* existing tests

Any new expensive clipping stages must cooperate with these mechanisms.

---

# CODE QUALITY

Avoid one giant `stream_clipper.py`.

Separate responsibilities.

A likely structure could resemble:

```text
pipeline/
    sources/
        base.py
        youtube.py
        kick.py
        direct.py

    clipping/
        highlights.py
        ranking.py
        transcript.py
        renderer.py
        models.py
```

But inspect the current repository first and choose the structure that best matches the existing architecture.

Prefer existing TubeForge conventions over this example.

---

# DEPENDENCY CLEANUP

Do NOT copy `stream-clipper`'s dependency file wholesale.

Determine which dependencies are actually needed.

For every significant new dependency, state:

```text
dependency
why it is required
where it is used
whether an existing TubeForge dependency could replace it
```

Remove dead donor-project dependencies.

---

# TESTS

Add tests covering at minimum:

### Source URL

* valid supported URL
* unsupported URL
* malformed URL
* dangerous URL/path rejection

### Provider

* provider selection
* metadata inspection
* acquisition mocking
* stable external content ID

### Job creation

* AI-generated jobs continue working
* source-clip jobs can be created
* source metadata persists

### Highlight analysis

* donor highlight logic produces candidates
* ranking deterministic where expected
* overlapping candidate handling

### Clip pipeline

* source checkpoint reuse
* restart/resume
* cancellation
* ownership loss
* stale worker cannot promote output
* multiple clip outputs

### Rendering

* FFmpeg command construction
* expected aspect ratio
* valid output validation
* partial artifact cleanup

### Migrations

* migration head
* fresh database
* existing database upgrade path

Do not require real network access in normal unit tests.

Use fixtures/mocks/sample media.

If practical, add an opt-in integration smoke test that uses a small public/sample media URL or local fixture.

---

# BACKWARD COMPATIBILITY

Existing AI-generated TubeForge jobs must continue working.

Do not break:

```text
existing configuration
existing database
existing API
existing dashboard
existing worker
existing Docker Compose workflow
existing tests
```

If architectural changes are required, make them incrementally.

---

# EXECUTION APPROACH

Work in this order:

## Step 1

Inspect both repositories.

## Step 2

Write an integration assessment.

## Step 3

Create the smallest sensible architecture boundary for source-based content.

## Step 4

Implement source URL job creation from the existing TubeForge dashboard/API.

## Step 5

Port source acquisition functionality from `stream-clipper`.

## Step 6

Port its highlight detection/ranking.

## Step 7

Port/refactor its short-form rendering/caption logic.

## Step 8

Connect output to TubeForge's existing artifact/publication pipeline.

## Step 9

Add DB migrations.

## Step 10

Add tests.

## Step 11

Run focused tests.

## Step 12

Run the complete existing TubeForge test suite.

## Step 13

Run `git diff --check`.

## Step 14

If dependencies/runtime changed, build the Docker images and run a smoke validation.

---

# DO NOT

Do not:

* delete working TubeForge features
* rewrite the application from scratch
* replace stable TubeForge infrastructure merely because `stream-clipper` has its own implementation
* blindly copy the donor repository
* preserve donor abstractions that no longer make sense
* create a second DB
* create a second dashboard
* bypass TubeForge's worker
* bypass leasing/checkpoint semantics
* introduce unnecessary microservices
* commit generated videos
* commit downloaded media
* commit secrets
* commit cookies
* commit API keys
* perform destructive Git operations

Do not commit or push unless explicitly requested.

---

# FINAL REPORT

When implementation is complete, provide:

## Architecture

Explain the resulting source/clipping architecture.

## Reused from `stream-clipper`

List exactly which capabilities/code concepts were ported.

## Not reused

Explain what was deliberately discarded and why.

## New files

List them.

## Modified files

List them.

## Database changes

Describe migrations/schema changes.

## Dependencies

List newly introduced runtime dependencies.

## Dashboard

Explain how I can manually submit a video/stream URL.

## Pipeline

Show the actual clipping lifecycle.

## Docker

Explain any image/Compose changes.

## Tests

Give exact test commands and results.

## Full suite

Give the complete TubeForge test result.

## Smoke test

Describe what was actually exercised.

## Remaining limitations

Clearly distinguish:

* implemented now
* scaffolded for later
* not implemented

## Recommended next milestone

Recommend the smallest next milestone toward:

```text
creator URL
→ periodic detection
→ automatically detect new content
→ identify top moments
→ create several shorts
→ publish automatically to multiple social platforms
```

Do not claim something works unless it was actually tested.

