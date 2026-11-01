"""Automatic pronunciation check: compare what the voice was told to say with what a speech model hears.

After synthesis the local Whisper model transcribes each voice group; words it cannot recover (acronyms,
product names, odd numbers) are reported, mapped back to the display words the writer used. The check is
advisory: it never fails a job, and a missing model simply skips it. Pure functions here are independent of
the model so they can be tested with a fake transcriber.
"""
from __future__ import annotations

import difflib
import re
from collections.abc import Callable, Sequence

VERSION = "pronunciation-v1"
WRITTEN_MIN_SIMILARITY = 0.88  # heard text must match the written form this closely to excuse a spoken-form miss
MIN_SIMILARITY = 0.72          # below this letter-level similarity a differing chunk is a suspect
MIN_LETTERS = 3                # ignore tiny differences such as "a" / "uh"
_SMALL = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
          "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen")
_TENS = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")


def _number_words(value: int) -> str:
    if value < 20:
        return _SMALL[value]
    if value < 100:
        return _TENS[value // 10] + (" " + _SMALL[value % 10] if value % 10 else "")
    if value < 1000:
        return _SMALL[value // 100] + " hundred" + (" " + _number_words(value % 100) if value % 100 else "")
    if value < 1_000_000:
        return _number_words(value // 1000) + " thousand" + (" " + _number_words(value % 1000) if value % 1000 else "")
    return " ".join(_SMALL[int(c)] for c in str(value))


def normalize(text: str) -> list[str]:
    """Lower-case word tokens with digits spoken out, so "93" and "ninety three" compare equal."""
    text = text.replace("’", "'").lower()
    text = re.sub(r"\$(\d[\d,]*)", lambda m: m.group(1).replace(",", "") + " dollars", text)   # "$12" is read as "twelve dollars"
    text = text.replace("%", " percent ")
    text = re.sub(r"\d+", lambda m: " " + (_number_words(int(m.group())) if len(m.group()) <= 6 else
                                           " ".join(_SMALL[int(c)] for c in m.group())) + " ", text)
    return re.findall(r"[a-z']+", text.replace("-", " "))


def expected_tokens(spoken_text: str) -> list[tuple[str, int]]:
    """(normalised token, index of the whitespace-separated spoken word it came from)."""
    result: list[tuple[str, int]] = []
    for index, word in enumerate(spoken_text.split()):
        result.extend((token, index) for token in normalize(word))
    return result


def compare(expected: Sequence[tuple[str, int]], heard_text: str, *, min_similarity: float = MIN_SIMILARITY) -> dict:
    """Align expected against heard tokens and list the chunks whose letters differ too much."""
    exp = [token for token, _ in expected]
    heard = normalize(heard_text)
    matcher = difflib.SequenceMatcher(None, exp, heard, autojunk=False)
    suspects: list[dict] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag not in {"replace", "delete"}:
            continue
        chunk_expected, chunk_heard = exp[i1:i2], heard[j1:j2]
        letters = "".join(chunk_expected)
        if len(letters) < MIN_LETTERS:
            continue
        similarity = difflib.SequenceMatcher(None, letters, "".join(chunk_heard)).ratio() if chunk_heard else 0.0
        if similarity < min_similarity:
            suspects.append({"expected": " ".join(chunk_expected), "heard": " ".join(chunk_heard) or "(nothing)",
                             "similarity": round(similarity, 2),
                             "spoken_indices": sorted({expected[k][1] for k in range(i1, i2)})})
    matched = sum(block.size for block in matcher.get_matching_blocks())
    return {"match_ratio": round(matched / len(exp), 3) if exp else 1.0, "suspects": suspects, "heard": " ".join(heard)}


def display_words_for(spoken_indices: Sequence[int], display_spans: Sequence[Sequence[int]], display_words: Sequence[str]) -> list[str]:
    """Display words whose spoken span contains any of the suspect spoken indices."""
    found: list[str] = []
    for index, (first, end) in enumerate(display_spans):
        if any(first <= i < end for i in spoken_indices) and index < len(display_words):
            found.append(display_words[index].strip(".,;:!?\"'()"))
    return found


def display_tokens(display_words: Sequence[str]) -> list[tuple[str, int]]:
    """Normalised tokens of the *written* form (e.g. "JNDI" -> "jndi", "2.15.0" -> "two fifteen zero"), with display indices."""
    result: list[tuple[str, int]] = []
    for index, word in enumerate(display_words):
        result.extend((token, index) for token in normalize(word))
    return result


def check_group(*, spoken_text: str, display_words: Sequence[str], display_spans: Sequence[Sequence[int]],
                transcribe: Callable[[], str], min_similarity: float = MIN_SIMILARITY) -> dict:
    """One voice group: ``transcribe()`` returns the recognised text of its audio.

    Speech models write what they recognise in its *written* form (an acronym spoken letter by letter comes back
    as "jndi", a year as "two thousand thirteen"). A word is therefore only a suspect when the heard text matches
    neither the spoken form nor the written form of that word.
    """
    heard = transcribe()
    by_spoken = compare(expected_tokens(spoken_text), heard, min_similarity=min_similarity)
    # Short acronyms score high on loose letter overlap ("api" vs "pi" is 0.8), so the written-form match is stricter.
    by_written = compare(display_tokens(display_words), heard, min_similarity=WRITTEN_MIN_SIMILARITY)
    written_bad = {index for suspect in by_written["suspects"] for index in suspect["spoken_indices"]}  # display indices here
    confirmed, seen = [], set()
    for suspect in by_spoken["suspects"]:
        words = display_words_for(suspect.pop("spoken_indices"), display_spans, display_words)
        indices = {i for i, word in enumerate(display_words) if word.strip(".,;:!?\"'()") in words}
        if indices and not (indices & written_bad):
            continue                                   # heard as the written form: fine
        key = (tuple(words), suspect["expected"])
        if key in seen:
            continue
        seen.add(key)
        suspect["display"] = words
        confirmed.append(suspect)
    return {"match_ratio": max(by_spoken["match_ratio"], by_written["match_ratio"]), "suspects": confirmed, "heard": by_spoken["heard"]}


def transcribe_with(model, audio_path, *, ffmpeg: str = "ffmpeg") -> str:
    """Transcribe a short WAV with an already-loaded faster-whisper model (greedy, no context)."""
    import subprocess

    import numpy as np
    decoded = subprocess.run([ffmpeg, "-v", "error", "-i", str(audio_path), "-ar", "16000", "-ac", "1", "-f", "f32le", "pipe:1"],
                             check=True, capture_output=True, timeout=60).stdout
    audio = np.frombuffer(decoded, dtype="<f4").copy()
    segments, _ = model.transcribe(audio, language="en", beam_size=1, temperature=0.0,
                                   condition_on_previous_text=False, without_timestamps=True)
    return " ".join(segment.text.strip() for segment in segments)
