"""Scene-specific explanatory frames rendered from the approved storyboard."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import textwrap
from datetime import UTC, datetime
from pathlib import Path

from tubeforge.core.config import FakeProviderConfig
from tubeforge.core.errors import ProviderValidationError
from tubeforge.domain.contracts import AssetCandidate, MediaSearchRequest


STYLE_VERSION = "portrait-storyboard-v12"
NEW_LAYOUT_STYLE_VERSION = "portrait-storyboard-v13"
SUPPORTED_STYLE_VERSIONS = frozenset({"portrait-storyboard-v9", "portrait-storyboard-v10", "portrait-storyboard-v11", STYLE_VERSION, NEW_LAYOUT_STYLE_VERSION})
PALETTE_ID = "midnight-cyan-violet-amber"
_FONT = next(
    (path for path in (
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    ) if path.is_file()),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
)


class LocalMotionGraphicsProvider:
    """Turn a scene's subject, display text and visual purpose into a reviewable frame.

    The approved scene fields determine every visible word. FFmpeg supplies
    typography and geometry; no model, network call or unapproved media enters
    the render. Source frames are stable under the same storyboard fields.
    """

    def __init__(self, settings: FakeProviderConfig) -> None:
        self.settings = settings
        self.calls = 0

    def search(self, request: MediaSearchRequest) -> list[AssetCandidate]:
        self.calls += 1
        if not (request.visual_subject.strip() or request.on_screen_text.strip() or request.queries):
            raise ProviderValidationError(f"scene {request.scene_id} has no visual subject")
        style_version = storyboard_style_for(request.visual_type)
        identity = json.dumps({"style": style_version, "request": request.model_dump(mode="json")}, sort_keys=True, ensure_ascii=False)
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        portrait = request.orientation == "portrait"
        width, height = (1080, 1920) if portrait else (1920, 1080)
        path = self.settings.artifact_root / "storyboard-graphics" / f"{digest[:24]}-{width}x{height}.png"
        checksum_path = path.with_suffix(".sha256")
        try:
            current_hash = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
            expected_hash = checksum_path.read_text(encoding="ascii").strip() if checksum_path.is_file() else None
        except (OSError, UnicodeError):
            current_hash = expected_hash = None
        if not current_hash or current_hash != expected_hash:
            _render_frame(request, path, width, height)
            checksum = hashlib.sha256(path.read_bytes()).hexdigest()
            descriptor, temporary_name = tempfile.mkstemp(prefix="storyboard-hash-", suffix=".part", dir=path.parent)
            temporary_checksum = Path(temporary_name)
            try:
                with os.fdopen(descriptor, "w", encoding="ascii") as stream:
                    stream.write(checksum + "\n")
                os.replace(temporary_checksum, checksum_path)
            finally:
                temporary_checksum.unlink(missing_ok=True)
        return [
            AssetCandidate(
                provider_asset_id=f"local-storyboard-{digest[:20]}",
                source_url=f"https://example.invalid/local-storyboard/{digest[:16]}.png",
                download_url=f"https://example.invalid/local-storyboard/{digest[:16]}.png",
                source_version=f"{style_version}:{PALETTE_ID}:{digest[:16]}",
                local_path=str(path),
                media_type="image",
                width=width,
                height=height,
                author="TubeForge local storyboard graphics",
                license_name=self.settings.media_license,
                attribution_text=f"TubeForge {PALETTE_ID} storyboard frame",
                retrieved_at=datetime.now(UTC),
            )
        ]


def storyboard_style_for(visual_type: str) -> str:
    """Keep existing layout bytes/cache identities stable as new layouts arrive."""
    return NEW_LAYOUT_STYLE_VERSION if visual_type in {"timeline", "source_card"} else STYLE_VERSION


def _fit_heading(value: str, *, width: int, scale: float, base_size: int, lines: int) -> tuple[str, int]:
    """Fit the complete approved heading in its safe region without ellipsis."""
    words = " ".join(value.split())
    for size in range(base_size, 33, -2):
        char_limit = max(12, int(width * .80 / (size * scale * .56)))
        wrapped = textwrap.wrap(words, width=char_limit, break_long_words=True, break_on_hyphens=False)
        if len(wrapped) <= lines:
            return "\n".join(wrapped), size
    raise ProviderValidationError("scene heading is too long for the safe title region")


def _terminal_outputs(command: str, elements: list[str]) -> list[str]:
    """Avoid repeating a command that is also the first display element."""
    if elements and " ".join(elements[0].split()) == " ".join(command.split()):
        return elements[1:]
    return elements


def _render_frame(request: MediaSearchRequest, path: Path, width: int, height: int) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or not _FONT.is_file():
        raise ProviderValidationError("local storyboard graphics require FFmpeg and DejaVu Sans")
    path.parent.mkdir(parents=True, exist_ok=True)
    portrait = height > width
    subject = request.visual_subject or request.queries[0]
    kind = (request.composition + " " + request.visual_type + " " + request.visual_subject).casefold()
    explicit_layout = request.visual_type if request.visual_type in {"terminal", "flow_diagram", "comparison", "timeline", "source_card"} else None
    terminal = explicit_layout == "terminal" or (explicit_layout is None and any(word in kind for word in ("terminal", "code", "cli")))
    heading = subject if terminal else (request.on_screen_text or subject)
    elements = list(request.visual_elements or request.queries[:3])
    if not elements:
        elements = [subject]
    with tempfile.TemporaryDirectory(prefix="tubeforge-storyboard-", dir=path.parent) as temporary_dir:
        temp = Path(temporary_dir)
        if os.name == "nt":
            shutil.copyfile(_FONT, temp / "font.ttf")
        scale = 1.0 if portrait else 1.25
        heading_text, heading_size = _fit_heading(
            heading, width=width, scale=scale, base_size=58 if portrait else 54,
            lines=3 if portrait else 2,
        )
        texts = [heading_text, *elements]
        files: list[Path] = []
        for index, value in enumerate(texts):
            text_path = temp / f"field-{index}.txt"
            text_path.write_text(value, encoding="utf-8")
            files.append(text_path)
        filters = [
            f"drawbox=x={round(width*.10)}:y={round(height*.055)}:w={round(width*.18)}:h={max(6,round(9*scale))}:color=0x3fdcee:t=fill",
        ]
        def box(x: float, y: float, w: float, h: float, color: str) -> str:
            return (f"drawbox=x={round(width*x)}:y={round(height*y)}:"
                    f"w={round(width*w)}:h={round(height*h)}:color={color}:t=fill")
        def text_filter(index: int, *, size: int, x: float, y: float, color: str = "white") -> str:
            font = "font.ttf" if os.name == "nt" else str(_FONT)
            source = files[index].name if os.name == "nt" else str(files[index])
            return (f"drawtext=fontfile={font}:textfile={source}:expansion=none:"
                    f"fontcolor={color}:fontsize={max(20,round(size*scale))}:line_spacing={max(5,round(10*scale))}:"
                    f"x={round(width*x)}:y={round(height*y)}")

        filters.append(text_filter(0, size=heading_size, x=.10, y=.085, color="0x3fdcee"))
        diagram: list[tuple[float, float, float, float, int]] = []
        if explicit_layout == "flow_diagram" or (explicit_layout is None and not terminal and ("branch" in kind or "blueprint" in kind or "instance" in kind or "two" in kind) and "checklist" not in kind):
            offset = 1 if len(elements) >= 4 else 0
            filters.extend([box(.25,.28,.50,.12,"0x1c3050"),box(.495,.40,.01,.10,"0x3fdcee"),
                            box(.28,.495,.44,.006,"0x3fdcee"),box(.28,.495,.008,.06,"0x3fdcee"),box(.712,.495,.008,.06,"0x3fdcee"),
                            box(.10,.55,.38,.14,"0x27385e"),box(.52,.55,.38,.14,"0x27385e")])
            diagram=[(.29,.315,.43,.10,offset),(.13,.595,.33,.09,offset+1),(.55,.595,.33,.09,offset+2)]
            if offset:
                filters.append(box(.25,.205,.50,.055,"0x1c3050"))
                diagram.append((.29,.21,.45,.05,0))
        elif terminal:
            command = " ".join((request.on_screen_text or elements[0]).split())
            if not command:
                raise ProviderValidationError(f"scene {request.scene_id} has no terminal command")
            command_size = 49 if portrait else 43
            command_width = .67
            while command_size >= 30:
                chars = max(12, int(width * command_width / (command_size * scale * .60)))
                command_lines = textwrap.wrap(command, width=chars, break_long_words=False, break_on_hyphens=False)
                if len(command_lines) <= 2 and all(len(line) <= chars for line in command_lines):
                    break
                command_size -= 2
            if command_size < 30:
                raise ProviderValidationError(f"scene {request.scene_id} terminal command is too long to read")
            command_file = temp / "terminal-command.txt"
            command_file.write_text("\n".join(command_lines), encoding="utf-8")
            command_index = len(files)
            files.append(command_file)
            filters.extend([box(.08,.25,.84,.47,"0x111d32"), box(.08,.25,.84,.04,"0x304660")])
            for x,color in ((.13,"0xfb9d78"),(.16,"0xfbbf24"),(.19,"0x3fdcee")):
                filters.append(box(x,.263,.015,.009,color))
            filters.append(text_filter(command_index,size=command_size,x=.16,y=.335,color="0x3fdcee"))
            output_lines = _terminal_outputs(command, elements)
            output_y = .46 if len(command_lines) == 1 else .51
            for i, output in enumerate(output_lines[:3]):
                output = " ".join(output.split())
                size = 36 if portrait else 31
                while size >= 25:
                    chars = max(12, int(width * .68 / (size * scale * .57)))
                    if len(output) <= chars:
                        break
                    size -= 2
                if size < 25:
                    raise ProviderValidationError(f"scene {request.scene_id} terminal output is too long to read")
                output_file = temp / f"terminal-output-{i}.txt"
                output_file.write_text(output, encoding="utf-8")
                output_index = len(files)
                files.append(output_file)
                filters.append(text_filter(output_index,size=size,x=.16,y=output_y+i*.07,color="0xf3f6fa"))
        elif (explicit_layout == "comparison" or (explicit_layout is None and ("comparison" in kind or "contrast" in kind))) and len(elements) == 3:
            filters.extend([
                box(.14,.26,.72,.28,"0x254669"),box(.16,.28,.68,.24,"0x111d32"),
                box(.19,.30,.62,.08,"0x1c3050"),box(.19,.30,.012,.08,"0x7f6fee"),
                box(.21,.40,.58,.09,"0x1c3050"),box(.21,.40,.012,.09,"0x7f6fee"),
                box(.495,.54,.01,.055,"0x3fdcee"),
                box(.14,.60,.72,.13,"0x1c3050"),box(.14,.60,.012,.13,"0x3fdcee"),
            ])
            diagram=[(.23,.32,.55,.07,0),(.25,.42,.51,.07,1),(.18,.64,.65,.07,2)]
        elif explicit_layout == "timeline":
            filters.extend([
                box(.205,.275,.008,.38,"0x3fdcee"),
                box(.18,.29,.055,.03,"0x7f6fee"),
                box(.18,.46,.055,.03,"0x7f6fee"),
                box(.18,.63,.055,.03,"0x7f6fee"),
            ])
            for y in (.27,.44,.61):
                filters.extend([box(.27,y,.62,.11,"0x1c3050"),box(.27,y,.012,.11,"0x3fdcee")])
            diagram=[(.31,.292,.54,.075,0),(.31,.462,.54,.075,1),(.31,.632,.54,.075,2)]
        elif explicit_layout == "source_card":
            filters.extend([
                box(.12,.265,.76,.10,"0x27385e"),box(.12,.265,.012,.10,"0x7f6fee"),
                box(.12,.39,.76,.20,"0x1c3050"),box(.12,.39,.012,.20,"0x3fdcee"),
                box(.12,.615,.76,.10,"0x254669"),box(.12,.615,.012,.10,"0xfbbf24"),
            ])
            diagram=[(.16,.286,.68,.06,0),(.16,.435,.68,.11,1),(.16,.636,.68,.06,2)]
        elif ("package" in kind or "cutaway" in kind or "layer" in kind or "stack" in kind) and "split" not in kind:
            filters.extend([box(.13,.26,.74,.47,"0x254669"),box(.15,.28,.70,.43,"0x111d32")])
            for i in range(min(len(elements),4)):
                x=.18+(i%2)*.33; y=.33+(i//2)*.16
                filters.extend([box(x,y,.30,.13,"0x1c3050"),box(x,y,.012,.13,"0x7f6fee")])
                diagram.append((x+.03,y+.025,.26,.10,i))
        elif "checklist" in kind or "step" in kind:
            for i in range(min(len(elements),4)):
                y=.27+i*.13
                filters.extend([box(.13,y,.74,.10,"0x1c3050"),box(.13,y,.04,.10,"0x7f6fee")])
                diagram.append((.20,y+.025,.60,.07,i))
        else:
            for i in range(min(len(elements),3)):
                y=.28+i*.16
                filters.extend([box(.13,y,.74,.12,"0x1c3050"),box(.13,y,.012,.12,"0x3fdcee")])
                if i<2: filters.append(box(.495,y+.12,.01,.04,"0x3fdcee"))
                diagram.append((.18,y+.035,.65,.07,i))
        for x,y,w,h,index in diagram:
            label = " ".join(elements[index].split())
            size = 39 if portrait else 31
            if explicit_layout in {"timeline", "source_card"}:
                size = 44 if portrait else 36
            elif w < .5 or len(label) > 32:
                size = 30 if portrait else 26
            while True:
                # Uppercase labels and technical identifiers are wider than
                # the average glyph; leave a deliberate horizontal margin.
                char_limit = max(12, int(width*w/(size*scale*.68)))
                line_limit = min(4, max(1, int(height*h/(size*scale*1.4))))
                wrapped = textwrap.wrap(label, width=char_limit, break_long_words=True, break_on_hyphens=False)
                if len(wrapped) <= line_limit or size <= 20:
                    break
                size -= 2
            if len(wrapped) > line_limit:
                raise ProviderValidationError(f"scene {request.scene_id} visual element cannot fit: {label[:50]}")
            files[index+1].write_text("\n".join(wrapped), encoding="utf-8")
            filters.append(text_filter(index+1,size=size,x=x,y=y))
        output = temp / "frame.png"
        result = subprocess.run(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-f", "lavfi", "-i",
             f"color=c=0x081123:s={width}x{height}:r=1:d=1", "-vf", ",".join(filters),
             "-frames:v", "1", "-threads", "2", "-y", str(output)],
            capture_output=True, text=True, timeout=60, check=False, cwd=temp,
        )
        if result.returncode or not output.is_file() or output.stat().st_size == 0:
            raise ProviderValidationError(f"local storyboard frame failed: {result.stderr[-500:]}")
        os.replace(output, path)


__all__ = ["LocalMotionGraphicsProvider", "PALETTE_ID", "STYLE_VERSION", "NEW_LAYOUT_STYLE_VERSION", "SUPPORTED_STYLE_VERSIONS", "storyboard_style_for"]
