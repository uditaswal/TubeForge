#!/usr/bin/env python3
"""Print the heuristic script scorecard for one or more content_package.json files (offline, no model calls).

    PYTHONPATH=src python scripts/script_scorecard.py data/artifacts/<job_id>/content_package.json [...]

Lines starting with "-" are fact-dump advisories, lines starting with "~" are naturalness advisories; none of them block a script.
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

from tubeforge.providers.content.craft import fact_dump_problems, script_scorecard


def _namespace(value):
    """Scene dicts become attribute objects (nested dicts too), so the on-screen text checks see the same fields as the app."""
    if isinstance(value, dict):
        return SimpleNamespace(**{key: _namespace(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_namespace(item) for item in value)
    return value


def main(paths: list[str]) -> int:
    for path in paths:
        data = json.loads(Path(path).read_text())
        # Accept a bare package, or the script API's wrapper ({"package": {...}}).
        scenes = (data.get("package") or data)["reference_short"]["scenes"]
        package = SimpleNamespace(reference_short=SimpleNamespace(scenes=[_namespace({"cues": [], **scene}) for scene in scenes]))
        print(path)
        card = script_scorecard(package)
        notes = card.pop("naturalness_notes", [])
        for key, value in card.items():
            print(f"  {key:28} {value}")
        for problem in fact_dump_problems(package):
            print("  - " + problem[:160])
        for note in notes:
            print("  ~ " + note[:220])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]) if len(sys.argv) > 1 else print(__doc__) or 2)
