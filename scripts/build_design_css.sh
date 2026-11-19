#!/usr/bin/env bash
# Build the dashboard stylesheet from the Tailwind input and the design tokens.
# Output is committed: src/tubeforge/assets/ui/tubeforge.css. Run after changing any class, token or component rule.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
(cd design && npm ci --no-audit --no-fund --loglevel=error)
design/node_modules/.bin/tailwindcss \
  -c src/tubeforge/assets/ui/tailwind.config.js \
  -i src/tubeforge/assets/ui/tailwind.input.css \
  -o src/tubeforge/assets/ui/tubeforge.css --minify
echo "built src/tubeforge/assets/ui/tubeforge.css"
