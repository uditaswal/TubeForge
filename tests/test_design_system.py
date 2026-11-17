"""The design system stays consistent: tokens, guide, DESIGN.md and checker agree."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _checker():
    spec = importlib.util.spec_from_file_location("check_design", ROOT / "scripts" / "check_design.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_design_check_passes(capsys):
    checker = _checker()
    assert checker.main(["check_design.py"]) == 0, capsys.readouterr().out


def test_checker_catches_common_mistakes(tmp_path, monkeypatch):
    checker = _checker()
    guide = tmp_path / "guide.html"
    guide.write_text(
        '<section id="x" data-component="x"><div class="bg-slate-800 text-2xl rounded-xl shadow-md bg-tf-ok/20 '
        'text-[#fff] p-[13px]" style="color:red"><button>Go</button><input id="a"></div></section>'
    )
    monkeypatch.setattr(checker, "GUIDE", guide)
    monkeypatch.setattr(checker, "ROOT", tmp_path)
    checker.errors.clear()
    checker.check_classes()
    checker.check_accessibility()
    joined = "\n".join(checker.errors)
    for expected in (
        "Tailwind palette",
        "not in the type scale",
        "not an allowed radius",
        "shadows are not used",
        "opacity modifier",
        "arbitrary value",
        "inline style",
        "without type=",
        "has no <label",
    ):
        assert expected in joined, f"checker missed: {expected}\n{joined}"


def test_contrast_math_matches_wcag_reference():
    checker = _checker()
    assert round(checker.contrast("#000000", "#ffffff"), 1) == 21.0
    assert round(checker.contrast("#777777", "#ffffff"), 2) == 4.48
