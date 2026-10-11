---
name: yt-script
description: >-
  Write a YouTube video script from a raw idea - hook options off 21
  formulas, scored, then the full spoken script with the retention beats
  marked. Use whenever the user wants a video script, a hook, an opening
  line, "what should I say", "write my next video", or is about to record
  and does not have the first fifteen seconds yet.
---

# yt-script

One idea into a script somebody finishes.

Two tools live in this folder and both actually run. Use them. Do not eyeball the hook.

```bash
python3 hookscore.py hooks.txt              # rank your hook options
python3 hookscore.py --hook "one line"      # score a single one
```

## Before you write

1. Use TubeForge's `pipeline.codex.voice_profiles` for the selected channel identity.
   Missing profiles use the documented default. Unattended jobs never wait for
   conversational input; interactive developers may request supplied voice examples.
2. Never invent a number, a result or a source. If a figure would strengthen it and you do not have
   one, ask for it or write the line without it.

## The shape

**The first 15 seconds is the whole job.** It does three things or the video leaks: confirm the
click the title promised, open a question the viewer cannot close, and prove the payoff exists.

1. **Hook.** Write FIVE against [the 21 formulas](hooks.json), run them through `hookscore.py`,
   keep the top two, and show the user both with their scores. Never hand over one hook.
2. **The turn** (0:15-0:45). Say what the video is going to do, in one sentence, and start doing it.
   No channel intro, no "before we get started", no subscribe pitch. Those are the single most
   common cause of the 0:30 cliff.
3. **The body.** One idea per beat. Mark each beat with what is ON SCREEN, not just what is said -
   a talking head with nothing to look at is a podcast.
4. **The payoff.** Deliver the thing the hook promised, explicitly, and say that you are delivering
   it: "that is the prompt, it is in the description".
5. **The close.** One ask. Not three.

## What to hand back

- the two best hooks with their scored panels
- the script, beat by beat, with `[ON SCREEN: ...]` on every beat
- the runtime estimate at 150 words per minute
- one line naming which formula the winning hook used and why it fits this idea

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


## Automation mode

For TubeForge generation, retries, field repairs and revisions, read
[the automation contract](automation.md) together with this file. It overrides
interactive handback instructions: finished audience-facing narration belongs
only in ordered `script_sections[].narration`; hooks, scores, sources and
production directions remain outside narration. The request supplies the full
brief and source packet. Do not ask unattended jobs questions.
