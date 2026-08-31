# TubeForge Overnight Autonomous Build Mission

You are the primary implementation engineer for TubeForge for this session. Work autonomously for as long as useful. Your goal is not to produce a plan and stop; your goal is to inspect the existing repository, preserve its existing architecture and safety mechanisms, implement the highest-value milestones end-to-end, run tests, fix failures, and leave the repository in a materially more complete and usable state.

## 0. Core outcome

TubeForge should become a self-hosted, provider-agnostic video factory where I can:

1. Log in to the dashboard securely.
2. Maintain a queue/backlog of video topics. Each topic has a title plus free-form notes/pointers that the content pipeline uses to produce the script.
3. Configure recurring schedules/cron rules such as twice per day. A schedule atomically picks the next eligible topic, creates a generation job, renders the video, runs quality checks, and publishes it to selected social accounts.
4. Manage multiple accounts per supported platform from the dashboard.
5. Generate a complete video end-to-end with as little human intervention as possible.
6. Publish one finished master/derived video to one or more configured accounts on YouTube, Instagram, Facebook, and Snapchat where the platform's official APIs actually support the requested behavior.
7. Track every generation, render, publish attempt, retry, failure, external post ID/URL, and schedule execution.
8. Continue supporting the existing TubeForge worker/job safety, leases, checkpoints, migrations, FFmpeg/Piper pipeline, tests, dashboard, publishing work, and any stream-clipping integration already present in the repository.

Do not assume my ChatGPT/Codex subscription is a runtime API available to TubeForge. Codex is being used to BUILD the system. Runtime AI providers must remain provider-agnostic and configured through proper APIs/local providers.

## 1. Operating rules for this overnight run

Do not stop after writing a plan. Implement.

At the beginning:

- Read AGENTS.md and all repository-local instructions.
- Inspect git status, current branch, recent commits, project layout, pyproject/package files, Docker Compose, migrations, tests, worker/orchestrator, dashboard, current publisher abstractions, configuration, and existing docs.
- Preserve all existing user changes. Never reset, clean, discard, or overwrite unrelated modifications.
- Do not rewrite working architecture just to make it prettier.
- Reuse current persistence, leases, checkpointing, job ownership fencing, heavy-work admission, cancellation, retry, and worker patterns instead of creating parallel mechanisms.
- Prefer small migrations and backward-compatible changes.
- Do not claim an integration works unless a real test, contract test, or clearly identified credential-blocked smoke test supports that claim.

Create and maintain these files while you work:

- `docs/overnight/MASTER_PLAN.md`
- `docs/overnight/STATUS.md`
- `docs/overnight/DECISIONS.md`
- `docs/overnight/BLOCKERS.md`
- `docs/overnight/TEST_RESULTS.md`

`STATUS.md` must contain a milestone table with: ID, scope, status (TODO/IN_PROGRESS/DONE/BLOCKED), tests, commit/hash if committed, and notes.

After every meaningful milestone:

- run focused tests;
- update STATUS.md;
- update TEST_RESULTS.md;
- record material design decisions;
- commit the milestone if the working tree and repository conventions make that safe.

Use descriptive commits such as `feat(auth): add dashboard session authentication` rather than one enormous final commit.

Never commit secrets, OAuth tokens, cookies, generated credentials, `.env`, private keys, or user media.

Do not push, deploy to production, delete external resources, publish real social posts, or make other irreversible external changes unless the repository already contains explicit safe test credentials/configuration authorizing that exact behavior. Live integrations should be implemented and testable without performing an unwanted real publication.

When an external credential or platform approval is missing, implement everything possible, add tests/mocks/contracts, document the exact blocker and setup steps, and continue with the next milestone instead of stopping the entire run.

## 2. Priority strategy

Prioritize a WORKING VERTICAL SLICE over partially implementing every feature.

The first major target is:

`authenticated dashboard -> topic queue -> scheduler picks topic -> script/video plan -> render -> quality gate -> publication package -> publisher dispatcher -> recorded result`

Make this path work locally/offline with fake providers where external credentials are unavailable. Then deepen real platform integrations and visual quality.

## 3. Milestone A - Repository audit and executable plan

Inspect the current code before adding anything. Identify what already exists for:

- job models and state machines;
- worker/orchestrator;
- database repositories;
- migrations;
- configuration;
- UI routes/templates/static JS;
- FFmpeg/ffprobe;
- Piper/TTS;
- captions;
- assets;
- LLM providers;
- YouTube publisher;
- analytics/learning;
- stream clipping;
- tests and fixtures.

