# Revised LF2 Claude pilot result

The approved desk-lamp pilot `a002cf651405422ba521f88902959f86` stopped at research. Claude reported 26,280 input tokens, including 1,456 cache-read tokens, and 1,875 output tokens. The durable ledger charged **28,155 tokens** against the 100,000-token admission budget. The runner recorded three web searches in its provenance. Claude returned an error without a usable structured research result. Source capture, narration, review and scoring did not run.

The original receipt retained an empty result string and the aggregate usage. It did not retain the CLI error envelope, so the specific stop reason is unknown. The host now preserves the bounded redacted error envelope, or stderr when stdout is empty, alongside the exact usage and any structured output. The diagnostic regression uses an error envelope with no result string.

The failed run remains immutable. Evidence is in `artifacts/review/long-form-lf2-d-compact/claude/real-run.json`, SHA-256 `ec23657c7b39c375d08dc1057ce842c3778b85980b384e7551acdd7035bb208e`. The earlier conveyor pilot remains separately exhausted. These two trials do not establish a five-hour subscription fraction or verify Phase D.

A follow-up Claude candidate can restore the research-stage settings that returned usable URLs in the first pilot while keeping the tighter writing limits. This is the preferred next experiment if the operator wants another bounded trial. The other path is to update the Codex host with administrator access and preflight a Codex trial. Either path requires a distinct reviewed brief and a separately authorized allowance.
