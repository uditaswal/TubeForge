---
name: om-social-delivery
description: Prepare reviewed video export bundles and platform-specific publishing handoffs through existing authorized integrations.
---

# Social delivery and publishing handoff

Use to prepare a finished video or clip batch for distribution. This skill organizes handoff; it contains no uploader, scheduler or channel-management integration. Preserve TubeForge review, scheduler, ownership, cancellation and publishing policies. Do not call external services or publish merely because this skill is loaded.

Inputs: exact reviewed master hash, passed quality review, channel voice, intended accounts/platforms, approved variants, rights/source evidence and requested visibility/schedule. Flag missing inputs explicitly.

1. Identify master and derivatives. Keep each clip connected to source video, source interval, accepted script and final render hashes. Rank suggested posting order by standalone clarity, hook and campaign purpose; label rankings as editorial judgments, never predicted reach.
2. Use yt-package for title/thumbnail pairings and its checker; yt-seo for descriptions/metadata; yt-shorts only when supplied long-form material is being repurposed; yt-plan for channel calendars. These remain the canonical skills for those tasks. Do not manufacture analytics, trend evidence or optimal posting times.
3. Tailor copy to the audience and destination while preserving factual claims and channel voice. Keep searchable titles useful and truthful. Add captions, source credits and disclosure notes as required by the actual content and applicable account workflow. Check current official destination requirements before a real upload; do not rely on copied duration, bitrate, safe-zone or file-size limits.
4. Prepare a platform/variant catalog: video path and SHA-256, master/source reference, title, description/caption, thumbnail, subtitle sidecar, language, rights evidence, disclosure fields, visibility, timezone-aware schedule, review identity and unresolved issues. Exclude tokens, cookies, private keys and local credential files from exports.
5. Verify bundle files exist, match reviewed hashes and can be opened. Keep exported, queued, uploading, processing, published and failed states distinct. A local export is not an upload, and an upload ID is not proof that processing/publication finished.
6. If the operator separately requests publishing and project policy permits it, use only a real existing tested integration under the current authorization. Confirm account, exact artifact, metadata, visibility and schedule through the existing approval workflow. Let the application handle leases, durable state, retries and duplicate prevention. Record returned remote IDs and durable confirmation; do not invent success or build an ad hoc browser/token uploader. If no integration exists, deliver the bundle and identify that dependency.
7. Use actual post-publication analytics only when available through an authorized read path; compare outcomes to the channel's own baseline and retain uncertainty. Feed evidence into the next brief without guaranteeing views.

Acceptance: inspected export bundle plus accurate handoff manifest, with unresolved platform/account/integration dependencies stated. Actual publishing acceptance additionally requires durable remote confirmation and project workflow checks. No upload occurs as part of importing these skills.

## Upload-ready package standard (TubeForge Publishing page)

- **Title:** pick from the writer's ten options for concrete stakes or a named subject; ≤ 100 characters; no date-only or CVE-number-only titles; no angle brackets.
- **Description:** exactly two lines. Line 1 is the hook sentence (≤ 125 characters, the part shown above the fold). Line 2 is a short teaser or the named source plus up to three hashtags (never a follow or subscribe request). Longer text belongs in a pinned comment.
- **Thumbnail:** 1280×720 JPEG ≤ 2 MB. Big 2–3-word headline (a question plus a payoff in yellow works well), one logo badge when the subject is a named technology, and a video frame chosen after the opening hook so no sentence appears twice. Never put the same words in thumbnail, on-frame text and title.
- **Operator control:** title, description, tags and thumbnail (text, video moment, logo, or an uploaded image) stay editable until the draft is saved; the reviewed identity covers the thumbnail checksum.
- Validate with `python .agents/skills/om-video-quality/qa_check.py data/artifacts/<job_id>` before creating a draft.

Provenance: docs/reviews/openmontage/README.md (repo-only archive, not packaged). OpenMontage itself only exports locally.
