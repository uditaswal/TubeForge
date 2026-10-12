# Video visual pipeline inventory — tasks 1–3

12 October 2026. This records the focused inventory and acceptance evidence for the first three tasks in [the implementation order](../design_doc/tubeforge-implementation-order.md). `docs/STATUS.md` owns current status. The operator stated that the donor authors granted written permission for code use and asked us to skip license review for this task.

| Existing part | Current path | Finding and adaptation |
|---|---|---|
| Script and scene contract | `src/tubeforge/domain/contracts.py`, `src/tubeforge/providers/content/prompts.py`, `.agents/skills/yt-script/automation.md` | Script sections map one-to-one to scene IDs. Previously `VideoPlanScene.visual_intent` retained only broad `visual_type`; it now carries concrete subject, purpose, composition, display text and search terms. Older approved packages project with derived fields. New skill instructions ask the writer for explicit scene fields; current v6 output is rejected when any scene omits its subject, purpose, composition or visual elements. |
| Asset routing and acceptance | `src/tubeforge/pipeline/visual_router.py`, `pipeline/assets.py`, `pipeline/orchestrator.py` | Existing local/stock routing, immutable accepted asset manifest, cache checks, restart handling and visual quality gate are retained. Local abstract v1 art is invalidated on resumed asset acquisition; new storyboard art is source-specific and style-versioned. A resumed scene is reused only when its serialized visual request still matches the accepted asset; a changed direction refreshes that scene without re-searching unchanged scenes. |
| Local visual generation | `src/tubeforge/providers/media/local_graphics.py` | Former four-layout abstract graphics did not explain the scene. FFmpeg now renders approved scene text with terminal, graph, stack, split or process geometry. No external image provider or paid API is invoked. Docker installs DejaVu Sans for the renderer. |
| Storyboard review | `src/tubeforge/pipeline/storyboard.py` | New manifest links narration, visual intent, asset hash, provider, source URL, author and license. Ordered FFmpeg contact sheets cover every accepted scene, including multiple pages. They are saved as durable asset-stage artifacts. |
| Final renderer | `src/tubeforge/rendering/preview.py` | Continues using accepted asset paths and checksums. Full final-video quality remains a later task; the earlier 1080×1920 OOM job is not retried. |
| Donor visual planner | `youtube-autopilot` at `69d8f0cf2872bd1467b4d09d12eb1109603345e7`, `yt_autopilot/agents/visual_planner.py` and `cinematographer.py` | Adapted the idea of narration-linked subject, explanatory purpose, composition and overlays into TubeForge's existing domain. The donor's additional LLM roles and provider-specific prompt stack were not needed for this slice. |
| Donor scene repair | `youtube-automation-agent` at `e26792ae00dc1ec2434faf32632896609396dfad`, `utils/scene-repair-service.js` | Persistent scene identity and revision-dependent repair belong to later tasks 5–6. No repair API was added while task 3 visual coverage is still under review. |

The retained approved tutorial, comparison and explainer packages each produced six portrait frames and a complete contact sheet under `artifacts/smoke/storyboard-visuals/`. Those outputs were inspected. Git scenes now show terminal commands or a branch graphic; Docker scenes show stack/flow geometry. **Creative relevance remains open:** these older packages lack explicit subject/purpose/composition/visual-element fields, so their fallback labels repeat visual search phrases and some diagrams lack explanatory labels. The deployed prompt can supply those fields; a new authorized production script and its contact sheet must be reviewed to prove that it did. This inventory does not claim that the generated video itself passes task 4.

A local pipeline smoke reached `ASSETS_READY` and saved both `storyboard_manifest` and `contact_sheet_001` under `artifacts/smoke/storyboard-pipeline/rendered/storyboard-smoke-3/`. The offline fake script in that smoke has only three scenes and demonstrates integration, not creative quality. Direct source/installed-wheel checks passed, including acceptance of an enriched retained tutorial package and rejection of an omitted scene element. Pytest and Docker checks were unavailable in this session because Docker access was denied and pytest could not be installed due DNS resolution failure. All smoke media and wheels remain ignored by Git.

## Deployment verification and remaining acceptance

