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


def _fit(text: str, width: int, height: int, lines: int, prefer_fewer: bool = True):
    """Largest Anton size that fits in three rows (more only when it cannot); portrait canvases allow all rows at once."""
    tokens = _tokens(text)
    for limit in ((min(lines, 3), lines) if prefer_fewer else (lines,)):
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


BRAND_LOGO = Path(__file__).resolve().parents[1] / "assets" / "brand" / "protech-logo.webp"
# Rough Shorts feed overlays on a 1080x1920 canvas, used only for the review guides (not for layout).
SHORTS_UI = {"title, channel and caption": (0, 1560, 1080, 1920), "action buttons": (930, 900, 1080, 1560), "top bar": (0, 0, 1080, 200)}


def _glow(size: tuple[int, int], center: tuple[int, int], radius: int, colour: str, strength: float) -> Image.Image:
    """Soft coloured light: only the alpha is blurred, so the colour stays pure instead of darkening toward black."""
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).ellipse((center[0] - radius, center[1] - radius, center[0] + radius, center[1] + radius), fill=int(255 * strength))
    layer = Image.new("RGBA", size, colour)
    layer.putalpha(mask.filter(ImageFilter.GaussianBlur(radius // 2)))
    return layer


def compose_portrait(frame: Image.Image | None, text: str, logo: str | None = None, *, config=None, brand: Path | None = BRAND_LOGO,
                     guides: bool = False) -> tuple[Image.Image, dict[str, tuple[int, int, int, int]]]:
    """1080x1920 Shorts thumbnail: dark navy, cyan glow, centred Anton headline, tech badge and a modest brand logo.

    Returns the image and the bounding boxes of the key content, all inside ``config.safe_region``.
    """
    from tubeforge.core.config import ShortsThumbnailConfig
    config = config or ShortsThumbnailConfig()
    width, height = config.width, config.height
    x0, y0, x1, y1 = config.safe_region
    accent = config.accent
    text = " ".join(text.upper().split())[:48]
    canvas = Image.new("RGBA", (width, height), config.background)
    if frame is not None:  # the video frame only tints the backdrop; it is never the subject
        backdrop = ImageOps.fit(frame.convert("RGB"), (width, height), Image.Resampling.LANCZOS).filter(ImageFilter.GaussianBlur(50))
        backdrop = Image.blend(backdrop, Image.new("RGB", backdrop.size, config.background), .45)
        canvas = Image.blend(canvas.convert("RGB"), backdrop, .16).convert("RGBA")
    canvas.alpha_composite(_glow((width, height), (width // 2, (y0 + y1) // 2), 520, accent, .30))
    canvas.alpha_composite(_glow((width, height), (width // 2, y0 + 200), 260, accent, .22))
    draw = ImageDraw.Draw(canvas)
    marks: dict[str, tuple[int, int, int, int]] = {}
    pad = config.headline_margin
    top = y0 + 30
    if logo in LOGO_NAMES:
        diameter = 300
        badge = logo_badge(logo, diameter)
        position = ((width - diameter) // 2, top)
        canvas.alpha_composite(badge, position)
        marks["tech_badge"] = (position[0], position[1], position[0] + diameter, position[1] + diameter)
        top += diameter + 50
    brand_size = config.brand_logo_size if config.brand_logo_enabled and brand is not None and Path(brand).is_file() else 0
    bottom = y1 - (brand_size + 70 if brand_size else 30)
    face, rows = _fit(text, x1 - x0 - 2 * pad, bottom - top - 40, 5, prefer_fewer=False)
    step = round(face.size * 1.04)
    stroke = max(7, face.size // 15)
    glyph_top, glyph_bottom = face.getbbox("HQ")[1], face.getbbox("HQ")[3]
    visible = (len(rows) - 1) * step + glyph_bottom - glyph_top + 2 * stroke
    block = visible
    y = top + max(0, (bottom - top - 40 - visible) // 2) - glyph_top + stroke
    left, right = width, 0
    for index, row in enumerate(rows):
        line = " ".join(word for word, _ in row)
        line_width = face.getlength(line)
        cursor = (width - line_width) / 2
        for word, accented in row:
            draw.text((cursor, y + index * step), word, font=face, fill=accent if accented else WHITE, stroke_width=stroke, stroke_fill="#03060d")
            cursor += face.getlength(word + " ")
        left, right = min(left, round((width - line_width) / 2 - stroke)), max(right, round((width + line_width) / 2 + stroke))
    marks["headline"] = (left, y + glyph_top - stroke, right, y + glyph_top - stroke + visible)
    bar_y = y + glyph_top - stroke + visible + 22
    if bar_y + 12 < bottom + 20:
        canvas.alpha_composite(_glow((width, height), (width // 2, bar_y + 5), 140, accent, .55))
        draw.rounded_rectangle((width // 2 - 260, bar_y, width // 2 + 260, bar_y + 10), radius=5, fill=accent)
        marks["accent_bar"] = (width // 2 - 260, bar_y, width // 2 + 260, bar_y + 10)
    if brand_size:
        mark = Image.open(brand).convert("RGB").resize((brand_size, brand_size), Image.Resampling.LANCZOS)
        tile = Image.new("L", mark.size, 0)
        ImageDraw.Draw(tile).rounded_rectangle((0, 0, brand_size - 1, brand_size - 1), radius=brand_size // 5, fill=255)
        position = ((width - brand_size) // 2, y1 - brand_size - 20)
        canvas.alpha_composite(_glow((width, height), (width // 2, position[1] + brand_size // 2), brand_size, accent, .35))
        canvas.paste(mark, position, tile)
        ImageDraw.Draw(canvas).rounded_rectangle((*position, position[0] + brand_size, position[1] + brand_size), radius=brand_size // 5, outline=accent, width=4)
        marks["brand_logo"] = (position[0], position[1], position[0] + brand_size, position[1] + brand_size)
    image = canvas.convert("RGB")
    if guides:
        image = draw_guides(image, config)
    return image, marks


def draw_guides(image: Image.Image, config) -> Image.Image:
    """Review overlay: the safe working region and approximate Shorts feed UI zones."""
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    overlay = ImageDraw.Draw(layer)
    for name, box in SHORTS_UI.items():
        overlay.rectangle(box, fill=(255, 71, 126, 70))
        overlay.text((box[0] + 12, box[1] + 10), name, font=ImageFont.truetype(str(FONTS / "Inter-Variable.ttf"), 30), fill=(255, 255, 255, 230))
    overlay.rectangle(config.safe_region, outline=(255, 196, 107, 255), width=5)
    return Image.alpha_composite(image.convert("RGBA"), layer).convert("RGB")


def save(image: Image.Image, target: Path) -> str:
    """Write a JPEG under YouTube's 2 MB limit and return its sha256."""
    target.parent.mkdir(parents=True, exist_ok=True)
    for quality in (92, 86, 80, 72):
        image.save(target, "JPEG", quality=quality, optimize=True)
        if target.stat().st_size <= MAX_BYTES:
            break
    return hashlib.sha256(target.read_bytes()).hexdigest()