Write the findings into MASTER_PLAN.md and map each requested capability to existing code vs new work.

Do not duplicate existing features.

## 4. Milestone B - VideoPlan / storyboard foundation

Introduce or complete a durable internal `VideoPlan` contract between content generation and rendering.

A useful plan should be able to represent at least:

- topic/title;
- user notes/pointers;
- target platform/content format;
- duration;
- aspect ratio;
- target audience;
- language;
- tone;
- hook;
- CTA;
- narration/script;
- style/pace;
- caption style;
- music intent;
- ordered scenes;
- per-scene duration;
- narration segment;
- visual intent;
- preferred visual strategy;
- fallback visual strategy;
- camera/motion direction;
- asset references;
- continuity/style identity metadata.

Use typed Pydantic/domain models and persist the plan or a durable serialized artifact/checkpoint so jobs can resume after restart.

The content pipeline should accept a queue topic title plus free-form pointers and turn them into a script and VideoPlan using the configured LLM provider. Keep fake/offline providers for tests.

## 5. Milestone C - Visual Router and scene asset strategy

Implement a provider-agnostic Visual Router instead of blindly generating AI video for every second.

For each scene, choose among capabilities such as:

- existing/local asset;
- stock image/video provider;
- screenshot or graphic;
- generated still image;
- generated video clip;
- motion graphics/text-only composition;
- fallback background + animated captions.

The routing policy should prefer the cheapest/reliable strategy capable of communicating the scene, and must have graceful fallbacks when premium AI video is not configured.

Create clean provider interfaces such as appropriate equivalents of:

- LLMProvider
- ImageProvider
- VideoProvider
- VoiceProvider
- AssetProvider
- Publisher

Do not couple the pipeline to one vendor.

The system must still be capable of producing a valid video using local/free components when no image/video generation API is configured, even if that output is visually simpler.

## 6. Milestone D - End-to-end render quality

Complete/strengthen the real rendering pipeline so a topic can produce a playable final video.

Use FFmpeg/ffprobe and the existing audio pipeline. Add or improve where appropriate:

- scene timing;
- scaling/cropping;
- 9:16 and 16:9 composition;
- still-image pan/zoom/Ken Burns movement;
- transitions only where they improve quality;
- animated text/title cards;
- captions/subtitles;
- voiceover alignment;
- music mixing and ducking;
- optional sound effects hooks;
- loudness normalization;
- final encode settings;
- publication-safe output names/paths;
- deterministic artifact promotion/checkpointing;
- clean failure recovery.

Avoid over-editing. Prefer coherent pacing and readable captions over excessive effects.

If word-level caption timing exists, reuse it. Otherwise introduce a provider/interface and a functional fallback.

## 7. Milestone E - Quality Gate

Before a video becomes publishable, add an automated validation stage that checks as many of these as practical:

- final file exists;
- ffprobe can parse it;
- expected duration tolerance;
- expected dimensions/aspect ratio;
- non-zero audio stream where narration is required;
- no unexpectedly long silent sections;
- no black/blank output caused by render failure;
- captions/artifacts exist when enabled;
- minimum resolution;
- file size is sane;
- no missing scene assets;
- no duplicate or obviously empty scene artifacts;
- platform-specific media constraints that can be validated locally.

Represent validation findings structurally. Hard failures should block publication. Soft warnings should be visible in the dashboard/job detail.

Where feasible, retry/regenerate only the failed stage rather than restarting the whole job.

## 8. Milestone F - Dashboard authentication

Protect the TubeForge dashboard from unauthorized use.

Implement a minimal, production-sensible local authentication system appropriate for a self-hosted app:

- no public self-registration by default;
- admin user model or equivalent;
- strong password hashing (Argon2id preferred; bcrypt acceptable if already used);
- login/logout;
- secure session handling;
- HttpOnly cookies;
- SameSite protection;
- Secure cookies when HTTPS is enabled;
- CSRF protection for mutating browser actions where applicable;
- login rate limiting/backoff;
- session expiry;
- redirect unauthenticated dashboard/API browser requests to login;
- API responses should return proper 401/403 behavior;
- secrets/passwords never logged.

Prefer a CLI/bootstrap mechanism such as `python -m tubeforge ... create-admin` or a first-run setup flow rather than shipping a hard-coded default password.

Add authentication tests.

## 9. Milestone G - Social account manager

Add a dashboard section for managing MULTIPLE destination accounts per platform.

Use a durable model conceptually similar to:

