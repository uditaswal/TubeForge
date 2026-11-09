# LF2 live Claude pilot result

Phase D is **BLOCKED** at real-script acceptance. The approved 10-minute 3Blue1Brown pilot used the existing Claude Code Pro subscription with usage credits disabled. Run `65e5b2c6100346f5a2c10625e276c8aa` ended in `exhausted` after research and one narration call.

| Stage | Reserved at dispatch | Observed input, including cache | Observed output | Charged |
| --- | ---: | ---: | ---: | ---: |
| Research | 4,074 | 28,927 | 1,368 | 30,295 |
| Draft | 32,424 | 149,324 | 50,105 | 199,429 |
| Total | 36,498 | 178,251 | 51,473 | 229,724 |

The 100,000-token admission budget stopped further dispatch after the draft receipt arrived. The completed call could exceed its estimate. The retained draft itself measured 7,276 local structured-text tokens. Claude's aggregate output was 50,105 tokens and included internal work. The precise reason for the aggregate is unresolved. These counts establish actual CLI usage and leave the five-hour subscription fraction unknown.

Research captured three independent primary pages from Google and PyTorch with HTTP-body and excerpt hashes. The retained 1,448-word, six-chapter narration presents a different example from the reference's handwritten digits. Its hypothetical conveyor scenario builds from a wrong prediction to a numerical weight update and shows how that update changes a second prediction. The opening gives viewers a concrete question to follow. The worked probabilities and loss are consistent to the stated rounding. Offline schema binding failed because scene 26 used a comparison layout without the required three visual elements. The independent review and scoring gates did not run, so the draft cannot be approved.

Evidence is in `artifacts/review/long-form-lf2-d-preflight/claude/real-run.json`, SHA-256 `f0280a90c42f88a04d53d6b4d99f81ba04ce91a3c4f540f52d8e784a61520b7d`. The exhausted run and both receipts are retained.

The next candidate is a revised brief with a simpler scene contract and an explicitly bounded Claude CLI configuration. Test a lower effort and agentic-turn limit with the structured-output workflow before proposing another live run. Raising the cap for the existing configuration is an alternative with greater quota exposure. Any new live trial requires separate authorization. [Claude CLI controls](https://code.claude.com/docs/en/cli-reference)
