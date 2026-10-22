"""Headless-Chromium capture of the paragraph that holds a quoted claim on a cited source page.

Only URLs from the immutable request's sources are ever opened, every sub-request is checked against
private address ranges, and any failure (blocked page, quote not found, browser missing) is reported as a
reason so the scene falls back to the code-drawn template. The marker highlight is drawn locally.
"""
from __future__ import annotations

import ipaddress
import logging
import socket
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image, ImageChops, ImageDraw

from tubeforge.core.config import SourceCaptureConfig
from tubeforge.rendering.shorts.plates import CARD

LOG = logging.getLogger(__name__)
CARD_WIDTH, CARD_HEIGHT = CARD[2] - CARD[0], CARD[3] - CARD[1]
USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
BLOCKED_TITLES = ("just a moment", "access denied", "attention required", "are you a robot", "captcha", "403 forbidden", "verify you are human")
HIDE_OVERLAYS = """
[id*="cookie" i],[class*="cookie" i],[id*="consent" i],[class*="consent" i],[id*="gdpr" i],[class*="gdpr" i],
[aria-label*="cookie" i],[role="dialog"],[class*="newsletter" i],[class*="subscribe-modal" i],[class*="paywall" i]
{display:none !important}
html,body{overflow:visible !important;position:static !important}
"""
FIND = """
(quote) => {
  const words = quote.replace(/[\\u2018\\u2019]/g, "'").replace(/[\\u201c\\u201d]/g, '"').split(/\\s+/).filter(Boolean);
  const floor = Math.min(4, words.length);
  for (let n = words.length; n >= floor; n--) {
    for (let s = 0; s + n <= words.length; s++) {
      getSelection().removeAllRanges();
      window.scrollTo(0, 0);
      const fragment = words.slice(s, s + n).join(' ');
      if (!window.find(fragment, false, false, true, false, false, false)) continue;
      const range = getSelection().getRangeAt(0);
      const dx = scrollX, dy = scrollY;
      const rects = [...range.getClientRects()].filter(r => r.width > 2 && r.height > 2)
        .map(r => ({x: r.x + dx, y: r.y + dy, w: r.width, h: r.height}));
      if (!rects.length) continue;
      return {rects, complete: n === words.length, words: n,
              docHeight: document.documentElement.scrollHeight, docWidth: document.documentElement.clientWidth};
    }
  }
  return null;
}
"""


def _public(host: str, cache: dict[str, bool]) -> bool:
    if host not in cache:
        try:
            infos = socket.getaddrinfo(host, None)
            cache[host] = bool(infos) and all(ipaddress.ip_address(info[4][0]).is_global for info in infos)
        except (OSError, ValueError):
            cache[host] = False
    return cache[host]


def _guard(cache: dict[str, bool]):
    def route(route):
        request = route.request
        parsed = urlparse(request.url)
        if request.resource_type in {"media", "websocket", "eventsource"}:
            return route.abort()
        if parsed.scheme in {"data", "blob", "about"}:
            return route.continue_()
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or not _public(parsed.hostname, cache):
            return route.abort()
        return route.continue_()
    return route


def plan_clip(rects: list[dict], doc_width: float, doc_height: float) -> tuple[float, float, float, float]:
    """Crop (x, y, w, h) in CSS pixels: the match plus context, shaped to the card's aspect ratio."""
    left = min(r["x"] for r in rects)
    right = max(r["x"] + r["w"] for r in rects)
    top = min(r["y"] for r in rects)
    bottom = max(r["y"] + r["h"] for r in rects)
    width = min(doc_width, max(520.0, min(doc_width, right - left + 80)))
    x = min(max(0.0, (left + right) / 2 - width / 2), max(0.0, doc_width - width))
    max_height = width * CARD_HEIGHT / CARD_WIDTH
    height = min(max_height, max(bottom - top + 180, max_height * .55))
    y = min(max(0.0, (top + bottom) / 2 - height / 2), max(0.0, doc_height - height))
    return x, y, width, min(height, doc_height)


