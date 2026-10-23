"""Upload-ready title, two-line description and tags drawn from the approved package (no extra model call)."""
from __future__ import annotations

import re

from tubeforge.domain.contracts import ContentPackage

CURIOSITY = {"why", "how", "this", "your", "you", "stop", "before", "never", "truth", "mistake", "warns", "now", "today", "fix", "risk", "offline", "critical", "flaw", "pull", "attack", "hacked", "exposed"}
MONTHS = {"january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"}
LINE_ONE_MAX = 125


def score_title(title: str, topic_words: set[str]) -> float:
    words = re.findall(r"[a-z0-9']+", title.casefold())
    score = 0.0
    length = len(title)
    score += 3 if 35 <= length <= 65 else 1 if length <= 80 else -3 if length > 95 else 0
    score += 1 if any(ch.isdigit() for ch in title) and not MONTHS & set(words) else 0
    score -= 1 if MONTHS & set(words) else 0
    score -= 2 if title.upper().startswith("CVE") else 0
    score += 1 if "?" in title else 0
    score += min(2.0, .5 * len(CURIOSITY & set(words)))
    score += 2 if topic_words & set(words) else 0
    letters = [c for c in title if c.isalpha()]
    score -= 2 if letters and sum(c.isupper() for c in letters) / len(letters) > .6 else 0
    return score


def choose_title(options: list[str], topic: str) -> str:
    topic_words = {w for w in re.findall(r"[a-z0-9]+", topic.casefold()) if len(w) > 2}
    ranked = sorted(((score_title(t, topic_words), -i, t) for i, t in enumerate(options)), reverse=True)
    return ranked[0][2]


def _hashtags(tags: list[str]) -> list[str]:
    found: list[str] = []
    for tag in tags:
        flat = re.sub(r"[^A-Za-z0-9]", "", tag)
        if flat and not any(c.isdigit() for c in flat) and len(flat) <= 24 and f"#{flat}".casefold() not in {h.casefold() for h in found}:
            found.append(f"#{flat}")
        if len(found) == 3:
            break
    return found


def _first_sentence(text: str) -> str:
    sentence = re.split(r"(?<=[.!?])\s+", " ".join(text.split()), maxsplit=1)[0]
    if len(sentence) > LINE_ONE_MAX:
        sentence = sentence[:LINE_ONE_MAX + 1].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    return sentence


def two_line_description(package: ContentPackage) -> str:
    metadata = package.metadata
    first = _first_sentence(metadata.description) or (package.hook_options[0] if package.hook_options else package.request.topic)
    match = re.search(r"Source:\s*([^.]+)", metadata.description)
    source = match.group(1).strip() if match else (package.request.sources[0].title if package.request.sources else "")
    parts = [metadata.call_to_action.strip().rstrip(".")] if metadata.call_to_action else []
    if source and not source.startswith("Brief notes"):
        parts.append(f"Source: {source.split(',')[0].strip()}")
    second = " · ".join(parts + [" ".join(_hashtags(list(metadata.tags)))]).strip(" ·")
    return (first + "\n" + second).replace("<", "").replace(">", "")


def suggest(package: ContentPackage) -> dict[str, object]:
    metadata = package.metadata
    title = choose_title(list(metadata.title_options), package.request.topic)
    return {"title": title[:100], "title_options": list(metadata.title_options), "description": two_line_description(package),
            "tags": list(metadata.tags)[:30], "thumbnail_text_options": list(package.thumbnail_brief.text_options) if package.thumbnail_brief else []}
