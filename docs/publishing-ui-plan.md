# Publishing UI work

## Phase 1 — reviewed post preparation and scheduling: **IMPLEMENTED**

Outcome: an operator can prepare a draft from an approved Day-review item, review its saved destinations, choose an IST slot, and manage eligible pending deliveries. Unsupported Instagram publication remains clearly unavailable until its adapter and gate are integrated.

Acceptance: focused API and signed-in browser checks cover preparation, review binding, slot selection, scheduling, warnings and pending actions at desktop, tablet and mobile widths. Evidence: test output and screenshots under `artifacts/review/publishing-ui/`. The signed-in fake-backed check covers draft creation, scheduling, cadence override and responsive screens; no live upload, account connection or deployment.

Out of scope: implementing the Instagram adapter or its API platform gate, live posts, public YouTube scheduling, merge and deployment.
