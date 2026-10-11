# Repository hygiene plan and acceptance

## Scope

1. Keep intentional source, migrations, tests, skill resources and configuration
   tracked. Remove generated runtime files from the index while preserving local
   copies. Acceptance: tracked-file audit and positive/negative ignore checks.
2. Organize operator guides and planning documents; correct the API guide's
   URL, authentication and exact script approval. Acceptance: shell syntax,
   local Markdown links and checks against current API contracts.

No remote push, history rewrite, local artifact deletion, generation attempt or
publication is part of this cleanup. Existing uncommitted application work stays
intact. Historical Git commits may still contain removed artifacts.

## Verified acceptance (2026-10-11)

- `.agents/skills/` was already tracked and is not ignored; the new yt-script
  automation reference is included in the index. Bytecode caches remain ignored.
- Removed 44 generated files from tracking (73,625,538 local bytes), retaining
  every local file: overnight output, smoke media/probe data, generated images,
  model weight, preview and stray session/empty scratch file.
- Positive/negative ignore checks, new local documentation links, all shell
  syntax checks and `git diff --check` passed. No generated files remain in the
  tracked-file inventory. No remote push or history rewrite occurred.
- Authentication and exact-script-identity curl examples were checked against
  current handlers; the examples were not executed against a live job.
- Local credentials and generated assets are excluded from Docker build context.
