"""Exact-script mode: the operator's wording is final; the writer only plans visuals around it."""
import pytest
from pydantic import ValidationError

from tubeforge.core.errors import ProviderValidationError
from tubeforge.domain.contracts import ContentRequest, SourceReference


def _request(**extra):
    return ContentRequest(topic="T", angle="A", target_duration_seconds=60, language="en", audience="general", prompt_version="m6-content-v8",
                          aspect_ratio="9:16", script_owner="claude", sources=(SourceReference(source_id="s1", url="https://example.org/a", title="A", excerpt="Some page text."),), **extra)


SCRIPT = "First scene has exactly these words here.\n\nSecond scene keeps every word too, said plainly."


def test_exact_mode_needs_a_script_and_leaves_existing_identity_untouched():
    with pytest.raises(ValidationError, match="exact_script needs"):
        _request(exact_script=True)
    plain = _request(operator_script=SCRIPT)
    assert "exact_script" not in plain.model_dump(mode="json")            # default omitted: cache keys of existing jobs do not change
    exact = _request(operator_script=SCRIPT, exact_script=True)
    assert exact.model_dump(mode="json")["exact_script"] is True           # but exact vs assist is a different generation identity


def test_prompt_tells_the_writer_not_to_touch_a_word_only_in_exact_mode():
    from tubeforge.providers.content.prompts import operator_script_clause
    assert "EXACT" in operator_script_clause(_request(operator_script=SCRIPT, exact_script=True))
    assist = operator_script_clause(_request(operator_script=SCRIPT))
    assert "EXACT" not in assist and "keep its wording" in assist


def _package(narrations):
    return {"script_sections": [{"scene_id": f"s{i}", "narration": n} for i, n in enumerate(narrations)],
            "reference_short": {"scenes": [{"scene_id": f"s{i}", "vo": n, "template": "flow"} for i, n in enumerate(narrations)]}}


def test_apply_exact_script_forces_the_operators_blocks_and_drops_the_writers_copy():
    from tubeforge.providers.content.exact_script import apply_exact_script
    request = _request(operator_script=SCRIPT, exact_script=True)
    forced = apply_exact_script(_package(["rewritten one", "rewritten two"]), request)
    assert [s["narration"] for s in forced["script_sections"]] == SCRIPT.split("\n\n")
    assert all("vo" not in scene for scene in forced["reference_short"]["scenes"])     # the binder rebuilds speech from the sections
    assert forced["script_sections"][0]["scene_id"] == "s0"


def test_apply_exact_script_refuses_a_plan_with_a_different_number_of_scenes_and_says_how_to_fix_it():
    from tubeforge.providers.content.exact_script import apply_exact_script
    with pytest.raises(ProviderValidationError, match="your script has 2 scenes .* the plan has 3"):
        apply_exact_script(_package(["a", "b", "c"]), _request(operator_script=SCRIPT, exact_script=True))


def test_binding_keeps_the_exact_wording_even_when_the_writer_changed_it():
    from tubeforge.providers.content.output import bind_reference_output
    from tubeforge.providers.content.exact_script import apply_exact_script
    request = _request(operator_script="Mix up your problem types, instead of drilling one kind of problem.\n\nThen rehearse out loud, because it's stressful.", exact_script=True)
    package = _package(["The writer reworded this line completely.", "And this one too, sadly."])
    package["metadata"] = {"title_options": ["T"]}
    bound = bind_reference_output(apply_exact_script(package, request), request)
    assert [scene["vo"] for scene in bound["reference_short"]["scenes"]] == [
        "Mix up your problem types, instead of drilling one kind of problem.", "Then rehearse out loud, because it's stressful."]


def test_writing_checks_are_skipped_for_exact_scripts_but_not_for_assisted_ones():
    from types import SimpleNamespace
    from test_script_craft import package as craft_package, YOU
    from tubeforge.providers.content.prompts import validate_video_package
    four_numbers = "Two seven five hundred of them were checked, then three hundred more were counted again."   # 5 spoken numbers in one scene
    pkg = craft_package(scenes={1: {"vo": four_numbers, "caption": four_numbers}})
    pkg.scene_plans, pkg.script_sections = [], [SimpleNamespace(narration=scene.vo) for scene in pkg.reference_short.scenes]
    for exact, must_raise in ((False, True), (True, False)):
        request = SimpleNamespace(exact_script=exact, target_duration_seconds=60)
        try:
            validate_video_package(pkg, request, provider_name="Claude")
            raised = None
        except ProviderValidationError as error:
            raised = str(error)
        if must_raise:
            assert raised and ("numbers" in raised or "hook" in raised.lower() or "craft" in raised), raised
        else:
            assert raised is None or ("numbers" not in raised and "craft needs repair" not in raised), raised


def test_batch_yaml_script_mode_exact_needs_a_script():
    from tubeforge.batch_plans import parse_batch
    base = "## A\n\n```yaml\nid: a-1\ntitle: T\nconcept: C\nbeats:\n  - {t: 0, point: Hook}\n%s\n```\n"
    ok = parse_batch(base % "script_mode: exact\nscript: |\n  One two three four five six seven eight.")
    assert not ok.errors and ok.shorts[0].script_mode == "exact"
    bad = parse_batch(base % "script_mode: exact")
    assert bad.errors and "needs a script" in bad.errors[0].message
    assert parse_batch(base % "narration: Plain assisted text.").shorts[0].script_mode == "assist"


def test_exact_mode_is_refused_for_the_codex_writer_and_can_default_on_from_settings(tmp_path, monkeypatch):
    from fastapi import HTTPException
    from tubeforge.api.app import VideoBriefRequest, _video_request
    from tubeforge.core import runtime_settings as rs
    from tubeforge.core.config import AppConfig, AuthConfig, DatabaseConfig, Settings
    settings = Settings(app=AppConfig(name="t", environment="test"), database=DatabaseConfig(url=f"sqlite:///{tmp_path / 's.db'}"), auth=AuthConfig(enabled=True))
    monkeypatch.setattr(rs, "_shared", rs.RuntimeSettings(tmp_path / "rs.json"))
    brief = dict(title="T", notes=["n"], operator_script=SCRIPT, exact_script=True, script_owner="codex")
    with pytest.raises(HTTPException) as refused:
        _video_request(VideoBriefRequest(**brief), settings)
    assert refused.value.status_code == 422 and "Claude writer" in refused.value.detail
