"""Own-script helpers: how well a hand-written script fits a Short's length, and the guide to give other AI agents.

Pure functions. The budget is the same one the writer prompt and validation use
(``prompts.reference_word_budget``), so the numbers an operator sees match what the pipeline accepts.
"""
from __future__ import annotations

import re

from tubeforge.providers.content.prompts import reference_word_budget

SECTION_MIN_WORDS, SECTION_MAX_WORDS = 8, 15
LENGTHS = (30, 45, 60, 75, 90)
_TAG = re.compile(r"\[(?:pause[^\]]*|breath|/?whisper)\]|\*(?=\S)|(?<=\S)\*")


def spoken_words(text: str) -> int:
    """Whitespace-separated spoken words with delivery tags removed (tags are not words)."""
    return len(_TAG.sub("", text).split())


def split_sections(text: str) -> list[str]:
    """One section per blank-line-separated paragraph; a single paragraph is split into sentences."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    if len(paragraphs) == 1:
        paragraphs = [s.strip() for s in re.split(r"(?<=[.!?…])\s+", paragraphs[0]) if s.strip()]
    return [" ".join(p.split()) for p in paragraphs]


def analyze_script(sections_or_text: str | list[str], length_s: int) -> dict:
    """Word/time fit of a script against ``length_s``; ``suggestion`` says what to cut or add."""
    sections = split_sections(sections_or_text) if isinstance(sections_or_text, str) else [s.strip() for s in sections_or_text if s.strip()]
    budget = reference_word_budget(length_s)
    rows = []
    for index, text in enumerate(sections, 1):
        words = spoken_words(text)
        note = "too short (under 8 words): merge it into a neighbour" if words < SECTION_MIN_WORDS else \
               "too long (over 15 words): split it into two scenes" if words > SECTION_MAX_WORDS else ""
        rows.append({"index": index, "words": words, "note": note, "text": text})
    total = sum(row["words"] for row in rows)
    if total == 0:
        status, suggestion = "empty", "Write or paste the narration."
    elif total > budget["max"]:
        status, suggestion = "too_long", f"Remove about {total - budget['aim_high']} words (aim {budget['aim_low']}-{budget['aim_high']}); the video would run past {length_s} s."
    elif total < budget["aim_low"]:
        status = "too_short" if total < budget["floor"] else "short"
        suggestion = f"Add about {budget['aim_low'] - total} words (aim {budget['aim_low']}-{budget['aim_high']}) or choose a shorter length."
    else:
        status, suggestion = "ok", "Fits the length."
    return {"length_s": length_s, "words": total, "estimated_seconds": round(total / 2.5, 1), "aim_low": budget["aim_low"],
            "aim_high": budget["aim_high"], "max_words": budget["max"], "scenes_low": budget["scenes_low"],
            "scenes_high": budget["scenes_high"], "status": status, "suggestion": suggestion,
            "sections": rows, "section_count": len(rows)}


def plan_template(length_s: int = 60) -> str:
    """The markdown plan format, with an own-script ``narration`` block, sized for ``length_s``."""
    b = reference_word_budget(length_s)
    third = round(length_s / 6)
    return f'''## Short title

```yaml
id: my-short-id            # lowercase letters, digits and dashes; unique
title: "Up to 100 characters"
concept: "One sentence: what this Short is about"
length_s: {length_s}       # 30-90
ending: loop               # loop (last line flows into the hook) or debate (closes on a question)
channel: engineering       # optional
publish_at: 2026-11-10T09:00:00+05:30   # optional, metadata only
hook: "Optional: the opening line you want"
beats:
  - {{t: "0-{third}", point: "Hook"}}
  - {{t: "{third}-{length_s - third}", point: "Main explanation"}}
  - {{t: "{length_s - third}-{length_s}", point: "Payoff / what to do"}}
cta: "Optional closing idea"
claims_to_verify:
  - "Optional claim a reviewer should check"
sources:                   # optional page URLs; when given, no web research runs
  - https://example.com/source-page
thumbnail: {{text: "Short Words", visual: "What the thumbnail shows"}}
tags: [tag one, tag two]
narration: |
  Optional: your own script, {b["aim_low"]}-{b["aim_high"]} words for {length_s} s.
  Short sentences. One idea per line or paragraph, 8-15 spoken words each.

  Blank lines separate scenes. Leave narration out to let the AI write it.
```
'''


def script_guide(length_s: int = 60) -> str:
    """Instructions to paste into another AI agent so it writes a script this pipeline accepts."""
    b = reference_word_budget(length_s)
    return f'''# Write a {length_s}-second YouTube Short script for TubeForge

Write ONLY the narration plus a markdown plan block in the format at the end.

## Length (hard limits for {length_s} s)
- Total narration: {b["aim_low"]}-{b["aim_high"]} words. Never more than {b["max"]}. The voice speaks about 2.5 words per second.
- {b["scenes_low"]}-{b["scenes_high"]} scenes. One scene per paragraph, 8-15 spoken words each, complete sentences.
- Scene 1 is the hook: at most 14 words, one concrete number, name or date, names a cost, risk or surprise, leaves it open.
- The last line flows back into the hook (loop ending) or asks one pointed question (debate ending). Never "like and subscribe".

## Voice
- Plain speech, like a smart friend explaining. Explain a technical term in the same sentence, at most two per scene.
- Take one clear side; no "might", "some say", "it depends". Opinions are the video's verdict, never presented as facts.
- At most one number per scene, four in the whole script. Say what a number means ("about nine in ten").
- Only facts you can back with a source URL. Never invent quotes, numbers, tools or personal experience.
- No cliches (game-changer, dive in, here's the thing, let that sink in). Do not start three scenes with the same word.

## The voice reads text literally
- Write numbers and units as words: "120 thousand dollars", "3.4 times", "megabytes", "milliseconds". No symbols such as $ % & / + =.
- Acronyms in CAPITALS are spelled letter by letter (API = "eh pee eye"). Words said as words must NOT be all capitals: write "readme", not "README". Write product names as people say them.
- Optional delivery tags inside narration only: [pause 0.4], [breath], *stressed word* (at most 2 per scene), [whisper]...[/whisper] (at most 2 per video).

## Output format
Return one markdown plan. Put the narration in the `narration` field; separate scenes with a blank line.

{plan_template(length_s)}
'''
