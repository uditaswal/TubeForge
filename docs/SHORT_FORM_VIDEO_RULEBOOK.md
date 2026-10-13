# TubeForge short-form video rulebook

Use this for future scripts, scene plans, renderer changes and review of vertical Shorts. The [reference audit](DOCKER_SHORT_BENCHMARK_REVIEW.md) holds attachment details and measured comparisons; this file contains reusable production rules. The canonical narration contract remains [yt-script automation](../.agents/skills/yt-script/automation.md).

## Story and source

- Promise one useful outcome. Make the hook readable on frame one and show a concrete action, example or payoff within three seconds. Give each scene one teaching purpose, then end with one brief ask that agrees with the spoken line. Do not claim measured retention without audience data.
- Use the accepted structured content package as the single source of spoken words. Only ordered `script_sections[].narration` reaches TTS. Keep hook alternatives, scores, citations and directions in their own fields. Render the exact approved revision; a changed script needs new approval.
- Ground copyable commands, figures, claims and outcomes in approved sources. Capture real output where feasible; otherwise label edited, abbreviated or illustrative output on screen. Color must not be the only way to understand a state change.
- For terminal tutorials, type commands in sync with speech, hold completed lines long enough to read, and use roughly 48–54 px monospace on a 1080 px canvas. Reduce lines or wrap intentionally before shrinking. Other subjects need visuals that demonstrate the mechanism, not decorative cards.

## Topic and scene data

Keep topic-specific wording and visual content in data, not renderer code. TubeForge's existing `ContentPackage` owns `request`, `claims`, ordered `script_sections` and matching `scene_plans`; the companion topic/render data references that approved package and may set `voice`, `speed`, `music` and scene layout. This is an illustrative data shape; each renderer defines and validates its supported scene layouts:

```json
{
  "package": "content-package.json",
  "voice": "approved_voice_id",
  "speed": 1.0,
  "music": {"enabled": true, "bpm": 96, "level": 0.16, "duck": 0.5},
  "scenes": [{"kind": "supported_layout", "label": "STEP", "heading": "WHAT CHANGES", "display_elements": ["source-grounded visual"]}]
}
```

Validate scene order against the approved package; reject stale hashes, unsupported visual claims and unknown layout kinds. `music` controls only the mix, never the spoken script. A supplied track needs a rights record, attribution requirements and a separately checked audio file.

## Portrait composition and captions

For 1080×1920, keep essential text inside **x=60–930, y=200–1500**. Reserve the top 200 px for platform chrome, the bottom 420 px for description/navigation, and the right action rail at roughly x>930 from y=1000–1700. Put progress near y=215. These are conservative design guides, so inspect the actual platform preview as well.

Use a separate caption zone below the teaching visual, centered near x=490, y=1385. Aim for one bold line of one to three words at **84 px or larger**, with a dark outline/backplate and an active-word highlight. Split chunks rather than silently shrinking or clipping them. Keep the terminal/card above the caption zone. Check full text bounding boxes, cursor and backplates against safe bounds on every rendered frame, then view representative encoded frames at phone scale.

Derive caption words from the accepted narration, align the **actual synthesized speech** using word timestamps or forced alignment (for example faster-whisper), and cross-check command names and scene boundaries. If alignment fails, a proportional estimate is a flagged fallback requiring listening review; it is not measured timing. Preserve both spoken and displayed forms where punctuation is said differently from text shown on screen.

## Sound and provenance

Keep speech intelligible. Music should be audible in pauses and duck under words; start by keeping the bed roughly 18 dB below speech in active passages, then judge by listening. Tie quiet clicks, whooshes or confirmation sounds to visible actions. Fade the bed in and out, and prevent the ending from cutting it off.

Synthesize music from original code or use a track with documented rights. Record the source or algorithm, track identity/hash, relevant dependency and voice-model terms, and required attribution in the artifact manifest. “Generated” does not by itself settle licensing. Record AI-voice disclosure needs for the publishing review; this guide does not authorize publication.

Measure the mix, then use **two-pass** loudness normalization targeting about **−14 LUFS and −1.5 dBTP**. Measure the *encoded AAC MP4* again; accept −15 to −13 LUFS integrated and true peak at or below −1.0 dBTP. A peak or loudness pass cannot prove pleasant balance: review the voice, music and effects by ear.

## Final gate

Use checked subprocess exit codes and atomic artifact promotion. Require 1080×1920, 30 fps, H.264/AAC, roughly 30–55 seconds for TubeForge Shorts, full FFmpeg decode, final loudness/peak, exact approved-script and asset hashes, and no clipped or overlapping text. Inspect the first frame, each scene change, finished on-screen actions, caption boundaries and last frame. Save an encoded contact sheet with safe-zone guides and inspect a full-size frame from each distinct layout. Report any listening or platform-preview check that remains unverified.
