---
name: yt-package
description: >-
  Write and lint the title and thumbnail for a YouTube video as one pairing,
  checking truncation, duplication and vagueness before publish. Use for
  "title ideas", "what should I call this", "thumbnail text", "my CTR is
  bad", packaging, or any request to rename or repackage an existing video.
---

# yt-package

The title and the thumbnail are ONE unit. Writing them separately is why most packaging fails: the
thumbnail repeats the title, and half the click surface says the same thing twice.

```bash
python3 title.py --title "..." --thumb "AI RAN IT"
python3 title.py titles.txt            # one per line, ranked
```

## Before you write

1. Use TubeForge's `pipeline.codex.voice_profiles` for the selected channel identity.
   Missing profiles use the documented default. Unattended jobs never wait for
   conversational input; interactive developers may request supplied voice examples.
2. Never invent a number, a result or a source. If a figure would strengthen it and you do not have
   one, ask for it or write the line without it.

## Rules the tool enforces, and why

- **60 characters** is where desktop search truncates, **40** is a mobile home feed. Both are
  reported because they fail differently: a desktop cut loses the tail, a mobile cut can lose the
  subject.
- **The thumbnail must not repeat the title.** Different words, same promise.
- **Three words maximum on the thumbnail.** At feed size a fourth word is a grey smear.
- **A number, a name or a date** beats every adjective available to you.
- **Two all-caps words is the ceiling** before a title reads as spam.

## Write ten, keep two

Generate ten titles, run them all through `title.py`, show the user the top three with their scores
and the specific issue on each. For the winner, write the thumbnail brief: the expression, the
framing, the three words, and what the background has to do to hold contrast at feed size.

## The gate

Nothing here publishes. Return structured content for TubeForge’s existing script-review
status and exact-artifact dashboard approval controls. Unattended jobs never ask
conversational approval questions or bypass review and scheduled-publishing policies.

## TubeForge runtime

Resolve resources relative to this skill directory. Instructions are embedded in
bounded Codex prompts from the installed wheel; application Python executes the
reviewed scoring tools and records reports. Scores are review signals, not view
predictions. Preserve source grounding. Shorts use 9:16, 30–55 seconds, an
immediate hook and concise payoff; retain requested long-form behavior for 16:9.
Return ContentPackage fields, including scene directions/on-screen text, title,
thumbnail brief, description/tags and five hook_options. The opening sentence
must exactly match a candidate. Keep model-selected source-appropriate hooks;
show scored alternatives during dashboard review rather than inventing scores.
