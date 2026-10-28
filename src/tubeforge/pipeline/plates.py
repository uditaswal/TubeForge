"""Prepare real-imagery plates (Pixabay B-roll, source screenshots) for a reference Short.

Runs once per job after the script is approved and before voice generation. Nothing here may fail
the job: each scene records ``kind: none`` with a reason and the renderer keeps the code-drawn template.
"""
from __future__ import annotations

import json
import logging
import shutil
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from tubeforge.core.errors import ProviderAuthenticationError, ProviderValidationError, RetryableProviderError
from tubeforge.providers.media.pixabay import PixabayClient
from tubeforge.providers.media.stock_rank import VERSION as STOCK_RANK_VERSION, rank_assets
from tubeforge.rendering.shorts.plates import MANIFEST
from tubeforge.rendering.shorts.schema import CodeVisual, ShortsTopic, SourceVisual, StockVisual

LOG = logging.getLogger(__name__)
ESTIMATED_SCENE_SECONDS = 4.0


def prepare_plates(topic: ShortsTopic, directory: Path, *, pixabay: PixabayClient | None,
                   capture: Callable[[str, str, Path], dict] | None, cancelled: Callable[[], bool] = lambda: False) -> dict:
    """Write ``plates/manifest.json`` and return it. ``capture(url, quote, out_dir)`` shoots a source page."""
    out = directory / "plates"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    sources = {source.source_id: str(source.url) for source in topic.sources}
    scenes: dict[str, dict] = {}
    used: set[str] = set()
    previous_tags: list[str] = []
    for index, scene in enumerate(topic.scenes):
        if cancelled():
            break
        visual = scene.visual
        if visual is None:
            continue
        try:
            if isinstance(visual, CodeVisual):
                scenes[str(index)] = {"kind": "code", "language": visual.language, "lines": len(visual.lines)}
            elif isinstance(visual, StockVisual):
                scenes[str(index)] = _stock(visual, scene.vo, index, out, pixabay, used, previous_tags)
            elif isinstance(visual, SourceVisual):
                scenes[str(index)] = _source(visual, index, scene.source_ids[0], sources, out, capture)
        except (ProviderValidationError, RetryableProviderError, ProviderAuthenticationError, OSError) as error:
            LOG.warning("scene %s plate unavailable: %s", index, error)
            scenes[str(index)] = {"kind": "none", "reason": f"{type(error).__name__}: {error}"[:300]}
    manifest = {"schema_version": "plates-v1", "prepared_at": datetime.now(UTC).isoformat(), "scenes": scenes}
    (directory / MANIFEST).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def _stock(visual: StockVisual, scene_text: str, index: int, out: Path,
           pixabay: PixabayClient | None, used: set[str], previous_tags: list[str]) -> dict:
    """Local library first (no network, topics repeat); Pixabay only for what the library cannot match."""
    if pixabay is None:
        return {"kind": "none", "reason": "pixabay disabled"}
    other = "photo" if visual.media == "video" else "video"
    for media, online in ((visual.media, False), (visual.media, True), (other, False), (other, True)):
        kind = "video" if media == "video" else "image"
        if online:
            if not pixabay.available:
                continue
            assets = pixabay.search_videos(visual.query) if media == "video" else pixabay.search_images(visual.query)
            local_sources = {}
            origin = "pixabay"
        else:
            found = pixabay.library.candidates(kind, min_duration=ESTIMATED_SCENE_SECONDS, exclude=used)
            assets = [asset for asset, _ in found]
            local_sources = {asset.asset_id: path for asset, path in found}
            origin = "local-library"
        ranked = rank_assets(assets, query=visual.query, scene_text=scene_text,
                             used_ids=used, previous_tags=tuple(previous_tags),
                             min_duration=ESTIMATED_SCENE_SECONDS)
        for choice in ranked[:3]:
            asset = choice["asset"]
            try:
                source = pixabay.download(asset) if online else local_sources[asset.asset_id]
                target = out / f"stock-{index}{source.suffix}"
                shutil.copyfile(source, target)
            except (ProviderValidationError, RetryableProviderError, ProviderAuthenticationError, OSError) as error:
                LOG.warning("stock candidate %s unavailable: %s", asset.asset_id, error)
                continue
            pixabay.library.add(asset, source, visual.query)
            used.add(asset.asset_id)
            previous_tags.append(asset.tags)
            return {"kind": "stock", "media": media, "file": f"plates/{target.name}",
                    "query": visual.query, "origin": origin, "evidence": asset.evidence(),
                    "ranking": {"version": STOCK_RANK_VERSION,
                                "selected": {key: value for key, value in choice.items() if key != "asset"},
                                "candidates": [{key: value for key, value in item.items() if key != "asset"}
                                               for item in ranked[:3]],
                                "scope": "tag-and-metadata relevance; requires visual inspection"}}
    return {"kind": "none", "reason": f"no stock match for {visual.query!r}" + ("" if pixabay.available else " (no API key; local library only)")}


def _source(visual: SourceVisual, index: int, source_id: str, sources: dict[str, str], out: Path,
            capture: Callable[[str, str, Path], dict] | None) -> dict:
    if capture is None:
        return {"kind": "none", "reason": "screenshot capture unavailable"}
    url = sources[source_id]
    result = capture(url, visual.quote, out / f"source-{index}")
    if not result.get("file"):
        return {"kind": "none", "reason": result.get("reason", "quote not captured"), "url": url}
    return {"kind": "source", "url": url, "quote": visual.quote, "file": result["file"], "highlight": result.get("highlight"),
            **{key: result[key] for key in ("file_2x", "highlight_2x") if result.get(key)},
            "matched": result.get("matched", False), "evidence": {"url": url, "captured_at": datetime.now(UTC).isoformat(), "provider": "headless-chromium"}}
