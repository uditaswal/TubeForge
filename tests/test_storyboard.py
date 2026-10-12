from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

import pytest

from tubeforge.core.errors import ProviderValidationError
from tubeforge.pipeline.storyboard import render_contact_sheets


def test_contact_sheets_cover_every_scene_and_reject_changed_assets(tmp_path: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("FFmpeg is unavailable")
    source = tmp_path / "source.png"
    subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
         "color=c=0x081123:s=320x180:d=1", "-frames:v", "1", "-y", str(source)],
        check=True, timeout=30,
    )
    checksum = hashlib.sha256(source.read_bytes()).hexdigest()
    manifest = {"aspect_ratio": "16:9", "scenes": [
        {"scene_id": f"scene-{index}", "asset_path": str(source), "asset_sha256": checksum}
        for index in range(7)
    ]}
    pages = render_contact_sheets(manifest, tmp_path / "sheets")
    assert len(pages) == 2
    assert all(page.is_file() and page.stat().st_size for page in pages)
    manifest["scenes"][6]["asset_sha256"] = "0" * 64
    with pytest.raises(ProviderValidationError, match="asset changed"):
        render_contact_sheets(manifest, tmp_path / "tampered")
