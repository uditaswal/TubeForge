"""Deterministic script-craft checks for reference Shorts (anti-slop, payoff position, loop ending).

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
    "think about that", "read that again", "let that settle",
    # Insider jargon a general viewer does not know (explain it in plain words instead).
    "cutover", "paradigm", "synergy", "leverage", "bandwidth", "idempotent", "orchestrate",
)
# Written forms the voice reads badly: currency symbols, thousands commas, "3.4x", unit abbreviations, operators.
SPEECH_UNSAFE = re.compile(r"[$€£¥&@#=+<>/\\]|\d,\d{3}|\d\s?[x×](?![\w])|\b\d+(?:\.\d+)?\s?(?:KB|MB|GB|TB|ms|kHz|MHz|GHz|fps)\b", re.I)
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


ORIGINALITY_NGRAM_WORDS, ORIGINALITY_OVERLAP_MAX = 7, 0.5


def _ngrams(words: list[str], n: int) -> set[tuple[str, ...]]:
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


def originality_problems(package, *, n: int = ORIGINALITY_NGRAM_WORDS, threshold: float = ORIGINALITY_OVERLAP_MAX) -> list[str]:
    """M-S2: a scene must not just restate its cited source verbatim.

    Flags a scene whose narration is mostly made of long word-runs that also appear, verbatim, in
    the excerpt(s) of the sources it cites — a sign the writer paraphrased too little. A verbatim
    on-screen quote (`visual.kind == "source"`) is a *different*, already-checked thing (it must
    match exactly, by `visual_problems` above); this checks the *spoken* narration, which should
    not read like a copy of the same text. No request/sources on the package (e.g. a bare fixture
    in a unit test) skips this check entirely, same convention as `visual_problems`.
    """
    sources = {source.source_id: source for source in getattr(getattr(package, "request", None), "sources", ())}
    if not sources:
        return []
    problems: list[str] = []
    for index, scene in enumerate(package.reference_short.scenes, 1):
        cited = [sources[s] for s in scene.source_ids if s in sources and sources[s].excerpt]
        if not cited:
            continue
        source_grams = _ngrams(" ".join(_norm(source.excerpt) for source in cited).split(), n)
        scene_grams = _ngrams(_norm(scene.vo).split(), n)
        if not source_grams or not scene_grams:
            continue
        overlap = sum(1 for gram in scene_grams if gram in source_grams) / len(scene_grams)
        if overlap >= threshold:
            problems.append(f"scene {index} narration is {overlap:.0%} copied {n}-word runs from its cited source; "
                            "say the same fact in your own words, with your own analysis or a concrete example, not the source's sentences")
    return problems


GREETING = re.compile(r"^\W*(hi|hello|hey|yo|welcome|what'?s up|good (morning|evening)|in this video|today (we|i)|so today|guys)\b", re.I)
OPEN_ENDING = re.compile(r"[.!?\u2026]\W*$")


FOLLOW_ASK = re.compile(r"\b(follow|subscribe|subscribing|hit the bell|turn on notifications)\b", re.I)


def debate_problems(last) -> list[str]:
    """The debate ending: a cta scene whose narration is a pointed comment question, with no follow ask."""
    problems: list[str] = []
    if last.template != "cta":
        return ["the final scene must use template cta: a comment-debate close (this video's ending is 'debate', not a loop)"]
    if not last.vo.strip().endswith("?"):
        problems.append("the closing narration must end with a question that makes viewers pick a side in the comments")
    if FOLLOW_ASK.search(" ".join([last.vo, last.caption, last.headline, *last.chips])):
        problems.append("the debate ending must not ask viewers to follow or subscribe; ask them to comment and pick a side")
    if not re.search(r"\bcomment", last.vo, re.I):
        problems.append("the closing narration must tell viewers to comment their side")
    return problems


def loop_problems(package) -> list[str]:
    """The video ends by looping into its own first sentence: no follow request, an open last sentence, a matching last frame."""
    scenes = package.reference_short.scenes
    first, last = scenes[0], scenes[-1]
    problems: list[str] = []
    if GREETING.search(first.vo):
        problems.append(f"scene 1 opens with a greeting or channel intro ({first.vo.split()[0]!r}); open on the concrete fact or stake itself")
    if getattr(getattr(package, "request", None), "ending", "loop") == "debate":
        problems += debate_problems(last)
        return problems
    if last.template != "loop":
        problems.append("the final scene must use template loop (no follow or subscribe request); the video ends by looping back into scene 1")
        return problems
    if OPEN_ENDING.search(last.vo.strip()):
        problems.append("the loop scene's narration must be an open-ended sentence with no final full stop, question mark or exclamation mark, "
                        "so it hands straight into scene 1's first words")
    if (tuple(last.headline), tuple(last.chips), last.icon, last.logo) != (tuple(first.headline), tuple(first.chips), first.icon, first.logo):
        problems.append("the loop scene must copy scene 1's headline lines, chips, icon and logo exactly so the last frame equals the first frame")
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
    problems += loop_problems(package)
    problems += visual_problems(package)
    problems += thumbnail_problems(package)
    problems += fact_dump_problems(package, hard_only=True)
    problems += unexplained_score_problems(package)
    problems += originality_problems(package)
    # One copy of the words: a heading that just repeats the narration adds nothing to the frame.
    for index, scene in enumerate(scenes[1:-1], 2):
        heading = _content(getattr(scene, "heading", ""))
        narration = set(_content(scene.vo))
        if len(heading) >= 3 and sum(word in narration for word in heading) / len(heading) >= .8:
            problems.append(f"scene {index} heading {scene.heading!r} repeats the narration; show a different fact, label or number")
    return problems


# --- Fact dumps: accurate, sourced and unlistenable --------------------------------------------------------------
# A viewer hears the narration once, at speaking speed. Version numbers back to back, lists of figures and pileups
# of acronyms are fine on screen and unbearable in the ear. These checks name what to change; they never rewrite.
VERSION_NUMBER = re.compile(r"\b\d+(?:\.\d+){1,3}\b")
DIGIT_NUMBER = re.compile(r"\b\d[\d,]*(?:\.\d+)?%?")
SPELLED_NUMBERS = frozenset((
    "two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen "
    "twenty thirty forty fifty sixty seventy eighty ninety hundred thousand million billion").split())
JARGON = re.compile(r"\b(?:[A-Z]{2,6}s?|[A-Z][a-z]+[A-Z]\w*|[A-Za-z]+\d+[A-Za-z]*)\b")
VIEWER_WORDS = frozenset("you your you're you'll we us means mean because why that's so".split())
MAX_NUMBERS_PER_SCENE, MAX_NUMBERS_PER_VIDEO = 2, 8
MAX_JARGON_PER_SCENE, MAX_JARGON_PER_VIDEO = 2, 8


def _numbers(text: str) -> list[str]:
    versions = VERSION_NUMBER.findall(text)
    rest = VERSION_NUMBER.sub(" ", text)
    return versions + DIGIT_NUMBER.findall(rest) + [word for word in _words(rest) if word in SPELLED_NUMBERS]


def _jargon(text: str) -> set[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    found: set[str] = set()
    for sentence in sentences:
        words = sentence.split()
        for position, word in enumerate(words):
            token = word.strip(".,;:!?\"'()")
            if JARGON.fullmatch(token) and not (position == 0 and token.istitle()) and token not in {"I", "OK"}:
                found.add(token.casefold())
    return found


SCORE_WORDS = re.compile(r"\b(scor(?:e|es|ed|ing)|rated|rating|ranked|ranking|graded|grade)\b|\bperfect (?:ten|10|score)\b", re.I)
SCALE_WORDS = re.compile(r"\b(out of|scale|percent|per cent|points?|percentile)\b|\d\s?/\s?\d+", re.I)
FIGURE = re.compile(r"\b(\d[\d.,]*|zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|hundred|thousand|million|billion)\b", re.I)


def unexplained_score_problems(package) -> list[str]:
    """A score, rating or rank is meaningless unless the sentence says what it measures and the scale ("ten out of ten on the danger scale")."""
    problems: list[str] = []
    for index, scene in enumerate(package.reference_short.scenes, 1):
        for sentence in re.split(r"(?<=[.!?])\s+", scene.vo):
            if SCORE_WORDS.search(sentence) and FIGURE.search(sentence) and not SCALE_WORDS.search(sentence):
                problems.append(f"scene {index} gives a score without saying what it measures or its scale ({sentence.strip()!r}); a viewer hears it once, so say "
                                "what is being scored and out of what ('the top danger rating, ten out of ten')")
                break
    return problems


def fact_dump_problems(package, *, hard_only: bool = False) -> list[str]:
    """Narration that reads like a list of facts: stacked numbers or versions, repeated frames, unexplained jargon.

    ``hard_only`` keeps the rules a writer can fix in one repair pass (version litanies, too many numbers in one scene);
    the rest (back-to-back figures, jargon totals, repeated openings, nothing for the viewer) stay advisory for the scorecard
    and the editor, because a hard gate on them burned both attempts in a live trial.
    """
    scenes = package.reference_short.scenes
    spoken = [scene.vo for scene in scenes]
    problems: list[str] = []
    counts = [len(_numbers(text)) for text in spoken]
    for index, text in enumerate(spoken, 1):
        versions = VERSION_NUMBER.findall(text)
        if len(versions) >= 2:
            problems.append(f"scene {index} reads out {len(versions)} version numbers back to back ({', '.join(versions)}); say what changed in plain words "
                            "('the first fix was not enough, then two more followed') and leave the version list to the screen")
        elif counts[index - 1] > MAX_NUMBERS_PER_SCENE:
            problems.append(f"scene {index} packs {counts[index - 1]} numbers into one scene; keep at most {MAX_NUMBERS_PER_SCENE}, round them, and explain what each means")
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            if len(_numbers(sentence)) >= 3 and len(versions) < 2:
                problems.append(f"scene {index} has a sentence with {len(_numbers(sentence))} figures in a row; it will sound like a list")
                break
    if hard_only:
        return problems
    if sum(counts) > MAX_NUMBERS_PER_VIDEO:
        problems.append(f"the narration contains {sum(counts)} numbers or versions; more than {MAX_NUMBERS_PER_VIDEO} makes a fact dump. Keep the two that matter and show the rest as text on screen")
    back_to_back = [i + 1 for i, (a, b) in enumerate(zip(counts, counts[1:])) if a >= 2 and b >= 2]
    if back_to_back:
        problems.append(f"scenes {back_to_back[0]} and {back_to_back[0] + 1} both stack numbers; put an explanation or a consequence between figures")
    jargon = [_jargon(text) for text in spoken]
    for index, terms in enumerate(jargon, 1):
        if len(terms) > MAX_JARGON_PER_SCENE:
            problems.append(f"scene {index} piles up {len(terms)} technical terms ({', '.join(sorted(terms))}); introduce one at a time and explain it in plain words")
    if len(set().union(*jargon)) > MAX_JARGON_PER_VIDEO:
        problems.append(f"the narration uses {len(set().union(*jargon))} different acronyms or technical names; keep the few the viewer needs and describe the rest")
    firsts = [_words(text)[0] for text in spoken if _words(text)]
    for word in sorted({w for w in firsts if firsts.count(w) >= 3 and w not in STOPWORDS}):
        problems.append(f"{firsts.count(word)} scenes start with '{word}'; repeating the same frame makes the script sound like a list, so vary how scenes begin")
    middle = spoken[1:-1]
    if len(middle) >= 5:
        addressed = sum(any(word in VIEWER_WORDS for word in _words(text)) for text in middle)
        if addressed / len(middle) < .3:
            problems.append("the narration almost never says what it means for the viewer (no 'you', 'means', 'because' or 'so'); "
                            "turn at least a third of the middle scenes into a consequence or an instruction for the viewer")
    return problems


# --- Naturalness advisories (scorecard and editor only; never a hard gate) -----------------------------------------
# These name what makes narration feel written by a template: a hook with nothing concrete in it, a hook that says its
# own idea twice, figures on screen the voice never explains, unnamed "other factors", and filler. They are heuristics:
# promote one to a repairable gate only after the reference set shows it never fires on an accepted script.
_ONES = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen "
         "eighteen nineteen").split()
_TENS = {2: "twenty", 3: "thirty", 4: "forty", 5: "fifty", 6: "sixty", 7: "seventy", 8: "eighty", 9: "ninety"}
ON_SCREEN_NUMBER = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?(?![\w])")
VAGUE_OTHER = re.compile(r"\bother (?:factors|things|reasons|issues|conditions|variables|circumstances|causes|elements)\b|\band more\b|\betc\b", re.I)
FILLER_PHRASES = ("slow and steady", "here is the catch", "here's the catch", "that is not it", "that's not it", "think of it as",
                  "long story short", "in other words", "simply put", "think soft", "thing is")
CONTRACTION = re.compile(r"\b\w+'(?:s|t|re|ve|ll|d|m)\b", re.I)
META_LABEL = re.compile(r"(?:^|(?<=[.!?]\s))(?:my verdict|the verdict|verdict|the takeaway|takeaway|bottom line|pro tip|fun fact|key point)\s*[:\u2014-]", re.I)
# A source named in the voice-over ("AWS says so", "Stripe's blog calls that bad"): the citation belongs on screen, in the scene's source chip.
ATTRIBUTION = re.compile(r"\b(?:blog|docs|documentation|doc|paper|spec)(?:'s)?\s+(?:says?|calls?|warns?|states?|notes?|recommends?)\b"
                         r"|\b[A-Z][A-Za-z0-9]+(?:\s[A-Z][A-Za-z0-9]+)?\s+(?:says|warns|states|recommends)\b|\b(?:says|said) so\b|\baccording to\b")
UNCONTRACTED = re.compile(r"\b(?:do|does|did|is|are|was|were|has|have|had|will|would|could|should) not\b|\bcannot\b", re.I)
VAGUE_QUALITY = re.compile(r"\b(?:real|proper|actual|right)\s+(?:\w+\s+)?(?:work|tools?|checks?|way|solution|fix|protection|security|answer)\b", re.I)


def _hook_bigrams(text: str) -> set[tuple[str, str]]:
    """Adjacent content-word pairs (stemmed, within a sentence), leaving out names (two capitalised words) and numbers."""
    found: set[tuple[str, str]] = set()
    for sentence in re.split(r"(?<=[.!?\u2026])\s+", text):
        tokens = re.findall(r"[A-Za-z0-9']+", sentence)
        content = [(token.casefold().strip("'"), index > 0 and token[:1].isupper() or token.isupper() and len(token) > 1)
                   for index, token in enumerate(tokens) if token.casefold() not in STOPWORDS]
        stems = [(w[:-1] if len(w) > 4 and w.endswith("s") and not w.endswith("ss") else w, cap) for w, cap in content if w and not w.isdigit()]
        for (a, cap_a), (b, cap_b) in zip(stems, stems[1:]):
            if not (cap_a and cap_b):
                found.add((a, b))
    return found


def loop_reads_as(package) -> str:
    """The last line followed by the first line, as the loop will sound. Read it: an open last line must join line 1 into one sentence."""
    scenes = package.reference_short.scenes
    last, first = scenes[-1].vo.strip(), scenes[0].vo.strip()
    if not last or not first:
        return ""
    word = first.split()[0].strip(".,;:!?\"'()")
    # A name keeps its capital: it is capitalised in other lines and never written in lower case.
    capitalised_elsewhere = any(re.search(rf"\b{re.escape(word)}\b", scene.vo) for scene in scenes[1:])
    seen_lower = any(re.search(rf"\b{re.escape(word.lower())}\b", scene.vo) for scene in scenes)
    joined_first = first if (word.isupper() or word == "I" or (capitalised_elsewhere and not seen_lower)) else first[0].lower() + first[1:]
    return f"{last} {joined_first}"


def _int_words(n: int) -> str:
    if n < 20:
        return _ONES[n]
    if n < 100:
        return _TENS[n // 10] + (" " + _ONES[n % 10] if n % 10 else "")
    if n < 1000:
        return _ONES[n // 100] + " hundred" + (" " + _int_words(n % 100) if n % 100 else "")
    if n < 1_000_000:
        return _int_words(n // 1000) + " thousand" + (" " + _int_words(n % 1000) if n % 1000 else "")
    return str(n)


def _spoken_forms(token: str) -> set[str]:
    """How a figure on screen may be said aloud: the digits, or the words ('200' -> 'two hundred', '100' also 'a hundred')."""
    clean = token.replace(",", "")
    forms = {clean}
    whole, _, fraction = clean.partition(".")
    if whole.isdigit():
        words = _int_words(int(whole))
        if fraction.isdigit():
            words += " point " + " ".join(_ONES[int(d)] for d in fraction)
        forms.add(words)
        if not fraction and int(whole) in (100, 1000):
            forms.add("a " + words.split(" ", 1)[1])
    return forms


def _display_texts(scene) -> list[str]:
    """Every string the viewer reads in a scene (not the caption, which repeats the narration)."""
    texts: list[str] = []
    for name in ("heading", "headline", "subline", "before", "after", "before_label", "after_label"):
        value = getattr(scene, name, None)
        if isinstance(value, str):
            texts.append(value)
        elif isinstance(value, (tuple, list)):
            texts += [item for item in value if isinstance(item, str)]
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            texts.append(f"{value:g}")
    for name in ("chips", "nodes", "items"):
        texts += [item for item in (getattr(scene, name, ()) or ()) if isinstance(item, str)]
    texts += [line.text for line in (getattr(scene, "lines", ()) or ()) if hasattr(line, "text")]
    visual = getattr(scene, "visual", None)
    if visual is not None and getattr(visual, "kind", "") == "code":
        texts += list(visual.lines)
    return texts


def naturalness_problems(package) -> list[str]:
    """Advisory notes on narration that reads as machine-written. Empty means nothing to flag."""
    scenes = package.reference_short.scenes
    notes: list[str] = []
    opening = scenes[0].vo.strip()
    first_sentences = [s for s in re.split(r"(?<=[.!?…])\s+", opening) if s]
    named = [w for sentence in first_sentences for w in sentence.split()[1:]
             if JARGON.fullmatch(w.strip(".,;:!?\"'()")) or w[:1].isupper()]  # a capital after the first word of a sentence names something
    scale = re.search(r"\b(one|millions?|billions?|thousands?|hundreds?|zero|never|every|\d+)\b", opening, re.I)
    if not _numbers(opening) and not named and not scale:
        notes.append("the opening has no number and no named thing; lead with a specific figure or a named product, not an abstraction")
    if len(first_sentences) >= 2:
        a, b = ({word.strip(".'") for word in _content(sentence)} for sentence in first_sentences[:2])
        if len(a) >= 3 and len(b) >= 3 and len(a & b) / min(len(a), len(b)) >= .6:
            notes.append(f"the opening says the same idea twice ({first_sentences[0]!r} then {first_sentences[1]!r}); keep one and spend the other on a new fact")
    said_so_far = ""
    for index, scene in enumerate(scenes, 1):
        # A figure counts as explained when this scene or an earlier one says it: the running example is introduced once.
        said_so_far += " " + re.sub(r"(?<!\d)\.|\.(?!\d)|[^\w.' ]", " ", scene.vo.lower().replace(",", "")) + " "
        spoken = said_so_far
        shown: list[str] = []
        for text in _display_texts(scene):
            shown += [token.rstrip(",") for token in ON_SCREEN_NUMBER.findall(VERSION_NUMBER.sub(" ", text)) if token.rstrip(",") not in {"0", ""}]  # a counter that starts at 0 is not a spoken figure
        missing = sorted({token for token in shown if not any(f" {form} " in spoken for form in _spoken_forms(token))})
        if missing:
            notes.append(f"scene {index} shows {', '.join(missing)} on screen but the narration never says it; say the figure or use the example the narration already explains")
        lowered = " " + re.sub(r"[^\w' ]", " ", scene.vo.casefold()) + " "
        vague = VAGUE_OTHER.search(scene.vo)
        if vague:
            notes.append(f"scene {index} says {vague.group(0)!r} without naming them; name the factors or cut the line")
        hits = [phrase for phrase in FILLER_PHRASES if f" {phrase} " in lowered]
        if hits:
            notes.append(f"scene {index} has filler {hits}; replace it with a concrete fact or cut it")
        label = META_LABEL.search(scene.vo)
        if label:
            notes.append(f"scene {index} opens with a reviewer's label ({label.group(0).strip()!r}); a narrator just says the line")
        cited = ATTRIBUTION.search(scene.vo)
        if cited:
            notes.append(f"scene {index} names its source in the voice-over ({cited.group(0)!r}); put the citation in the source chip and keep the voice for the fact, unless the citation is the surprise")
        vague_quality = VAGUE_QUALITY.search(scene.vo)
        if vague_quality:
            notes.append(f"scene {index} says {vague_quality.group(0)!r}; name the actual tool, setting or step instead of calling it real or proper")
    stiff = [str(i) for i, scene in enumerate(scenes, 1) if UNCONTRACTED.search(scene.vo)]
    if stiff:
        notes.append(f"scenes {', '.join(stiff)} use stiff uncontracted forms ('will not', 'is not'); write how it is spoken ('won't', 'isn't')")
    hook = _hook_bigrams(scenes[0].vo)
    for index, scene in enumerate(scenes[1:-1], 2):
        shared = sorted(hook & _hook_bigrams(scene.vo))
        if shared:
            notes.append(f"scene {index} restates the hook's idea ('{' '.join(shared[0])}'); say the thesis once in the hook and once in the loop line, and spend this scene on a new fact or figure")
    per_scene = [{n.replace(",", "") for n in _numbers(scene.vo)} for scene in scenes]
    if not any(per_scene):
        notes.append("the narration has no figure at all; introduce the running example with concrete values early (for example 'set 100 a second, burst 200')")
    elif not any(sum(number in figures for figures in per_scene) >= 2 for number in set().union(*per_scene)):
        notes.append("no figure is carried through more than one scene; pick one example with concrete values and reuse it, instead of one-off figures")
    for index, scene in enumerate(scenes[1:-1], 2):
        sentences = [x for x in re.split(r"(?<=[.!?\u2026])\s+", scene.vo.strip()) if x]
        for earlier, later in zip(sentences, sentences[1:]):
            shared = {w.strip(".'") for w in _content(earlier) if len(w.strip(".'")) >= 5} & {w.strip(".'") for w in _content(later) if len(w.strip(".'")) >= 5}
            stems = {w[:-1] if w.endswith("s") else w for w in shared}
            if len(later.split()) <= 4 and stems:   # a slogan is short; a five-word sentence that reuses a noun is usually an explanation
                notes.append(f"scene {index} echoes itself ({later.strip()!r} repeats '{sorted(stems)[0]}' from the sentence before); cut the slogan and spend the words on a fact")
                break
    return notes + spoken_craft_problems(package)


# --- P5 (script audit): faults found by reading the rate-limit Short aloud, all advisory ---------------------------------
CONTRAST_SLOGAN = re.compile(r",\s+not\s+(?:a|an|the|\w+)\b", re.I)                      # "a speed bump, not a wall", "soft, not hard"
CLOSING_FILLER = ("now you know", "now you understand", "so remember", "in conclusion", "to sum up", "to recap", "that's all", "that is all")
CONTRACTABLE = re.compile(r"\b(?:that|here|there|it|what) is\b(?! not)|\b(?:you|we|they) (?:are|will)\b", re.I)   # "Here is the catch" -> "Here's"
SUBJECT_WORDS = 4          # the words at the start of a sentence that name what it is about
SUBJECT_REPEAT_SCENES = 5  # the same subject noun opening sentences in this many scenes reads as a list of definitions (tuned on 8 scripts: advisory)


def _sentences(text: str) -> list[str]:
    return [x for x in re.split(r"(?<=[.!?\u2026])\s+", text.strip()) if x]


def spoken_craft_problems(package) -> list[str]:
    """Advisory notes from the forensic audit of the rate-limit Short (docs/original-script-audit.md). Empty means nothing to flag.

    Each rule is a proxy for something a listener hears: the same slogan frame again and again, one noun starting
    sentence after sentence (documentation voice), a script with no contractions, 'Here is the catch' where a person
    says 'Here's', and a closing line that only announces that the lesson is over.
    """
    scenes = package.reference_short.scenes
    notes: list[str] = []
    slogans = [(i, s) for i, scene in enumerate(scenes, 1) for s in _sentences(scene.vo) if CONTRAST_SLOGAN.search(s)]
    if len(slogans) >= 3:
        where = ", ".join(sorted({str(i) for i, _ in slogans}, key=int))
        notes.append(f"{len(slogans)} sentences use the 'X, not Y' slogan frame (scenes {where}); keep the one that carries the thesis and say the others as plain facts")
    subjects: dict[str, set[int]] = {}
    topic_words = {w.strip(".'").casefold() for w in scenes[0].vo.split()}   # the topic's own noun is named in the hook and may recur
    for i, scene in enumerate(scenes, 1):
        for sentence in _sentences(scene.vo):
            for word in {w.strip(".'") for w in _content(" ".join(sentence.split()[:SUBJECT_WORDS]))}:
                stem = word[:-1] if word.endswith("s") and not word.endswith("ss") else word
                if len(stem) >= 5 and not stem.isdigit() and stem not in topic_words and word not in topic_words:
                    subjects.setdefault(stem, set()).add(i)
    for stem, where in sorted(subjects.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        if len(where) >= SUBJECT_REPEAT_SCENES:
            notes.append(f"'{stem}' starts a sentence in {len(where)} scenes ({', '.join(map(str, sorted(where)))}); it reads like a list of definitions, so make the viewer or an action the subject")
            break
    words = sum(len(scene.vo.split()) for scene in scenes)
    if words >= 100 and not any(CONTRACTION.search(scene.vo) for scene in scenes):
        notes.append(f"no contraction in {words} words; a person says 'it's', 'that's', 'doesn't' (read it aloud: the voice sounds like a manual)")
    stiff = [str(i) for i, scene in enumerate(scenes, 1) if CONTRACTABLE.search(scene.vo)]
    if stiff:
        notes.append(f"scenes {', '.join(stiff)} say 'that is' / 'here is' / 'you are'; write 'that's', 'here's', 'you're' the way it is spoken")
    closing = " ".join(scene.vo.casefold() for scene in scenes[-2:])
    hit = next((phrase for phrase in CLOSING_FILLER if phrase in closing.replace("\u2019", "'")), None)
    if hit:
        notes.append(f"the ending says {hit!r}; end on the action or consequence the viewer takes away, not on an announcement that the lesson is over")
    return notes


def rewrite_keeps_evidence(original: dict, rewrite: dict) -> list[str]:
    """A rewrite is only a rewrite if every claim id, source id and figure of the original survives. Both arguments are fixture dicts."""
    problems: list[str] = []
    claims = {c for scene in rewrite["scenes"] for c in scene.get("claim_ids", [])}
    sources = {s for scene in rewrite["scenes"] for s in scene.get("source_ids", [])}
    for scene in original["scenes"]:
        problems += [f"claim {c} of {scene['scene_id']} is no longer cited" for c in scene.get("claim_ids", []) if c not in claims]
    problems += [f"source {s} is no longer used" for s in sorted({s for sc in original["scenes"] for s in sc.get("source_ids", [])}) if s not in sources]
    spoken = " ".join(scene["narration"] for scene in rewrite["scenes"])
    for figure in sorted({n for scene in original["scenes"] for n in _numbers(scene["narration"])}):
        if figure not in _numbers(spoken):
            problems.append(f"the figure {figure} was dropped")
    known = {claim["claim_id"] for claim in original["claims"]}
    problems += [f"claim {c} is not one of the original's claims" for c in sorted(claims - known)]
    return problems


def _rhythm(spoken: list[str]) -> dict:
    sentences = [len(s.split()) for text in spoken for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]
    words = sum(len(text.split()) for text in spoken) or 1
    mean = sum(sentences) / len(sentences) if sentences else 0
    spread = (sum((n - mean) ** 2 for n in sentences) / len(sentences)) ** .5 if sentences else 0
    return {"sentence_length_variation": round(spread / mean, 2) if mean else 0.0,
            "contractions_per_100_words": round(100 * sum(len(CONTRACTION.findall(text)) for text in spoken) / words, 1)}


def script_scorecard(package) -> dict:
    """Heuristic review signals for comparing versions of the writer. Not a prediction of views or retention."""
    spoken = [scene.vo for scene in package.reference_short.scenes]
    counts = [len(_numbers(text)) for text in spoken]
    jargon = [_jargon(text) for text in spoken]
    middle = spoken[1:-1] or spoken
    sentences = [s for text in spoken for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]
    firsts = [_words(text)[0] for text in spoken if _words(text)]
    words = sum(len(text.split()) for text in spoken)
    return {
        "scenes": len(spoken), "words": words,
        "numbers_total": sum(counts), "numbers_max_in_a_scene": max(counts, default=0),
        "version_numbers": sum(len(VERSION_NUMBER.findall(text)) for text in spoken),
        "technical_terms_distinct": len(set().union(*jargon)) if jargon else 0,
        "viewer_address_share": round(sum(any(w in VIEWER_WORDS for w in _words(text)) for text in middle) / len(middle), 2),
        "distinct_openings_share": round(len(set(firsts)) / len(firsts), 2) if firsts else 1.0,
        "avg_words_per_sentence": round(words / max(1, len(sentences)), 1),
        "fact_dump_problems": len(fact_dump_problems(package)),
        "naturalness_notes": naturalness_problems(package), "loop_reads_as": loop_reads_as(package), **_rhythm(spoken),
        # M-AU2: scorecard-only (not a hard gate — a forced minimum risks an awkward, tacked-on
        # cue just to satisfy a rule). The prompt's DELIVERY CUES section sets its own ceiling
        # (at most 4 tags/scene, 2 stress words/scene, 2 whispers total); this just counts what
        # actually landed, so "the first live job used none" (M-AU2's finding) is visible without
        # an operator having to open content_package.json and count tags by hand.
        "delivery_cues_total": sum(len(getattr(scene, "cues", ()) or ()) for scene in package.reference_short.scenes),
    }


# --- Repair-loop helpers: dict-level checks that work on a draft that does not validate yet -----------------------
_TAGS = re.compile(r"\[(?:pause(?:\s+[0-9.]+)?|breath|whisper|/whisper)\]", re.I)


def _scene_vo(draft: dict, index: int) -> str:
    scene = draft["reference_short"]["scenes"][index]
    text = scene.get("vo") or draft["script_sections"][index]["narration"]
    return _TAGS.sub(" ", text).replace("*", "")


def heading_repeats(heading: str, narration: str) -> bool:
    words = _content(heading)
    return len(words) >= 3 and sum(word in set(_content(narration)) for word in words) / len(words) >= .8


def display_preflight(draft: dict, ending: str = "loop") -> list[str]:
    """The display-text rules that kept rejecting drafts one group at a time, checked together on the raw draft."""
    problems: list[str] = []
    try:
        scenes = draft["reference_short"]["scenes"]
        for index, scene in enumerate(scenes):
            heading = scene.get("heading")
            if isinstance(heading, str) and 0 < index < len(scenes) - 1 and heading_repeats(heading, _scene_vo(draft, index)):
                problems.append(f"scene {index + 1} heading {heading!r} repeats the narration; use a two-to-four-word label in different words")
            if scene.get("template") == "terminal":
                for line in scene.get("lines", ()):
                    total = len(line.get("text", "")) + (2 if line.get("kind") == "command" else 0)
                    if total > 30:
                        problems.append(f"scene {index + 1} terminal line {line.get('text', '')!r} is {total} characters with its prompt; at most 26, use a short illustrative command")
        for number, text in enumerate((draft.get("thumbnail_brief") or {}).get("text_options", ()), 1):
            if len(str(text).split()) > 3:
                problems.append(f"thumbnail text_option {number} {text!r} has more than three words; use two or three")
        expected = "cta" if ending == "debate" else "loop"
        if scenes and scenes[-1].get("template") != expected:
            problems.append(f"the final scene must use template {expected} for this request's {ending} ending")
    except (KeyError, IndexError, TypeError, AttributeError):
        return problems
    return problems


def normalize_headings(draft: dict) -> list[dict]:
    """Last-resort repair: shorten a heading that repeats its narration to its last two content words. Returns notes."""
    notes: list[dict] = []
    try:
        scenes = draft["reference_short"]["scenes"]
        for index, scene in enumerate(scenes):
            heading = scene.get("heading")
            if isinstance(heading, str) and 0 < index < len(scenes) - 1 and heading_repeats(heading, _scene_vo(draft, index)):
                kept = [word for word in heading.split() if word.casefold().strip(".,;:!?") not in STOPWORDS][-2:]
                if len(kept) == 2:
                    notes.append({"rule": "heading_shortened", "scene_id": scene.get("scene_id"), "from": heading, "to": " ".join(kept)})
                    scene["heading"] = " ".join(kept)
    except (KeyError, IndexError, TypeError, AttributeError):
        pass
    return notes
