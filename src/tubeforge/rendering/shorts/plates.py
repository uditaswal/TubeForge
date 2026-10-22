"""Real-imagery plates for reference Shorts: Pixabay B-roll, source screenshots and typed code.

Preparation (network, browser) happens once per job before voice generation and writes
``plates/manifest.json``; rendering only reads local files. Every scene falls back to the
code-drawn template when its plate is missing, so a plate failure never fails a job.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .schema import CodeVisual, ShortsTopic, SourceVisual, StockVisual

WIDTH, HEIGHT = 1080, 1920
CARD = (90, 500, 900, 1170)            # visual zone of card scenes (inside SAFE, above the caption band)
STOCK_SIZE = (540, 960)                # decoded at half size; the blur hides the 2x upscale
NAVY = (8, 15, 31)
MANIFEST = "plates/manifest.json"


def load_manifest(directory: Path) -> dict:
    path = directory / MANIFEST
    return json.loads(path.read_text()) if path.is_file() else {"scenes": {}}


def card_indices(topic: ShortsTopic, manifest: dict) -> frozenset[int]:
    """Scenes whose body is replaced by a card: typed code always, screenshots only when captured."""
    result = set()
    for index, scene in enumerate(topic.scenes):
        visual = scene.visual
        entry = manifest.get("scenes", {}).get(str(index), {})
        if isinstance(visual, CodeVisual) or (isinstance(visual, SourceVisual) and entry.get("kind") == "source" and entry.get("file")):
            result.add(index)
    return frozenset(result)


# ---------------------------------------------------------------------------- stock B-roll
class StockStream:
    """Sequential RGB frames of a stock clip (looped, centre-cropped to 9:16) via one ffmpeg pipe."""

    def __init__(self, path: Path, seconds: float, *, ffmpeg: str = "ffmpeg") -> None:
        w, h = STOCK_SIZE
        loop = ["-stream_loop", "-1"] if path.suffix.lower() in {".mp4", ".webm"} else ["-loop", "1"]
        self.process = subprocess.Popen(
            [ffmpeg, "-v", "error", *loop, "-i", str(path), "-an", "-t", f"{seconds + 1:.2f}", "-vf",
             f"fps=30,scale=-2:{h},crop={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=1 << 22)  # buffered: read(n) returns whole frames
        self.size, self.frame_no, self.last = (w, h), -1, None

    def frame(self, number: int) -> Image.Image | None:
        while self.frame_no < number:
            raw = self.process.stdout.read(self.size[0] * self.size[1] * 3)
            if len(raw) < self.size[0] * self.size[1] * 3:
                break  # clip shorter than the scene (should not happen with looping): hold the last frame
            self.last, self.frame_no = raw, self.frame_no + 1
        return Image.frombytes("RGB", self.size, self.last) if self.last else None

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait()
        self.process.stdout.close()


def dim_background(frame: Image.Image, strength: float = .58) -> Image.Image:
    """Soften, darken and navy-tint stock footage so the foreground text stays readable."""
    frame = frame.filter(ImageFilter.GaussianBlur(5)).resize((WIDTH, HEIGHT), Image.Resampling.BILINEAR)
    array = np.asarray(frame, np.float32) * (1 - strength) + np.array(NAVY, np.float32) * strength
    gradient = np.linspace(.78, 1.0, HEIGHT, dtype=np.float32)[:, None, None]  # darker towards the top header
    return Image.fromarray(np.clip(array * gradient, 0, 255).astype(np.uint8))


# ---------------------------------------------------------------------------- cards
def rounded(image: Image.Image, radius: int = 28) -> Image.Image:
    mask = Image.new("L", image.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, *image.size), radius=radius, fill=255)
    out = image.convert("RGBA")
    out.putalpha(mask)
    return out


def with_shadow(card: Image.Image, pad: int = 28) -> Image.Image:
    layer = Image.new("RGBA", (card.width + 2 * pad, card.height + 2 * pad), (0, 0, 0, 0))
    shadow = Image.new("RGBA", card.size, (0, 0, 0, 170))
    shadow.putalpha(card.getchannel("A").point(lambda v: v * 170 // 255))
    layer.alpha_composite(shadow, (pad, pad + 10))
    layer = layer.filter(ImageFilter.GaussianBlur(14))
    layer.alpha_composite(card, (pad, pad))
    return layer


def source_card(plate: Path, highlight: Path | None, progress: float) -> Image.Image:
    """The captured paragraph with a marker highlight sweeping left to right as the claim is spoken."""
    base = Image.open(plate).convert("RGB")
    if highlight is not None and progress > 0:
        marked = Image.open(highlight).convert("RGB")
        sweep = Image.new("L", base.size, 0)
        ImageDraw.Draw(sweep).rectangle((0, 0, round(base.width * min(1.0, progress)), base.height), fill=255)
        base = Image.composite(marked, base, sweep)
    return with_shadow(rounded(base))


def _token_colors():
    from pygments.token import Comment, Keyword, Name, Number, Operator, String
    return [(Comment, "#6b7a90"), (Keyword, "#ff7ab6"), (String, "#a6e37a"), (Number, "#ffc46b"),
            (Name.Function, "#6bd6ff"), (Name.Class, "#6bd6ff"), (Name.Builtin, "#6bd6ff"), (Operator, "#ffd479")]


def code_card(visual: CodeVisual, typed: int | None = None) -> Image.Image:
    """Syntax-highlighted card; ``typed`` limits the visible characters for the typing animation."""
    from pygments import lex
    from pygments.lexers import get_lexer_by_name
    from pygments.token import Token
    palette = _token_colors()
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", 40)
    label_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 26)
    advance, line_height = font.getlength("M"), 66
    width = CARD[2] - CARD[0]
    height = min(CARD[3] - CARD[1], 150 + line_height * len(visual.lines))  # fit the snippet; the card stays centred
    card = Image.new("RGB", (width, height), "#0a121e")
    draw = ImageDraw.Draw(card)
    draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=28, outline="#536b87", width=3)
    for i, color in enumerate(("#ff5f56", "#ffbd2e", "#27c93f")):
        draw.ellipse((28 + i * 38, 26, 52 + i * 38, 50), fill=color)
    draw.text((width - 28, 38), visual.language.upper(), font=label_font, fill="#6b7a90", anchor="rm")
    lexer = get_lexer_by_name("text" if visual.language == "text" else visual.language, stripnl=False)
    top = 110
    remaining = typed if typed is not None else 10 ** 9
    for row, line in enumerate(visual.lines):
        x = 36
        for token_type, text in lex(line, lexer):
            if text.endswith("\n"):
                text = text[:-1]
            if not text:
                continue
            shown = text[:max(0, remaining)]
            color = next((c for kind, c in palette if token_type in kind), "#f4f8ff")
            if shown:
                draw.text((x, top + row * line_height), shown, font=font, fill=color)
            x += advance * len(text)
            remaining -= len(text)
        remaining -= 1  # the implied newline
    return with_shadow(rounded(card))


def code_length(visual: CodeVisual) -> int:
    return sum(len(line) + 1 for line in visual.lines)


@dataclass
class Plates:
    topic: ShortsTopic
    directory: Path
    manifest: dict
    ffmpeg: str = "ffmpeg"

    def __post_init__(self) -> None:
        self.stream: StockStream | None = None
        self.stream_index: int | None = None
        self._cards: dict[tuple, Image.Image] = {}

    def entry(self, index: int) -> dict:
        return self.manifest.get("scenes", {}).get(str(index), {})

    def background(self, index: int, scene_t: float, scene_dur: float) -> Image.Image | None:
        """Dimmed stock frame for the scene, or None to keep the ambient glow."""
        entry = self.entry(index)
        if entry.get("kind") != "stock" or not entry.get("file"):
            if self.stream_index is not None:
                self.release()
            return None
        if self.stream_index != index:
            self.release()
            self.stream = StockStream(self.directory / entry["file"], scene_dur + .5, ffmpeg=self.ffmpeg)
            self.stream_index = index
        frame = self.stream.frame(round(scene_t * 30))
        return dim_background(frame) if frame is not None else None

    def card(self, index: int, scene_t: float, scene_dur: float, since_reveal: float | None) -> Image.Image | None:
        visual = self.topic.scenes[index].visual
        if isinstance(visual, CodeVisual):
            total = code_length(visual)
            typed = min(total, round(total * min(1.0, scene_t / min(2.4, max(.8, scene_dur * .55)))))
            key = ("code", index, typed)
            if key not in self._cards:
                self._cards = {k: v for k, v in self._cards.items() if k[1] == index}
                self._cards[key] = code_card(visual, typed)
            return self._cards[key]
        if isinstance(visual, SourceVisual):
            entry = self.entry(index)
            if not entry.get("file"):
                return None
            progress = 0.0 if since_reveal is None else min(1.0, since_reveal / .5)
            key = ("source", index, round(progress * 20))
            if key not in self._cards:
                self._cards = {k: v for k, v in self._cards.items() if k[1] == index}
                highlight = self.directory / entry["highlight"] if entry.get("highlight") else None
                self._cards[key] = source_card(self.directory / entry["file"], highlight, progress)
            return self._cards[key]
        return None

    def release(self) -> None:
        if self.stream is not None:
            self.stream.close()
        self.stream, self.stream_index = None, None
