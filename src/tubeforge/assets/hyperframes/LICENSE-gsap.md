# GSAP: license and provenance

`gsap.min.js` is GSAP core 3.14.2 (MIT licensed as of GSAP 3.12+; see
https://gsap.com/community/standard-license/), vendored here so a HyperFrames
composition never fetches it from a CDN at render time (the HyperFrames contract bans
network fetches during render — `.agents` skill reference, video-quality review §4.2).

Fetched 26 Oct 2026 from `https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js`,
the exact version HyperFrames' own registry components pin
(`heygen-com/hyperframes`, e.g. `registry/components/caption-kinetic-slam/`).
