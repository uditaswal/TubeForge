"""Script owner: Codex stays byte-identical by default; Claude is routed explicitly."""
import pytest

from tubeforge.core.errors import ProviderValidationError
from tubeforge.domain.contracts import ContentRequest, generation_request_key_payload
from tubeforge.providers.content.factory import ScriptOwnerRouter
from tubeforge.providers.content.host_runner import HostRunnerContentProvider
from tubeforge.core.config import CodexProviderConfig


def request(**extra):
    return ContentRequest(
        topic="t", angle="a", target_duration_seconds=30, language="en", audience="x",
        sources=[{"source_id": "s", "url": "https://a.example/c", "title": "T", "excerpt": "e"}],
        prompt_version="m6-content-v7", **extra)


def test_default_owner_is_omitted_so_existing_jobs_and_cache_keys_do_not_change():
    codex = request()
    assert codex.script_owner == "codex"
    assert "script_owner" not in codex.model_dump(mode="json")
    assert "script_owner" not in generation_request_key_payload(codex)


def test_claude_owner_round_trips_and_changes_the_key():
    claude = request(script_owner="claude")
    assert ContentRequest.model_validate_json(claude.model_dump_json()).script_owner == "claude"
    assert generation_request_key_payload(claude) != generation_request_key_payload(request())


def test_unknown_owner_is_rejected():
    with pytest.raises(ValueError):
        request(script_owner="gemini")


class Recorder:
    def __init__(self, name):
        self.name, self.calls, self.last_provenance, self.last_usage = name, [], {"p": name}, {"u": name}

    def generate_package(self, req):
        self.calls.append(req.script_owner)
        return self.name


def test_router_sends_each_job_to_its_owner_and_reports_that_provenance():
    codex, claude = Recorder("codex"), Recorder("claude")
    router = ScriptOwnerRouter({"codex": codex, "claude": claude})
    assert router.generate_package(request(script_owner="claude")) == "claude"
    assert router.last_provenance == {"p": "claude"}
    assert router.generate_package(request()) == "codex"
    assert router.last_usage == {"u": "codex"}
    assert (codex.calls, claude.calls) == (["codex"], ["claude"])


def test_disabled_owner_fails_closed_instead_of_falling_back_to_codex():
    router = ScriptOwnerRouter({"codex": Recorder("codex")})
    with pytest.raises(ProviderValidationError, match="not enabled"):
        router.generate_package(request(script_owner="claude"))


def test_codex_provider_refuses_a_claude_job_when_no_router_is_installed():
    provider = HostRunnerContentProvider(CodexProviderConfig(), cache=None)  # type: ignore[arg-type]
    with pytest.raises(ProviderValidationError, match="not enabled"):
        provider.generate_package(request(script_owner="claude"))


def test_script_model_is_optional_validated_and_omitted_by_default():
    assert "script_model" not in request().model_dump(mode="json")
    picked = request(script_owner="claude", script_model="sonnet-medium")
    assert ContentRequest.model_validate_json(picked.model_dump_json()).script_model == "sonnet-medium"
    assert generation_request_key_payload(picked) != generation_request_key_payload(request(script_owner="claude", script_model="opus"))
    with pytest.raises(ValueError):
        request(script_owner="claude", script_model="gpt-9")


def test_runner_maps_only_allow_listed_models_to_cli_model_and_effort():
    from tubeforge.host_claude_runner import MODELS, resolve_model
    class Wrapper:  # mimics GenerateShortsScriptRequest.request
        def __init__(self, req): self.request = req
    assert resolve_model(Wrapper(request(script_owner="claude"))) == MODELS["sonnet-medium"]
    assert resolve_model(Wrapper(request(script_owner="claude", script_model="opus"))) == ("claude-opus-5-5", "high")


def test_hook_gate_is_only_a_floor_and_report_voice_is_a_craft_error():
    from types import SimpleNamespace
    from tubeforge.providers.content.craft import REPORT_VOICE
    from tubeforge.providers.content.youtube_skills import hook_gate
    def package(text):
        return SimpleNamespace(script_sections=[SimpleNamespace(narration=text + " More follows here.")])
    assert hook_gate(package("Microsoft rewrote Copilot's engine in Rust for $120,000.")) is None  # named story must pass the floor
    assert hook_gate(package("Stuff happened.")) is not None
    for report in ("Memory bugs fell from 76% to 24% of Android's flaws.", "Researchers found most bugs hide in new code.", "A study shows rewrites fail."):
        assert REPORT_VOICE.search(report)
    for story in ("Microsoft rewrote Copilot's engine in Rust. One engineer.", "You couldn't afford this rewrite before."):
        assert not REPORT_VOICE.search(story)
