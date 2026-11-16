"""The clip engine is a self-contained package: it must not reach into the rest of TubeForge."""
import ast
import subprocess
import sys
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "tubeforge" / "clips"
FORBIDDEN_LOADS = ("sqlalchemy", "boto3", "botocore", "redis", "asyncpg", "assemblyai", "apify_client", "fastapi")


def _modules():
    return sorted(path for path in PACKAGE.rglob("*.py"))


def test_engine_imports_nothing_from_the_rest_of_tubeforge():
    offenders = []
    for path in _modules():
        depth = len(path.relative_to(PACKAGE).parts) - 1  # directories below the package root
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom):
                absolute = node.module or ""
                if node.level == 0 and (absolute == "src" or absolute.startswith("src.")):
                    offenders.append(f"{path.name}: {absolute}")
                if node.level == 0 and absolute.startswith("tubeforge") and not absolute.startswith("tubeforge.clips"):
                    offenders.append(f"{path.name}: {absolute}")
                if node.level > depth + 1:
                    offenders.append(f"{path.name}: relative import leaves the package")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("tubeforge") and not alias.name.startswith("tubeforge.clips"):
                        offenders.append(f"{path.name}: {alias.name}")
    assert not offenders, offenders


def test_importing_the_engine_loads_no_service_dependencies():
    code = (
        f"import sys; sys.path.insert(0, {str(PACKAGE.parents[1])!r})\n"
        "import tubeforge.clips.engine\n"
        f"bad = [m for m in {FORBIDDEN_LOADS!r} if m in sys.modules]\n"
        "bad += [m for m in sys.modules if m.startswith(('tubeforge.db', 'tubeforge.api'))]\n"
        "print(','.join(bad))\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""


def test_no_legacy_top_level_package_remains():
    needle = "from src" + "."
    assert not [p.name for p in _modules() if needle in p.read_text(encoding="utf-8")]


def test_a_worker_without_the_clip_dependencies_still_starts():
    """The clip libraries load only when a clip job runs, so a stale image never breaks Shorts."""
    code = (
        f"import sys; sys.path.insert(0, {str(PACKAGE.parents[1])!r})\n"
        "for name in ('cv2', 'faster_whisper', 'pydantic_ai', 'srt', 'curl_cffi'):\n"
        "    sys.modules[name] = None\n"
        "import tubeforge.pipeline.orchestrator, tubeforge.api.app, tubeforge.workers.main\n"
        "print('ok')\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0 and result.stdout.strip() == "ok", result.stderr[-800:]
