"""Reference-derived RGB scene library shared by dashboard and CLI adapters.

All geometry is owned here. Semantic JSON never supplies drawing coordinates.
The geometry ledger validates the fully revealed scene, including hidden text,
before any frame is eligible for encoding.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .icons import badge

from .schema import ShortsTopic

WIDTH, HEIGHT = 1080, 1920
SAFE = (60, 200, 930, 1500)
CAPTION = (60, 1300, 930, 1470)
WHITE, CYAN, MUTED = "#f4f7ff", "#53e0ef", "#a4b3ca"
PANEL, GREEN, AMBER = "#101e32", "#79e8b0", "#ffc46b"


class LayoutError(ValueError):
    def __init__(self, code: str, element: str, detail: str):
        self.issue = {"code": code, "element": element, "detail": detail}
        super().__init__(f"{code}: {element}: {detail}")


FONTS = Path(__file__).with_name("fonts")  # OFL-licensed; licence texts next to the files
CAPTION_SIZE = 96


@lru_cache(maxsize=128)
def font(size: int, mono: bool = False, display: bool = False):
    """Inter ExtraBold for text, Anton for hooks/numbers/captions, DejaVu Mono for terminals."""
    if mono:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", size)
    if display:
        return ImageFont.truetype(str(FONTS / "Anton-Regular.ttf"), size)
    face = ImageFont.truetype(str(FONTS / "Inter-Variable.ttf"), size)
    face.set_variation_by_axes([min(32, max(14, size)), 800])
    return face


def contains(outer, inner):
    return outer[0] <= inner[0] and outer[1] <= inner[1] and outer[2] >= inner[2] and outer[3] >= inner[3]


def intersects(a, b):
    return max(a[0], b[0]) < min(a[2], b[2]) and max(a[1], b[1]) < min(a[3], b[3])


@dataclass(frozen=True)
class Mark:
    key: str
    role: str
    bounds: tuple[float, float, float, float]
    parent: str | None = None
    font_size: int | None = None


class Canvas:
    def __init__(self, image):
        self.image, self.draw, self.marks = image, ImageDraw.Draw(image), []

    def mark(self, mark):
        if not contains(SAFE, mark.bounds):
            raise LayoutError("safe_bounds", mark.key, str(mark.bounds))
        if mark.role not in {"caption", "progress"} and intersects(CAPTION, mark.bounds):
            raise LayoutError("caption_collision", mark.key, str(mark.bounds))
        if mark.parent:
            parent = next(m for m in self.marks if m.key == mark.parent)
            if not contains(parent.bounds, mark.bounds):
                raise LayoutError("parent_bounds", mark.key, str(mark.bounds))
        if mark.role == "box":
            for existing in self.marks:
                if existing.role == "box" and intersects(mark.bounds, existing.bounds):
                    raise LayoutError("box_collision", mark.key, existing.key)
        if mark.font_size is not None:
            for existing in self.marks:
                if existing.font_size is not None and intersects(mark.bounds, existing.bounds):
                    raise LayoutError("text_collision", mark.key, existing.key)
        self.marks.append(mark)

    def box(self, key, bounds, color=PANEL, outline=CYAN):
        self.mark(Mark(key, "box", bounds))
        self.draw.rounded_rectangle(bounds, radius=24, fill=color, outline=outline, width=3)

    def text(self, key, value, center, *, size=64, minimum=40, width=810,
             color=WHITE, mono=False, role="text", parent=None, stroke=0, display=False):
        if not value.strip() or "\n" in value:
            raise LayoutError("invalid_text", key, "requires a nonempty single line")
        while size >= minimum:
            face = font(size, mono, display)
            bounds = self.draw.textbbox(center, value, font=face, anchor="mm", stroke_width=stroke)
            if bounds[2] - bounds[0] <= width:
                break
            size -= 1
        else:
            raise LayoutError("text_overflow", key, f"cannot fit above {minimum}px: {value}")
        self.mark(Mark(key, role, bounds, parent, size))
        self.draw.text(center, value, font=face, anchor="mm", fill=color,
                       stroke_width=stroke, stroke_fill="#080f1f")

    def arrow(self, key, y1, y2):
        self.mark(Mark(key, "arrow", (480, y1, 510, y2)))
        self.draw.line((495, y1, 495, y2 - 12), fill=CYAN, width=6)
        self.draw.polygon(((480, y2 - 18), (510, y2 - 18), (495, y2)), fill=CYAN)


@lru_cache(maxsize=1)
def background():
    # Same restrained cyan/violet RGB glow as the reviewed reference.
    # A smooth glow needs no full-resolution float working buffers.
    # Compute at quarter scale and retain only the final RGB image.
    yy, xx = np.ogrid[:HEIGHT:4, :WIDTH:4]
    yy, xx = yy.astype(np.float32), xx.astype(np.float32)
    glow = np.exp(-((xx - 140) ** 2 + (yy - 900) ** 2) / (2 * 610 ** 2))
    violet = np.exp(-((xx - 930) ** 2 + (yy - 1500) ** 2) / (2 * 750 ** 2))
    rgb = np.stack([8 + glow * 3 + violet * 12, 15 + glow * 14,
                    31 + glow * 22 + violet * 20], axis=-1).astype(np.uint8)
    return Image.fromarray(rgb).resize((WIDTH, HEIGHT), Image.Resampling.BILINEAR)


def caption_groups(caption: str) -> tuple[tuple[str, ...], ...]:
    result, current = [], []
    for word in caption.upper().split():
        if font(CAPTION_SIZE, display=True).getlength(word) + 12 > 850:
            raise LayoutError("caption_token_overflow", "caption", word)
        if current and (len(current) == 3 or font(CAPTION_SIZE, display=True).getlength(" ".join([*current, word])) + 12 > 850):
            result.append(tuple(current))
            current = []
        current.append(word)
    if current:
        result.append(tuple(current))
    return tuple(result)


class SceneRenderer:
    """Event-driven frames: retain one base layer and one caption frame.

    The caller supplies aligned reveal/word events. Repeated event keys return
    the same image without recomposition; memory does not grow with duration.
    """
    def __init__(self, topic: ShortsTopic):
        self.topic = topic
        self.groups = [caption_groups(s.caption) for s in topic.scenes]
        self._base_key = self._frame_key = None
        self._base = self._frame = None

    def compose(self, index: int, revealed: int = 3, grow: float = 1.0, transparent: bool = False):
        """Draw one scene. ``transparent`` omits the background so a motion layer
        can composite it; ``grow`` (0..1) animates the newest big_stat figure."""
        scene = self.topic.scenes[index]
        c = Canvas(Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0)) if transparent else background().copy())
        count = len(self.topic.scenes)
        gap, span = 12, (850 - (count - 1) * 12) / count
        for j in range(count):
            bounds = (70 + j * (span + gap), 212, 70 + j * (span + gap) + span, 219)
            c.mark(Mark(f"progress{j}", "progress", bounds))
            c.draw.rounded_rectangle(bounds, radius=3, fill=CYAN if j <= index else "#29374d")
        kind = scene.template
        dy = 0
        if kind == "hook":
            top, step = 520, 150
            if scene.icon:
                self.icon(c, scene.icon, (495, 380), 220)
                top, step = 620, 135
            for j, line in enumerate(scene.headline):
                c.text(f"headline{j}", line, (495, top + j * step), size=step - 10, minimum=84, display=True,
                       color=CYAN if j == len(scene.headline) - 1 else WHITE)
            self.chips(c, scene.chips, top + step * len(scene.headline) + 20, len(scene.chips))
        elif kind == "cta":
            if scene.icon:
                self.icon(c, scene.icon, (495, 430), 200)
            self.chips(c, scene.chips, 620, revealed)
            # A longer follow request uses two deliberately composed lines.
            words = scene.headline.split()
            lines = [scene.headline] if font(88, display=True).getlength(scene.headline) <= 810 else [
                " ".join(words[:2]), " ".join(words[2:])]
            for j, line in enumerate(lines):
                c.text(f"cta{j}", line, (495, 850 + j * 100), size=88, minimum=60, color=CYAN, display=True)
            c.text("subline", scene.subline, (495, 1120), size=44)
        else:
            if scene.icon:
                self.icon(c, scene.icon, (495, 300), 140)
                dy = 65
            c.text("heading", scene.heading, (495, 355 + dy), size=72, minimum=48)
            if kind == "big_stat":
                values = [(scene.before, scene.before_label), (scene.after, scene.after_label)]
                scale = max(scene.before, scene.after, 1)
                for j, (value, label) in enumerate(values):
                    y = 560 + dy + j * 390
                    if j >= revealed:
                        continue
                    amount = grow if j == revealed - 1 else 1.0
                    shown = value * amount
                    text = f"{shown:.1f}".rstrip("0").rstrip(".") if amount < 1 and value != int(value) else f"{round(shown) if amount < 1 else value:g}"
                    c.text(f"label{j}", label, (495, y - 95), size=44, color=MUTED)
                    c.text(f"number{j}", text + scene.unit, (495, y + 20),
                           size=160, minimum=110, color=AMBER if j == 0 else CYAN, display=True)
                    bounds = (100, y + 120, 890, y + 148)
                    c.mark(Mark(f"bar{j}", "graphic", bounds))
                    c.draw.rounded_rectangle(bounds, radius=12, fill="#26364d")
                    if shown:
                        c.draw.rounded_rectangle((100, y + 120, max(112, 100 + 790 * shown / scale), y + 148),
                                                 radius=10, fill=AMBER if j == 0 else CYAN)
                if revealed > 1:
                    c.arrow("change", 740 + dy, 790 + dy)
            elif kind in {"flow", "checklist", "before_after"}:
                items = scene.nodes if kind == "flow" else scene.items if kind == "checklist" else (scene.before, scene.after)
                # Fixed slots for the full set, centred in the content band, so
                # a reveal never shifts neighbours and the frame is used well.
                height, gap = 170, 76
                block = len(items) * height + (len(items) - 1) * gap
                top = round(820 - block / 2)
                for j, value in enumerate(items):
                    y = top + j * (height + gap)
                    if j >= revealed:  # unrevealed slots stay empty; motion animates each one in
                        continue
                    key = f"item{j}"
                    c.box(key, (90, y, 900, y + height), outline=CYAN if j else "#536b87")
                    label = f"✓  {value}" if kind == "checklist" else value
                    c.text(key + "text", label, (495, y + height // 2), size=66, minimum=40, width=760, parent=key)
                    if kind != "checklist" and j:
                        c.arrow(f"arrow{j}", y - gap + 10, y - 10)
            elif kind == "terminal":
                c.box("terminal", (80, 510 + dy, 910, 1160 + dy), color="#0a121e", outline="#536b87")
                c.text("evidence", scene.evidence_label, (495, 565 + dy), size=28, minimum=28,
                       color=MUTED, parent="terminal")
                for j, line in enumerate(scene.lines):
                    if j >= revealed:
                        continue
                    prefix = "$ " if line.kind == "command" else ""
                    c.text(f"line{j}", prefix + line.text, (495, 700 + dy + j * 160), size=48,
                           minimum=40, width=770, mono=True, parent="terminal",
                           color=GREEN if line.kind == "output" else WHITE)
        sources = {source.source_id: source for source in self.topic.sources}
        for j, source_id in enumerate(scene.source_ids):
            c.text(f"source{j}", "Source: " + sources[source_id].name, (495, 1200 + 32 * j),
                   size=26, minimum=26, color=MUTED, role="source")
        return c

    def icon(self, c, name, center, diameter):
        x, y = center
        bounds = (x - diameter / 2, y - diameter / 2, x + diameter / 2, y + diameter / 2)
        c.mark(Mark("icon", "graphic", bounds))
        sprite = badge(name, diameter)
        c.image.alpha_composite(sprite, (round(bounds[0]), round(bounds[1]))) if c.image.mode == "RGBA" else c.image.paste(sprite, (round(bounds[0]), round(bounds[1])), sprite)

    def chips(self, c, labels, y, revealed):
        for j, label in enumerate(labels):
            width = (810 - 20 * (len(labels) - 1)) / len(labels)
            x = 90 + j * (width + 20)
            if j >= revealed:
                continue
            key = f"chip{j}"
            c.box(key, (x, y, x + width, y + 100), color="#183c46")
            c.text(key + "text", label, (x + width / 2, y + 50), size=44, minimum=40,
                   width=width - 24, parent=key)

    def caption(self, c, words, active):
        value = " ".join(words)
        face = font(CAPTION_SIZE, display=True)
        length = face.getlength(value)
        x = 495 - length / 2
        for j, word in enumerate(words):
            width = face.getlength(word)
            c.text(f"caption{j}", word, (x + width / 2, 1385), size=CAPTION_SIZE, minimum=CAPTION_SIZE,
                   width=width + 30, color=CYAN if j == active else WHITE, role="caption", stroke=6, display=True)
            x += width + face.getlength(" ")

    def validate(self):
        reports = []
        for index, scene in enumerate(self.topic.scenes):
            canvas = self.compose(index)
            for group in self.groups[index]:
                # Measure every caption, not only one convenient sample.
                scratch = Canvas(canvas.image.copy())
                self.caption(scratch, group, 0)
            reports.append({"scene_id": scene.scene_id, "template": scene.template,
                            "marks": [asdict(m) for m in canvas.marks],
                            "caption_chunks": self.groups[index]})
        return {"schema_version": "reference-layout-qa-v1", "passed": True, "scenes": reports}

    def frame(self, index, revealed=3, chunk=None, active=0, rails=False):
        key = (index, revealed)
        if key != self._base_key:
            self._base = self.compose(index, revealed).image
            self._base_key = key
            self._frame_key = None
        frame_key = (key, chunk, active, rails)
        if frame_key != self._frame_key:
            canvas = Canvas(self._base.copy())
            if chunk is not None:
                self.caption(canvas, self.groups[index][chunk], active)
            if rails:
                canvas.draw.rectangle(SAFE, outline="#ff477e", width=3)
                canvas.draw.rectangle(CAPTION, outline="#ffc46b", width=3)
            self._frame, self._frame_key = canvas.image, frame_key
        return self._frame
