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
                scenes[str(index)] = _stock(visual, index, out, pixabay, used)
            elif isinstance(visual, SourceVisual):
                scenes[str(index)] = _source(visual, index, scene.source_ids[0], sources, out, capture)
        except (ProviderValidationError, RetryableProviderError, ProviderAuthenticationError, OSError) as error:
            LOG.warning("scene %s plate unavailable: %s", index, error)
            scenes[str(index)] = {"kind": "none", "reason": f"{type(error).__name__}: {error}"[:300]}
    manifest = {"schema_version": "plates-v1", "prepared_at": datetime.now(UTC).isoformat(), "scenes": scenes}
    (directory / MANIFEST).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def _stock(visual: StockVisual, index: int, out: Path, pixabay: PixabayClient | None, used: set[str]) -> dict:
    if pixabay is None or not pixabay.available:
        return {"kind": "none", "reason": "pixabay disabled or no API key"}
    wanted = [visual.media, "photo" if visual.media == "video" else "video"]
    for media in wanted:
        assets = pixabay.search_videos(visual.query) if media == "video" else pixabay.search_images(visual.query)
        asset = pixabay.best(assets, min_duration=ESTIMATED_SCENE_SECONDS, exclude=used, query=visual.query)
        if asset is None:
            continue
        source = pixabay.download(asset)
        target = out / f"stock-{index}{source.suffix}"
        shutil.copyfile(source, target)
        used.add(asset.asset_id)
        return {"kind": "stock", "media": media, "file": f"plates/{target.name}", "query": visual.query, "evidence": asset.evidence()}
    return {"kind": "none", "reason": f"no Pixabay result for {visual.query!r}"}


def _source(visual: SourceVisual, index: int, source_id: str, sources: dict[str, str], out: Path,
            capture: Callable[[str, str, Path], dict] | None) -> dict:
    if capture is None:
        return {"kind": "none", "reason": "screenshot capture unavailable"}
    url = sources[source_id]
    result = capture(url, visual.quote, out / f"source-{index}")
    if not result.get("file"):
        return {"kind": "none", "reason": result.get("reason", "quote not captured"), "url": url}
    return {"kind": "source", "url": url, "quote": visual.quote, "file": result["file"], "highlight": result.get("highlight"),
            "matched": result.get("matched", False), "evidence": {"url": url, "captured_at": datetime.now(UTC).isoformat(), "provider": "headless-chromium"}}
