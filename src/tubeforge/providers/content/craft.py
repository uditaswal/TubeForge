"""Deterministic script-craft checks for reference Shorts (anti-slop, payoff position, comment CTA).

These are repairable writer errors, not quality scores: each problem names what to change so the
script writer can fix it in its repair loop. They never rewrite creative text.
"""
from __future__ import annotations

import re

# Phrases that mark machine-written or lazy short-form narration. Matching is case-insensitive on
# whole words; extend deliberately (every entry blocks generation until repaired).
BANNED_PHRASES = (
    "game-changer", "game changer", "here's the thing", "let's dive", "dive in", "dive into",
    "the truth is", "pays off", "but what changed", "in today's world", "in this video",
    "buckle up", "stay tuned", "mind-blowing", "mind blowing", "unlock", "unleash", "revolutionize",
    "revolutionise", "delve", "landscape", "let that sink in", "you won't believe", "it's no secret",
    "at the end of the day", "the secret sauce", "not just", "elevate", "supercharge", "harness the power",
    # Insider jargon a general viewer does not know (explain it in plain words instead).
    "cutover", "paradigm", "synergy", "leverage", "bandwidth", "idempotent", "orchestrate",
)
# Written forms the voice reads badly: currency symbols, thousands commas, "3.4x", unit abbreviations, operators.
SPEECH_UNSAFE = re.compile(r"[$€£¥&@#=+<>/\\]|\d,\d{3}|\d\s?[x×](?![\w])|\b\d+(?:\.\d+)?\s?(?:KB|MB|GB|TB|ms|kHz|MHz|GHz|fps)\b", re.I)
COMMENT_PROMPT = re.compile(r"\?|\b(comment|tell me|defend|prove me wrong|fight me|change my mind|disagree|agree)\b", re.I)
STOPWORDS = frozenset("a an the and or but so of to in on for with by is are was were be it its this that your you we our at as from".split())


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9%$.']+", text.casefold())


def _content(text: str) -> list[str]:
    return [word for word in _words(text) if word not in STOPWORDS]


def visual_problems(package) -> list[str]:
    """Real imagery: enough of it, never two plain template scenes in a row, quotes copied from the cited source."""
    scenes = package.reference_short.scenes
    problems: list[str] = []
    kinds = [scene.visual.kind if scene.visual is not None else None for scene in scenes]
    if sum(kind is not None for kind in kinds) < 4:
        problems.append(f"only {sum(kind is not None for kind in kinds)} of {len(scenes)} scenes have a visual; give at least 4 scenes a stock, source or code visual")
    if any(a is None and b is None for a, b in zip(kinds, kinds[1:])):
        problems.append("two consecutive scenes have no visual; alternate so the viewer never sees two plain template scenes in a row")
    if kinds.count("stock") > 3:
        problems.append("more than 3 stock scenes; use source screenshots or code for scenes that prove a claim")
    for index, scene in enumerate(scenes, 1):
        visual = scene.visual
        if visual is not None and visual.kind == "code" and all(line.lstrip().startswith(("//", "#", "--", "/*", "*")) for line in visual.lines):
            problems.append(f"scene {index} code visual contains only comments; use real syntax from the sources, or a source or stock visual")
    sources = {source.source_id: source for source in getattr(getattr(package, "request", None), "sources", ())}
    for index, scene in enumerate(scenes, 1):
        visual = scene.visual
        if visual is not None and visual.kind == "source" and sources:
            excerpts = " ".join(_norm(sources[s].excerpt) for s in scene.source_ids if s in sources)
            if _norm(visual.quote) not in excerpts:
                problems.append(f"scene {index} visual quote is not an exact passage of its cited source excerpt; copy the words verbatim")
    return problems


def thumbnail_problems(package) -> list[str]:
    """Thumbnail words are 2-3 punchy words that add to the hook; repeating the opening wastes the click."""
    brief = getattr(package, "thumbnail_brief", None)
    if brief is None:
        return []
    first = package.reference_short.scenes[0]
    opening = set(_content(" ".join([first.vo, *(first.headline if isinstance(first.headline, tuple) else (first.headline,))])))
    problems: list[str] = []
    for index, text in enumerate(brief.text_options, 1):
        words = _content(text)
        if len(text.split()) > 3:
            problems.append(f"thumbnail text_option {index} {text!r} has more than three words; use two or three punchy words")
        elif words and len(opening & set(words)) / len(words) >= .6:
            problems.append(f"thumbnail text_option {index} {text!r} repeats the opening scene's words; add a different angle (a verdict, stake or number)")
    return problems


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[\u2018\u2019]", "'", re.sub(r"[\u201c\u201d]", '"', text)).casefold().split())


