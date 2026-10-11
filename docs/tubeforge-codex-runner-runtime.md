# Root-owned Codex runtime

The host runner executes only this pinned runtime:

- Node: `/opt/tubeforge-codex-runner/codex-runtime/node/bin/node`
- Codex: `@openai/codex@0.149.0` at
  `/opt/tubeforge-codex-runner/codex-runtime/lib/node_modules/@openai/codex`
- Fixed script model: `gpt-5.6-sol`, confirmed in the dedicated account's
  refreshed Codex catalog; there is no automatic fallback.

Provision these paths from a host administrator shell, owned by `root:root`
and not writable by `tubeforge-codex`. Install Node into the `node/` directory,
then use that Node/npm pair to install the exact Codex package into the same
prefix. Download the Node distribution from its approved release source; do
not use an NVM installation or copy files from any user home.

```bash
sudo install -d -o root -g root -m 0755 /opt/tubeforge-codex-runner/codex-runtime/node
curl -fsSLO https://nodejs.org/dist/v24.19.0/node-v24.19.0-linux-x64.tar.xz
sudo tar -xJf node-v24.19.0-linux-x64.tar.xz \
  -C /opt/tubeforge-codex-runner/codex-runtime/node --strip-components=1
sudo env PATH=/opt/tubeforge-codex-runner/codex-runtime/node/bin \
  /opt/tubeforge-codex-runner/codex-runtime/node/bin/npm install --global \
  --prefix /opt/tubeforge-codex-runner/codex-runtime @openai/codex@0.149.0
sudo chown -R root:root /opt/tubeforge-codex-runner/codex-runtime
sudo chmod -R go-w /opt/tubeforge-codex-runner/codex-runtime
sudo -u tubeforge-codex test ! -w /opt/tubeforge-codex-runner/codex-runtime
/opt/tubeforge-codex-runner/codex-runtime/node/bin/node --version
/opt/tubeforge-codex-runner/codex-runtime/node/bin/node \
  /opt/tubeforge-codex-runner/codex-runtime/lib/node_modules/@openai/codex/bin/codex.js --version
```

Authentication is a separate, interactive operation performed as
`tubeforge-codex` with `CODEX_HOME=/var/lib/tubeforge-codex/.codex`. Do not
copy, mount, or reference another user's Codex home. Do not run this login
until both version commands above succeed.

## Service deployment

The service also needs a root-owned Python environment containing the reviewed
TubeForge package and dependencies. It must be installed outside a user home,
because `ProtectHome=yes` intentionally hides all homes from the service.
From the reviewed TubeForge checkout, install the package and unit files, then
inspect the unit before starting it:

```bash
sudo python3 -m venv /opt/tubeforge-codex-runner/venv
sudo /opt/tubeforge-codex-runner/venv/bin/pip install .
sudo chown -R root:root /opt/tubeforge-codex-runner/venv
sudo chmod -R go-w /opt/tubeforge-codex-runner/venv
sudo install -o root -g root -m 0644 docs/tubeforge-codex-runner.tmpfiles.conf /etc/tmpfiles.d/tubeforge-codex-runner.conf
sudo systemd-tmpfiles --create /etc/tmpfiles.d/tubeforge-codex-runner.conf
sudo install -o root -g root -m 0644 docs/tubeforge-codex-runner.service /etc/systemd/system/
sudo install -o root -g root -m 0644 docs/tubeforge-codex-runner.socket /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl reset-failed tubeforge-codex-runner.socket tubeforge-codex-runner.service
sudo systemctl enable --now tubeforge-codex-runner.socket
sudo systemctl cat tubeforge-codex-runner.service tubeforge-codex-runner.socket
```

`pip install .` must use the reviewed checkout, not a user-owned editable
install. The installed service has a fixed `/opt/.../venv` interpreter and
imports its code from that root-owned venv. The tmpfiles rule preserves the
socket directory as `0750 root:1000` across boots. Bubblewrap receives the
root-owned `codex-runtime` tree, the request workspace, and the dedicated
account's private Codex home.
The namespace additionally exposes only Node's required shared libraries, DNS
resolver configuration, and the host CA certificates. It does not mount the
host's general `/usr` or `/bin` trees. After changing runner source, reinstall
the wheel with `sudo /opt/tubeforge-codex-runner/venv/bin/pip install
--force-reinstall --no-deps .` and restart the service; restarting the socket
alone leaves an already-running service on the previous code.
The host itself stores a per-request SQLite invocation count under its private
`/var/lib/tubeforge-codex` directory and rejects a third request before
launching Codex. This is independent of the worker's durable attempt counter.
The fixed `codex exec` invocation ignores user config and rules and allows the
temporary non-Git workspace; these flags are supported by the pinned CLI.
On CLI failure, the socket response prefers bounded Codex JSONL error events
and omits generated text and the source packet. Do not retry a failed request
until its error is diagnosed: the host consumes an attempt before launching the
CLI, including launches that fail before producing a script.

After a successful CLI response, the runner may shorten only a
`scene_plans[*].fallback_visual` value exceeding the domain's 100-character
limit. It cuts at the last complete-word boundary within that limit and records
the field path and before/after lengths in response provenance. It does not
change narration, claims, source request, or any other field, and it does not
invoke Codex again. If no safe boundary exists, ordinary domain validation
still rejects the package. This is a format repair, not creative-quality
acceptance; the resulting script still needs source and editorial review.


## Content skill resources

Generation and repair prompts explicitly embed the selected yt-script, yt-package and yt-seo resources
from the root-owned wheel's `tubeforge/content_skills/`. Python executes the
reviewed scorer/checker outside Bubblewrap; the Codex namespace still exposes
only the fixed Node runtime, workspace and dedicated Codex home. No worker-
supplied path, command or arbitrary prompt is accepted. `PreflightContentV1`
validates prompt assembly, tool availability and fixed runtime paths without
calling Codex or charging either attempt ledger. A worker compares the seven
resource hashes before its generation reservation. Redeploy the wheel to both
source/runtime boundaries whenever these resources change. See README for
voice profiles and the reviewed wheel installation command.

The canonical updated script skill is `.agents/skills/yt-script/`; include its
referenced `automation.md` in the wheel. v6 uses a strict ContentGenerationResult
envelope to return insufficient-source failures without a ContentPackage.
Successful invocation provenance records a SHA256 of the actual stdin prompt
and its resource hashes. The production model and fallback policy are unchanged.
After deployment, verify `PreflightContentV1` matches the canonical resource
hashes before spending an invocation. Historical v5 packages remain reviewable;
resource changes require a new reviewed brief, never an exhausted-ledger reset.
