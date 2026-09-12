Continued the overnight build with the dashboard authentication foundation.

Implemented:

- Migration `20260831_0017_dashboard_auth.py`
  - `admin_users` with Argon2id password hashes.
  - `auth_sessions` with only hashed opaque session tokens.
- Local auth service:
  - Admin bootstrap via `tubeforge create-admin --username …`
  - Login/logout, session expiry, HttpOnly/SameSite cookies.
  - CSRF validation for mutating requests.
  - Per-client login rate limiting.
  - API returns 401/403; browser dashboard redirects to `/login`.
- Auth configuration added under `auth` in `config/default.yaml`.
- Added auth test coverage.
- Updated overnight status, blockers, test results, decisions, and autonomous progress.

Validation:

- `git diff --check` passed.
- `docker compose config --quiet` passed.
- Container-focused auth/queue/migration tests started and emitted one pass, but the migration-heavy process exceeded the environment’s ~30-second command limit. This is documented as inconclusive, not passing.

Repository remains resumable. Existing user changes, including `run_codex_overnight.sh`, were preserved untouched.