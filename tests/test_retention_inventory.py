from __future__ import annotations

import sqlite3
from pathlib import Path

from tubeforge.pipeline.retention_inventory import cgroup_memory, inventory


def test_legacy_inventory_protects_all_files_and_ignores_paths_outside_data(tmp_path: Path) -> None:
    data = tmp_path / "data"
    artifact = data / "artifacts" / "job-one" / "final.mp4"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"final media")
    orphan = data / "artifacts" / "unregistered.bin"
    orphan.write_bytes(b"orphan")
    cache = data / "cache" / "cached.bin"
    cache.parent.mkdir()
    cache.write_bytes(b"cache")
    backup = data / "backups" / "prior.db"
    backup.parent.mkdir()
    backup.write_bytes(b"backup")
    database = data / "tubeforge.db"
    with sqlite3.connect(database) as connection:
        connection.executescript("""
            CREATE TABLE artifacts (path TEXT);
            CREATE TABLE pipeline_jobs (state TEXT);
            CREATE TABLE approvals (id TEXT);
            CREATE TABLE alembic_version (version_num TEXT);
        """)
        connection.executemany("INSERT INTO artifacts VALUES (?)", [
            (str(artifact.resolve()),),
            (str(artifact.resolve()),),
            (str((data / "missing.mp4").resolve()),),
            (str(data / "../../outside.txt"),),
        ])
        connection.execute("INSERT INTO pipeline_jobs VALUES ('publication_approval_required')")
        connection.execute("INSERT INTO approvals VALUES ('approval-one')")
        connection.execute("INSERT INTO alembic_version VALUES ('test-head')")

    report = inventory(database, data)
    assert report["database_migration"] == "test-head"
    assert report["job_states"] == {"publication_approval_required": 1}
    assert report["approval_records"] == 1
    assert report["artifact_records"] == 4
    assert report["referenced_files"] == 1
    assert report["missing_artifact_records"] == 1
    assert report["outside_data_root_records"] == 1
    assert report["artifact_files"] == 2
    assert report["referenced_artifact_bytes"] == len(b"final media")
    assert report["unregistered_or_other_artifact_bytes"] == len(b"orphan")
    assert report["cache_bytes"] == len(b"cache") and report["backup_bytes"] == len(b"backup")
    assert report["cleanup_candidates"] == 0
    assert artifact.is_file() and orphan.is_file() and backup.is_file()

    # Legacy records from a prior runtime can still be mapped explicitly.
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE artifacts SET path = replace(path, ?, ?)",
            (str(data.resolve()), "/app/data"),
        )
    legacy_report = inventory(database, data, stored_data_root=Path("/app/data"))
    assert legacy_report["referenced_files"] == 1
    assert legacy_report["missing_artifact_records"] == 1


def test_cgroup_memory_labels_lifetime_peak_and_sampled_working_set(tmp_path: Path) -> None:
    assert cgroup_memory(tmp_path)["scope"] == "unavailable"
    (tmp_path / "memory.peak").write_text("900\n")
    (tmp_path / "memory.current").write_text("500\n")
    (tmp_path / "memory.max").write_text("1000\n")
    (tmp_path / "memory.stat").write_text("anon 200\ninactive_file 150\n")
    assert cgroup_memory(tmp_path) == {
        "scope": "container_lifetime",
        "peak_bytes": 900,
        "current_bytes": 500,
        "limit_bytes": 1000,
        "sampled_working_set_bytes": 350,
    }
