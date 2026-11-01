#!/usr/bin/env python3
"""Print the heuristic script scorecard for one or more content_package.json files (offline, no model calls).

    PYTHONPATH=src python scripts/script_scorecard.py data/artifacts/<job_id>/content_package.json [...]
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

from tubeforge.providers.content.craft import fact_dump_problems, script_scorecard


def main(paths: list[str]) -> int:
    for path in paths:
        scenes = json.loads(Path(path).read_text())["reference_short"]["scenes"]
        package = SimpleNamespace(reference_short=SimpleNamespace(scenes=[SimpleNamespace(vo=s["vo"], template=s["template"], cues=s.get("cues", [])) for s in scenes]))
        print(path)
        for key, value in script_scorecard(package).items():
            print(f"  {key:28} {value}")
        for problem in fact_dump_problems(package):
            print("  - " + problem[:160])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]) if len(sys.argv) > 1 else print(__doc__) or 2)
