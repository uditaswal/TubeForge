"""AI transport for clip selection.

The pipeline's agents (window analysis, rerank, B-roll, hook review) are pydantic-ai
agents. They all talk to one model, which hands the flattened prompt and the output
JSON schema to a transport the host application installs with ``set_transport``.
Nothing here starts a process or reads a credential.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Awaitable, Callable, Optional

from pydantic_ai.exceptions import ModelAPIError
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

logger = logging.getLogger(__name__)

RUNNER_PROVIDER = "runner"
CLI_PROVIDERS = {RUNNER_PROVIDER}

# (system, prompt, json_schema) -> answer text
Transport = Callable[[str, str, Optional[dict]], Awaitable[str]]
_transport: Optional[Transport] = None


class RunnerError(ModelAPIError):
    """The runner failed or is not configured; a ``ModelAPIError`` so fallbacks can react."""

    def __init__(self, message: str, model_name: str = "runner"):
        super().__init__(model_name, message)


def set_transport(transport: Optional[Transport]) -> None:
    global _transport
    _transport = transport


def transport_ready() -> bool:
    return _transport is not None


def messages_to_prompt(messages: list[ModelMessage]) -> tuple[str, str]:
    """Flatten pydantic-ai messages into ``(system, conversation)`` text."""
    system: list[str] = []
    turns: list[str] = []
    for message in messages:
        if isinstance(message, ModelRequest):
            for part in message.parts:
                if isinstance(part, SystemPromptPart):
                    system.append(part.content)
                elif isinstance(part, UserPromptPart):
                    content = part.content if isinstance(part.content, str) else " ".join(
                        str(c) for c in part.content if isinstance(c, str)
                    )
                    turns.append(content)
                elif isinstance(part, RetryPromptPart):
                    turns.append(
                        "Your previous answer was rejected:\n"
                        f"{part.model_response()}\nReturn corrected JSON only."
                    )
                elif isinstance(part, ToolReturnPart):
                    turns.append(str(part.content))
        elif isinstance(message, ModelResponse):
            for part in message.parts:
                if isinstance(part, TextPart):
                    turns.append(f"[assistant]\n{part.content}")
                elif isinstance(part, ToolCallPart):
                    turns.append(f"[assistant]\n{part.args_as_json_str()}")
    return "\n\n".join(system), "\n\n".join(turns)


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def extract_json(text: str) -> Any:
    """Parse JSON from model output, tolerating code fences and surrounding prose."""
    cleaned = _FENCE.sub("", text.strip()).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    start = min((i for i in (cleaned.find("{"), cleaned.find("[")) if i != -1), default=-1)
    if start == -1:
        raise RunnerError("The model did not return JSON")
    try:
        value, _ = json.JSONDecoder().raw_decode(cleaned[start:])
        return value
    except json.JSONDecodeError as error:
        raise RunnerError(f"The model returned invalid JSON: {error}") from None


async def run_completion(system: str, prompt: str, schema: Optional[dict]) -> str:
    if _transport is None:
        raise RunnerError("No AI runner is configured for clip selection")
    return await _transport(system, prompt, schema)


def build_runner_model() -> FunctionModel:
    """A pydantic-ai model that answers through the installed transport."""

    async def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        system, conversation = messages_to_prompt(messages)
        tool = info.output_tools[0] if info.output_tools else None
        schema = tool.parameters_json_schema if tool else None
        prompt = conversation
        if schema:
            prompt += (
                "\n\nReply with ONLY a JSON object (no prose, no code fence) that matches this "
                f"JSON Schema:\n{json.dumps(schema)}"
            )
        text = await run_completion(system, prompt, schema)
        if tool is None:
            return ModelResponse(parts=[TextPart(content=text)])
        try:
            args = json.dumps(extract_json(text))
        except RunnerError:
            return ModelResponse(parts=[TextPart(content=text)])  # pydantic-ai asks again
        return ModelResponse(parts=[ToolCallPart(tool_name=tool.name, args=args)])

    return FunctionModel(respond, model_name=RUNNER_PROVIDER)
