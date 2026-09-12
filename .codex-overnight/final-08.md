Continued the platform-variant milestone.

Implemented:

- [variants.py](/home/uditaswal/docker/tubeforge/Youtube_Video_Producer/src/tubeforge/pipeline/variants.py)
  - Persists publication plans for:
    - YouTube landscape
    - YouTube Shorts
    - Instagram Reels
    - Facebook Reels
    - Snapchat handoff
  - Reuses the same approved master artifact.
  - Explicitly flags 9:16 profiles as requiring a derivative.
  - Generates platform-safe hashtag metadata from existing tags.
- Publication packages now include `variants`.
- Fixed quality-gate sequencing:
  - Quality validation now runs before `FINAL_READY` is exposed.
  - Applies to generated and source-clip paths.

Validation:

```text
Platform variant test: 1 passed in 0.20s
Changed-source syntax compilation: passed
docker compose config --quiet: passed
git diff --check: passed
```

The offline integration retry exceeded the command window after the sequencing fix, so it is recorded as inconclusive rather than passed. The repository and overnight documentation are current and resumable.