"""Real 1280x720 YouTube thumbnails composed from a frame of the finished video, big text and an optional logo."""
from __future__ import annotations

import hashlib
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps, ImageStat

from tubeforge.rendering.shorts.layout import FONTS
from tubeforge.rendering.shorts.logos import LOGO_NAMES, logo_badge

SIZE = (1280, 720)
MAX_BYTES = 2_000_000  # YouTube's thumbnail limit
YELLOW, WHITE = "#ffd84a", "#ffffff"


def grab_frame(ffmpeg: str, video: Path, seconds: float) -> Image.Image:
    with tempfile.TemporaryDirectory(prefix="thumb-") as scratch:
        target = Path(scratch) / "frame.png"
        subprocess.run([ffmpeg, "-nostdin", "-v", "error", "-ss", f"{max(0.0, seconds):.3f}", "-i", str(video), "-frames:v", "1", str(target)],
                       check=True, timeout=60, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return Image.open(target).convert("RGB")


def candidate_times(duration: float) -> list[float]:
    """Spread of moments after the opening hook (whose text the headline would repeat), shown as choices."""
    return [round(max(0.5, min(duration - 0.5, duration * share)), 2) for share in (0.2, 0.32, 0.44, 0.56, 0.68, 0.8, 0.9)]


def best_time(ffmpeg: str, video: Path, duration: float) -> float:
    """The candidate with the most colour and detail; flat or dark frames make weak thumbnails."""
    best, best_score = candidate_times(duration)[1], -1.0
    for seconds in candidate_times(duration):
        small = grab_frame(ffmpeg, video, seconds).resize((160, 160))
        detail = ImageStat.Stat(small.convert("L").filter(ImageFilter.FIND_EDGES)).mean[0]
        colour = ImageStat.Stat(small.convert("HSV")).mean[1]
        brightness = ImageStat.Stat(small.convert("L")).mean[0]
        score = detail * 2 + colour * .5 - abs(brightness - 110) * .3
        if score > best_score:
            best, best_score = seconds, score
    return best


def _tokens(text: str) -> list[tuple[str, bool]]:
    """Words with an accent flag: everything after the first ? ! or : is the yellow payoff, else only the last word."""
    for mark in "?!:":
        head, found, tail = text.partition(mark)
        if found and tail.strip():
            return [(w, False) for w in (head + found).split()] + [(w, True) for w in tail.split()]
    words = text.split()
    return [(w, i == len(words) - 1) for i, w in enumerate(words)]


def _wrap(tokens: list[tuple[str, bool]], face, width: int) -> list[list[tuple[str, bool]]] | None:
    rows: list[list[tuple[str, bool]]] = [[]]
    payoff = sum(accent for _, accent in tokens) >= 2  # a multi-word payoff starts on its own line
    for index, token in enumerate(tokens):
        if payoff and token[1] and index and not tokens[index - 1][1]:
            rows.append([])
        trial = " ".join(w for w, _ in rows[-1] + [token])
        if face.getlength(trial) <= width:
            rows[-1].append(token)
        elif rows[-1]:
            rows.append([token])
            if face.getlength(token[0]) > width:
                return None
        else:
            return None
    return rows


def _fit(text: str, width: int, height: int, lines: int):
    """Largest Anton size that fits in three rows (four only when it cannot)."""
    tokens = _tokens(text)
    for limit in (min(lines, 3), lines):
        for size in range(260, 60, -6):
            face = ImageFont.truetype(str(FONTS / "Anton-Regular.ttf"), size)
            rows = _wrap(tokens, face, width)
            if rows and len(rows) <= limit and len(rows) * size * 1.05 <= height:
                return face, rows
    face = ImageFont.truetype(str(FONTS / "Anton-Regular.ttf"), 60)
    return face, _wrap(tokens, face, width) or [tokens]


def compose(frame: Image.Image, text: str, logo: str | None = None) -> Image.Image:
    """Dark blurred backdrop, the sharp frame as a card, outlined headline with an accent word, optional logo badge."""
    text = " ".join(text.upper().split())[:48]
    canvas = ImageOps.fit(frame, SIZE, Image.Resampling.LANCZOS).filter(ImageFilter.GaussianBlur(26))
    canvas = Image.blend(canvas, Image.new("RGB", SIZE, "#0b1220"), .55)
    portrait = frame.height > frame.width
    card_h = 640
    card_w = round(card_h * frame.width / frame.height) if portrait else 560
    card = ImageOps.fit(frame, (card_w, card_h), Image.Resampling.LANCZOS)
    mask = Image.new("L", card.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, card.width - 1, card.height - 1), radius=34, fill=255)
    x = SIZE[0] - card_w - 60
    shadow = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((x, 46, x + card_w, 46 + card_h), radius=34, fill=(0, 0, 0, 170))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), shadow.filter(ImageFilter.GaussianBlur(18)))
    canvas.paste(card, (x, 40), mask)
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((x, 40, x + card_w, 40 + card_h), radius=34, outline="#53e0ef", width=6)
    box_w, top = x - 100, 120 if logo else 90
    face, rows = _fit(text, box_w, SIZE[1] - top - 80, 4)
    step = round(face.size * 1.05)
    y = top + max(0, (SIZE[1] - top - 80 - step * len(rows)) // 2)
    for index, row in enumerate(rows):
        x_cursor = 60
        for word, accent in row:
            draw.text((x_cursor, y + index * step), word, font=face, fill=YELLOW if accent else WHITE, stroke_width=max(6, face.size // 16), stroke_fill="#05080f")
            x_cursor += face.getlength(word + " ")
    if logo in LOGO_NAMES:
        badge = logo_badge(logo, 150)
        canvas.alpha_composite(badge, (50, 30))
    return canvas.convert("RGB")


def save(image: Image.Image, target: Path) -> str:
    """Write a JPEG under YouTube's 2 MB limit and return its sha256."""
    target.parent.mkdir(parents=True, exist_ok=True)
    for quality in (92, 86, 80, 72):
        image.save(target, "JPEG", quality=quality, optimize=True)
        if target.stat().st_size <= MAX_BYTES:
            break
    return hashlib.sha256(target.read_bytes()).hexdigest()
