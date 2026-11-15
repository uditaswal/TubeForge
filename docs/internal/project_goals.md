# Publishing work: completed and pending

Updated 15 November 2026. This document summarizes the publishing work merged into the local `dev` branch from the YouTube and Instagram workstreams.

## What was done

- Added a YouTube connection flow and private-upload backend, including reviewed disclosure, video checks, an estimated quota ledger and readiness information.
- Added Instagram connection screens and authorization code, plus a delivery framework for separate container preparation and publication.
- Added a Day review action to prepare a draft for selected destinations, and Publishing controls for private YouTube slots and eligible pending deliveries.
- Hardened publisher startup, retries, account reconnection handling and recovery from uncertain delivery outcomes. A worker with no valid encryption key stays idle.
- Merged the work into local `dev`. The combined publishing regression passed 151 tests, including signed-in responsive dashboard checks. A seven-day simulated run completed 42 deliveries without duplicates or losses. These checks used local or fake services.

## What is pending

- **YouTube live check:** Connect the intended channel when convenient, select an approved final and separately authorize that exact private upload. Verify its remote metadata, processing, thumbnail and video frames afterward. The default estimated upload reservation is 1,600 quota units.
- **Instagram publication:** Adapt the existing Instagram adapter and public confirmation gate to the durable separate-publication protocol. The connection code is present, but the publisher worker does not advertise Instagram and the executor rejects the old adapter before remote work. A real connection and post remain unverified.
- **Scheduling:** Verify real scheduled delivery when separately authorized. A full calendar interface and Instagram scheduling interface remain to be built. YouTube stays private while API audit approval is pending.
- **Release:** The changes are on local `dev`; they have not been deployed, pushed or merged into `main`.

Detailed evidence and technical handoff: [publishing backend review](../publishing-backend-review.md) and [handoff](../HANDOFF.md).
