"""Durable visual review sheets for the exact accepted scene assets."""

from __future__ import annotations

import math
import hashlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from tubeforge.core.errors import ProviderValidationError
from tubeforge.domain.contracts import ContentPackage, VideoPlan


def storyboard_manifest(package: ContentPackage, plan: VideoPlan, accepted: dict[str, object], *, scene_contract_sha256: str | None = None) -> dict[str, object]:
    """Keep narration-to-visual intent, provenance, and asset bytes together."""
    planned = {scene.scene_id: scene for scene in plan.scenes}
    rows: list[dict[str, object]] = []
    for section in package.script_sections:
        scene_id = section.scene_id
        scene = planned.get(scene_id)
        item = accepted.get(scene_id)
        if scene is None or not isinstance(item, dict):
            raise ProviderValidationError(f"storyboard scene {scene_id} has no accepted asset")
        candidate = item.get("candidate")
        if not isinstance(candidate, dict) or not isinstance(item.get("path"), str):
            raise ProviderValidationError(f"storyboard scene {scene_id} has incomplete provenance")
        rows.append({
            "scene_id": scene_id,
            "section_id": section.section_id,
            "narration": section.narration,
            "visual_subject": scene.visual_subject,
            "visual_purpose": scene.visual_purpose,
            "composition": scene.composition,
            "on_screen_text": scene.on_screen_text,
            "search_queries": list(scene.search_queries),
            "visual_elements": list(scene.visual_elements),
            "visual_elements_source": "scene_plan" if scene.visual_elements else "search_query_fallback",
            "asset_path": item["path"],
            "asset_sha256": item["checksum_sha256"],
            "asset_source_url": candidate.get("source_url"),
            "asset_author": candidate.get("author"),
            "asset_license": candidate.get("license_name"),
            "asset_provider_id": candidate.get("provider_asset_id"),
            "visual_route": item.get("visual_route"),
            "fallback": item.get("fallback"),
        })
    return {"version": "storyboard-v1", "topic": plan.topic, "aspect_ratio": plan.aspect_ratio, "scenes": rows, **({"scene_contract_sha256": scene_contract_sha256} if scene_contract_sha256 else {})}


def render_contact_sheets(manifest: dict[str, object], output_root: Path, *, ffmpeg: str = "ffmpeg") -> list[Path]:
    """Render every accepted scene, in narration order, across six-tile pages."""
    executable = shutil.which(ffmpeg)
    if not executable:
        raise ProviderValidationError("contact sheet requires FFmpeg")
    scenes = manifest.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        raise ProviderValidationError("contact sheet requires complete storyboard scenes")
    tile_w, tile_h = (270, 480) if manifest.get("aspect_ratio") == "9:16" else (320, 180)
    output_root.mkdir(parents=True, exist_ok=True)
    pages: list[Path] = []
    for offset in range(0, len(scenes), 6):
        subset = scenes[offset:offset + 6]
        inputs: list[str] = []
        filters: list[str] = []
        locations: list[str] = []
        for index, row in enumerate(subset):
            if not isinstance(row, dict):
                raise ProviderValidationError("contact sheet has malformed scene entry")
            path = Path(str(row.get("asset_path", "")))
            if not path.is_file():
                raise ProviderValidationError(f"contact sheet asset missing: {row.get('scene_id')}")
            with path.open("rb") as source:
                digest = hashlib.file_digest(source, "sha256").hexdigest()
            if digest != row.get("asset_sha256"):
                raise ProviderValidationError(f"contact sheet asset changed: {row.get('scene_id')}")
            inputs.extend(["-i", str(path)])
            filters.append(
                f"[{index}:v]scale={tile_w}:{tile_h}:force_original_aspect_ratio=decrease,"
                f"pad={tile_w}:{tile_h}:(ow-iw)/2:(oh-ih)/2:color=0x081123,"
                f"setsar=1[v{index}]"
            )
            locations.append(f"{index % 3 * tile_w}_{index // 3 * tile_h}")
        if len(subset) == 1:
            filters.append("[v0]format=yuv420p[out]")
        else:
            filters.append("".join(f"[v{index}]" for index in range(len(subset)))
                           + f"xstack=inputs={len(subset)}:layout={'|'.join(locations)}:fill=0x081123[out]")
        destination = output_root / f"contact-sheet-{offset // 6 + 1:03d}.png"
        with tempfile.TemporaryDirectory(prefix="contact-sheet-", dir=output_root) as temporary_dir:
            temporary = Path(temporary_dir) / "sheet.png"
            command = [executable, "-hide_banner", "-loglevel", "error", "-nostdin", *inputs,
                       "-filter_complex", ";".join(filters), "-map", "[out]", "-frames:v", "1",
                       "-threads", "2", "-y", str(temporary)]
            try:
                result = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
            except subprocess.TimeoutExpired as error:
                raise ProviderValidationError("contact sheet rendering timed out") from error
            if result.returncode or not temporary.is_file() or temporary.stat().st_size == 0:
                raise ProviderValidationError(f"contact sheet rendering failed: {result.stderr[-500:]}")
            os.replace(temporary, destination)
        pages.append(destination)
    if math.ceil(len(scenes) / 6) != len(pages):
        raise ProviderValidationError("contact sheet omitted scenes")
    return pages
