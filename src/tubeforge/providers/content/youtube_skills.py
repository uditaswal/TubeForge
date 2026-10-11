"""Bounded wheel-shipped content instructions and reviewed local tools."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from pathlib import Path

from tubeforge.core.errors import ProviderValidationError

SKILL_TEMPLATE = "m6-content-v6"
SKILL_TEMPLATES = {"m6-content-v5", SKILL_TEMPLATE}
DEFAULT_VOICE = "Clear, practical and conversational. Address the viewer directly; use complete sentences, explain unfamiliar terms, avoid hype, unsupported claims and invented personal experience."
RESOURCES = {
    "yt-script": ("SKILL.md", "automation.md", "hooks.json", "hookscore.py"),
    "yt-package": ("SKILL.md", "title.py"),
    "yt-seo": ("SKILL.md",),
}


def resource_root() -> Path:
    packaged = Path(__file__).resolve().parents[2] / "content_skills"
    if packaged.is_dir():
        return packaged
    # Editable checkout only; host wheels must contain their own resources.
    return Path(__file__).resolve().parents[4] / ".agents" / "skills"


def load_resources(root: Path | None = None) -> tuple[str, dict[str, str]]:
    root = root or resource_root()
    blocks, hashes = [], {}
    try:
        for skill, files in RESOURCES.items():
            for filename in files:
                path = root / skill / filename
                data = path.read_bytes()
                if not data or len(data) > 40_000:
                    raise ValueError(f"invalid resource size: {skill}/{filename}")
                hashes[f"{skill}/{filename}"] = hashlib.sha256(data).hexdigest()
                # Include scorer logic as well as formulas in every invocation;
                # tools run in application Python, outside the Codex namespace.
                blocks.append(f"RESOURCE {skill}/{filename}\n{data.decode('utf-8')}")
        json.loads((root / "yt-script" / "hooks.json").read_text())
    except (OSError, UnicodeError, ValueError) as error:
        raise ProviderValidationError(f"YouTube skill preflight failed: {error}") from error
    return "\n\n".join(blocks), hashes


def _tool(root: Path, skill: str, filename: str):
    spec = importlib.util.spec_from_file_location(f"tubeforge_{skill.replace('-', '_')}", root / skill / filename)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot load {skill}/{filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def preflight(root: Path | None = None) -> dict[str, str]:
    root = root or resource_root()
    _, hashes = load_resources(root)
    try:
        hook = _tool(root, "yt-script", "hookscore.py")
        title = _tool(root, "yt-package", "title.py")
        hook.score("Why should you check your supplied script before rendering?")
        title.check("TubeForge review", "CHECK FIRST")
    except Exception as error:
        raise ProviderValidationError(f"YouTube scoring tool preflight failed: {error}") from error
    return hashes


def evaluate(package, root: Path | None = None) -> dict[str, object]:
    """Execute supplied tools, preserve the chosen narration, expose alternatives."""
    root = root or resource_root()
    hashes = preflight(root)
    try:
        candidates = package.hook_options
        if len(candidates) != 5 or len(set(candidates)) != 5 or any(not text.strip() or len(text) > 500 for text in candidates):
            raise ValueError("expected five distinct hook_options")
        opening = re.split(r"(?<=[.!?…])\s+", package.script_sections[0].narration.strip(), maxsplit=1)[0]
        if opening not in candidates:
            raise ValueError("opening sentence must exactly match one hook candidate")
        hook = _tool(root, "yt-script", "hookscore.py")
        title = _tool(root, "yt-package", "title.py")
        hooks = []
        for text in candidates:
            parts, verdict, formula, _ = hook.score(text)
            hooks.append({"hook": text, "properties": parts, "verdict": verdict, "band": hook.band(verdict), "formula": formula, "selected": text == opening})
        hooks.sort(key=lambda row: -row["verdict"])
        thumb = package.thumbnail_brief.text_options[0]
        if len(title.words(thumb)) > 3:
            raise ValueError("thumbnail text must contain at most three words")
        if len(package.metadata.title_options) != 10 or len(set(package.metadata.title_options)) != 10:
            raise ValueError("expected ten title_options")
        reports = [title.check(text, thumb) for text in package.metadata.title_options]
        if any(not text.strip() or len(text) > 100 for text in package.metadata.title_options):
            raise ValueError("titles must be nonblank and within 100 characters")
        if not package.metadata.description.strip() or len(package.metadata.tags) > 15:
            raise ValueError("description must be nonblank and tags limited to fifteen")
        if any(not scene.on_screen_text or not scene.on_screen_text.strip() for scene in package.scene_plans):
            raise ValueError("every scene requires on_screen_text")
        return {"skills": list(RESOURCES), "resource_hashes": hashes, "hooks": hooks, "titles": reports,
                "selected_hook": opening, "channel_identity": package.request.channel_identity,
                "voice_profile": package.request.channel_voice_profile, "tools_executed": ["hookscore.py", "title.py"],
                "notice": "Heuristic review signals; not predictions of views. Selected content still requires source and creative review."}
    except Exception as error:
        raise ProviderValidationError(f"YouTube skill acceptance failed: {error}") from error


def voice_for(config, channel: str | None = None) -> tuple[str, str]:
    identity = channel or config.default_channel_identity
    profile = config.voice_profiles.get(identity, config.voice_profiles.get("default", DEFAULT_VOICE))
    if not isinstance(profile, str) or not profile.strip() or len(profile) > 4000:
        raise ProviderValidationError(f"Invalid channel voice profile: {identity}")
    return identity, profile


def select_hook(package):
    """Score first, select within the strongest suitable candidates, then review."""
    report = evaluate(package)
    limit = 18 if package.request.aspect_ratio == "9:16" else 24
    eligible = [row for row in report['hooks'] if len(re.findall(r"\b\w+\b", row['hook'])) <= limit and re.search(r"[.!?…]$", row['hook'].strip())]
    if not eligible:
        raise ProviderValidationError("No hook candidate fits the selected format's immediate opening")
    finalists = eligible[:2]
    selected = next((row for row in finalists if row['selected']), finalists[0])
    original = report['selected_hook']
    if selected['hook'] != original:
        section = package.script_sections[0]
        narration = selected['hook'] + section.narration.strip()[len(original):]
        section = section.model_copy(update={'narration': narration})
        package = package.model_copy(update={'script_sections': (section, *package.script_sections[1:])})
        report = evaluate(package)
    report['hook_selection'] = {'model_choice': original, 'selected': selected['hook'], 'finalists': [row['hook'] for row in finalists], 'rule': 'Preserve model suitability choice among the two highest-scoring format-compatible hooks; otherwise select the highest.'}
    return package, report
