# Security

TubeForge is a self-hosted, single-operator application. Report a vulnerability privately to the
repository owner (GitHub private vulnerability report); do not open a public issue.

## Secrets
- Secrets live only in the untracked `.env` (template: `.env.example`) or the encrypted account store
  (`TUBEFORGE_ACCOUNT_ENCRYPTION_KEY`). OAuth client files, tokens, keys and databases are gitignored.
- The dashboard binds to loopback (`127.0.0.1:62065`); remote access goes through an SSH tunnel.
- If a secret is ever committed: rotate it first, then purge it from history (`git filter-repo`).

## Automated checks
| Check | Where | Command |
|---|---|---|
| Secret scan (gitleaks, `.gitleaks.toml`) | pre-commit + CI (full history) | `gitleaks git --log-opts="--all" --redact` |
| Large/generated/env files, private keys, merge markers, YAML/TOML/JSON syntax | pre-commit + CI | `pre-commit run --all-files` |
| Tracked files that `.gitignore` excludes | CI | `git ls-files -ci --exclude-standard` |
| Dependency vulnerabilities (pip-audit) | CI | `pip-audit --skip-editable` |
| Dependency updates | Dependabot (pip, GitHub Actions, Docker) | `.github/dependabot.yml` |

## Local setup (once per clone)
```bash
# gitleaks: https://github.com/gitleaks/gitleaks/releases (verify the checksum), install to ~/.local/bin
.venv-benchmark/bin/python -m pip install pre-commit pip-audit
.venv-benchmark/bin/pre-commit install
```
Never bypass the hooks with `--no-verify`. Commit messages carry no AI-attribution trailers.
