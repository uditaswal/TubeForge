# TubeForge Shorts workflow

This record defines the product decisions and validation gates for good-quality
YouTube Shorts. The current release status is in `design_doc/tubeforge-publishing-design.md`.

## Output contract

- The dashboard exposes a dedicated **YouTube Short (9:16)** preset alongside
  the unchanged widescreen workflow.
- The requested writing target is 30–120 seconds, with 45 seconds as the default. Measured narration and final video must be 30–120 seconds; target deviation is diagnostic, not a rejection.
- Preview output is 540×960. Final output is 1080×1920 at 30 fps, H.264/AAC with 48 kHz audio.
- The opening narration must begin inside the first three seconds.
- No visual camera hold may exceed three seconds.
- Word-highlight captions use the generated narration audio as their local
  timing source. The final gate verifies monotonic timings, the opening word,
  and the last word against assembled audio duration.
- Caption styling uses large uppercase type, a yellow active word, white
  context, and explicit portrait safe-area margins. The gate rejects lines
  that exceed the supported width.

## Implementation decisions

The local waveform aligner detects the voiced portion of each generated PCM
WAV and assigns duration-weighted timings to the exact approved words. This is
deterministic, offline, and tied to the media that is actually rendered. It is
not represented as phoneme recognition or semantic transcription.

Long narration scenes are split into bounded render segments. Each segment
gets one of four deterministic FFmpeg camera moves (horizontal and vertical,
at two speeds), while the underlying licensed or generated scene asset and
provenance remain unchanged. Crisp paced cuts are intentional: dissolves on
sub-three-second captioned scenes reduce useful composition time and soften
word-highlight readability. Portrait rendering uses modest overscan to avoid
unnecessary 4K-scale intermediate images.

Production writing runs through the restricted host Codex runner, never in the
worker container and never through Ollama. The authority-bearing request/source
packet is replaced with the exact operator input before domain validation, so a
model cannot rewrite its provenance. The prompt and structured output format require six developed
scenes, 108–166 narration words for the default 45-second Short, a first
sentence of at most 18 words, complete sentences, and a concrete final CTA.
Rejected drafts are not cached and may be regenerated twice with the bounded
local validator result.

Final Shorts captions require at least 84 px with word highlighting, matching
the rulebook's phone-first caption target. A smaller custom final setting is
rejected; preview and long-form profiles remain configurable. The renderer
identity is `shorts-final-v4`, so a render with the older 80 px default cannot
be reused under the new final profile.

Generated Shorts frames use local FFmpeg storyboard graphics at native
1080×1920. Each scene carries an approved subject, purpose, composition and
display elements; old packages use search-query fallback labels that require
visual review. The current style descriptor is
`portrait-storyboard-v6:midnight-cyan-violet-amber`. Asset acceptance stores
a complete scene-linked manifest and contact sheet and checks native portrait
resolution, unique scene bytes and one palette identity. Those technical checks
do not prove the diagrams teach the narration; inspect the contact sheet.
Portrait stock must be at least 720×1280; unsuitable stock falls back before
acquisition. The final gate also verifies camera variants, maximum hold time,
and caption safe-area/line-width limits. Final captions anchor at x=490 with a
470 px bottom margin so their full rendered bounds remain above the bottom
controls and clear of the right-side action rail.

### Real-media pipeline smoke

The opt-in `tests/test_captured_shorts_smoke.py` verifies media execution with
source-controlled test packages, never production narration. To exercise the
local Piper server, set `TUBEFORGE_SMOKE_PIPER_MODEL` to the matching local ONNX
model and `TUBEFORGE_SMOKE_PIPER_SERVER_URL` to its worker-reachable base URL.
Set `TUBEFORGE_SMOKE_NORMALIZE_AUDIO=1` to require the encoded AAC gate; it
checks −15 to −13 LUFS, true peak ≤−1 dBTP and 48 kHz, then saves ignored
preview/final artifacts under `data/artifacts/stage22_fixture_smoke/`. Fixture
approvals in this isolated database are technical test setup, not operator
approval for a production job.

Music comes only from the approved local catalog. Dashboard uploads require a
decodable audio file, source URL, actual licence and terms URL, attribution
requirements/text, and explicit confirmation that the terms allow publishing.
“Free” and “royalty-free” are rejected as licence names. The render manifest
binds the file checksum and rights record; FFmpeg uses a 16% bed,
speech-keyed side-chain compression, and a limiter. Required credit is added
to publication metadata before approval.

