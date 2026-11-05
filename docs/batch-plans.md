# Batch plans (script-batch production)

Operator notes for importing a plan file, producing a day of Shorts, reviewing, staging exports and the overnight schedule. Example plan: `examples/batch-plan-example.md`.

## Batch plan import

In signed-in Studio, open **Batch plans**. Choose a markdown file (or paste it),
select **Validate and preview**, review the table and any line-numbered errors,
then **Commit import**. Each `## Heading` requires exactly one fenced `yaml`
block with `id`, `title`, `concept`, and `beats: [{t: 0, point: Hook}]`.
Optional fields include `length_s` (30–90; default 60), `ending` (`loop` or
`debate`), `channel`, `publish_at`, `hook`, `cta`, `claims_to_verify`, `sources`,
`thumbnail: {text: ..., visual: ...}`, `tags`, and opaque `narration` text.
Publish dates are metadata; importing never schedules or uploads anything.
Re-importing skips identical IDs, updates unused shorts, and reports conflicts
for changed shorts already reserved or produced. A validation error saves nothing.

Filter Batch plans by day, select shorts, then choose **Produce selected shorts**.
A configured vertical preset must support every selected duration. Each short
becomes one normal generation; repeat clicks reuse its existing job. Script and
preview approvals remain in Generations. The queue waits for these approvals,
uses the existing heavy-work lease, and records checker results in Activity.
A failed or cancelled short does not block later work; exhausted script allowances
require an operator decision. Finished batch jobs stop before publication.
Progress uses measured completed work; ETA stays unavailable before timing evidence
or while approvals are pending. No script attempt allowance is reset.

Open **Batch plans → Day review queue** to inspect a day's final videos, available
thumbnails, QA output, and script/beats. **Approve** binds the exact video and
review identity; **Stage as ready** requires that approval and matching successful
QA. Ready is local staging only. **Reject** returns the item to needs review.
**Regenerate** creates a new ordinary generation with fresh script/preview/final
review requirements; it preserves the exact brief and its script allowance.
An unchanged script may replay its accepted cache. Existing decisions are invalid
if reviewed artifacts change. Missing thumbnails and unfinished videos are shown
truthfully; the player stays open during background refresh.

Batch finals also receive a local 1080×1920 portrait thumbnail using the existing
thumbnail composer. Plan `thumbnail.text` takes precedence over the generated
package's first nonblank thumbnail option. The visual hint is advisory; no image
is fetched. A thumbnail failure leaves the video intact and appears as a truthful
unavailable reason in Day review. Worker restart resumes missing thumbnail work.

## Overnight batch production

Apply the current database migrations before starting updated web, scheduler and
worker processes (`alembic upgrade head`). On Batch plans, use a **Plan ID**
(default `default`) when importing a file. Short IDs remain globally unique;
importing an existing ID under a different plan reports a conflict.

**Produce automatically** is off by default. Save a local start time, IANA time
zone (default Asia/Kolkata), and target day offset (`1` produces tomorrow's dated
shorts tonight). The existing scheduler submits ordinary manual-review jobs;
no approvals or staging happen automatically. Next run and last submission result
are shown in Studio. “Done” means submission finished, not that videos passed review.
Interrupted submissions resume the same short IDs after their five-minute lease;
repeated fires reuse existing jobs and preserve script allowances.

**Hold all batch production** prevents manual/automatic batch creation,
regeneration, and new batch worker admission across every plan. Running work
stops at its next ownership/checkpoint check; the current operation may finish.
Turn hold off to resume. Hold does not affect unrelated non-batch jobs or approve,
stage, upload, or publish anything.

## Local staged exports

**Stage as ready** now writes the final video, registered portrait thumbnail,
and `package.json` under the existing publishing staging area:
`data/publishing/staging/batch/<plan-id>/<date>/<short-id>/` (relative to the
configured artifact root's parent). The date is the short's publish metadata date,
or the review date in Asia/Kolkata when no publish date is supplied.
A missing thumbnail prevents export and leaves the approval available for review.

Each folder is an atomic pointer to a completed immutable version. Re-approval
and staging replace that pointer only after all copied files match reviewed
checksums. The manifest preserves title, generated description (or concept when
unavailable), tags, thumbnail text, source URLs, QA, reviewed hashes and `publish_at`
as metadata only. Old versions stay retained under `.versions` for traceability.

Use **Open export** on a ready review row to open the authenticated local file
list and download the video, thumbnail or manifest. Every open/download checks
current review, QA and file hashes. Changed artifacts or staged bytes invalidate
the export, remove its active pointer, and require review/staging again. Rejecting,
regenerating or re-approving also removes the prior active export. No upload or
platform operation is performed.

## Disclosure and rights review

Before approving a final in Day review, choose whether it requires the platform's
AI disclosure. The choice has no default. Review the actual imagery and narration;
AI assistance alone does not settle the platform requirement. TubeForge records
AI-assisted writing and synthetic narration separately from that decision.
Sources, the existing originality check, and the audio licence trail accompany
the staged manifest. Missing evidence blocks approval and staging. Catalog music
must resolve to its actual licence terms; a file pointer alone is insufficient.
Changing the source/audio evidence invalidates the previous approval and export.
Nothing in this workflow publishes a video or sets a platform disclosure control.

## Channel repetition and cadence

Use the [before-upload checklist](channel-safety-checklist.md) when reviewing.
Day review shows advisory repetition and cadence warnings from the structured
`GET /api/batch-plans/safety-report` response. Repetition covers the selected day
and preceding six days, grouped by channel. Missing render evidence stays unknown.
Hook formulas are simple question/conditional/statement heuristics. Phrase and
word-overlap matches need human judgment; they do not predict platform enforcement.
Cadence covers stored plans across plan IDs, including adjacent days for spacing.
Import preview and commit responses include `cadence`; Batch plans displays those
warnings. Missing or timezone-free publish times cannot be assessed and warn.

Configure `channel_safety` in the application YAML. Defaults are three Shorts per
channel per day, 180 minutes apart, using Asia/Kolkata for day boundaries. These
are local review preferences, not platform limits. Override them per channel:

```yaml
channel_safety:
  defaults: {max_per_day: 3, min_spacing_minutes: 180, timezone: Asia/Kolkata}
  channels:
    engineering: {max_per_day: 2, min_spacing_minutes: 240, timezone: Asia/Kolkata}
  similarity_threshold: 0.7
  repeated_phrase_words: 5
```

The guard warns; it does not block production, move dates, or schedule uploads.

For undated Shorts, the repetition window uses the stored job/topic creation time;
`window_basis` identifies that fallback. Entries without either usable timestamp
are listed in `unassessed_ids`. Cadence still warns that a publish time is missing.
