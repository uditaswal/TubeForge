"""Exact-script mode: the operator's wording is final.

The writer still plans the scenes, headings, diagrams and sources around the script, but its narration is replaced by the
operator's own blocks before the package is bound and validated, so nothing can rewrite a word. The writing checks (hook
score, craft and number rules, titles) and the rewriting passes of the Claude runner are skipped for these requests;
structure, layout, length cap and claim/source binding still apply.
"""
from __future__ import annotations

from tubeforge.core.errors import ProviderValidationError


def expected_sections(operator_script: str) -> list[str]:
    from tubeforge.pipeline.script_fit import split_sections
    return split_sections(operator_script)


def apply_exact_script(package: dict, request) -> dict:
    """Return the writer's package with narration forced to the operator's blocks (one section per block, in order)."""
    expected = expected_sections(request.operator_script or "")
    sections = package.get("script_sections")
    if not isinstance(sections, list) or len(sections) != len(expected):
        got = len(sections) if isinstance(sections, list) else 0
        raise ProviderValidationError(
            f"Exact script: your script has {len(expected)} scenes (blank lines separate them) but the plan has {got}. "
            f"Return exactly one script section and one scene per block of the script, in the same order.")
    topic = package.get("reference_short")
    if isinstance(topic, dict) and isinstance(topic.get("scenes"), list):
        # A scene's own copy of the speech would be compared with the narration; the binder rebuilds it from the section.
        topic = {**topic, "scenes": [{key: value for key, value in scene.items() if key != "vo"} if isinstance(scene, dict) else scene
                                     for scene in topic["scenes"]]}
        package = {**package, "reference_short": topic}
    return {**package, "script_sections": [{**section, "narration": text} for section, text in zip(sections, expected)]}
