# Reviewed OpenMontage guidance

This directory records a static review and documentation-only consolidation. Read SECURITY_REVIEW.md for findings and limitations; source-manifest.json pins the inspected working tree. No upstream skill instructions were followed during review, and no upstream program was executed.

Installed beside this folder:
- om-storyboard: visual treatment and asset planning after canonical narration acceptance.
- om-video-quality: source fidelity and actual video inspection.
- om-social-delivery: export manifests and publishing handoff through existing integrations.

These are manually rewritten summaries, not executable copies. They do not install OpenMontage or its dependencies, replace yt-script, change TubeForge configuration, add runtime/wheel resources, generate a video, manage a channel, or upload content. Existing project and operator controls apply. Future pipeline adoption requires the normal source/resource hash checks and deployment validation.

## Source map

| Consolidation | Reviewed source paths in OpenMontage |
|---|---|
| Storyboard | skills/meta/creative-intake.md; skills/creative/broll-planning.md; skills/creative/video-gen-prompting.md; skills/pipelines/cinematic/scene-director.md |
| Quality | skills/meta/reviewer.md; skills/creative/sound-design.md; skills/creative/short-form.md |
| Delivery | skills/pipelines/clip-factory/publish-director.md; skills/pipelines/hybrid/publish-director.md; tools/publishers/export_bundle.py |

Source concepts were filtered: omit performance percentages, model rankings, fixed current-platform limits, unconditional stock-license assertions, automatic remote installation and upstream orchestration mandates. Project loudness, duration, captions, provider and approval contracts take precedence.

## Acceptance evidence

See VALIDATION.md. Documentation acceptance does not certify OpenMontage safe to execute or establish an end-to-end video/publishing milestone.
