"""Local, indexed library of the stock files already downloaded, so repeated tech topics need no network.

The index (``library.sqlite`` next to the cached files) is rebuilt from the per-file evidence sidecars when
files are missing from it, so the files themselves stay the source of truth. Lookup is purely local: it
scores stored Pixabay tags against the words of a scene's search query.
"""
from __future__ import annotations

import json
import re
import sqlite3
import time
from dataclasses import fields
from pathlib import Path

from tubeforge.providers.media.pixabay import StockAsset

STOP = frozenset({"the", "and", "for", "with", "from", "into", "over", "this", "that", "shot", "view", "stock"})
MIN_MATCH = 0.5
EXTENSIONS = {"video": (".mp4", ".webm"), "image": (".jpg", ".jpeg", ".png")}


def words(text: str) -> frozenset[str]:
    """Lower-cased words with a plural ``s`` dropped, so 'servers' meets 'server'."""
    found = (w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w for w in re.findall(r"[a-z0-9]+", text.casefold()))
    return frozenset(w for w in found if len(w) > 2 and w not in STOP)


class StockLibrary:
    def __init__(self, root: Path) -> None:
        self.files = root / "files"
        self.files.mkdir(parents=True, exist_ok=True)
        self.path = root / "library.sqlite"
        with self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS assets(asset_id TEXT, kind TEXT, file TEXT NOT NULL, tags TEXT, evidence TEXT NOT NULL,
                    uses INTEGER DEFAULT 0, last_used REAL, PRIMARY KEY(kind, asset_id));
                CREATE TABLE IF NOT EXISTS queries(query TEXT, kind TEXT, asset_id TEXT, PRIMARY KEY(query, kind, asset_id));""")
        self.reindex()

    def _db(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        return db

    def reindex(self) -> int:
        """Add any downloaded file whose sidecar is not indexed yet; drop rows whose file is gone."""
        added = 0
        with self._db() as db:
            known = {(r["kind"], r["asset_id"]): r["file"] for r in db.execute("SELECT kind, asset_id, file FROM assets")}
            for key, name in known.items():
                if not (self.files / name).is_file():
                    db.execute("DELETE FROM assets WHERE kind=? AND asset_id=?", key)
            for sidecar in self.files.glob("*.json"):
                try:
                    evidence = json.loads(sidecar.read_text())
                    kind, asset_id = evidence["kind"], str(evidence["asset_id"])
                except (OSError, ValueError, KeyError):
                    continue
                media = next((p for p in (sidecar.with_suffix(e) for e in EXTENSIONS.get(kind, ())) if p.is_file()), None)
                if media is not None and (kind, asset_id) not in known:
                    db.execute("INSERT OR REPLACE INTO assets(asset_id, kind, file, tags, evidence) VALUES(?,?,?,?,?)",
                               (asset_id, kind, media.name, evidence.get("tags", ""), json.dumps(evidence)))
                    added += 1
        return added

    def add(self, asset: StockAsset, file: Path, query: str = "") -> None:
        with self._db() as db:
            db.execute("INSERT OR REPLACE INTO assets(asset_id, kind, file, tags, evidence, uses, last_used) VALUES(?,?,?,?,?,"
                       "COALESCE((SELECT uses FROM assets WHERE kind=? AND asset_id=?), 0), ?)",
                       (asset.asset_id, asset.kind, file.name, asset.tags, json.dumps(asset.evidence()), asset.kind, asset.asset_id, time.time()))
            if query.strip():
                db.execute("INSERT OR IGNORE INTO queries VALUES(?,?,?)", (" ".join(sorted(words(query))), asset.kind, asset.asset_id))

    def find(self, query: str, kind: str, *, min_duration: float = 0.0, exclude: frozenset[str] | set[str] = frozenset()) -> tuple[StockAsset, Path] | None:
        """Best stored asset for ``query``: an exact earlier query match, else at least half the query words in its tags."""
        wanted = words(query)
        if not wanted:
            return None
        normal = " ".join(sorted(wanted))
        best: tuple[float, sqlite3.Row] | None = None
        with self._db() as db:
            linked = {r["asset_id"] for r in db.execute("SELECT asset_id FROM queries WHERE query=? AND kind=?", (normal, kind))}
            for row in db.execute("SELECT * FROM assets WHERE kind=?", (kind,)):
                if row["asset_id"] in exclude or not (self.files / row["file"]).is_file():
                    continue
                evidence = json.loads(row["evidence"])
                if kind == "video" and float(evidence.get("duration") or 0) < min_duration:
                    continue
                overlap = len(wanted & words(row["tags"] or "")) / len(wanted)
                score = 1.5 if row["asset_id"] in linked else overlap
                if score >= MIN_MATCH and (best is None or (score, -row["uses"]) > (best[0], -best[1]["uses"])):
                    best = (score, row)
        if best is None:
            return None
        row = best[1]
        with self._db() as db:
            db.execute("UPDATE assets SET uses=uses+1, last_used=? WHERE kind=? AND asset_id=?", (time.time(), kind, row["asset_id"]))
        allowed = {f.name for f in fields(StockAsset)}
        asset = StockAsset(**{k: v for k, v in json.loads(row["evidence"]).items() if k in allowed})
        return asset, self.files / row["file"]
