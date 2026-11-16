"""The engine's real agents answer through whatever transport the host installs."""
import asyncio
import json

import pytest

from tubeforge.clips import ai
from tubeforge.clips.config import Config, set_config_override
from tubeforge.clips.runner_model import RunnerError, set_transport

TRANSCRIPT = "[00:00 - 00:30] A useful standalone explanation of a common mistake and how to avoid it in practice."


@pytest.fixture(autouse=True)
def runner_config():
    config = Config()
    config.llm = "runner"
    config.llm_fallbacks = []
    set_config_override(config)
    ai._transcript_agent = None
    try:
        yield
    finally:
        set_config_override(None)
        set_transport(None)
        ai._transcript_agent = None


def test_the_selection_agent_gets_a_schema_and_returns_validated_segments():
    seen = {}

    async def transport(system, prompt, schema):
        seen.update(system=system, prompt=prompt, schema=schema)
        return json.dumps({
            "most_relevant_segments": [{"start_time": "00:00", "end_time": "00:30", "text": "A useful standalone explanation of a common mistake."}],
            "summary": "A common mistake.", "key_topics": ["mistakes"],
        })

    set_transport(transport)
    result = asyncio.run(ai.get_most_relevant_parts_by_transcript(TRANSCRIPT))
    assert result.most_relevant_segments and result.summary == "A common mistake."
    assert seen["schema"]["type"] == "object" and "most_relevant_segments" in json.dumps(seen["schema"])
    assert "JSON" in seen["prompt"]


def test_without_a_runner_the_engine_says_so_plainly():
    with pytest.raises(RuntimeError, match="AI runner"):
        asyncio.run(ai.get_most_relevant_parts_by_transcript(TRANSCRIPT))


def test_a_runner_failure_surfaces_as_a_model_error():
    async def transport(system, prompt, schema):
        raise RunnerError("The Claude runner refused the clip request (quota_exhausted): limit")

    set_transport(transport)
    with pytest.raises(Exception, match="quota_exhausted"):
        asyncio.run(ai.get_most_relevant_parts_by_transcript(TRANSCRIPT))
