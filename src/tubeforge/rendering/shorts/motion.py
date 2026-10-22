"""Motion layer: entrances, count-ups, scene transitions, slow push-in, living background.

It composites the *same* transparent scene layers the static compositor draws
(``SceneRenderer.compose(..., transparent=True)``), so geometry QA still covers
every pixel that can appear. All motion is deterministic from the timeline.
"""
from __future__ import annotations

import math
import random
from collections import OrderedDict

import numpy as np
from PIL import Image, ImageChops, ImageDraw

from .layout import CAPTION, HEIGHT, SAFE, WIDTH, SceneRenderer
from .plates import CARD
from .timeline import FrameState

PAD = 60
ENTRANCE_SECONDS = 0.42
COUNT_SECONDS = 0.8
SCENE_IN_SECONDS = 0.3
PUSH_IN = 0.02


def ease_out_cubic(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


def ease_out_back(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    c1, c3 = 1.4, 2.4
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2


def ambient_background() -> Image.Image:
    """The reference glow, rendered PAD px larger on every side for parallax drift."""
    w, h = WIDTH + 2 * PAD, HEIGHT + 2 * PAD
    yy, xx = np.ogrid[:h:4, :w:4]
    yy, xx = yy.astype(np.float32) - PAD, xx.astype(np.float32) - PAD
    glow = np.exp(-((xx - 140) ** 2 + (yy - 900) ** 2) / (2 * 610 ** 2))
    violet = np.exp(-((xx - 930) ** 2 + (yy - 1500) ** 2) / (2 * 750 ** 2))
    rgb = np.stack([8 + glow * 3 + violet * 12, 15 + glow * 14, 31 + glow * 22 + violet * 20], axis=-1).astype(np.uint8)
    return Image.fromarray(rgb).resize((w, h), Image.Resampling.BILINEAR)


def soft_dot(size: int, alpha: int) -> Image.Image:
    y, x = np.ogrid[:size, :size]
    r = np.sqrt((x - size / 2) ** 2 + (y - size / 2) ** 2) / (size / 2)
    a = (np.clip(1 - r, 0, 1) ** 2 * alpha).astype(np.uint8)
    sprite = np.zeros((size, size, 4), np.uint8)
    sprite[..., 0], sprite[..., 1], sprite[..., 2], sprite[..., 3] = 120, 220, 255, a
    return Image.fromarray(sprite, "RGBA")


class LRU(OrderedDict):
    def __init__(self, limit):
        super().__init__()
        self.limit = limit

    def fetch(self, key, make):
        if key in self:
            self.move_to_end(key)
            return self[key]
        value = self[key] = make()
        while len(self) > self.limit:
            self.popitem(last=False)
        return value


class Animator:
    def __init__(self, renderer: SceneRenderer, seed: int = 20261022, plates=None):
        self.renderer = renderer
        self.plates = plates  # optional real-imagery plates (stock B-roll, source/code cards)
        self.bg = ambient_background()
        rng = random.Random(seed)
        self.dots = [(rng.uniform(40, WIDTH - 40), rng.uniform(0, HEIGHT + 300), rng.uniform(18, 46),
                      rng.choice((28, 44, 64)), rng.uniform(0, 6.28)) for _ in range(16)]
        self.sprites = {s: soft_dot(s, 46) for s in (28, 44, 64)}
        self.layers, self.captions = LRU(12), LRU(48)

    # -- cached transparent layers -------------------------------------------
    def layer(self, index: int, revealed: int, grow: float = 1.0) -> Image.Image:
        key = (index, revealed, round(grow * 24))
        return self.layers.fetch(key, lambda: self.renderer.compose(index, revealed, grow=key[2] / 24, transparent=True).image)

    def caption(self, index: int, chunk: int | None, active: int) -> Image.Image | None:
        if chunk is None:
            return None

        def make():
            from .layout import Canvas
            canvas = Canvas(Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0)))
            self.renderer.caption(canvas, self.renderer.groups[index][chunk], active)
            return canvas.image
        return self.captions.fetch((index, chunk, active), make)

    # -- pieces ----------------------------------------------------------------
    def background(self, t: float) -> Image.Image:
        dx = round(PAD + 30 * math.sin(t * .35))
        dy = round(PAD + 40 * math.cos(t * .27))
        frame = self.bg.crop((dx, dy, dx + WIDTH, dy + HEIGHT))
        for x0, y0, speed, size, phase in self.dots:
            y = (y0 - speed * t) % (HEIGHT + 300) - 150
            x = x0 + 26 * math.sin(t * .5 + phase)
            sprite = self.sprites[size]
            frame.paste(sprite, (round(x - size / 2), round(y - size / 2)), sprite)
        return frame

    def content(self, st: FrameState) -> Image.Image:
        scene = self.renderer.topic.scenes[st.index]
        grow, base = 1.0, None
        if scene.template == "big_stat" and st.since_reveal is not None and st.since_reveal < COUNT_SECONDS:
            grow = ease_out_cubic(st.since_reveal / COUNT_SECONDS)
        current = self.layer(st.index, st.revealed, grow)
        if (scene.template != "big_stat" and st.since_reveal is not None and st.since_reveal < ENTRANCE_SECONDS
                and st.revealed >= 1):
            before = self.layer(st.index, st.revealed - 1)
            box = ImageChops.difference(current, before).getbbox()
            if box:
                p = ease_out_back(st.since_reveal / ENTRANCE_SECONDS)
                piece = current.crop(box)
                scale = .78 + .22 * p
                size = (max(1, round(piece.width * scale)), max(1, round(piece.height * scale)))
                piece = piece.resize(size, Image.Resampling.BILINEAR)
                fade = min(1.0, p * 1.6)
                if fade < 1:
                    piece.putalpha(piece.getchannel("A").point(lambda v: round(v * fade)))
                base = before.copy()
                base.alpha_composite(piece, (round((box[0] + box[2]) / 2 - size[0] / 2),
                                             round((box[1] + box[3]) / 2 - size[1] / 2)))
        content = base if base is not None else current
        if st.scene_t < SCENE_IN_SECONDS:
            e = ease_out_cubic(st.scene_t / SCENE_IN_SECONDS)
            if st.index > 0 and e < .5:
                # Outgoing scene fades first, so two scenes never overlap on screen.
                gone = Image.new("RGBA", content.size, (0, 0, 0, 0))
                gone.paste(self.layer(st.index - 1, 3), (0, round(-30 * e)))
                gone.putalpha(gone.getchannel("A").point(lambda v: round(v * (1 - e / .5))))
                content = gone
            else:
                k = 1.0 if st.index == 0 else (e - .5) / .5
                shifted = Image.new("RGBA", content.size, (0, 0, 0, 0))
                shifted.paste(content, (0, round((1 - k) * 60)))
                shifted.putalpha(shifted.getchannel("A").point(lambda v: round(v * k)))
                content = shifted
        if self.plates is not None and st.index in self.renderer.cards:
            card = self.plates.card(st.index, st.scene_t, st.scene_dur, st.since_reveal)
            if card is not None:
                e = ease_out_back(min(1.0, st.scene_t / .4))
                k = .9 + .1 * e
                size = (max(1, round(card.width * k)), max(1, round(card.height * k)))
                piece = card.resize(size, Image.Resampling.BILINEAR) if k != 1 else card
                if e < 1:
                    piece = piece.copy()
                    piece.putalpha(piece.getchannel("A").point(lambda v: round(v * min(1.0, e * 1.5))))
                content = content.copy()
                cx, cy = (CARD[0] + CARD[2]) // 2, (CARD[1] + CARD[3]) // 2
                content.alpha_composite(piece, (round(cx - size[0] / 2), round(cy - size[1] / 2)))
        zoom = 1 + PUSH_IN * min(1.0, st.scene_t / max(st.scene_dur, .1))
        return content.transform(content.size, Image.Transform.AFFINE,
                                 (1 / zoom, 0, WIDTH / 2 * (1 - 1 / zoom), 0, 1 / zoom, 860 * (1 - 1 / zoom)),
                                 resample=Image.Resampling.BILINEAR)

    def frame(self, st: FrameState, t: float, rails: bool = False) -> Image.Image:
        stock = self.plates.background(st.index, st.scene_t, st.scene_dur) if self.plates is not None else None
        image = stock if stock is not None else self.background(t)
        content = self.content(st)
        image.paste(content, (0, 0), content)
        caption = self.caption(st.index, st.chunk, st.active)
        if caption is not None:
            image.paste(caption, (0, 0), caption)
        if rails:
            d = ImageDraw.Draw(image)
            d.rectangle(SAFE, outline="#ff477e", width=3)
            d.rectangle(CAPTION, outline="#ffc46b", width=3)
        return image
