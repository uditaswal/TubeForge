# Settings (runtime values you can change yourself)

Open **Settings** in the Studio sidebar (`/settings`). Each value shows its default, whether you changed it,
and who changed it last; **Save** applies it to the next job (no restart), **Reset to default** removes your
override. Every change is listed under "Recent changes". Values are kept in `data/config/runtime-settings.json`,
shared by the web server and the worker. API: `GET /api/runtime-settings`, `PUT` and `DELETE`
`/api/runtime-settings/{key}` (signed in, with the CSRF token like every other write).

| Setting | Default | What it does |
|---|---|---|
| `prompt.max_chars_claude` | `pipeline.claude.max_prompt_chars` | Largest assembled Claude writer prompt. The Claude runner has its own ceiling (90000 unless `TUBEFORGE_CLAUDE_MAX_PROMPT_CHARS` says otherwise), so higher values are clamped to it. |
| `prompt.max_chars_codex` | `pipeline.codex.max_prompt_chars` | Same for Codex. |
| `prompt.auto_trim_sources` | on | While a request is built, shorten the longest source excerpts (at a sentence end, longest first) so the prompt fits. Off: a too-large brief is refused with the numbers instead. |
| `prompt.min_chars_per_source` | 1500 | Trimming never goes below this per source; if it still does not fit the brief is refused. |
| `prompt.margin_chars` | 2500 | Room left under the ceiling for the repair and editor passes. |
| `script.exact_by_default` | off | Treat every script you provide as exact (see "Exact script" in `docs/batch-plans.md`): wording forced in, writing checks skipped, scenes re-cut and length fitted around your wording. |
| `generation.auto_retry_rejected` | on | A script that fails validation is retried by the worker while the source packet still has an attempt left. |
| `clips.max_source_minutes` | `pipeline.source_clips.max_source_duration_seconds` (240 min) | Longest video a clip job reads; a longer video is trimmed to its first stretch instead of refused. |
| `clips.claude_calls_per_day` | `TUBEFORGE_CLAUDE_CLIP_CALLS_PER_DAY` on the runner (12) | Claude calls per day for clip selection, inside the shared limit; the runner reads it on every request. |
| `clips.max_download_gb` | `pipeline.source_clips.max_download_bytes` (6 GB) | Largest download for one clip job. |
| `reference.use_transcript_as_script` | off | Preparing a Short from a reference starts with the transcript used exactly as the script (otherwise fresh AI narration); changeable per Short. |
| `clips.max_clip_seconds` | `pipeline.source_clips.max_clip_seconds` (60) | No clip is cut longer than this. |
| `clips.engaging_only` | `pipeline.source_clips.engaging_only` (on) | Transcribe only the busiest parts of a long video. |
| `clips.signal_windows` / `clips.signal_window_before` / `clips.signal_window_after` | 8 parts, 60 s before, 90 s after | How many busy parts are transcribed and how much is kept around each. |
| `clips.whisper_threads` | 4 | CPU threads for transcription. |
| `clips.max_height` | 1080 | Highest video quality downloaded. |
| `clips.cache_days` | 7 | Days downloaded videos are kept. |
| `clips.analysis_window_max_chars` | 24,000 | Transcript per AI call before neighbouring parts stop sharing a call. |
| `clips.inspect_timeout_seconds` | `pipeline.source_clips.timeout_seconds` (45) | Time allowed for the first look-up of a link. |
| `worker.retry_base_seconds` / `worker.retry_max_seconds` | `worker.*` (30 / 900) | First and longest wait between retries. |
| `worker.max_attempts` | `worker.max_attempts` in config (3) | Worker retries for temporary failures (runner down, timeout) before a job fails. |

**Not a setting:** the two-attempt limit per exact source packet is part of the safety contract (`AGENTS.md`). The
automatic retry uses the remaining attempt and never goes past it; a revised brief or new sources is a new packet.

**Why the size check exists.** The fixed writer instructions are about 57,000 characters, so a few long source
pages could push the assembled prompt over the ceiling, and the job used to fail after it was queued. The check
now runs when the request is built (Studio, Batch plans, and "retry as new job"), trims excerpts before they are
hashed into the source packet, and logs what it cut (`tubeforge.prompt_budget`).

## Everything else (read-only)

The page ends with a read-only reference built from the loaded config: every other `config/production.yaml` value with its
current value and how to change it (edit the file and restart; some are locked on purpose and say why), plus the environment
variables that change how runs behave. Secrets show only "set" or "not set". Add new settings by the rules in `AGENTS.md`
("Settings page upkeep").