Earlier on 12 October, the running worker exposed the then-current storyboard style, v6 prompt template and all four scene-direction fields; its DejaVu font was present. Selected host-installed Python modules then byte-matched this checkout, the canonical skill automation file matched the host copy, and a live `PreflightContentV1` request matched both the assembled prompt SHA256 and all seven skill-resource hashes. This operation did not start Codex or spend a script attempt. That earlier offline wheel was
`artifacts/smoke/storyboard-visuals/wheels/tubeforge-0.1.0-py3-none-any.whl`
with SHA256 `15c852b537409926d0174ef452d77123a859d8c7f87ddc2bde06dbf1c0a799eb`. It was installed into an isolated temporary target during preparation; the live installation was verified by matching files and preflight, not by asserting a package-manager wheel hash. It was assembled from this checkout because DNS prevented installing the normal build backend; rebuild it with Hatchling when package-network access returns.

That wheel is superseded. The current absolute host commands and wheel hash are
recorded below; web and worker have already been rebuilt for the current source.

The container image includes `fonts-dejavu-core`, needed for deterministic local storyboard typography; its presence was checked in the running worker. There is no schema migration in tasks 1–3. Focused Compose tests passed: 12 storyboard/contract/media-routing tests and 3 asset-recovery tests; a corrected six-scene v6 validation test passed separately (16 passing checks total). Do not retry the exhausted prior script packet or final-render job.

On 12 October, a separate Docker image/container comparison job (`42899f0c102248e3a64af4baaa41429e`) used official Docker source excerpts. Live production preflight matched the assembled prompt and all seven installed skill resource hashes. One Codex invocation returned six narration sections, five source-linked claims and six explicit scene directions; the exact script checksum was approved. The job then saved a six-scene storyboard manifest/sheet and a 41.592-second preview. The [production contact sheet](../data/artifacts/42899f0c102248e3a64af4baaa41429e/storyboard/contact-sheet-001.png) was inspected. Its frame hashes, license fields and scene coverage are complete, but the visuals do not pass creative acceptance: the image/container relationship is represented by repeated bars and disconnected lists, and subject descriptions are truncated. Sampled preview frames also show these same weak visuals under karaoke captions. Task 2 is VERIFIED; task 3 remains IMPLEMENTED pending a layout repair and another full-sheet inspection. This local preview is not a finished or published video.

The v7 local layout repair replaced repeated subject paragraphs with distinct
flow, package, branch, terminal and checklist diagrams; `assets.py` now checks
the style from the provider constant. The tested web/worker images were rebuilt
and restarted; the running worker reported `portrait-storyboard-v7`. Ten focused
Compose storyboard/asset/orchestrator tests passed. Job
`0d8a765c71a948cebaf6c8f01e572043` reused the same approved content
package SHA256 from the generation cache, without another model invocation,
and reached `preview_ready`. Its six accepted frame hashes, rights manifest,
[contact sheet](../data/artifacts/0d8a765c71a948cebaf6c8f01e572043/storyboard/contact-sheet-001.png),
and 41.592-second H.264/AAC preview were checked. At 13 seconds the frame
visibly connects one shared image to container A and B with captions below.
However, "docker run command", "image outline" and "two running rows" are
still placeholder labels rather than concrete demonstrations. This improvement
does not meet task 3's creative acceptance threshold or prove full audiovisual
quality. The dashboard review gate remains open; nothing was published.

The next editorial repair is in the canonical
`.agents/skills/yt-script/automation.md`: visual elements must be short,
source-supported labels containing the actual command, output, object or state;
placeholders such as "command", "two rows" and "image outline" are explicitly
rejected. A Hatchling wheel built from this checkout is at
`data/artifacts/yt-script-visual-labels-wheel/tubeforge-0.1.0-py3-none-any.whl`
(SHA256 `375bab05a7e679d830546ef7b2c3d42a7ea77826f73a0e5711075259085eb88c`).
All four yt-script files inside it byte-match the canonical folder. Rebuilt
web/worker images contain the new resource; 36 focused skill/script tests
passed. A live read-only `PreflightContentV1` returned `ok=True`, but
`resource_match=False` and `prompt_match=False`: worker automation SHA256 is
`43d6266882abaa515e4b5c9b114e6585d9ae2a215d039263ad20f281573e4a13`,
while the installed host runner still reports
`e41d6756f637221c4c819112c0328dc30f52f905899f61a26108a29ab71a01be`.
The production client rejects the mismatch before reserving or charging a
model attempt. At that point host administrator deployment required:

