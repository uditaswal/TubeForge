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
- Long videos: a video longer than the limit is **trimmed to its first stretch instead of refused** (the job card says which part is used). On the Clips page you can set *Start at* (`1:05:00`) and *Use at most N minutes* to use any other part; only that part is read (signals, transcription and moment selection stay inside it). The limits are on the Settings page under Clips: *Longest video a clip job reads* (default 720 min, 12 hours) and *Largest download* (default 6 GB).
- Calls: a long video where only the busiest parts are transcribed now shares one call across neighbouring windows (about two to four calls instead of twelve). The daily allowance is the Settings value *Claude calls per day for clip selection* (default 12); a refusal says when the oldest call leaves the 24-hour window. Downloads are cached in `data/cache/clips-source` for 7 days, so a retry or a second job on the same video does not download it again. Downloads that earlier jobs cached in their own folders are hard-linked into the shared cache at the start of the next clip run (no copy, no second 5 GB).
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
- After a long download the engine used to copy the whole file into its source cache (5 GB, about 10 minutes on this disk, no CPU use, which looks like a hang); it now hard-links it. The Clips page shows each running job's stage, percent, what it is doing now, how much it has written to disk, and warns if nothing has changed for 5 minutes.
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

## Speed

- **Where the time went.** Each clip job card on the Clips page has a "Where the time went" list: download, preparing, transcription,
  AI, the chosen-sections download, and every clip's render, each with its duration. It is read from `jobs/<id>/clip-work/timings.json`
  and survives restarts. Use it before tuning anything.
- **Sections only (default on, Settings → "Download only the parts the clips need").** The audio is downloaded first, the AI picks the
  moments, and only those sections of the video are fetched. Measured on the 175-minute podcast from this machine (about 2.4 MB/s): audio
  170 MB in 79 s, then two padded sections (35 MB) in 178 s, about 4.5 minutes and 213 MB in total, against 30-45 minutes and 2.8-5.3 GB
  for the whole video. If a section download fails the job falls back to the whole video by itself.
- **Parallel pieces (Settings → "Download pieces at the same time", default 1).** Measured: the audio took 69 s with 1 connection and
  79 s with 4, so on this connection it does not help (the bandwidth is the limit). Raise it only on a faster line.

## When YouTube says "Sign in to confirm you're not a bot"

YouTube sometimes refuses a download from a server it does not trust. The worker already uses a JavaScript runtime for YouTube's
player check. If it still refuses, give it your YouTube cookies:

1. In a browser where you are signed in to YouTube, export the cookies for `youtube.com` as a Netscape `cookies.txt` file (a
   browser extension such as "Get cookies.txt LOCALLY" does this).
2. Save it as `data/config/youtube-cookies.txt` (the folder is git-ignored). No restart is needed; the Clips page strip shows "YouTube cookies found".
3. Retry the job.

Use a spare Google account if you can: the cookies are a login for that account, and YouTube can flag an account that is used for
automated downloads. They are passed to yt-dlp only and are never logged or saved with a job. Cookies expire; export them again if the error returns.

## Decision log

Each clip job writes `decisions.jsonl` in its `clip-work` folder (`clips/decisions.py`) and the Clips page shows it as "Why these clips". It records which viewer signals existed (most-replayed heatmap, chapters, auto-captions, timestamp comments), which parts of the video were transcribed and why, every AI pick with its reasoning and scores, what was dropped or left out afterwards, and per clip whether faces were found or the default crop was used and whether captions were burned in or skipped (with the reason). Logging never changes a result.

## How moments are chosen

Only the busiest parts of a long video are transcribed, so what picks them matters most. Signals, strongest first:

1. **Most-replayed heatmap** (not present on live streams or small videos).
2. **Live-chat replay**: messages per 30 s of a finished stream, read with yt-dlp. A burst of chat marks the funny, tense or shocking moment. Only a rise above the stream's usual level counts, so a busy chat does not mark every minute. Not every stream has it: when the replay is off or missing, the decision log says `chat-missing` and the job carries on without it.
3. **Timestamps in comments**, weighted by likes.
4. **Loudness**: the audio is decoded at 8 kHz and measured per 30 s (`audio-energy.json` beside the media). Loud stretches add a weaker score.
5. **Auto-caption pace and chapters.**

The AI always gets a default goal (`DEFAULT_GOAL` in `clips/engine.py`): each clip should make a viewer want to watch the whole video, with a hook, a payoff, and no mid-thought starts. The operator's own notes follow it.

The Settings page has "Use the larger speech-to-text model" (Whisper small.en when its folder is present under `data/benchmark/models`, otherwise base.en). It mishears less and takes about three times as long per minute of speech.
