# Clips

Turn one long video into vertical clips: TubeForge reads the transcript, the AI picks the best standalone
moments, and each moment is rendered 9:16 with a face-aware crop, word-synced captions and a hook title.
The Clips page is `/clips` (sidebar: Clips).

## How it fits TubeForge

- **One job type.** A clip job is a normal job with `production_mode=source_clip`: same leases, pause/retry/cancel,
  events, artifacts and quality gate as a Short. States: `source_inspecting` (metadata) → `source_acquiring`
  (records the plan) → `source_analyzing` (download, transcript, AI picks the moments) → `clip_rendering` (renders
  every clip) → `final_ready`. Each stage is resumable from `jobs/<id>/clip-work/state/` after a crash.
- **One database, one queue.** No separate service: the code is the `tubeforge.clips` package, started by the
  existing worker. The package imports nothing from the rest of TubeForge (`tests/test_clips_boundary.py` enforces it,
  and that importing it loads no SQL, S3 or web-framework code); the pipeline reaches it through `pipeline/clip_runs.py`
  and `ClipEngine.analyze` / `render` / `run`.
- **Shared resources.** One worker image (the `clips` extra), one Whisper model (the narration alignment model), one
  yt-dlp pin, one heavy-work lease (a clip render and a Short never render together), one Claude spend ledger.
- **AI through the runner.** The worker never holds a Claude login. Clip selection sends `ClipCompletionRequest`
  (typed, bounded to 48,000 characters, no command/path/model fields) to the host Claude runner, which runs it tool-less
  and counts it in the shared ledger **and** a separate clip limit: `TUBEFORGE_CLAUDE_CLIP_CALLS_PER_DAY` (default 12 per
  24 h) on the runner process. A run uses about six calls; more for long videos.
- **Many clips, one final.** The job's own video is the best-ranked clip (`final`), which follows the usual
  Generations → publication flow. Every other clip is approved on the Clips page: *Approve for publishing* creates a
  child job (`clip_of=<job>:<clip>:<sha256>`) whose video is that exact file; if the file changes after approval the
  child fails instead of publishing it. Nothing is published by the Clips page.

## Operating it

- Enable: `pipeline.source_clips.enabled: true` (default in `config/production.yaml`), then rebuild the worker image.
- Worker modes: `scripts/stackctl.sh clips|shorts|all|status` sets `TUBEFORGE_WORKER_MODES`; a worker in `clips` mode
  leaves Shorts queued and vice versa. Default `all`, one job at a time, so memory stays within the 3 GB worker limit.
- Long videos: a video longer than the limit is **trimmed to its first stretch instead of refused** (the job card says which part is used). On the Clips page you can set *Start at* (`1:05:00`) and *Use at most N minutes* to use any other part; only that part is read (signals, transcription and moment selection stay inside it). The limits are on the Settings page under Clips: *Longest video a clip job reads* (default 240 min) and *Largest download* (default 6 GB).
- Config defaults (`config/production.yaml → pipeline.source_clips`): `max_clip_seconds`, `max_source_duration_seconds`, `max_download_bytes` (6 GB, enough for the 4-hour source limit),
  `engaging_only` (transcribe only the windows viewers engaged with: heatmap, timestamped comments, chapters).
- Needs: the Claude runner (`scripts/run_claude_runner.sh`), ffmpeg, yt-dlp. A YouTube 429 on captions only removes
  one fail-soft signal; downloads still work.

## What is in and out

In: YouTube links, local Whisper (engaging windows or whole video), AI moment selection with hook/engagement/value/shareability
scores, hook titles, opening cleanup, still-footage skipping, face-aware vertical crop, split screen, captions, atomic
clip files, resume without duplicates.
Out for now (deliberately): paid downloaders and transcription, other AI providers, accounts/billing, social posting
(TubeForge's own publishing is used), the series/recap/trailer/topic workflows (the code is present but not exposed),
Twitch/Kick (present, not exposed), B-roll (needs a Pexels key).

## Verification status

IMPLEMENTED and tested with fake media (`tests/clips/`, `tests/test_clips_engine.py`, `tests/test_clips_api.py`,
`tests/test_clip_runner.py`, orchestrator tests); Clips page checked signed in at 1280, 820 and 390 px.

**Real run, 17 Nov 2026 (engine called directly, outside Docker, through a runner on a temporary socket that counted
against `dev`'s Claude ledger):** a 175-minute podcast, three clips requested, captions on. Result: three 1080×1920
H.264/AAC 30 fps clips of 33–40 s with a hook title, AI scores (68–72), word-synced captions with the spoken word
highlighted, and the speaker kept in frame by the face-aware crop (checked on contact sheets and a full frame).
Loudness −15.1, −15.7 and −14.2 LUFS. It took 19 minutes plus the download. **Not yet exercised:** the same run through
the Docker worker and `/clips` page, the clip QA profile for `qa_check.py`, and a side-by-side against another tool.
Findings from the run:

- `faster-whisper 1.2.1` fails with PyAV 17 or later (`open() got an unexpected keyword argument 'metadata_errors'`);
  the `clips` extra now pins `av>=14,<17`.
- The per-job download cap (2 GB, `YOUTUBE_DOWNLOAD_MAX_BYTES`) rejects a 175-minute source (2.9 GB at 1080p); the run used 4 GB.
- Without a JavaScript runtime yt-dlp cannot use section downloads, so it downloaded the whole video (about 2.8 GB, 30 min at 3 MB/s).
- A 175-minute video is read in 13 windows and used all 12 of the day's clip calls, so the last window and the final ranking
  were skipped ("Analysis window 13/13 failed", ranking kept first-pass order). Long sources need a higher
  `TUBEFORGE_CLAUDE_CLIP_CALLS_PER_DAY` or larger windows; a typical 30–60 minute video needs about 6.
- Clip loudness is not normalized (one clip was 0.7 LUFS under the −15 target).
- A failure inside the engine (download cap, runner limit, no usable moments) now fails the job with a reason, or retries when it may recover (runner unreachable, timeout); it used to escape as an unclassified error and crash the worker. The lease is renewed by a keepalive poll during long downloads and renders.
- `/tmp` on this host is a 1.9 GB RAM disk: keep job work folders on the data volume.

## Later, decide before this work is finalized

- **Performance loop** (published clips' views steer future clip picks): needs real upload data; deferred. **Ask the operator
  before the branch is finalized.**
- **Clip editor** (decision deferred to the end; current proposal: leave out and use an online editor, optionally with a
  small "replace with edited file" upload that asks for a fresh approval). Features, for the decision: trim/split/merge,
  keep or cut ranges, remove fillers and pauses, caption wording/templates/fonts/emoji/position, hook title, framing,
  colour, volume, B-roll add/move/remove, AI edit (a plain-language request turned into those operations; no music,
  voiceover, transitions or speed changes), export presets for TikTok/Reels/Shorts and ZIP download.
- Other workflows (series, recap, topic, trailer), Twitch/Kick, B-roll.
- Instagram publishing stays parked (see HANDOFF).
