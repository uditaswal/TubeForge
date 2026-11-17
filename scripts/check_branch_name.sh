#!/usr/bin/env bash
# Rejects commits and pushes from branches named after an AI tool.
# Allowed: main, dev, and <type>/<topic> with type in feat|feature|fix|chore|docs|exp|backup|release.
# Rename an existing branch with:  git branch -m <old> feat/<topic>
set -euo pipefail

branch="$(git symbolic-ref --quiet --short HEAD 2>/dev/null || true)"
# Detached HEAD (rebase, bisect, CI checkout): nothing to check.
[ -z "$branch" ] && exit 0

case "$branch" in
  main|dev) exit 0 ;;
esac

if [[ "$branch" =~ ^(claude|codex|cursor|copilot|gpt|ai|agent)([/_-]|$) ]]; then
  echo "Branch '$branch' is named after an AI tool. Use feat/, fix/, chore/, docs/ or exp/." >&2
  echo "Rename it:  git branch -m '$branch' 'feat/${branch#*/}'" >&2
  exit 1
fi

if [[ ! "$branch" =~ ^(feat|feature|fix|chore|docs|exp|backup|release)/[a-z0-9][a-z0-9._-]*$ ]]; then
  echo "Branch '$branch' does not match <type>/<topic> (type: feat|feature|fix|chore|docs|exp|backup|release; topic: lowercase, digits, . _ -)." >&2
  exit 1
fi
