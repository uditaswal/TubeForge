"""Deterministic portrait editor animation; scene time is independent of encode FPS.

A library primitive only: callers must bind its timing and content to an accepted
scene contract before using it in a production job.
"""
from dataclasses import dataclass
from functools import cached_property
import math

from PIL import Image, ImageDraw, ImageFont
from pygments import lex
from pygments.lexers import get_lexer_by_name
from pygments.token import Comment, Keyword, Name, Number, Operator, String

VERSION = "portrait-editor-v2"
PALETTE = ((Comment, "#8799b0"), (Keyword, "#cf91ed"), (String, "#a4dfa0"),
           (Number, "#ffc66d"), (Name.Function, "#7ed4fa"), (Operator, "#b8cbde"))


@dataclass(frozen=True)
class EditorScene:
    lines: tuple[str, ...]
    language: str = "python"
    filename: str = "example.py"
    start: float = .4
    typing_seconds: float = 3.0
    hold_seconds: float = 2.0
    # Scene-local intervals derived by the caller from accepted word anchors.
    # Empty means explicitly synthetic proportional timing, never measured speech.
    line_windows: tuple[tuple[float, float], ...] = ()

    def __post_init__(self):
        if not self.lines or len(self.lines) > 6:
            raise ValueError("editor needs one to six lines")
        if any(len(line) > 30 or any(ord(char) < 32 for char in line) for line in self.lines):
            raise ValueError("use explicit lines of at most 30 characters without tabs")
        if not self.filename or len(self.filename) > 28:
            raise ValueError("filename must contain 1–28 characters")
        if not all(math.isfinite(v) for v in (self.start, self.typing_seconds, self.hold_seconds)):
            raise ValueError("timing must be finite")
        if self.start < 0 or self.typing_seconds <= 0 or self.hold_seconds < 1:
            raise ValueError("typing must be positive and finished text must hold at least one second")
        if self.line_windows:
            if len(self.line_windows) != len(self.lines):
                raise ValueError("one reveal window is required per line")
            previous = self.start
            for begin, end in self.line_windows:
                if not all(math.isfinite(v) for v in (begin, end)) or begin < previous or end <= begin:
                    raise ValueError("line windows must be finite, ordered and nonoverlapping")
                previous = end
            if previous > self.start + self.typing_seconds:
                raise ValueError("line windows must finish before the reading hold")
        get_lexer_by_name(self.language)

    @property
    def duration(self):
        return self.start + self.typing_seconds + self.hold_seconds

    @cached_property
    def text(self):
        return "\n".join(self.lines)

    def count(self, seconds: float) -> int:
        if not math.isfinite(seconds):
            raise ValueError("scene time must be finite")
        if self.line_windows:
            offset = 0
            for line, (begin, end) in zip(self.lines, self.line_windows, strict=True):
                if seconds < begin:
                    return max(0, offset - 1)
                if seconds < end:
                    return offset + math.floor(len(line) * (seconds - begin) / (end - begin))
                offset += len(line) + 1
            return len(self.text)
        return math.floor(len(self.text) * min(1, max(0, (seconds - self.start) / self.typing_seconds)))

    def cursor(self, seconds: float) -> tuple[int, int]:
        visible = self.text[:self.count(seconds)]
        return visible.count("\n"), len(visible.rsplit("\n", 1)[-1])


class EditorRenderer:
    """Cache static chrome and token layout, drawing only the revealed text per frame."""
    def __init__(self, scene: EditorScene):
        self.scene = scene
        self.font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 42)
        self.small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 25)
        self.advance = self.font.getlength("M")
        self.base = Image.new("RGB", (1080, 1920), "#080f1f")
        d = ImageDraw.Draw(self.base)
        d.rounded_rectangle((60, 420, 930, 1190), 24, fill="#101827", outline="#34465d", width=2)
        d.rounded_rectangle((61, 421, 929, 505), 24, fill="#1c2839")
        d.rectangle((61, 465, 929, 505), fill="#1c2839")
        for i, color in enumerate(("#ff625d", "#ffc34f", "#28cd74")):
            d.ellipse((88 + 33*i, 453, 103 + 33*i, 468), fill=color)
        d.text((220, 448), scene.filename, font=self.small, fill="#b2c0d3")
        d.line((80, 1100, 910, 1100), fill="#34465d", width=2)
        d.text((90, 1130), "ILLUSTRATIVE CODE", font=self.small, fill="#8799b0")
        self.cells = []
        offset = 0
        lexer = get_lexer_by_name(scene.language, stripnl=False, ensurenl=False)
        # Lex the complete snippet so multiline strings/comments keep their state.
        coloured = []
        for kind, token in lex(scene.text, lexer):
            color = next((c for group, c in PALETTE if kind in group), "#d2dbe7")
            coloured.extend((char, color) for char in token)
        if "".join(char for char, _ in coloured) != scene.text:
            raise ValueError("lexer changed display text")
        for row, line in enumerate(scene.lines):
            d.text((85, 550 + 78*row), str(row+1), font=self.small, fill="#8799b0")
            for col, (char, color) in enumerate(coloured[offset:offset+len(line)]):
                self.cells.append((offset+col, char, (140+col*self.advance, 540+78*row), color))
            offset += len(line) + 1

    def frame(self, seconds: float) -> Image.Image:
        count = self.scene.count(seconds)
        frame = self.base.copy()
        draw = ImageDraw.Draw(frame)
        for index, char, position, color in self.cells:
            if index < count:
                draw.text(position, char, font=self.font, fill=color)
        row, col = self.scene.cursor(seconds)
        typing = seconds < self.scene.start + self.scene.typing_seconds
        if typing or int((seconds - self.scene.start) * 2) % 2 == 0:
            x, y = 140 + col*self.advance, 547 + row*78
            draw.rectangle((x, y, x+3, y+43), fill="#65ead4")
        return frame
