"""Socket-activated, host-only Codex runner.

This module deliberately accepts no command, path, model, or prompt supplied by
the worker.  systemd owns the listening socket; the runner verifies peer UID
before it reads a request.
"""

from __future__ import annotations

import json
import hashlib
import os
import shutil
import socket
import sqlite3
import struct
import subprocess
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from tubeforge.core.errors import InsufficientSourcesError, ProviderValidationError
from tubeforge.domain.contracts import ContentPackage
from tubeforge.providers.content.host_runner_protocol import GenerateShortsScriptRequest, HostRunnerResponse, HostRunnerSuccess
from tubeforge.providers.content.prompts import build_content_prompt, normalize_content_request

WORKER_UID = 1000
MAX_MESSAGE_BYTES = 65_536
MAX_RESPONSE_BYTES = 4_000_000
MAX_OUTPUT_BYTES = 2_000_000
TIMEOUT_SECONDS = 480
RUNNER_ROOT = Path("/var/lib/tubeforge-codex")
CODEX_HOME = RUNNER_ROOT / ".codex"
BWRAP = "/usr/bin/bwrap"
CODEX_MODEL = "gpt-5.6-sol"
CODEX_RUNTIME = Path("/opt/tubeforge-codex-runner/codex-runtime")
CODEX_NODE = CODEX_RUNTIME / "node" / "bin" / "node"
CODEX_ENTRYPOINT = CODEX_RUNTIME / "lib" / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
INVOCATION_LIMIT = 2
MAX_FALLBACK_VISUAL_CHARS = 100
NODE_LIBRARIES = (
    "libdl.so.2", "libstdc++.so.6", "libm.so.6", "libgcc_s.so.1",
    "libpthread.so.0", "libc.so.6", "ld-linux-x86-64.so.2",
)


class RejectedContentError(ValueError):
    """Return a domain-valid rejected draft to the worker's existing audit cache."""

    def __init__(self, reason: str, result: HostRunnerSuccess) -> None:
        super().__init__(reason)
        self.result = result


def peer_uid(connection: socket.socket) -> int:
    credentials = connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
    return struct.unpack("3i", credentials)[1]


def receive_request(connection: socket.socket) -> GenerateShortsScriptRequest:
    """Read exactly one bounded JSON request after caller authorization."""
    if peer_uid(connection) != WORKER_UID:
        raise PermissionError("runner accepts only worker UID 1000")
    payload = connection.recv(MAX_MESSAGE_BYTES + 1)
    if not payload or len(payload) > MAX_MESSAGE_BYTES:
        raise ValueError("request is missing or exceeds the runner limit")
    return GenerateShortsScriptRequest.model_validate_json(payload)


def fixed_paths(request_id: str, root: Path = Path("/var/lib/tubeforge-codex")) -> tuple[Path, Path]:
    """Return runner-owned schema/output paths; callers never provide paths."""
    safe = request_id.replace("-", "")
    if not safe.isalnum() or len(safe) > 64:
        raise ValueError("invalid runner request id")
    output = root / "outputs" / safe
    return output / "content-package.schema.json", output / "content-package.json"


def encode_failure(code: str, message: str, *, invocation_started: bool = True) -> bytes:
    return HostRunnerResponse(ok=False, failure={"code": code, "message": message[:1000], "invocation_started": invocation_started}).model_dump_json().encode()


def _redact(value: str) -> str:
    return value.replace("\n", " ").replace("\r", " ")[:1000]


def cli_failure_detail(stdout: bytes, stderr: bytes) -> str:
    """Extract CLI error events, never generated text or the input prompt."""
    failures: list[str] = []
    event_types: list[str] = []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        kind = event.get("type")
        if isinstance(kind, str) and len(event_types) < 12:
            event_types.append(kind)
        if kind not in {"error", "turn.failed"}:
            continue
        detail = event.get("error") if kind == "turn.failed" else event.get("message")
        if isinstance(detail, dict):
            detail = detail.get("message")
        if isinstance(detail, str):
            failures.append(_redact(detail))
    return _redact("; ".join(failures[-2:]) or stderr.decode(errors="replace") or f"CLI events: {event_types}")


