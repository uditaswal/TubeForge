# LF2 compact pilot result

The approved spam-classifier pilot `2b9341f667c2407b81f493ab6c6bc951` captured all three primary pages. Claude research reported 76,140 input tokens, including 55,869 cache-read tokens, and 2,493 output tokens. The ledger charged 78,633 of the 100,000 admission units. The remaining 21,367 units could not cover the draft reservation, so the worker stopped before dispatch. This pilot did not exercise the compact draft contract live.

The exhausted run and source packet are preserved in `artifacts/review/long-form-lf2-d-small-output/claude/real-run.json`, SHA-256 `acf61ee3e8a7cdd073d151d26a57b99c6850a274e08876eb3ae4f08fcfa263b0`. Phase D remains **BLOCKED**. The result verifies that the worker stops further dispatch after unexpectedly high observed research usage. The five-hour subscription fraction remains unknown.

The preferred next design is a supported workflow that captures operator-selected primary pages before any writer call, preserving claim-level checks and independent review while removing repeated research usage. Another option is a newly authorized higher admission budget with the existing research workflow. Raising the cap would expose more subscription usage without resolving earlier draft JSON failures.