REPORT_VOICE = re.compile(r"^(researchers?|scientists?|analysts?|a (new |recent )?(study|report|survey|paper)|studies|according to|new data|data shows?)\b"
                          r"|\b(fell|rose|dropped|grew|increased|decreased|climbed|declined) from [\w.%$]+ to [\w.%$]+", re.I)


def craft_problems(package) -> list[str]:
    """Return repair instructions for a reference package, or an empty list."""
    topic = package.reference_short
    scenes = topic.scenes
    problems: list[str] = []
    spoken = [scene.vo for scene in scenes]
    opening = re.split(r"(?<=[.!?…])\s+", spoken[0].strip(), maxsplit=1)[0]
    if REPORT_VOICE.search(opening):
        problems.append(f"the opening {opening!r} is in report voice; open with a named story, a verdict, a paradox or a stake instead of describing a finding")
    for index, scene in enumerate(scenes, 1):
        headline = getattr(scene, "headline", ())
        texts = [scene.vo, *(headline if isinstance(headline, tuple) else (headline,)), getattr(scene, "heading", "")]
        lowered = " " + " ".join(re.sub(r"[^\w'\- ]", " ", text.casefold()) for text in texts if text) + " "
        hits = [phrase for phrase in BANNED_PHRASES if f" {phrase} " in lowered]
        if hits:
            problems.append(f"scene {index} uses cliché phrasing {hits}; say it plainly and specifically")
    for index, text in enumerate(spoken, 1):
        unsafe = sorted({m.group(0).strip() for m in SPEECH_UNSAFE.finditer(text)})
        if unsafe:
            problems.append(f"scene {index} narration has written forms the voice reads badly {unsafe}; write them as spoken words "
                            "('120 thousand dollars' not '$120,000', '3.4 times' not '3.4x', 'megabytes' not 'MB', no thousands commas)")
    for index, hook in enumerate(package.hook_options, 1):
        lowered = " " + re.sub(r"[^\w'\- ]", " ", hook.casefold()) + " "
        hits = [phrase for phrase in BANNED_PHRASES if f" {phrase} " in lowered]
        if hits:
            problems.append(f"hook_option {index} uses cliché phrasing {hits}")
    options = list(package.hook_options)
    if len(options) >= 3:
        if sum(h.strip().endswith("?") for h in options) > 2:
            problems.append("more than two hook_options end in a question mark; use different formulas (named story, paradox, verdict, number shock, stakes)")
        if sum(" but " in f" {h.casefold()} " for h in options) > 2:
            problems.append("more than two hook_options use 'but'; vary the structure")
    questions = [index for index, text in enumerate(spoken[:-1], 1) if "?" in text]
    if len(questions) > 2:
        problems.append(f"scenes {questions} all ask rhetorical questions; keep at most two before the CTA and make the rest statements")
    starts = [_words(text)[0] for text in spoken if _words(text)]
    for word in {"so", "but"}:
        if starts.count(word) > 2:
            problems.append(f"{starts.count(word)} scenes start with '{word}'; vary the openings")
    # Payoff late: the last numeric reveal must land in the back half, not right after the hook.
    stat_positions = [index for index, scene in enumerate(scenes) if scene.template == "big_stat"]
    if stat_positions and stat_positions[-1] < 2:
        problems.append(f"the big_stat payoff is scene {stat_positions[-1] + 1} of {len(scenes)}; move the strongest number/twist "
                        "to scene 3 or later so the hook's question stays open longer")
    # Comment CTA: the closing line must provoke a reply, not only ask for a follow.
    final = scenes[-1].vo
    before_follow = re.split(r"(?i)\bfollow\b", final, maxsplit=1)[0]
    if not COMMENT_PROMPT.search(before_follow):
        problems.append("the CTA scene must open with a one-sided challenge viewers can answer in the comments "
                        "(a question or 'tell me I'm wrong') before the follow request")
    problems += visual_problems(package)
    problems += thumbnail_problems(package)
    # One copy of the words: a heading that just repeats the narration adds nothing to the frame.
    for index, scene in enumerate(scenes[1:-1], 2):
        heading = _content(getattr(scene, "heading", ""))
        narration = set(_content(scene.vo))
        if len(heading) >= 3 and sum(word in narration for word in heading) / len(heading) >= .8:
            problems.append(f"scene {index} heading {scene.heading!r} repeats the narration; show a different fact, label or number")
    return problems