def codex_output_schema(*, envelope: bool = False, reference: bool = False, keep_lengths: bool = False) -> dict[str, object]:
    """Make the domain schema acceptable to Codex's strict structured output.

    Pydantic omits defaulted fields from ``required`` and emits string
    constraints unsupported by Codex (notably ``format: uri``). The immutable
    request is supplied in full in the prompt. Envelope outputs omit it; the
    application binds trusted inputs before validating generated content.
    """
    from tubeforge.providers.content.output import ContentGenerationResult
    schema = (ContentGenerationResult if envelope else ContentPackage).model_json_schema()
    package_schema = schema["$defs"]["ContentPackage"] if envelope else schema
    if not reference:
        package_schema["properties"].pop("reference_short", None)
        # The pinned debate comment belongs to the reference-short profile only.
        metadata_schema = schema["$defs"]["VideoMetadata"]
        metadata_schema["properties"].pop("engagement_comment", None)
    else:
        if not envelope:
            raise ValueError("reference output requires the trusted-request envelope")
        package_schema["properties"]["reference_short"] = {"$ref": "#/$defs/ShortsTopic"}
        package_schema["properties"].pop("scene_plans")
        package_schema["required"].remove("scene_plans")
        topic_schema = schema["$defs"]["ShortsTopic"]
        for field in ("title", "sources"):
            topic_schema["properties"].pop(field)
            topic_schema["required"].remove(field)
        for kind in ("Hook", "BigStat", "BeforeAfter", "Flow", "Checklist", "Terminal", "CTA"):
            item = schema["$defs"][kind]
            item["properties"].pop("vo")
            item["required"].remove("vo")
    if envelope:
        # The application binds immutable inputs; do not make the model copy
        # long fetched excerpts or runtime settings into generated output.
        schema["$defs"]["ContentPackage"]["properties"].pop("request")
        schema["$defs"]["ContentPackage"]["required"].remove("request")
        # These are existing acceptance invariants, made visible to the CLI.
        schema["$defs"]["VideoMetadata"]["properties"]["title_options"]["minItems"] = 10
        schema["$defs"]["ContentPackage"]["properties"]["hook_options"]["minItems"] = 5

    if envelope and not reference:
        # Cross-field Pydantic validators are not represented by model_json_schema.
        # Give the writer legal alternatives instead of letting it combine a
        # free-text layout with motion cues that the renderer cannot execute.
        import copy

        scene = schema["$defs"]["ScenePlan"]
        variants = []
        for layout in ("terminal", "flow_diagram", "comparison", "timeline", "source_card"):
            modes = [None, "terminal_cues"] if layout == "terminal" else [None, "teaching_cues"]
            if layout in {"flow_diagram", "comparison", "timeline"}:
                modes.append("card_cues")
            for mode in modes:
                variant = copy.deepcopy(scene)
                props = variant["properties"]
                props["visual_type"] = {"type": "string", "enum": [layout]}
                props["visual_elements"]["minItems"] = 3
                props["visual_elements"]["maxItems"] = 3
                if layout == "terminal":
                    props["on_screen_text"] = {"type": "string", "minLength": 1}
                for cue in ("terminal_cues", "card_cues", "teaching_cues"):
                    if cue != mode:
                        props[cue] = {"type": "null"}
                    else:
                        props[cue] = next(item for item in props[cue]["anyOf"] if "$ref" in item)
                if mode == "teaching_cues" and layout != "comparison":
                    teaching = copy.deepcopy(schema["$defs"]["TeachingRevealCues"])
                    teaching["properties"]["comparison_panels_first"] = {"type": "boolean", "enum": [False]}
                    props[mode] = teaching
                variants.append(variant)
        schema["$defs"]["ScenePlan"] = {"anyOf": variants}

    def make_strict(value: object) -> None:
        if isinstance(value, dict):
            value.pop("default", None)
            value.pop("discriminator", None)
            if "oneOf" in value:
                value["anyOf"] = value.pop("oneOf")
            # Keep the CLI-facing schema within the documented strict subset.
            # The Pydantic model remains the authoritative output validator.
            if not keep_lengths:
                value.pop("minLength", None)
                value.pop("maxLength", None)
            if value.get("format") not in {None, "date-time", "time", "date", "duration", "email", "hostname", "ipv4", "ipv6", "uuid"}:
                value.pop("format", None)
            if value.get("type") == "object":
                properties = value.get("properties")
                if not isinstance(properties, dict):
                    raise ValueError("Codex output schema has an object without properties")
                value["required"] = list(properties)
                value["additionalProperties"] = False
            for child in value.values():
                make_strict(child)
        elif isinstance(value, list):
            for child in value:
                make_strict(child)

    make_strict(schema)
    return schema


