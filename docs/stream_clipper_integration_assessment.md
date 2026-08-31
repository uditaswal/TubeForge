# Stream Clipper integration assessment

`stream-clipper` is MIT licensed (copyright 2024 Stream Clipper), so its
algorithms may be adapted with attribution in this assessment. TubeForge does
not copy or run its Tauri application.

## Reused concepts

- RMS audio-window analysis, dynamic baseline/percentile thresholding, and
  peak/change evidence for source-video highlight candidates.
- Optional timestamped-chat activity/keyword spikes as an independent score
  signal.
- Weighted audio/chat combination, padded clip ranges, overlap suppression,
  and FFmpeg re-encode extraction.

## Deliberately not reused

- Tauri/Svelte UI, its separate local project files, licensing/Pro gates,
  desktop file pickers, bundled Windows binary, watermark, and random
  free-tier selection. They conflict with TubeForge's web dashboard,
  deterministic ranking, server deployment, and existing audit trail.
- WebRTC VAD Rust implementation: it would require a Rust sidecar and a
  permanently different runtime. This milestone records voice-independent
  RMS/peak evidence and keeps a configurable future transcript/VAD provider.
- Donor URL acquisition: it has none; it accepts local files. TubeForge adds
  a bounded `yt-dlp` source provider instead.

## Native TubeForge design

`SOURCE_CLIP` requests use a `SourceProvider` to inspect and acquire media,
then use durable source, analysis, candidate, and per-clip artifacts under the
existing job root. The existing worker claim, global heavy-work lease,
ownership fencing, cancellation callback, event timeline, and artifact
repository remain authoritative. Source metadata and candidate provenance are
stored as JSON artifacts rather than a second database.

New dependency: `yt-dlp` is used only by the source provider for supported
HTTP(S) video URLs; it is invoked with an argument array, no cookies, no
playlist expansion, no redirects managed by TubeForge, and a bounded output
directory. FFmpeg/ffprobe are already TubeForge dependencies.

## Risks and follow-up

This milestone supports manually submitted public HTTP(S) video URLs and
deterministic audio highlights. Creator monitoring, chat-log upload,
transcripts/VAD, face tracking, and additional social publishers remain future
providers; their data boundaries are preserved by the source request and
candidate provenance formats.
