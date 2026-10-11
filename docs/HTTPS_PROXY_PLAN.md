# Existing external proxy HTTPS repair

2026-10-11. Scope: the operator's existing TubeForge nginx route only.
The documented loopback developer URL remains http://127.0.0.1:62065.
No new host listener, firewall/Tailscale routing change or cookie-policy relaxation.

| Phase | User-visible outcome | Acceptance | Evidence | Out of scope |
| --- | --- | --- | --- | --- |
| 1 | Prepared HTTPS replacement for existing HTTP route | Isolated nginx syntax test against temporary test certificate | Ignored staged configuration and validation output | Installing a test certificate in production |
| 2 | Browser login over trusted HTTPS | Actual certificate, nginx -t, verified HTTPS health/login and operator sign-in | Certificate metadata and endpoint checks; no private keys in Git/logs | Other proxy services, new host ports, publication |

Phase 1: **IMPLEMENTED**, syntax test pending. Phase 2: **BLOCKED** on
administrator certificate access (`tailscale cert` returns Access denied).
The database issue is already resolved: schema 20261005_0028, heartbeat table
exists, nginx-proxied HTTP health/login succeed. The submitted external URL is
HTTP; production session cookies have Secure=true.
