"""Exact scripts are adapted around their wording (re-cut, length-matched, or whole sentences dropped), never reworded."""
import re

from tubeforge.pipeline.exact_fit import fit_exact_script, rechunk
from tubeforge.pipeline.script_fit import spoken_words

GOOD = "\n\n".join([
    "Stop grinding hundreds of random LeetCode problems. There's a smarter way.",
    "One mock interview site checked its users' data, and problems solved only loosely predicted results.",
    "The correlation was weak, about zero point three, so it's far from a guarantee.",
    "The gains slowed past about five hundred problems, though volume still helps a little.",
    "So here's a better habit: mix up your problem types, instead of drilling one kind.",
    "In one classroom trial, mixed practice beat repetition, though that was math, not code.",
    "So treat it as an analogy, and practice spotting which pattern a question is hiding.",
    "Then rehearse out loud, because interviews are stressful in a way that solo practice isn't.",
    "In a study of forty eight students, being watched on a whiteboard raised stress.",
    "It also cut performance by more than half, compared with solving the same problems alone.",
    "So run mock interviews, and practice explaining your thinking to take the edge off.",
    "Would you rather grind another hundred problems, or rehearse out loud?"])


def words(text):
    return re.findall(r"[\w'’-]+", text.lower())


def test_a_script_that_already_fits_is_left_exactly_as_written():
    fit = fit_exact_script(GOOD, 60)
    assert fit.text == GOOD and fit.length_s == 60 and not fit.changed


def test_long_scenes_are_split_without_changing_a_word():
    long_block = ("Interviewing is stressful because you are watched while you think, and that pressure changes how you perform, "
                  "so practising out loud with a friend makes the real thing feel far less strange when it finally arrives.")
    fit = fit_exact_script(GOOD + "\n\n" + long_block, 60)
    scenes = fit.text.split("\n\n")
    assert all(8 <= spoken_words(scene) <= 15 for scene in scenes), [spoken_words(s) for s in scenes]
    assert words(fit.text) == words(GOOD + " " + long_block)                    # same words, same order
    assert any("Re-cut" in note for note in fit.notes)


def test_tiny_scenes_join_a_neighbour():
    fit = fit_exact_script("Short one here.\n\nAnother short line follows it right after that point.\n\n" + "\n\n".join(GOOD.split("\n\n")[:10]), 60)
    scenes = fit.text.split("\n\n")
    assert all(spoken_words(s) >= 8 for s in scenes)
    assert words(fit.text).count("short") >= 2


def test_video_length_follows_the_script_instead_of_failing_it():
    twelve = ["Twelve plain words fill this line so counting stays really very easy."]
    extra = "\n\n".join(twelve * 20)                                               # 240 words: too long for 60 s, fine at 90 s
    fit = fit_exact_script(extra, 60)
    assert 75 <= fit.length_s <= 90 and any("Video length set to" in n for n in fit.notes)
    assert fit.text.count("Twelve plain words fill this line") == 20                           # nothing was dropped
    short = fit_exact_script("\n\n".join(twelve * 5), 90)                         # 60 words at a 90 s request
    assert short.length_s < 90 and short.length_s >= 30


def test_a_script_longer_than_the_longest_video_loses_whole_low_value_sentences_not_words():
    opening, closing = "Open with this exact hook line right here, word for word please.", "And close with this exact last line, word for word please."
    filler = [f"Sentence number {i} says something plain and ordinary about a very ordinary topic today." for i in range(40)]
    keeper = "In a study of forty eight students, being watched raised stress by more than half."
    script = "\n\n".join([opening, *filler[:20], keeper, *filler[20:], closing])
    fit = fit_exact_script(script, 60)
    assert fit.length_s == 90 and fit.text.startswith(opening) and fit.text.endswith(closing)
    assert keeper in fit.text.replace("\n\n", " ")                                # sentences with figures survive longest
    assert any(n.startswith("Too long") and "dropped" in n and "Sentence number" in n for n in fit.notes)
    kept = [s for s in re.split(r"(?<=[.!?])\s+", fit.text.replace("\n\n", " ")) if s]
    assert all(s in script for s in kept)                                         # every kept sentence is verbatim
    assert sum(spoken_words(s) for s in fit.text.split("\n\n")) <= 266


def test_rechunk_never_invents_or_loses_words():
    blocks = ["One two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty.", "Tiny."]
    scenes = rechunk(blocks)
    assert words(" ".join(scenes)) == words(" ".join(blocks))


def test_random_scripts_keep_every_word_in_order_and_fit_the_layout():
    """Property check (seeded): fitting never rewords; scenes stay 8-15 words; length stays 30-90 s."""
    import random
    import re
    from tubeforge.pipeline.exact_fit import fit_exact_script
    from tubeforge.pipeline.script_fit import spoken_words
    rng = random.Random(7)
    vocab = 'the server cache request fast slow and but so because when users 40 percent Redis Amazon scales data keeps pages load quickly every time it fails then returns'.split()

    def sentence(n):
        words = [rng.choice(vocab) for _ in range(n)]
        if rng.random() < .4 and n > 6:
            words.insert(rng.randint(3, n - 3), 'and')
        return ' '.join(words).capitalize() + rng.choice('.!?')
    for _ in range(300):
        blocks = ['  '.join(sentence(rng.randint(2, 40)) for _ in range(rng.randint(1, 4))) for _ in range(rng.randint(1, 14))]
        script = '\n\n'.join(blocks)
        fitted = fit_exact_script(script, rng.choice([30, 45, 60, 90]))
        scenes = fitted.text.split('\n\n')
        if not any('dropped' in note for note in fitted.notes):
            assert re.sub(r'\s+', ' ', ' '.join(scenes)).split() == re.sub(r'\s+', ' ', script).split()
        assert all(spoken_words(scene) <= 15 for scene in scenes) and 30 <= fitted.length_s <= 90
