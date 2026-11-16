import pytest


@pytest.fixture(autouse=True)
def isolated_clip_environment(monkeypatch, tmp_path):
    """No test may reach a paid provider, a real runner or a shared lock folder."""
    monkeypatch.setenv("TUBEFORGE_CLIPS_LOCK_DIR", str(tmp_path / "locks"))
    for name in ("RAPIDAPI_YOUTUBE_API_KEY", "APIFY_API_TOKEN", "YOUTUBE_PROXY_URL"):
        monkeypatch.delenv(name, raising=False)


import sys
from pathlib import Path

_HERE = str(Path(__file__).parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)  # sibling test helpers such as workflow_planner_fakes

