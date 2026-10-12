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


STYLE_VERSION = "portrait-storyboard-v10"
SUPPORTED_STYLE_VERSIONS = frozenset({"portrait-storyboard-v9", STYLE_VERSION})
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
        identity = json.dumps({"style": STYLE_VERSION, "request": request.model_dump(mode="json")}, sort_keys=True, ensure_ascii=False)
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
                source_version=f"{STYLE_VERSION}:{PALETTE_ID}:{digest[:16]}",
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


def _wrapped(value: str, *, width: int, lines: int) -> str:
    """Keep text in the safe region while retaining its complete source in the manifest."""
    words = " ".join(value.split())
    wrapped = textwrap.wrap(words, width=width, break_long_words=True, break_on_hyphens=False)
    if len(wrapped) > lines:
        wrapped = wrapped[:lines]
        wrapped[-1] = wrapped[-1].rstrip(" .") + "…"
    return "\n".join(wrapped)


def _render_frame(request: MediaSearchRequest, path: Path, width: int, height: int) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or not _FONT.is_file():
        raise ProviderValidationError("local storyboard graphics require FFmpeg and DejaVu Sans")
    path.parent.mkdir(parents=True, exist_ok=True)
    portrait = height > width
    subject = request.visual_subject or request.queries[0]
    kind = (request.composition + " " + request.visual_type + " " + request.visual_subject).casefold()
    terminal = any(word in kind for word in ("terminal", "code", "cli"))
    heading = subject if terminal else (request.on_screen_text or subject)
    elements = list(request.visual_elements or request.queries[:3])
    if not elements:
        elements = [subject]
    with tempfile.TemporaryDirectory(prefix="tubeforge-storyboard-", dir=path.parent) as temporary_dir:
        temp = Path(temporary_dir)
        if os.name == "nt":
            shutil.copyfile(_FONT, temp / "font.ttf")
        texts = [_wrapped(heading, width=24 if portrait else 38, lines=2), *elements]
        files: list[Path] = []
        for index, value in enumerate(texts):
            text_path = temp / f"field-{index}.txt"
            text_path.write_text(value, encoding="utf-8")
            files.append(text_path)
        scale = 1.0 if portrait else 1.25
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

        filters.append(text_filter(0, size=58 if portrait else 54, x=.10, y=.105, color="0x3fdcee"))
        diagram: list[tuple[float, float, float, float, int]] = []
        if not terminal and ("branch" in kind or "blueprint" in kind or "instance" in kind or "two" in kind) and "checklist" not in kind:
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
            output_lines = elements if request.on_screen_text else elements[1:]
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
        elif ("comparison" in kind or "contrast" in kind) and len(elements) == 3:
            filters.extend([
                box(.14,.26,.72,.28,"0x254669"),box(.16,.28,.68,.24,"0x111d32"),
                box(.19,.30,.62,.08,"0x1c3050"),box(.19,.30,.012,.08,"0x7f6fee"),
                box(.21,.40,.58,.09,"0x1c3050"),box(.21,.40,.012,.09,"0x7f6fee"),
                box(.495,.54,.01,.055,"0x3fdcee"),
                box(.14,.60,.72,.13,"0x1c3050"),box(.14,.60,.012,.13,"0x3fdcee"),
            ])
            diagram=[(.23,.32,.55,.07,0),(.25,.42,.51,.07,1),(.18,.64,.65,.07,2)]
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
            if w < .5 or len(label) > 32:
                size = 30 if portrait else 26
            while True:
                char_limit = max(12, int(width*w/(size*scale*.56)))
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


__all__ = ["LocalMotionGraphicsProvider", "PALETTE_ID", "STYLE_VERSION", "SUPPORTED_STYLE_VERSIONS"]