def normalize_fallback_visuals(raw: object) -> tuple[object, list[dict[str, object]]]:
    """Shorten only overlong scene fallbacks, at a complete-word boundary.

    A fallback without a usable boundary remains invalid for the domain
    validator. Never modify the model's original object or other script fields.
    """
    if not isinstance(raw, dict) or not isinstance(raw.get("scene_plans"), list):
        return raw, []
    scenes = list(raw["scene_plans"])
    changes: list[dict[str, object]] = []
    for index, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            continue
        fallback = scene.get("fallback_visual")
        if not isinstance(fallback, str) or len(fallback) <= MAX_FALLBACK_VISUAL_CHARS:
            continue
        boundary = max((i for i, char in enumerate(fallback[:MAX_FALLBACK_VISUAL_CHARS + 1]) if char.isspace()), default=-1)
        if boundary <= 0:
            continue
        shortened = fallback[:boundary].rstrip()
        if not shortened:
            continue
        scenes[index] = {**scene, "fallback_visual": shortened}
        changes.append({
            "field": f"scene_plans.{index}.fallback_visual",
            "original_length": len(fallback),
            "normalized_length": len(shortened),
            "method": "word_boundary_truncation",
        })
    if not changes:
        return raw, []
    return {**raw, "scene_plans": scenes}, changes


class AllowanceExhaustedError(Exception):
    """The host has already spent this request's fixed CLI allowance."""


