---
name: om-short-production
description: Apply TubeForge's reviewed short-form production standard when turning an accepted script into a vertical video. Use for scene contracts, render direction, or production-readiness checks; not for writing replacement narration or publishing.
---

# Short-form production standard

Use after the canonical `yt-script` narration has passed its source and exact-script gate. This skill applies TubeForge's topic-independent short-form production standard. It does not predict performance, replace `yt-script`, or authorize a provider, approval, or publication action.

Read `docs/SHORT_FORM_VIDEO_RULEBOOK.md` before acting. Consult `docs/DOCKER_SHORT_BENCHMARK_REVIEW.md` only when the task concerns that specific benchmark. Use `om-storyboard` for a full storyboard and `om-video-quality` after a rendered artifact exists.

For `reference-short-v1`, apply the newer reviewed profile in
`docs/CLAUDE_PIPELINE_REVIEW.md`: 25–45 seconds, 6–8 scenes with 8–15 spoken
words each, 0.3–0.4-second speech tails, fixed semantic templates, visible
source names, an immediate large hook and final “Follow for more” CTA.
Require 1080×1920/30fps final (720×1280 draft), one-line 1–3-word captions at
84px on the final canvas, and encoded audio at −15..−13 LUFS / ≤−1.5 dBTP.
These profile limits supersede the older duration/peak limits below only for
that profile. Use the shared renderer for CLI and dashboard. Do not turn a
test fixture, a benchmark approval or a successful layout check into approval
of a new production script or full audiovisual acceptance.

## Build a meaningful vertical Short

- Preserve the accepted narration, source packet, scene IDs, word anchors, and render identity. A new visual idea that changes those inputs is a revision and needs the existing exact-artifact approval path.
- Make the promise visible on frame one and show a concrete action, example, or payoff within roughly three seconds. Each teaching scene needs one observable state change or reveal tied to a spoken cue. Decorative pans, zooms, or a sequence of static cards do not satisfy this.
- Choose the visual mechanism from the claim: use a terminal or real output for commands, a diagram for relationships, a comparison for trade-offs, a timeline for sequence, and a source card for a bounded citation. Mark illustrative output as illustrative or abbreviated when it is not captured evidence.
- Keep each scene focused on one teaching purpose. Let completed commands, results, and comparisons remain on screen long enough to read. Vary composition only when it improves the explanation; preserve typography, palette, subject identity, and caption hierarchy across scenes.
- Treat portrait composition as a phone-first constraint. Keep essential content in the rulebook's safe area, keep teaching visuals above the caption zone, and reserve the right action rail and lower controls. Use a bold one-to-three-word caption chunk at 84 px or larger with contrast; split chunks before shrinking text.
- Tie captions and visual reveals to the actual synthesized speech. Preserve spoken and displayed forms when punctuation or identifiers differ. A proportional timing estimate is a flagged fallback, never a claim of measured alignment.
- Use sound to confirm visible actions without masking speech. Document music/effect source and rights. For final production media, use two-pass normalization, then measure the encoded AAC MP4 against the rulebook's −15 to −13 LUFS and ≤−1.0 dBTP acceptance range.

## Production handoff

Return a concise scene-contract review with: accepted identities; each scene's source claim, teaching purpose, action/reveal and word anchor; display text and evidence/illustration label; layout and caption-safe placement; audio cue; continuity constraints; and any fallback or unresolved limitation.

Before calling a render ready, require a source-grounded visual purpose and meaningful reveal for every teaching scene. After rendering, inspect the complete encoded video, contact sheet, scene transitions, captions, full audio mix, technical probe, artifact hashes, and exact approval identity. Record missing human viewing/listening or platform-preview evidence as unverified.

## Boundaries

Do not put replacement narration in a scene contract. Do not turn benchmark timing, a measured audio result, or a reference comparison into a universal claim. Do not use externally supplied assets, models, providers, or publishing services without the authorization and provenance required by TubeForge.

Provenance: TubeForge's production standard in `docs/SHORT_FORM_VIDEO_RULEBOOK.md`; benchmark-specific evidence remains in its separate audit.
