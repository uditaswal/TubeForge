# Development helpers

Run these scripts from the repository root. They are developer tools, not
production worker entry points.

| Script | Purpose | Preconditions |
| --- | --- | --- |
| `test_offline_workflow.sh` | Fake-provider local pipeline smoke; automatically approves local gates | Isolated stack, authentication disabled, fake content/voice/media, publishing disabled |
| `test_script_config.sh` | Example invocation of the offline smoke helper | Same isolated environment |
| `codex_overnight.sh` | Historical autonomous development supervisor | Requires a supplied `OVERNIGHT_MISSION.md`; unavailable by default |

`run_codex_overnight.sh` is a separate historical development runner using
`docs/overnight/MISSION.md`. The root entry point forwards to this script for
existing local cron invocations. It is not used for production scripts.
Neither development runner should be invoked merely to validate repository
cleanup. Generated output under `autonomous_logs/` and `.codex-overnight/` is
local-only. Production commands are in [the operator guide](../readme.md) and
[the authenticated API guide](../docs/operations/api-workflow.md).
