# Blockers

- Live YouTube, Meta/Instagram/Facebook, and Snapchat smoke tests require operator
  OAuth applications, approved permissions, and test credentials. No credentials
  were inspected or used during this run.
- The host Python installation lacks pip/pytest and the existing local container
  image predates the new dependency. A legacy Docker build began but exceeded the
  command execution window; therefore runtime tests are not claimed as passing.
- The command runner limits individual container test invocations to roughly 30
  seconds. The migration-heavy focused suite must be run in a normal shell or a
  rebuilt Compose container to establish a passing result.
- Production dashboard bootstrap requires an operator to run `tubeforge
  create-admin --username <name>` after migrations; no default account is
  supplied by design.
- The generic multi-target dispatcher is exercised only with the local fake
  publisher. Wiring official YouTube/Meta/Snap adapters to account credentials
  remains credential- and approval-blocked.
- Live social authorization remains blocked pending operator-provided OAuth apps,
  redirects, approved scopes, and encryption key. The account APIs do not claim
  a connected live platform without those prerequisites.
