"""Read-only inventory for retention planning and cgroup memory baselines.

Existing files predate the managed-retention contract. They remain protected;
this module never removes or changes them and never proposes their deletion.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path


RETENTION_DAYS = {
    "failed_partial_render": 7,
    "inactive_intermediate_media": 14,
    "detailed_diagnostics": 30,
    "inactive_source_snapshot": 180,
}
ADMISSION_BUDGET_BYTES = 50 * 1024**3


def _tree_size(root: Path) -> tuple[int, int]:
    count = size = 0
    if not root.is_dir():
        return count, size
    for directory, _, filenames in os.walk(root, followlinks=False):
        for name in filenames:
            path = Path(directory) / name
            if path.is_symlink():
                continue
            try:
                size += path.stat().st_size
                count += 1
            except OSError:
                continue
    return count, size


def inventory(database: Path, data_root: Path, *, stored_data_root: Path | None = None) -> dict[str, object]:
    """Summarize legacy artifacts without reading payloads or modifying state."""
    database, data_root = database.resolve(strict=True), data_root.resolve(strict=True)
    if not database.is_file() or not data_root.is_dir():
        raise ValueError("database must be a file and data root must be a directory")
    connection = sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True)
    try:
        records = connection.execute("SELECT path FROM artifacts").fetchall()
        jobs = dict(connection.execute("SELECT state, COUNT(*) FROM pipeline_jobs GROUP BY state"))
        approvals = connection.execute("SELECT COUNT(*) FROM approvals").fetchone()[0]
        migration = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    finally:
        connection.close()

    referenced: set[Path] = set()
    outside_root = missing = 0
    # Native installs store paths under the selected data root. Older records
    # may come from another runtime; callers can pass that recorded prefix.
    source_prefix = str((stored_data_root or data_root).resolve()).rstrip("/") + "/"
    for (stored_path,) in records:
        if not stored_path.startswith(source_prefix):
            outside_root += 1
            continue
        relative = Path(stored_path.removeprefix(source_prefix))
        path = (data_root / relative).resolve()
        if not path.is_relative_to(data_root):
            outside_root += 1
        elif path.is_file():
            referenced.add(path)
        else:
            missing += 1

    artifact_root = data_root / "artifacts"
    total_count, total_bytes = _tree_size(artifact_root)
    referenced_bytes = sum(path.stat().st_size for path in referenced if path.is_relative_to(artifact_root))
    cache_count, cache_bytes = _tree_size(data_root / "cache")
    backup_count, backup_bytes = _tree_size(data_root / "backups")
    return {
        "schema_version": "1.0",
        "scope": "legacy_inventory_only",
        "database_migration": migration,
        "job_states": jobs,
        "approval_records": approvals,
        "artifact_records": len(records),
        "referenced_files": len(referenced),
        "missing_artifact_records": missing,
        "outside_data_root_records": outside_root,
        "artifact_files": total_count,
        "artifact_bytes": total_bytes,
        "referenced_artifact_bytes": referenced_bytes,
        "unregistered_or_other_artifact_bytes": max(0, total_bytes - referenced_bytes),
        "cache_files": cache_count,
        "cache_bytes": cache_bytes,
        "backup_files": backup_count,
        "backup_bytes": backup_bytes,
        "retention_days_for_future_managed_artifacts": RETENTION_DAYS,
        "admission_budget_bytes": ADMISSION_BUDGET_BYTES,
        "cleanup_candidates": 0,
        "cleanup_reason": "legacy files and existing approvals are protected until a managed-retention marker and ownership checks exist",
    }


def cgroup_memory(cgroup_root: Path = Path("/sys/fs/cgroup")) -> dict[str, int | str | None]:
    """Read kernel counters; a container-lifetime peak is never a job peak."""
    peak_file = cgroup_root / "memory.peak"
    current_file = cgroup_root / "memory.current"
    limit_file = cgroup_root / "memory.max"
    if not all(path.is_file() for path in (peak_file, current_file, limit_file)):
        return {"scope": "unavailable", "peak_bytes": None, "current_bytes": None, "limit_bytes": None, "sampled_working_set_bytes": None}
    peak, current = int(peak_file.read_text()), int(current_file.read_text())
    limit_text = limit_file.read_text().strip()
    inactive = 0
    stat_file = cgroup_root / "memory.stat"
    if stat_file.is_file():
        for line in stat_file.read_text().splitlines():
            if line.startswith("inactive_file "):
                inactive = int(line.split()[1])
                break
    return {
        "scope": "container_lifetime",
        "peak_bytes": peak,
        "current_bytes": current,
        "limit_bytes": None if limit_text == "max" else int(limit_text),
        "sampled_working_set_bytes": max(0, current - inactive),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only TubeForge retention and memory inventory")
    parser.add_argument("--database", type=Path, default=Path("data/tubeforge.db"))
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--stored-data-root", type=Path, help="recorded data-root prefix in legacy artifact paths")
    parser.add_argument("--cgroup-root", type=Path, default=Path("/sys/fs/cgroup"))
    args = parser.parse_args()
    report = inventory(args.database, args.data_root, stored_data_root=args.stored_data_root)
    report["cgroup_memory"] = cgroup_memory(args.cgroup_root)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
