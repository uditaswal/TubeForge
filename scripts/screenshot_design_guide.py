"""Screenshot design/guide.html at phone, tablet and desktop widths so an agent can look at it.

Usage:
    .venv-benchmark/bin/python scripts/screenshot_design_guide.py            # whole page, 3 widths
    .venv-benchmark/bin/python scripts/screenshot_design_guide.py button     # one component (its section id)

Prints the PNG paths. Open each one (Read tool) and check it against the checklist in design/DESIGN.md.
Needs network access for the Tailwind CDN and Google Fonts. Output: artifacts/design-guide/ (git-ignored).
"""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "design" / "guide.html"
OUT = ROOT / "artifacts" / "design-guide"
WIDTHS = {"phone": (390, 844), "tablet": (768, 1024), "desktop": (1440, 900)}


def main(argv: list[str]) -> int:
    section = argv[1] if len(argv) > 1 else None
    OUT.mkdir(parents=True, exist_ok=True)
    problems: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name, (width, height) in WIDTHS.items():
            page = browser.new_page(viewport={"width": width, "height": height})
            page.on("console", lambda m: problems.append(f"{name}: console {m.type}: {m.text}") if m.type == "error" else None)
            page.on("pageerror", lambda e: problems.append(f"{name}: page error: {e}"))
            page.goto(GUIDE.as_uri())
            page.wait_for_load_state("load")
            page.evaluate("document.fonts.ready")
            overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
            if overflow > 0:
                problems.append(f"{name}: page scrolls sideways by {overflow}px")
            target = OUT / f"{section or 'guide'}-{name}.png"
            if section:
                locator = page.locator(f"section#{section}")
                if locator.count() == 0:
                    print(f"No section with id '{section}' in design/guide.html", file=sys.stderr)
                    return 2
                locator.screenshot(path=str(target))
            else:
                page.screenshot(path=str(target), full_page=True)
            print(target.relative_to(ROOT))
            page.close()
        browser.close()
    for problem in problems:
        print("PROBLEM:", problem)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