## Delivery phases

| Phase | Deliverable | Current state |
| --- | --- | --- |
| 1 | Portrait preset, duration/output contract, word timing, highlighted captions, pacing gate | Implemented; real Piper/FFmpeg acceptance evidence retained under `artifacts/smoke/` |
| 2 | Source-grounded local production writer with hook, complete sentences, CTA, and script/source review | Implemented; approved host Codex generation acceptance remains blocked on deployment |
| 3 | Consistent vertically composed b-roll/motion-graphics style plus visual-quality gate | Implemented; focused media/render tests pass, full finished-Short inspection remains in Phase 5 |
| 4 | Operator-approved music catalog, recorded licence/attribution, quiet ducked mix, dashboard audio upload | Implemented; focused catalog/API/mix tests pass, full audio inspection remains in Phase 5 |
| 5 | Signed-in browser acceptance of a finished Short with visual/audio inspection and dry-run publication | Pending |

## Approved host Codex runner plan

Production script generation will use the existing Codex CLI on the `ua` host,
not a local model and not a CLI installed in the TubeForge worker container.
The runner is a dedicated `tubeforge-codex` host account with its own private
`CODEX_HOME` and one-time ChatGPT CLI sign-in. Its executable is the root-owned
pinned `@openai/codex@0.149.0` runtime at
`/opt/tubeforge-codex-runner/codex-runtime`; it must not use
`/home/uditaswal/.nvm` or read or copy the operator's Codex authentication files.

| Phase | User-visible outcome | Acceptance test and retained evidence | Out of scope |
| --- | --- | --- | --- |
| 1 | A private host runner accepts only a typed script request from the worker. | A UID 1000 worker connects through the Unix socket; another UID is rejected; the runner has no `/home/uditaswal`, project, Docker socket, or arbitrary command/path mount. Retain systemd status and socket-mode evidence. | Producing a script or rendering a video. |
| 2 | One reviewed, source-grounded Short script comes from Codex CLI. | Retain the exact source packet, returned package, claims, usage events, validator result, and manual claim/creative review. | Rendering or publication. |
| 4 | Creator Studio reflects the persisted review/render/delete workflow. | Signed-in browser evidence for every operator action and refresh. | Live YouTube publication. |
| 5 | The finished Short is handed off with regression and runtime evidence. | Full suite, health check, real 30–120s portrait artifact inspection, and updated status/progress records. | Enabling YouTube publishing. |

The runner protocol has one generation request: `GenerateShortsScriptV1`, plus
read-only `PreflightContentV1`, which validates resources/runtime without calling
Codex or consuming an attempt. The generation request accepts only
the bounded topic, audience, duration, prompt version, and immutable approved
source packet. It never accepts a prompt, path, executable, model, CLI flag,
environment value, schema, or arbitrary command from the worker. It builds the
fixed prompt and schema itself, invokes Codex in a fresh restricted workspace,
and returns only a structured package, redacted provenance/usage, or typed
failure.

Each script permits at most two total Codex invocations, each limited to eight
minutes. The second is only for a technical or structural failure. A creative
quality rejection always stops for operator review. The runner fails closed on
timeout, outage, allowance exhaustion, invalid output, or source mismatch and
never falls back to Ollama or promotes a rejected draft. Prompt and output byte
caps are enforceable; a precise per-call ChatGPT token/dollar ceiling is not,
so recorded usage plus the two-invocation limit is the safe local boundary.

## Safety boundaries

Production content must not use deterministic fake prose. Sources, claims, and
the exact reviewed script must remain visible to the operator. Visual and music
assets must carry durable licence/provenance records; “royalty-free” is not a
licence. YouTube remains disabled and dry-run unless the operator explicitly
configures credentials and approves publication.


## YouTube skill integration

New `m6-content-v5` jobs embed the installed yt-script, yt-package and yt-seo
resources from the wheel. Application Python scores five hooks, selects a
format-compatible finalist, checks ten title/thumbnail pairings and retains
reports for exact-script review. Channel voice profiles are snapshotted in the
request; older jobs and supported widescreen formats remain readable. See
README and `docs/CONTENT_SKILLS_CONTRACT.md`. Local integration tests are separate
from real host Codex generation, finished-video inspection and browser acceptance;
none of those production gates is upgraded by a synthetic fixture.