def consume_invocation(request: GenerateShortsScriptRequest, root: Path = RUNNER_ROOT) -> None:
    """Durably count even failed CLI launches before any model invocation."""
    from tubeforge.domain.contracts import generation_request_key_payload
    material = request.model_dump(mode="json")
    material["request"] = generation_request_key_payload(request.request)
    digest = hashlib.sha256(json.dumps(material, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    with sqlite3.connect(root / "invocations.sqlite3", timeout=10) as database:
        database.execute("CREATE TABLE IF NOT EXISTS invocations (request_hash TEXT PRIMARY KEY, count INTEGER NOT NULL)")
        cursor = database.execute(
            "INSERT INTO invocations (request_hash, count) VALUES (?, 1) "
            "ON CONFLICT(request_hash) DO UPDATE SET count = count + 1 WHERE count < ?",
            (digest, 1 if request.operation == "ResearchSourcesV1" else INVOCATION_LIMIT),
        )
        if cursor.rowcount != 1:
            raise AllowanceExhaustedError("Research attempt already consumed; revise the brief or inspect the saved research result" if request.operation == "ResearchSourcesV1" else "TubeForge's two-attempt limit for this exact source packet is exhausted")


def bubblewrap_args(workspace: Path) -> list[str]:
    """Build a namespace exposing only the pinned root-owned Codex runtime."""
    if not CODEX_NODE.is_file() or not CODEX_ENTRYPOINT.is_file():
        raise RuntimeError("the pinned root-owned Codex runtime is unavailable")
    if not Path(BWRAP).is_file():
        raise RuntimeError("Bubblewrap is unavailable")
    args = [BWRAP, "--die-with-parent", "--unshare-all", "--share-net", "--new-session"]
    for directory in ("/lib", "/lib/x86_64-linux-gnu", "/lib64", "/etc", "/etc/ssl", "/opt", "/opt/tubeforge-codex-runner"):
        args.extend(("--dir", directory))
    for library in NODE_LIBRARIES:
        source = Path("/lib/x86_64-linux-gnu") / library
        target = (Path("/lib64") if library.startswith("ld-linux") else Path("/lib/x86_64-linux-gnu")) / library
        if not source.is_file():
            raise RuntimeError(f"required Node library is unavailable: {library}")
        args.extend(("--ro-bind", str(source), str(target)))
    for path in ("/etc/resolv.conf", "/etc/ssl/certs"):
        if Path(path).exists():
            args.extend(("--ro-bind", path, path))
    args.extend(("--ro-bind", str(CODEX_RUNTIME), str(CODEX_RUNTIME), "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp", "--bind", str(workspace), "/work", "--bind", str(CODEX_HOME), "/codex-home", "--chdir", "/work", "--setenv", "HOME", "/tmp", "--setenv", "CODEX_HOME", "/codex-home", "--setenv", "PATH", str(CODEX_RUNTIME / "node" / "bin"), "--", str(CODEX_NODE), str(CODEX_ENTRYPOINT), "exec", "--ephemeral", "--ignore-user-config", "--ignore-rules", "--skip-git-repo-check", "--sandbox", "read-only", "--model", CODEX_MODEL, "--output-schema", "/work/content-package.schema.json", "--output-last-message", "/work/content-package.json", "--json"))
    return args


def run_request(request: GenerateShortsScriptRequest, *, root: Path = RUNNER_ROOT) -> HostRunnerSuccess:
    """Use only runner-created files and a fixed CLI command for one request."""
    request_id = uuid4().hex
    schema_path, output_path = fixed_paths(request_id, root)
    workspace = schema_path.parent
    workspace.mkdir(mode=0o700, parents=True, exist_ok=False)
    try:
        from tubeforge.providers.content.prompts import CONTENT_ENVELOPE_TEMPLATES
        schema_path.write_text(json.dumps(codex_output_schema(envelope=request.request.prompt_version in CONTENT_ENVELOPE_TEMPLATES, reference=request.request.prompt_version == "m6-content-v8"), sort_keys=True), encoding="utf-8")
        prompt = build_content_prompt(request.request, template_version=request.request.prompt_version, max_chars=60_000)
        from tubeforge.providers.content.youtube_skills import SKILL_TEMPLATES, preflight
        skill_hashes = preflight(template_version=request.request.prompt_version) if request.request.prompt_version in SKILL_TEMPLATES else None
        command = bubblewrap_args(workspace)
        if request.request.prompt_version in CONTENT_ENVELOPE_TEMPLATES:
            from tubeforge.providers.content.output import require_source_excerpts
            require_source_excerpts(request.request)
        consume_invocation(request, root)
        started = time.monotonic()
        try:
            completed = subprocess.run(command, input=prompt.encode(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=TIMEOUT_SECONDS, check=False)
        except subprocess.TimeoutExpired as error:
            raise TimeoutError("Codex invocation exceeded the eight-minute limit") from error
        if completed.returncode:
            raise RuntimeError(f"Codex CLI failed ({completed.returncode}): {cli_failure_detail(completed.stdout, completed.stderr)}")
        if not output_path.is_file() or output_path.stat().st_size > MAX_OUTPUT_BYTES:
            raise ValueError("Codex CLI did not produce a bounded structured package")
        raw = json.loads(output_path.read_text(encoding="utf-8"))
        if request.request.prompt_version in CONTENT_ENVELOPE_TEMPLATES:
            from tubeforge.providers.content.output import unwrap_generation
            raw = unwrap_generation(raw, request=request.request)
        normalized, normalizations = normalize_fallback_visuals(raw)
        package = ContentPackage.model_validate(normalized)
        if normalize_content_request(package.request) != normalize_content_request(request.request):
            raise ValueError("Codex output source packet differs from the immutable request")
        usage: dict[str, object] = {}
        for line in completed.stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict) and isinstance(event.get("usage"), dict):
                usage = event["usage"]
        provenance: dict[str, object] = {"provider": "host-codex-runner", "model": CODEX_MODEL, "generated_at": datetime.now(UTC).isoformat(), "elapsed_seconds": round(time.monotonic() - started, 3)}
        from tubeforge.providers.content.prompts import prompt_evidence
        provenance["invocations"] = [prompt_evidence(prompt)]
        if skill_hashes is not None:
            from tubeforge.providers.content.youtube_skills import select_hook
            try:
                package, provenance["youtube_skills"] = select_hook(package)
            except ProviderValidationError as error:
                raise RejectedContentError(str(error), HostRunnerSuccess(
                    package=package.model_dump(mode="json"), provenance=provenance, usage=usage,
                )) from error
        if normalizations:
            provenance["normalizations"] = normalizations
        return HostRunnerSuccess(package=package.model_dump(mode="json"), provenance=provenance, usage=usage)
    finally:
        # Output is returned through the socket; do not retain source packets or drafts on the host.
        shutil.rmtree(workspace, ignore_errors=True)


def run_research(request: GenerateShortsScriptRequest, *, root: Path = RUNNER_ROOT) -> HostRunnerSuccess:
    """One cached research invocation per exact brief; no script allowance reset."""
    from tubeforge.providers.content.research import ResearchResult, research_prompt
    from tubeforge.domain.contracts import generation_request_key_payload
    material = json.dumps(generation_request_key_payload(request.request), sort_keys=True).encode()
    cache_path = root / "research-cache" / (hashlib.sha256(material).hexdigest() + ".json")
    if cache_path.is_file():
        return HostRunnerSuccess.model_validate_json(cache_path.read_text())
    schema_path, output_path = fixed_paths(uuid4().hex, root)
    workspace = schema_path.parent
    workspace.mkdir(mode=0o700, parents=True, exist_ok=False)
    try:
        schema = ResearchResult.model_json_schema()
        def strict(value):
            if isinstance(value, dict):
                for key in ("default", "minLength", "maxLength"):
                    value.pop(key, None)
                if value.get("type") == "object":
                    value["required"] = list(value["properties"])
                    value["additionalProperties"] = False
                for child in value.values(): strict(child)
            elif isinstance(value, list):
                for child in value: strict(child)
        strict(schema)
        schema_path.write_text(json.dumps(schema))
        command = bubblewrap_args(workspace)
        command.insert(command.index("exec"), "--search")
        prompt = research_prompt(request.request)
        if len(prompt) > 60_000:
            raise ValueError("research brief exceeds prompt limit")
        consume_invocation(request, root)
        started = time.monotonic()
        completed = subprocess.run(command, input=prompt.encode(), stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, timeout=TIMEOUT_SECONDS, check=False)
        if completed.returncode:
            raise RuntimeError(f"Research CLI failed: {cli_failure_detail(completed.stdout, completed.stderr)}")
        if not output_path.is_file() or output_path.stat().st_size > MAX_OUTPUT_BYTES:
            raise ValueError("research output missing or oversized")
        result = ResearchResult.model_validate_json(output_path.read_text())
        usage, searches = {}, 0
        for line in completed.stdout.splitlines():
            try: event = json.loads(line)
            except json.JSONDecodeError: continue
            if isinstance(event, dict):
                if isinstance(event.get("usage"), dict): usage = event["usage"]
                if event.get("type") == "item.completed" and event.get("item", {}).get("type") == "web_search": searches += 1
        if not searches:
            raise ValueError("research did not record any completed web search; refusing unverified citations")
        response = HostRunnerSuccess(package=result.model_dump(mode="json"), usage=usage,
            provenance={"provider": "host-codex-research", "model": CODEX_MODEL,
                        "web_searches": searches, "elapsed_seconds": round(time.monotonic()-started, 3),
                        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest()})
        cache_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = cache_path.with_suffix("." + uuid4().hex + ".tmp")
        temporary.write_text(response.model_dump_json())
        temporary.chmod(0o600)
        os.replace(temporary, cache_path)
        return response
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def inherited_socket() -> socket.socket:
    """Use only systemd's first passed listening FD."""
    if os.environ.get("LISTEN_PID") != str(os.getpid()) or os.environ.get("LISTEN_FDS") != "1":
        raise RuntimeError("runner must be started by its systemd socket unit")
    return socket.socket(fileno=3)


def main() -> None:
    """Serve one socket-activated request at a time; never execute client data."""
    listener = inherited_socket()
    while True:
        connection, _ = listener.accept()
        with connection:
            try:
                request = receive_request(connection)
                if request.operation == "PreflightContentV1":
                    from tubeforge.providers.content.youtube_skills import preflight
                    hashes = preflight()
                    prompt = build_content_prompt(request.request, template_version=request.request.prompt_version, max_chars=60_000)
                    from tubeforge.providers.content.prompts import prompt_evidence
                    evidence = prompt_evidence(prompt)
                    with tempfile.TemporaryDirectory(dir=RUNNER_ROOT) as workspace:
                        bubblewrap_args(Path(workspace))
                    result = HostRunnerSuccess(package={}, provenance={"resource_hashes": hashes, "prompt_sha256": evidence["prompt_sha256"], "preflight": True, "operations": ["ResearchSourcesV1"]})
                elif request.operation == "ResearchSourcesV1":
                    result = run_research(request)
                else:
                    result = run_request(request)
                response = HostRunnerResponse(ok=True, result=result).model_dump_json().encode()
                if len(response) > MAX_RESPONSE_BYTES:
                    raise ValueError("runner response exceeds its socket limit")
                connection.sendall(response)
            except RejectedContentError as error:
                response = HostRunnerResponse(ok=False, result=error.result, failure={
                    "code": "quality_rejected", "message": str(error)[:1000], "invocation_started": True,
                }).model_dump_json().encode()
                connection.sendall(response if len(response) <= MAX_RESPONSE_BYTES else encode_failure("invalid_output", "rejected draft exceeds socket limit"))
            except InsufficientSourcesError as error:
                connection.sendall(encode_failure("insufficient_sources", str(error).removeprefix("insufficient_sources: ")))
            except PermissionError as error:
                connection.sendall(encode_failure("unavailable", str(error)))
            except TimeoutError as error:
                connection.sendall(encode_failure("timeout", str(error)))
            except AllowanceExhaustedError as error:
                connection.sendall(encode_failure("allowance_exhausted", str(error)))
            except Exception as error:
                connection.sendall(encode_failure("invalid_output", str(error), invocation_started=request.operation != "PreflightContentV1" if "request" in locals() else False))


if __name__ == "__main__":
    main()
