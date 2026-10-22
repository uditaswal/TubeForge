# OpenMontage static security review

Reviewed 2026-10-14. Local repository: `/home/uditaswal/docker/tubeforge/git-repos/OpenMontage`. Main ref: `e45f5b12bd46440b04f3675af9a77d0718e6a254`.
Snapshot: 2172 working-tree files, 89,150,519 bytes excluding .git. The per-file SHA-256 manifest was removed on 2026-10-21 (recoverable from git history); regenerate it from the upstream checkout if needed. Working-tree hashes, rather than the branch ref alone, identify reviewed content.

## Decision

No clear evidence of malware was identified in this static review. Repository retained: the conditional instruction to delete on malicious findings was not triggered. This is not a clean bill of health or proof that execution is safe. Ordinary destructive utilities and code-execution features below have real risk but do not establish malicious intent.

## Method and scope

Inventoried all non-Git files and scanned decodable text for process execution, dynamic execution/deserialization, encoded payloads, deletion, credential locations, persistence, remote installation, network destinations and suspicious instruction language. Inspected selected matches in context, including installation/dependency manifests, CI, subprocess wrapper, cleanup script, renderer safety gate, dashboard and publisher. Checked local Git config/hooks, symlinks and common native executable magic. No active Git hooks, symlinks or common ELF/PE/Mach-O executables were found in the scanned working tree. Config showed an ordinary GitHub origin with no configured command execution.

No repository program, test suite, installer, agent instruction or skill instruction was executed or adopted. Reads of skills were solely source review for this requested consolidation. No dependencies were installed, credentials used, network APIs called or content published. Keyword scanning and selected manual review are not an exhaustive semantic audit of every line. Dependencies, remote installer contents, downloaded models, binary media/fonts and runtime behavior were not independently audited. No vulnerability-database or antivirus scan was performed.

## Findings requiring care before execution

- Remote code installation: `.agents/skills/media-use/SKILL.md:119` recommends piping a remote HeyGen installer into bash. Not executed or copied. Remote payload remains unreviewed.
- Destructive utility: `scripts/wan_disk_cleanup.sh:24-25,104` honors environment-selected cache paths and recursively deletes selected paths with explicit target flags and --yes. Shared uv caches and Wan weights may belong to other workflows; a bad UV_CACHE_DIR can direct deletion outside the project. This is an opt-in cleanup utility, not evidence of a malicious payload. Not copied.
- Host code execution: `tools/graphics/math_animate.py:166-170,230-290` accepts caller-supplied Python for Manim; it has a denylist scan and an allow_unsafe_code bypass. A static denylist is not isolation. Other rendering stacks process generated Python/JavaScript and media. No renderer code was copied or run.
- Package installation: `.agents/skills/beautiful-mermaid/scripts/render.ts:149-157` installs packages through execSync; `render_demo.py:63` runs npm install. Python requirements have lower bounds and JavaScript manifests have version ranges; transitive supply-chain safety is not established. No install hooks were present in inspected top-level package scripts/setup.py.
- External data/cost boundary: tools contain explicit AI/media provider integrations and configurable endpoints. Legitimate use sends prompts/media to providers and can spend money. No clear credential-stealing destination or miner/persistence payload was identified by the scan; this does not verify every possible destination or redirect. Do not pass secrets to unreviewed endpoints.
- Local dashboard: Backlot serves project data/media and lacks an authentication layer in the inspected server. Retain loopback-only operation; it is not imported into TubeForge.

## Capability finding

`tools/publishers/export_bundle.py` explicitly declares `uploads: False` and produces a local bundle with status exported. It is the only publisher implementation besides __init__.py. Publish-director documents describe packaging, not a working social uploader. Neither uploading nor autonomous channel management is supplied by this import.

## Consolidation choices

Created original, concise documentation derived from reviewed concepts, with source paths and hashes preserved. No upstream scripts, runtime dependencies, media, agent bootstrap instructions, provider rankings, fixed platform limits, invented analytics, license assurances or mandatory upstream approval rituals were imported. No license grant for the overall repository was established from a root license file; upstream files were not wholesale redistributed. Existing TubeForge skills are preserved, especially canonical yt-script. This import does not integrate application resources into wheels or deployments.
