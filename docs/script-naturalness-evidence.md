# P2 live trial: writer prompt rules (6 Nov 2026)

Status: **IMPLEMENTED, trialled on two briefs, not operator-reviewed.** Evidence for phase P2 of `docs/script-naturalness-plan.md`.
The rules are `host_claude_runner.py::RULES` (the WRITING CHECK block) and the editor's sense check; they are live on `dev` since `190a4f2`.

## What was run

- Two new briefs through the real batch API (plan `p2-trial`) with explicit sources, so no research call, and the Claude runner started from `dev` with the rules.
  Baselines are the earlier pilot scripts for the same topics (old prompt), compared with `scripts/script_scorecard.py` and by reading.
- Spend: 7 Claude calls, $1.78 (authorized: about 5 to 10 calls). Rate limit: 4 calls (one repair after a word-count rejection). Idempotency: 3 calls.
  A first idempotency submission with three sources (including the long IETF draft) failed before any call: the assembled prompt exceeded the 90,000-character limit.
- Neither script was approved or rendered. The trial jobs were deleted afterwards so they would not block the FIFO batch queue.

## Rate-limit brief (the case in the review)

New script (P2 rules):

1. Your AWS API Gateway limit is a target, not a wall.
2. Throttling protects your API from being flooded with requests. It feels like a wall.
3. Both throttles and quotas are best-effort targets, not guaranteed request ceilings. AWS says so.
4. Requests drain a token bucket in your gateway. Each one spends a token.
5. Worse, the bucket allows a planned overrun. Traffic can pass your limit by design.
6. Quotas leak too. Even without a burst, AWS says clients can exceed your quotas.
7. AWS warns against relying on either one to control costs. Same for blocking access.
8. Use these instead. AWS Budgets monitors your costs, and AWS WAF manages your API requests.
9. To keep people out, use real login checks. Usage plan quotas will not do it.
10. A limit is a target. Let AWS Budgets and AWS WAF do the real work.
11. Go ahead and set your limits if you like, but never forget that

Against the review's seven points:

- Pass: the payoff now ends on the source's own recommendation (AWS Budgets and AWS WAF), not on more throttling.
- Pass: burst-by-design (scene 5) and best-effort leakage (scene 6) are separate scenes with their own labels.
- Pass: terminology is consistent, and the "that is not it" filler is gone.
- Fail: the hook names AWS API Gateway but carries no figure, and the whole script uses no numbers, so there is no running example (points 2 and 3).
  The hook idea is also restated in scene 2 ("It feels like a wall").
- Not visible in text: caption breaks (point 7) are the renderer change.

## Idempotency brief

Baseline (old prompt, pilot):

1. Did Stripe charge you twice when your payment timed out?
2. That fear is real. The payment can work, but your reply gets lost.
3. Your app invents a unique label, called an idempotency key, for each payment.
4. Retry with the same label and the server hands back its saved answer.
5. Stripe saves the first answer, even when that answer is a server error.
6. But some failures never get saved. Bad input and clashing requests run fresh.
7. Change a detail and the server says no. Same key, different payment, error.
8. Old keys expire, though. Past twenty four hours, they can be deleted.
9. The web is writing this down. Draft revision eight of the header is out.
10. Keys go on POST requests, which create things. Reading and deleting repeat safely already.
11. Replay the first answer and a retry never charges you twice.
12. So when your payment times out, the real question is

New script (P2 rules):

1. Stripe remembers your first answer, even when it was a 500 error.
2. You tap pay. The charge goes through, but the reply never reaches you.
3. Retry blindly and your customer is charged twice. Stripe's blog calls that very bad.
4. Your client makes up a unique ID and sends it along. The server spots repeats.
5. The older Stripe API saves the status and full reply of your first request.
6. Then your retry returns that saved reply. Failures included.
7. But if your request fails its basic checks, Stripe saves nothing. Retrying is fine.
8. Change the request details but reuse the key. Stripe returns an error.
9. After 24 hours, Stripe can delete a key. Reusing it makes a new request.
10. Make your key long and random. Never use an email address.
11. My verdict: a key is memory, not magic. Your retry replays the first answer.
12. and that is the one rule behind every safe retry, because

| signal | baseline | P2 |
| --- | --- | --- |
| viewer address share (middle scenes) | 0.3 | 0.8 |
| sentence length variation | 0.34 | 0.44 |
| contractions per 100 words | 0.0 | 0.7 |
| hook | a question about being charged twice | a specific consequence ("remembers your first answer, even when it was a 500 error") |

Read-through: the new script speaks to the viewer, opens on a concrete consequence and ends on a plain rule.
Two lines need a source check before approval: "Stripe's blog calls that very bad" and "The older Stripe API saves the status and full reply".

## Limits of this evidence

Two topics, one run each, one reader. The scorecard is a heuristic. The rate-limit script still lacks a figure, and nothing was listened to or rendered.
P3 (promoting any check to a gate) and P4 (voice listening test) are still open, and the operator's own read of these scripts is the real acceptance.
To undo the prompt rules: run `git revert -m 1 190a4f2` on `dev`, then restart the Claude runner.