- id
- platform
- display_name
- external username/account identifier
- external platform account/channel/page/IG ID as needed
- auth type
- encrypted credential/token payload or secure reference
- granted scopes
- token expiry / refresh metadata
- connection health/status
- created/updated timestamps
- last successful validation

Important security rule:

DO NOT implement password scraping or browser automation against YouTube/Google, Meta, or Snapchat. Do not store platform login passwords when an official OAuth/token mechanism is available. The UI can ask for a friendly account name/user identifier, but authorization must use the platform's supported OAuth/API credential flow.

Encrypt persisted refresh/access tokens at rest with an application encryption key supplied outside the database/repository. Redact tokens from logs and UI. App client secrets should use environment/config secret injection, not source control.

Account UI should support:

- list accounts grouped by platform;
- connect/add account;
- OAuth callback where applicable;
- validate/test connection;
- show status/scopes/expiry safely;
- disable account;
- disconnect/revoke local token;
- choose default account;
- select multiple publishing targets for a schedule/job.

## 10. Milestone H - Publisher architecture and publication records

Create/complete a common Publisher contract and dispatcher.

A publication attempt must be durable and idempotent. Persist at least:

- generation/job ID;
- target account ID;
- platform;
- state;
- attempt count;
- idempotency/deduplication key if relevant;
- started/finished timestamps;
- external media/post ID;
- external URL where available;
- sanitized error category/message;
- retry eligibility;
- metadata sent to the platform.

One finished master may produce platform-specific derivatives and then publish to multiple accounts without regenerating the entire content job.

Implement retries with backoff for transient errors. Do not retry permanent auth/policy/input errors forever.

## 11. Milestone I - YouTube integration

Use the official YouTube Data API and OAuth 2.0, reusing any existing YouTube publisher code in the repository.

Support:

- connecting multiple YouTube channels/accounts;
- refresh-token based background authorization;
- resumable/reliable upload if existing libraries support it;
- title, description, tags/category where available;
- privacy status;
- made-for-kids configuration;
- synthetic/altered media metadata support if relevant to the current API and content;
- scheduled publishing only if supported cleanly by current integration, otherwise let TubeForge's own scheduler control upload time;
- record video ID and watch URL;
- clear errors for quota/auth/audit restrictions.

Use official docs/current API behavior. Do not invent scopes or bypass Google OAuth.

## 12. Milestone J - Instagram integration

Implement only the current official Meta/Instagram publishing flow supported for eligible accounts.

Support multiple eligible Instagram professional accounts. Use supported Meta/Instagram OAuth/access-token flows, required account IDs, content-publishing permissions, media-container creation/upload, readiness polling, publish finalization, and durable result tracking.

Generate/validate a 9:16 Reel derivative when appropriate.

If the account type or permissions do not permit API publishing, surface that as an actionable account capability/status rather than attempting password automation.

## 13. Milestone K - Facebook integration

Implement publishing to supported Facebook destinations through the current official Meta Graph API.

Prioritize Facebook Pages/Reels/video posting if that is what the current API supports. Reuse Meta authorization infrastructure with Instagram where sensible, while keeping separate account targets and capabilities.

Support:

- page/account discovery where permitted;
- selected Page target;
- video/reel publishing flow;
- title/description/caption metadata as supported;
- durable external ID/URL/result;
- auth refresh/validation;
- retries and error classification.

Do not implement automated posting to personal profiles if the official API does not support it.

## 14. Milestone L - Snapchat integration with capability honesty

Research the CURRENT official Snap developer APIs before coding this adapter.

Do not assume Snapchat offers a generic server-to-server headless API equivalent to YouTube/Meta for arbitrary personal-account posting.

If the official API supports an eligible automated publishing path for the intended destination, implement it using official auth and document account eligibility/review requirements.

If the official supported mechanism requires a client/mobile share/preview step (for example Creative Kit/Spotlight flows), implement the cleanest supported capability/handoff and mark the account/publisher capability accordingly.

Never use stored Snapchat username/password automation, Selenium, unofficial private APIs, device emulation, or bypasses.

A Snapchat adapter that accurately reports `manual_handoff_required` or `unsupported_for_headless_publish` is preferable to a fake “successful” integration.

## 15. Milestone M - Topic queue/backlog

Add a durable topic queue suitable for dumping many ideas into TubeForge.

A topic should support at least:

- title/topic;
- free-form notes/pointers;
- priority;
- status;
- optional desired duration;
- optional content type/style/tone/audience/language;
- optional target platform/profile;
- optional target account set;
- created/updated timestamps;
- attempts/failure reason;
- selected/reserved lease metadata so two schedulers/workers cannot consume the same topic.

Suggested statuses:

- IDEA
- READY
- RESERVED
- GENERATING
- REVIEW
- COMPLETED
- FAILED
- ARCHIVED

Use existing project conventions where better names already exist.

Dashboard requirements:

- add single topic;
- bulk-add many topics quickly;
- edit title/notes;
- reorder/change priority;
- pause/archive;
- retry failed topic;
- filter statuses;
- see the generation created from a topic.

Bulk entry should be convenient: provide a multiline UI where the user can paste many topics, plus a structured per-topic editor for notes/pointers.

The runtime LLM provider, not Codex itself, turns topic + pointers into the script.

## 16. Milestone N - Cron/scheduler management

Add durable schedules configurable from the dashboard.

A schedule should support at least:

- name;
- enabled flag;
- cron expression;
- timezone;
- queue/topic selection policy;
- target generation profile;
- target social accounts;
- review mode;
- max retries / behavior on failure;
- last run;
- next run;
- last result.

Use a real cron parser/library compatible with the project unless a scheduler already exists.

The requested core use case is TWO VIDEOS PER DAY, but do not hard-code that. Example schedules should make twice-daily configuration easy.

Scheduler behavior:

1. acquire a DB-backed schedule/run lease or equivalent;
2. avoid duplicate firing across multiple processes;
3. atomically reserve the next eligible READY topic;
4. create a normal TubeForge generation job;
5. release/record schedule execution;
6. let the existing worker execute the job;
7. never create duplicate jobs because two scheduler ticks overlap.

Add `Run now`, enable/disable, next-run preview, and schedule history to the dashboard.

If no READY topic exists, record a clean no-op rather than failing noisily.

## 17. Milestone O - Dashboard redesign around operations

Keep the current UI lightweight, but evolve navigation to include at least:

- Dashboard
- New Generation
- Topic Queue
- Generations
- Schedules
- Social Accounts
- Publication History
- Settings/Providers
- Activity/Health

The simple generation form should remain simple. Preserve `title + notes + duration + review mode + captions` and add an Advanced section rather than forcing dozens of fields.

Advanced options may include:

- content type: AI-generated / stream clip / existing video;
- target platform/profile;
- duration;
- aspect ratio;
- style;
- tone;
- audience;
- voice;
- hook strength;
- visual policy;
- caption style;
- background music;
- AI image policy;
- AI video policy;
- review mode;
- CTA;
- language;
- publish targets.

All fields should have sane defaults.

Generation detail should show a timeline of stages, artifacts, warnings, retry state, publish targets, and links/results.

## 18. Milestone P - Platform variants

From one master/VideoPlan, support platform-specific outputs without re-running content generation unnecessarily.

At minimum handle configurable profiles such as:

- YouTube landscape 16:9;
- YouTube Shorts 9:16;
- Instagram Reels 9:16;
- Facebook Reels/video;
- Snapchat-supported short-form derivative/handoff.

Derivatives should use the same narration/content unless a platform-specific metadata/length transformation is required.

Generate platform-specific title/description/caption/hashtags through a typed metadata stage and persist them.

## 19. Milestone Q - Stream clipping integration compatibility

If the stream-clipper project or merged code is already present, ensure new account/scheduler/queue/publisher architecture does not break it.

The target model is:

streamer/channel -> monitor -> new stream/video -> analyze/transcribe -> detect/scored moments -> clip -> 9:16 reframe -> captions -> quality gate -> publisher dispatcher.

Do not spend the entire overnight run rewriting stream clipping if the primary AI generation vertical slice is incomplete, but preserve a clean path for both content sources to converge on the same render/publication pipeline.

## 20. Milestone R - Analytics and learning compatibility

Reuse existing analytics/learning work where present.

Ensure publication records can later collect metrics such as views, watch time, retention, CTR, likes/comments and relate them back to:

- topic;
- hook;
- VideoPlan/style;
- generation profile;
- destination account;
- published media ID.

Do not block core delivery on advanced learning features, but do not design new schemas that make the feedback loop impossible.

## 21. Tests required

Add focused tests as each area is built. Target useful coverage rather than superficial line coverage.

At minimum, where applicable, cover:

- migrations upgrade to head on fresh DB;
- auth login/logout/session rejection/rate limit;
- secret redaction;
- token encryption round trip;
- account CRUD and capability status;
- topic queue ordering/reservation/concurrency;
- scheduler next-run calculation;
- scheduler duplicate-fire prevention;
- two-worker topic/job contention;
- no-topic no-op;
- VideoPlan validation/persistence;
- Visual Router fallback behavior;
- offline end-to-end generation smoke test;
- FFmpeg final artifact probe;
- quality gate pass/fail cases;
- publisher idempotency;
- publisher retry classification;
- YouTube adapter contract with mocked HTTP/client;
- Instagram adapter container/poll/publish contract;
- Facebook adapter contract;
- Snapchat capability behavior without unsupported automation;
- multi-account target dispatch;
- restart/resume from persisted checkpoints.