```bash
sudo /opt/tubeforge-codex-runner/venv/bin/pip install --force-reinstall --no-deps /home/uditaswal/docker/tubeforge/Youtube_Video_Producer/data/artifacts/yt-script-visual-labels-wheel/tubeforge-0.1.0-py3-none-any.whl
sudo systemctl restart tubeforge-codex-runner.service
```

The later deployment was verified by a fresh read-only preflight before
production generation. This was an external deployment dependency at that time,
not a successful creative result by itself.

A further bounded v8 text-fitting change prevents supported commands from
being clipped in narrow diagram slots. Style version `portrait-storyboard-v8`
invalidates older cached frames. Two 1080×1920 offline frames with the exact
`docker run --name web-a -d nginx:alpine` / `web-b` examples were inspected;
commands and state labels fit. The focused storyboard/asset/orchestrator
selection passed 8 tests and all 6 media-routing tests passed after the final
fit adjustment. These are design proofs, not approved production frames.
At that point the running worker reported v8; the rebuilt wheel's four skill
files and renderer byte-matched the then-current checkout. Its SHA256 was the
hash above. The current worker later advanced to v9, while host skill resources
remained byte-identical to their canonical folder.

A fresh four-source packet is prepared at
`artifacts/smoke/storyboard-production-v7/docker-concrete-visuals/request.json`.
It adds the official [Docker CLI run reference](https://docs.docker.com/reference/cli/docker/container/run/)
to the image/container sources, giving a named `nginx:alpine` example and
`docker ps` fields. The brief explicitly calls for two distinct names and
forbids invented IDs, times and port mappings. `ContentRequest` and source
preflight accepted it; the assembled prompt is 40,360 characters, embeds the
new skill and exact command, and hashes to
`a094a10866e97abe8ffab882881177367ca114632a8e1e84587328f04fbf3407`.
At that point host preflight for this exact packet still returned old skill
and prompt hashes, so no job or model invocation was started then. A later
matching preflight allowed the production job described below.

## Production acceptance — v9 Docker comparison

A fresh live preflight matched prompt SHA256
`a094a10866e97abe8ffab882881177367ca114632a8e1e84587328f04fbf3407`
and all seven canonical skill-resource hashes, including
`yt-script/automation.md` SHA256
`43d6266882abaa515e4b5c9b114e6585d9ae2a215d039263ad20f281573e4a13`.
Production Codex job `884fc38c19fa430f946dd4078bc1868d` made one accepted
model invocation, returned six source-linked narration/scene pairs and saved a
concrete source-backed storyboard. Its initial 45-second narration failed the
measured duration gate after TTS; 57.481 seconds of speech plus pauses exceeded
tolerance. That failed job was retained, not silently accepted.

A second job `0394bd453cd24dc4adbeee5ac5c1fee4` reused the exact generated
package from cache, without a second model invocation. A six-section shortened
narration passed the revision validator, was saved through the existing script
revision handler, and received a fresh exact approval for content SHA256
`68e711a27e121355e24605a4f4b7af696be47407540aaa61bb67af1fa831ffdc`.
The worker was updated to `portrait-storyboard-v9` before approval. V9 adds a
comparison composition and recognizes CLI tables; affected focused layout
tests passed 8/8. The resulting [contact sheet](../data/artifacts/0394bd453cd24dc4adbeee5ac5c1fee4/storyboard/contact-sheet-001.png)
shows all six narrated beats with concrete, source-supported commands and state:
one image branching to two named containers, a clear image/container contrast,
two complete `docker run` commands, a `docker ps` table with distinct rows and
the persistent-state boundary. Every accepted asset is distinct, marked as
TubeForge local CC0 art, tied to the scene plan, and SHA256-matched against its
file; the storyboard has no fallback or missing scene. The local preview is
43.016 seconds, H.264/AAC, 540×960 at 30 fps; its manifest names the approved
content checksum and all six accepted asset hashes. Sampled frames show
readable labels and caption-safe placement. No preview/final/publication
approval was granted. Full audiovisual quality and a finished 1080×1920 Short
are task 4, not evidence claimed for task 3.

The affected Compose regression batch finished within the operator's
20-minute cap: 58 passed, 3 environment-dependent local-smoke skips in
11m39s. Task 3 visual acquisition/contact-sheet acceptance is VERIFIED.
