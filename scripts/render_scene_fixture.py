"""Render a fixed approved scene contract for local visual inspection."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

from tubeforge.core.config import FakeProviderConfig
from tubeforge.pipeline.scene_contracts import ScriptBoundSceneContract, scene_media_request
from tubeforge.pipeline.storyboard import render_contact_sheets
from tubeforge.providers.media.local_graphics import LocalMotionGraphicsProvider


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--database", required=True, type=Path, help="local TubeForge SQLite database")
    parser.add_argument("--job-id", required=True, help="job whose exact script and source artifacts were approved")
    args = parser.parse_args()
    fixture: Path = args.fixture
    output: Path = args.output
    contract = ScriptBoundSceneContract.model_validate_json((fixture / "scene_contract.json").read_bytes())
    with sqlite3.connect(f"file:{args.database.resolve()}?mode=ro", uri=True) as database:
        approval = database.execute(
            "SELECT status, reviewed_identity FROM approvals WHERE job_id=? AND gate='script' "
            "AND decision_identity=? LIMIT 1",
            (args.job_id, contract.package_sha256),
        ).fetchone()
        recorded: dict[str, str] = {}
        for name, checksum in database.execute(
            "SELECT name, checksum_sha256 FROM artifacts WHERE job_id=? "
            "AND name IN ('content_package','source_packet') ORDER BY id DESC",
            (args.job_id,),
        ):
            recorded.setdefault(name, checksum)
    if recorded != {"content_package": contract.package_sha256, "source_packet": contract.source_packet_sha256}:
        raise ValueError("fixture bytes do not match the job's recorded script and source artifacts")
    contract.validate_against(
        (fixture / "content_package.json").read_bytes(),
        (fixture / "source_packet.json").read_bytes(),
        accepted_script_identity=approval[1] if approval and approval[0] == "approved" else None,
    )
    provider = LocalMotionGraphicsProvider(FakeProviderConfig(artifact_root=output))
    rows: list[dict[str, str]] = []
    for row in contract.scenes:
        candidate = provider.search(scene_media_request(row))[0]
        path = Path(str(candidate.local_path))
        rows.append({
            "scene_id": row.scene_id,
            "layout": row.layout.value,
            "asset_path": str(path),
            "asset_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        })
    manifest = {
        "schema_version": "1.0",
        "scene_contract_sha256": hashlib.sha256((fixture / "scene_contract.json").read_bytes()).hexdigest(),
        "package_sha256": contract.package_sha256,
        "source_packet_sha256": contract.source_packet_sha256,
        "aspect_ratio": "9:16",
        "scenes": rows,
    }
    pages = render_contact_sheets(manifest, output / "sheets")
    (output / "storyboard.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"scene_count": len(rows), "contact_sheets": [str(page) for page in pages]}))


if __name__ == "__main__":
    main()
