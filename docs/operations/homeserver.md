# TubeForge homeserver operator guide

This is the routine startup and access procedure for TubeForge when the
application runs on the Debian homeserver and the browser runs on a Windows
computer. TubeForge remains bound to the homeserver loopback interface; the
SSH tunnel provides private access without exposing the dashboard to the LAN.

## What must be running

For opening the dashboard and processing local video jobs, the required
services are:

- Docker Engine on the homeserver.
- The Compose services `web`, `worker`, `scheduler`, and `piper-tts`. The
  one-shot `migrate` service runs automatically before `web` and `worker`.
- The Codex host runner socket when a new job uses Codex as its script writer.

The publisher worker is deliberately excluded from routine startup. It is only
needed after an explicit publishing decision. Ollama is not required by the
production script or render pipeline.

## Routine startup after a homeserver reboot

In the first Windows PowerShell window, log in normally:

```powershell
ssh homeserver
```

Then, on the homeserver:

```bash
cd ~/docker/tubeforge/Youtube_Video_Producer
sudo systemctl start docker
docker compose up -d web worker scheduler
docker compose ps
curl -fsS http://127.0.0.1:62065/healthz
```

The health response must be:

```json
{"status":"ok","database":"ok"}
```

`docker compose up` also starts `piper-tts` and runs the database migration
because they are declared dependencies. If all services already show `Up`, the
command is safe and normally makes no changes.

After pulling code or changing Python dependencies, rebuild the application
images once:

```bash
docker compose up -d --build web worker scheduler
```

Do not use `docker compose down` as a routine startup or restart step. It is
unnecessary and creates avoidable downtime.

## Check the Codex script runner

Opening the dashboard and reviewing existing artifacts does not require the
Codex runner. Creating a job with **Codex** selected as script writer does.

Check its socket on the homeserver:

```bash
sudo systemctl is-active tubeforge-codex-runner.socket
```

If the result is not `active`, start it and enable it for future boots:

```bash
sudo systemctl enable --now tubeforge-codex-runner.socket
```

The service is socket-activated. For diagnosis, inspect both units:

```bash
sudo systemctl status tubeforge-codex-runner.socket tubeforge-codex-runner.service --no-pager
```

If a job uses Claude instead, its optional user service is separate:

```bash
systemctl --user enable --now tubeforge-claude-runner
systemctl --user status tubeforge-claude-runner --no-pager
```

Only the runner selected for the job needs to be available.

## Open the dashboard from Windows

Keep the first shell available for diagnostics. Open a second Windows
PowerShell window and create the tunnel using the existing SSH alias:

```powershell
ssh -N -L 62065:127.0.0.1:62065 homeserver
```

Leave this window open. A blank terminal after connection is expected. Open:

<http://127.0.0.1:62065>

Sign in with the existing TubeForge dashboard account. This account is
separate from the SSH account and the Codex account.

## Fast status check

Run these commands on the homeserver when the page does not open or a job does
not progress:

```bash
cd ~/docker/tubeforge/Youtube_Video_Producer
docker compose ps
curl -fsS http://127.0.0.1:62065/healthz
sudo systemctl is-active tubeforge-codex-runner.socket
docker compose logs --tail 100 web worker piper-tts scheduler
```

Interpret the results in this order:

1. If `ssh homeserver` fails, fix the SSH connection before testing TubeForge.
2. If Docker is inactive, run `sudo systemctl start docker`.
3. If `web`, `worker`, or `piper-tts` is missing or unhealthy, run
   `docker compose up -d web worker scheduler`, then check the logs again.
4. If `/healthz` fails on the homeserver, the SSH tunnel cannot work; diagnose
   `web` and `migrate` first.
5. If `/healthz` works on the homeserver but Windows cannot open the page,
   close the tunnel window and recreate the tunnel. Check that another Windows
   process is not already using port 62065 with
   `Get-NetTCPConnection -LocalPort 62065`.
6. If the dashboard opens but a Codex job fails before script generation,
   inspect the Codex runner units and the job Activity panel.

To restart application processes without rebuilding images:

```bash
docker compose restart web worker scheduler piper-tts
curl -fsS http://127.0.0.1:62065/healthz
```

## First-time setup only

If no dashboard administrator exists, create one interactively on the
homeserver:

```bash
cd ~/docker/tubeforge/Youtube_Video_Producer
docker compose exec web tubeforge create-admin --username operator
```

Use a password of at least 12 characters. Do not put the password on the
command line or in project documentation.