Run the full suite periodically, not after every tiny edit. Fix regressions introduced by this work.

## 22. Docker / operational completion

Make sure the normal Docker Compose path still works.

Where appropriate:

- add scheduler service/process only if needed rather than embedding unsafe duplicate loops in every web worker;
- add health checks;
- keep migrations explicit;
- update `.env.example` with placeholder variable NAMES only, never values;
- document required OAuth callback URLs and environment variables;
- ensure persistent artifact paths/DB paths are unchanged or migrated safely;
- verify `docker compose config`;
- build containers if time/resources allow;
- run a local smoke path.

Do not expose the dashboard publicly without authentication. Bind/networking should remain conservative.

## 23. Documentation deliverables

Update the project docs with a practical operator guide covering:

- first boot;
- creating the admin user;
- logging in;
- adding topics;
- creating a twice-daily schedule;
- configuring provider keys;
- connecting YouTube;
- connecting Meta/Instagram/Facebook;
- Snapchat capability/limitations;
- running a generation manually;
- observing queue/job status;
- running scheduler/worker/web services;
- retrying failed publications;
- where artifacts/logs live;
- backup/security notes.

Add a `docs/platform-integrations.md` with each platform's implemented status, official auth mechanism, required developer setup, required scopes/permissions, known approval/review requirements, and what still needs manual configuration.

## 24. Security and correctness requirements

Never store third-party social passwords just because the UI could ask for them.

Never log:

- passwords;
- access tokens;
- refresh tokens;
- authorization codes;
- OAuth client secrets;
- cookie/session secrets;
- encryption keys.

Use server-side validation for all dashboard input.

Treat uploaded/generated filenames and external metadata as untrusted.

Avoid command injection into FFmpeg/shell. Use argument arrays rather than string-concatenated shell commands where possible.

Do not introduce SSRF through arbitrary remote asset URLs without validation/allowlisting appropriate to the provider architecture.

Keep publication operations idempotent.

Protect against concurrent workers/schedulers by using the existing database ownership/lease patterns.

## 25. Autonomy / what to do when uncertain

Make reasonable engineering choices without asking me for cosmetic or reversible decisions.

Do not stop for questions such as naming, exact spacing, minor library choices, or routine schema structure; choose a sensible option consistent with the codebase and document it.

Stop only if:

- continuing would risk deleting or corrupting user data;
- a destructive/irreversible external action is required;
- required credentials are unavailable AND no further code/test/documentation work can be done;
- product requirements are mutually contradictory in a way that materially changes data/security behavior.

Otherwise log the assumption and continue.

## 26. Definition of "done enough for this overnight run"

Before ending, maximize the number of genuinely completed milestones, but make sure there is at least one coherent local vertical slice.

The ideal final smoke demo is:

1. Start the stack.
2. Login as admin.
3. Add 2-3 topics with notes.
4. Create a schedule or use Run now.
5. Scheduler reserves one topic exactly once.
6. TubeForge generates script + VideoPlan.
7. Visual Router selects assets/fallbacks.
8. Voice/render pipeline creates a real playable MP4.
9. Captions and quality gate complete.
10. Publication package is created.
11. Fake publisher proves multi-target dispatch; any configured real sandbox/test publisher can be validated without accidental public posting.
12. Dashboard shows completed stages and publication results.
13. Restarting services does not duplicate the job or publication.

If live YouTube/Meta credentials are not available, the code must still be ready for the OAuth setup and have contract tests. Clearly mark live credential smoke tests as BLOCKED, not DONE.

## 27. Final response when you eventually stop

Do not give me a vague summary.

Return:

- completed milestones;
- partially completed milestones;
- blockers requiring me;
- migrations added;
- key files/modules added or changed;
- focused test results;
- full-suite result;
- Docker/smoke result;
- exact next 5 highest-value tasks;
- exact commands I should run to test the system;
- any OAuth/platform setup steps I personally must complete.

Also make sure `docs/overnight/STATUS.md` is current so a NEW Codex session can continue without needing this conversation.

BEGIN NOW. Inspect the repository first, write the master plan/status files, then immediately start implementing the highest-value vertical slice. Do not merely return a plan.

