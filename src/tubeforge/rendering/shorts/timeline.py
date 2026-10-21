"""Validated local audio timing, separate from model-authored scene direction."""
from __future__ import annotations

import math
from dataclasses import dataclass

from .layout import SceneRenderer
from .schema import ShortsTopic


@dataclass(frozen=True)
class Word:
    start: float
    end: float


@dataclass(frozen=True)
class SceneTiming:
    start: float
    end: float
    words: tuple[Word, ...]
    alignment: str
    voice_end: float | None = None


class Timeline:
    def __init__(self, topic: ShortsTopic, timings: tuple[SceneTiming, ...]):
        if len(topic.scenes) != len(timings):
            raise ValueError("timings must match every scene")
        previous = 0.0
        for scene, timing in zip(topic.scenes, timings, strict=True):
            if not math.isfinite(timing.start) or not math.isfinite(timing.end) or abs(timing.start - previous) > .001:
                raise ValueError("scene timing is nonfinite or not contiguous")
            if len(timing.words) != len(scene.vo.split()):
                raise ValueError("word timing must cover exact narration tokens")
            # Different spelling/case is supported; omitted/added display words
            # need an explicit mapping before they can be aligned truthfully.
            if len(scene.caption.split()) != len(timing.words):
                raise ValueError("display caption must map one-to-one to spoken words")
            if not timing.alignment:
                raise ValueError("alignment method/fallback must be recorded")
            cursor = timing.start
            for word in timing.words:
                if not all(math.isfinite(v) for v in (word.start, word.end)) or word.start < cursor - .001 or word.end <= word.start:
                    raise ValueError("word timing is invalid or overlaps")
                cursor = word.end
            voice_end = cursor if timing.voice_end is None else timing.voice_end
            if not math.isfinite(voice_end) or cursor > voice_end + .05 or voice_end < timing.start:
                raise ValueError("word timing exceeds actual voice audio")
            if not .299 <= timing.end - voice_end <= .401:
                raise ValueError("each scene requires a 0.3–0.4 second speech tail")
            previous = timing.end
        if not 25 <= previous <= 45:
            raise ValueError("reference Shorts duration must be 25–45 seconds")
        if timings[-1].end - timings[-1].start < 2.5:
            raise ValueError("closing CTA needs at least 2.5 seconds")
        self.topic, self.timings, self.duration = topic, timings, previous
        self.renderer = SceneRenderer(topic)
        self.renderer.validate()

    def event(self, seconds: float):
        index = next((i for i, scene in enumerate(self.timings) if seconds < scene.end), len(self.timings) - 1)
        timing, scene = self.timings[index], self.topic.scenes[index]
        revealed = sum(seconds >= timing.words[word_index].start for word_index in scene.reveal_words)
        active_word = next((i for i, word in enumerate(timing.words) if word.start <= seconds < word.end), None)
        if active_word is None:
            return index, revealed, None, 0
        offset = 0
        for chunk_index, group in enumerate(self.renderer.groups[index]):
            if active_word < offset + len(group):
                return index, revealed, chunk_index, active_word - offset
            offset += len(group)
        raise ValueError("caption mapping does not cover aligned words")