def draw_highlight(image: Image.Image, rects: list[dict], clip: tuple[float, float, float, float]) -> Image.Image:
    """Yellow marker (multiply blend) over the matched text, mapped from page to card pixels."""
    scale = image.width / clip[2]
    layer = Image.new("RGB", image.size, "white")
    draw = ImageDraw.Draw(layer)
    for r in rects:
        box = ((r["x"] - clip[0]) * scale - 3, (r["y"] - clip[1]) * scale - 2,
               (r["x"] - clip[0] + r["w"]) * scale + 3, (r["y"] - clip[1] + r["h"]) * scale + 2)
        draw.rounded_rectangle(box, radius=6, fill=(255, 226, 60))
    return ImageChops.multiply(image.convert("RGB"), layer)


def make_capture(config: SourceCaptureConfig):
    """Return ``capture(url, quote, base) -> dict`` or None when capture is disabled/unavailable."""
    if not config.enabled or not Path(config.chromium_path).is_file():
        return None
    try:
        from playwright.sync_api import Error as PlaywrightError, sync_playwright
    except ImportError:
        return None

    def capture(url: str, quote: str, base: Path) -> dict:
        parsed = urlparse(url)
        cache: dict[str, bool] = {}
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or not _public(parsed.hostname, cache):
            return {"reason": "source URL is not a public http(s) address"}
        try:
            # The worker runs as an arbitrary uid with HOME=/, so give Chromium a private writable profile.
            with tempfile.TemporaryDirectory(prefix="chromium-") as home, sync_playwright() as playwright:
                browser = playwright.chromium.launch(executable_path=str(config.chromium_path), args=[
                    "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--hide-scrollbars", "--mute-audio"],
                    env={"PATH": "/usr/bin:/bin", "HOME": home, "XDG_CONFIG_HOME": home, "XDG_CACHE_HOME": home})
                try:
                    context = browser.new_context(viewport={"width": config.viewport_width, "height": 1100}, device_scale_factor=2,
                                                  user_agent=USER_AGENT, locale="en-US", accept_downloads=False)
                    context.route("**/*", _guard(cache))
                    page = context.new_page()
                    page.set_default_timeout(config.timeout_seconds * 1000)
                    page.goto(url, wait_until="domcontentloaded")
                    page.wait_for_timeout(1800)
                    title = (page.title() or "").casefold()
                    if any(marker in title for marker in BLOCKED_TITLES):
                        return {"reason": f"page blocked automated access ({title[:40]!r})"}
                    page.add_style_tag(content=HIDE_OVERLAYS)
                    found = page.evaluate(FIND, quote)
                    if not found:
                        return {"reason": "quote not found on the page"}
                    page.evaluate("getSelection().removeAllRanges()")  # the native selection from window.find must not show
                    clip = plan_clip(found["rects"], found["docWidth"], found["docHeight"])
                    shot = page.screenshot(clip={"x": clip[0], "y": clip[1], "width": clip[2], "height": clip[3]}, full_page=True)
                finally:
                    browser.close()
        except (PlaywrightError, TimeoutError, OSError) as error:
            return {"reason": f"capture failed: {type(error).__name__}: {str(error)[:120]}"}
        import io
        image = Image.open(io.BytesIO(shot)).convert("RGB")
        image = image.resize((CARD_WIDTH, max(1, round(image.height * CARD_WIDTH / image.width))), Image.Resampling.LANCZOS)
        plain, marked = base.with_suffix(".png"), base.with_name(base.name + "-hl.png")
        image.save(plain)
        draw_highlight(image, found["rects"], clip).save(marked)
        return {"file": f"plates/{plain.name}", "highlight": f"plates/{marked.name}", "matched": bool(found["complete"]),
                "matched_words": found["words"]}
    return capture
