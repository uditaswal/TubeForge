# LF2 warehouse-routing pilot result

The approved warehouse-routing run `d89896022c604913be4e6c8272c79c3d` captured three operator-supplied primary documents with zero writer calls. It dispatched draft as its first Claude CLI stage. The receipt reported 57,782 input tokens and 30,988 output tokens, for 88,770 total admission units. This includes 6,041 cache-read input tokens. The five-hour subscription fraction is unknown.

Claude rejected its own structured submission with `error_max_structured_output_retries`. The receipt names an extra `scene_plans_note` field in the package. No complete structured draft was returned. The run stopped before review or repair. Phase D remains **BLOCKED**, even though local source capture bypassed the previous research failure and saved a writer launch.

Evidence is in `artifacts/review/long-form-lf2-d-supplied/claude/real-run.json`, SHA-256 `a307845d0a9c8529fce7eabf1d509d7a8bef97a3316ebd5fff18db89b921d1ca`. All prior receipts and the terminal run are preserved.

Two options remain. A Claude path can test a simpler structured-output submission with a separately authorized brief and allowance, but prior failures and 88,770 tokens for one draft make it uncertain within 100,000. The preferred next experiment is to update and preflight the restricted Codex host before proposing a live trial. The exact source, script and independent review gates remain in force.
