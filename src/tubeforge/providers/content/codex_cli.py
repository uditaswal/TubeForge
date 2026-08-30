"""Narrow, safe Codex CLI adapter with persistent validated-result caching."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from pydantic import ValidationError

from tubeforge.core.config import CodexProviderConfig
from tubeforge.core.errors import ProviderAuthenticationError, ProviderValidationError, RetryableProviderError
from tubeforge.db.repositories import CachedGeneration, GenerationCacheRepository
from tubeforge.domain.contracts import ClaimReviewStatus, ConfidenceLevel, ContentPackage, ContentRequest
from tubeforge.providers.content.prompts import build_content_prompt, build_repair_prompt, normalize_content_request, validate_video_package


@dataclass(frozen=True, slots=True)
class ProcessResult:
    returncode: int
    stdout: bytes
    stderr: bytes


ProcessRunner = Callable[[list[str], str, Path, int, int], ProcessResult]


class CodexCliContentProvider:
    """Generate a validated package using an explicitly configured Codex CLI only."""

    provider_name = "codex-cli"

    def __init__(self, config: CodexProviderConfig, cache: GenerationCacheRepository, *, clock: Callable[[], datetime] | None = None, process_runner: ProcessRunner | None = None) -> None:
        self.config, self.cache = config, cache
        self._clock = clock or (lambda: datetime.now(UTC))
        self._process_runner = process_runner or _run_codex_process
        self.last_provenance: dict[str, object] | None = None
        self.last_usage: dict[str, object] | None = None

    def generate_package(self, request: ContentRequest) -> ContentPackage:
        now = self._now()
        cached = self.cache.reserve_or_get(request, self.provider_name, self.config.model, request.prompt_version, now=now, reservation_seconds=self.config.reservation_seconds)
        if isinstance(cached, CachedGeneration):
            package = self._validate_package(cached.package, request)
            self.last_provenance, self.last_usage = cached.provenance, cached.usage
            return package
        if cached is None:
            raise RetryableProviderError("Codex generation is already reserved; retry after the reservation expires")
        try:
            prompt = build_content_prompt(request, template_version=self.config.prompt_template_version, max_chars=self.config.max_prompt_chars)
            raw, usage = self._invoke(prompt)
            package = self._validate_or_repair(raw, request)
            package_json = package.model_dump(mode="json")
            provenance: dict[str, object] = {"cache_key": cached.cache_key, "generated_at": self._now().isoformat(), "model": self.config.model, "prompt_template_version": self.config.prompt_template_version, "prompt_version": request.prompt_version, "provider": self.provider_name}
            if not self.cache.accept(cached, package_json, provenance, usage, now=self._now()):
                raise RetryableProviderError("Codex generation reservation expired before validated result could be accepted")
        except Exception:
            self.cache.abandon(cached)
            raise
        self.last_provenance, self.last_usage = provenance, usage
        return package

    def build_cli_args(self, output_schema: Path, output_file: Path) -> list[str]:
        """Return fixed arguments; typed request values are never command arguments."""
        return [self.config.executable, "exec", "--ephemeral", "--sandbox", "read-only", "--model", self.config.model, "--output-schema", str(output_schema), "--output-last-message", str(output_file), "--json"]

    def _invoke(self, prompt: str) -> tuple[Any, dict[str, object]]:
        with tempfile.TemporaryDirectory(prefix="tubeforge-codex-") as temporary:
            root = Path(temporary)
            schema_path, output_path = root / "content-package.schema.json", root / "content-package.json"
            schema_path.write_text(json.dumps(ContentPackage.model_json_schema(), sort_keys=True), encoding="utf-8")
            result = self._process_runner(self.build_cli_args(schema_path, output_path), prompt, output_path, self.config.timeout_seconds, self.config.max_output_bytes)
            diagnostics = _safe_diagnostic(result.stderr or result.stdout, self.config.max_diagnostic_bytes)
            if result.returncode != 0:
                self._raise_process_failure(result.returncode, diagnostics)
            if not output_path.is_file():
                raise ProviderValidationError("Codex CLI completed without a structured output file")
            if output_path.stat().st_size > self.config.max_output_bytes:
                raise ProviderValidationError("Codex structured output exceeded configured output limit")
            try:
                raw = json.loads(output_path.read_text(encoding="utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ProviderValidationError("Codex structured output was not valid JSON") from error
            return raw, _extract_usage(result.stdout, self.config.max_diagnostic_bytes)

    def _validate_or_repair(self, raw: Any, request: ContentRequest) -> ContentPackage:
        candidate = raw
        for attempt in range(self.config.repair_attempt_limit + 1):
            try:
                return self._validate_package(candidate, request)
            except ProviderValidationError:
                raise
            except ValidationError as error:
                if attempt >= self.config.repair_attempt_limit:
                    raise ProviderValidationError("Codex output failed ContentPackage validation") from error
                target = _repair_target(error, candidate)
                if target is None:
                    raise ProviderValidationError("Codex output has a non-targetable ContentPackage validation error") from error
                path, value = target
                repair_prompt = build_repair_prompt(request, field_path=_format_path(path), invalid_value=value, validation_error=_safe_validation_error(error), template_version=self.config.prompt_template_version, max_chars=self.config.max_prompt_chars)
                replacement, _ = self._invoke(repair_prompt)
                candidate = _replace_path(candidate, path, _extract_repair_value(replacement, path))
        raise AssertionError("unreachable")

    def _validate_package(self, raw: Any, request: ContentRequest) -> ContentPackage:
        package = ContentPackage.model_validate(raw)
        if normalize_content_request(package.request) != normalize_content_request(request):
            raise ProviderValidationError("Codex output request or cited source packet differs from the requested source packet")
        validate_video_package(package, request, provider_name="Codex")
        claims = tuple(claim.model_copy(update={"review_status": ClaimReviewStatus.NEEDS_REVIEW, "human_review_required": True}) if claim.time_sensitive or claim.confidence in {ConfidenceLevel.LOW, ConfidenceLevel.MEDIUM} else claim for claim in package.claims)
        return package.model_copy(update={"claims": claims})

    def _raise_process_failure(self, returncode: int, diagnostics: str) -> None:
        detail = f": {diagnostics}" if diagnostics else ""
        lower = diagnostics.lower()
        if any(marker in lower for marker in ("auth", "login", "credential", "sign in", "unauthorized", "forbidden")):
            raise ProviderAuthenticationError(f"Codex CLI authentication is required{detail}")
        if returncode in {124, 137, 143} or any(marker in lower for marker in ("timeout", "temporar", "rate limit", "connection", "network")):
            raise RetryableProviderError(f"Codex CLI transient process failure ({returncode}){detail}")
        raise ProviderValidationError(f"Codex CLI failed ({returncode}){detail}")

    def _now(self) -> datetime:
        value = self._clock()
        return value if value.tzinfo else value.replace(tzinfo=UTC)


def _run_codex_process(args: list[str], prompt: str, output_path: Path, timeout_seconds: int, max_output_bytes: int) -> ProcessResult:
    """Run with bounded-on-disk capture and without inspecting Codex authentication."""
    del output_path
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        try:
            process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr, shell=False)
            process.communicate(prompt.encode("utf-8"), timeout=timeout_seconds)
        except subprocess.TimeoutExpired as error:
            process.kill(); process.communicate()
            raise RetryableProviderError("Codex CLI timed out") from error
        except OSError as error:
            raise RetryableProviderError("Codex CLI could not be started") from error
        stdout.seek(0, os.SEEK_END); stderr.seek(0, os.SEEK_END)
        if stdout.tell() > max_output_bytes or stderr.tell() > max_output_bytes:
            raise ProviderValidationError("Codex CLI process output exceeded configured output limit")
        stdout.seek(0); stderr.seek(0)
        return ProcessResult(process.returncode, stdout.read(), stderr.read())


def _extract_usage(stdout: bytes, maximum: int) -> dict[str, object]:
    for line in stdout[:maximum].splitlines():
        try: event = json.loads(line)
        except json.JSONDecodeError: continue
        if isinstance(event, dict) and isinstance(event.get("usage"), dict): return event["usage"]
    return {}


def _safe_diagnostic(value: bytes, maximum: int) -> str:
    text = value[:maximum].decode("utf-8", errors="replace").replace("\n", " ").replace("\r", " ")
    return re.sub(r"(?i)(api[_-]?key|token|authorization|password|secret)\s*[:=]\s*[^\s,;]+", r"\1=[REDACTED]", text)[:maximum].strip()


def _safe_validation_error(error: ValidationError) -> str:
    first = error.errors(include_url=False)[0]
    return f"{_format_path(tuple(first['loc']))}: {first['msg']}"[:1_000]


def _repair_target(error: ValidationError, candidate: Any) -> tuple[tuple[str | int, ...], Any] | None:
    """Return the exact Pydantic field path and its current value (or None if absent)."""
    if not isinstance(candidate, (dict, list)):
        return None
    location = tuple(error.errors(include_url=False)[0]["loc"])
    if not location or not all(isinstance(part, (str, int)) for part in location):
        return None
    current = candidate
    try:
        for part in location:
            current = current[part]
    except (KeyError, IndexError, TypeError):
        parent = candidate
        try:
            for part in location[:-1]:
                parent = parent[part]
        except (KeyError, IndexError, TypeError):
            return None
        if not isinstance(parent, (dict, list)):
            return None
        return location, None
    return location, current


def _replace_path(value: Any, path: tuple[str | int, ...], replacement: Any) -> Any:
    """Replace one existing or missing leaf without replacing its parent object."""
    if not path:
        raise ValueError("repair path must identify a field")
    copied = json.loads(json.dumps(value))
    target = copied
    for part in path[:-1]:
        if not isinstance(target, (dict, list)):
            raise ValueError("repair path traverses a scalar")
        target = target[part]
    if not isinstance(target, (dict, list)):
        raise ValueError("repair path parent is not a collection")
    target[path[-1]] = replacement
    return copied


def _extract_repair_value(replacement: Any, path: tuple[str | int, ...]) -> Any:
    """Accept a leaf response or unwrap the requested leaf from a containing object."""
    leaf = path[-1]
    if isinstance(replacement, dict) and isinstance(leaf, str) and leaf in replacement:
        return replacement[leaf]
    current = replacement
    try:
        for part in path:
            current = current[part]
    except (KeyError, IndexError, TypeError):
        return replacement
    return current


def _format_path(path: tuple[Any, ...]) -> str:
    return ".".join(str(part) for part in path)
