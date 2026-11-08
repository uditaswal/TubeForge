# Reference-video intake (LF1)

Open Creator Studio at `http://127.0.0.1:62065`, sign in and choose **Reference videos** (`/references`). This workflow captures context for a later original long-form treatment. It does not generate a script or video, verify factual claims, approve material or publish anything.

## Capture and review

1. Paste a public HTTPS YouTube video link. Watch, short, embed and youtu.be links normalize to one video identity.
2. Choose a configured channel, a 10/12/15-minute target and the exact caption language code (for example `en` or `hi`). The API accepts any target from 600 to 900 seconds. No automatic translation occurs.
3. Select **Capture reference**. The web process saves a pending request; the existing TubeForge worker retrieves metadata and accessible captions. A running worker and migration `20261108_0033` are required. The live stack must be rebuilt/migrated/restarted when deploying this branch; it is not deployed by creating an intake.
4. Review the title, creator, source duration, language, origin, capture time, limitations and timestamped text. **Context captured** means usable transcript context was persisted; it does not mean the source audio/video was inspected or the facts accepted.
5. Open **Proposed improvement brief** for indexed source excerpts and provisional opening/example/payoff questions. It is deterministic, bound to the exact snapshot hash and makes no AI calls. Its caption-interval percentage describes timestamp coverage only. Research, audience interpretation, originality comparison against the full transcript and accepted scene planning remain later gates.
6. Download the canonical captured-context JSON if needed. Its SHA-256 matches `intake.reference_snapshot_sha256`; source text remains untrusted reference material.

## Missing captions and retries

YouTube can advertise a caption track while returning an empty or restricted response. Intake then shows **Transcript needed**, retaining available metadata and an actionable reason. Login/private/deleted references or network failures can show **Capture failed**. Neither state fabricates a transcript. No cookies, account credentials, access bypass, paid transcription or media download are used.

Open **Supply a timestamped transcript** and paste or select an SRT, VTT or JSON file, up to 1 MB of UTF-8. JSON is an ordered cue list such as:

```json
[{"start_seconds":0,"end_seconds":4,"text":"An operator-supplied caption."}]
```

Cues must be nonblank, ordered, have positive intervals and fit inside the source duration. Invalid timestamps are rejected; the application does not silently repair them. Saving creates a new queued revision. When earlier metadata exists, the worker reuses it without another network call and labels the transcript **supplied**, unverified against source audio. If metadata was never captured, a public metadata fetch is still necessary.

**Capture fresh revision** retrieves the public source again, bypassing the capture cache and clearing supplied cues in the new request. Earlier supplied text and snapshots remain in their revisions. Use the revision selector to inspect them; only the current revision can be revised. **Cancel pending capture** durably cancels that revision and prevents its worker from promoting a later result. Cancellation appears as `failed` with code `cancelled` in the frozen read contract.

An identical create request returns the existing revision without another capture. Equivalent extraction inputs across channels/target lengths reuse saved captures. There is no automatic freshness promise: inspect capture time or request a fresh revision. Transient retrieval failures are not reused as successful captures. Worker claims expire and can be recovered after restart; a stale owner cannot replace a recovered or cancelled result.

## API and operating bounds

All endpoints use existing sign-in/session protection; mutations also require the session CSRF header. The server records the authenticated actor. Clients cannot submit approval, trusted hashes or fetch-success assertions.

| Operation | Endpoint |
| --- | --- |
| Choices | `GET /api/reference-intakes/options` |
| Latest 50 compact history summaries | `GET /api/reference-intakes` |
| Queue intake | `POST /api/reference-intakes` |
| Full detail, worksheet, revision history and activity | `GET /api/reference-intakes/{id}?revision=1` (revision optional) |
| Transcript/refresh/cancel | `POST /api/reference-intakes/{id}/revisions` with `expected_revision` and `action` |
| Exact canonical snapshot | `GET /api/reference-intakes/{id}/snapshot?revision=1` |

Create fields follow `ReferenceIntakeRequest`: `reference_url`, `target_duration_seconds`, optional `channel_identity`, `language` and `supplied_cues`. Revision actions are `transcript` (plus `transcript_text`), `refresh` or `cancel`. Concurrent stale actions return 409. Invalid input returns 422; a request body over 2 MB returns 413. History summaries intentionally omit transcripts; the selected detail/export supplies them.

Acquisition permits only allowlisted public YouTube HTTPS hosts, validates all resolved IPs and redirects, pins the checked address for TLS, and bounds each fetch to 25 seconds, metadata to 3 MB and captions to 1.5 MB. Snapshots allow at most 10,000 cues and 1 MB of transcript text; source duration is capped at six hours. Role-control source text is rejected. Signed caption URLs are not persisted or exposed in errors.

Local acceptance and its live-caption limitations are recorded in [LF1 review](../long-form-lf1-review.md). No production writer/profile has been enabled by LF1.
