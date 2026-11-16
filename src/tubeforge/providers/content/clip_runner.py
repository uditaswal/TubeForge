"""Worker-side transport that lets the clip engine ask the host Claude runner for completions."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Callable, Optional

from tubeforge.clips.runner_model import RunnerError
from tubeforge.providers.content.host_runner import _request
from tubeforge.providers.content.host_runner_protocol import CLIP_PROMPT_MAX_CHARS, ClipCompletionRequest, HostRunnerResponse

Call = Callable[[str, bytes, int], bytes]


class ClipRunnerTransport:
    """``(system, prompt, schema) -> answer text`` over the runner's Unix socket."""

    def __init__(self, socket_path: Path, *, timeout_seconds: int = 600, call: Call = _request) -> None:
        self.socket_path, self.timeout_seconds, self._call = Path(socket_path), timeout_seconds, call

    async def __call__(self, system: str, prompt: str, schema: Optional[dict]) -> str:
        if len(prompt) > CLIP_PROMPT_MAX_CHARS:
            raise RunnerError(f"The clip prompt is {len(prompt):,} characters; the runner accepts at most {CLIP_PROMPT_MAX_CHARS:,}.")
        request = ClipCompletionRequest(system=system[:20_000], prompt=prompt, output_schema=schema)
        try:
            raw = await asyncio.to_thread(self._call, str(self.socket_path), request.model_dump_json().encode(), self.timeout_seconds)
            response = HostRunnerResponse.model_validate_json(raw)
        except OSError as error:
            raise RunnerError(f"The Claude runner is not reachable: {type(error).__name__}") from error
        if not response.ok or response.result is None:
            failure = response.failure
            raise RunnerError(f"The Claude runner refused the clip request ({failure.code if failure else 'unknown'}): {failure.message if failure else ''}"[:600])
        return json.dumps(response.result.package)

    def ping(self) -> bool:
        """True when something answers on the socket (used by the Clips page status strip)."""
        try:
            return Path(self.socket_path).exists()
        except OSError:
            return False
