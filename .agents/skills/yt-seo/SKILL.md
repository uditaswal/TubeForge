---
name: yt-seo
description: >-
  Write the description, tags and search-facing text for a YouTube video,
  aimed at the query a real person types. Use for "write my description",
  "tags", "SEO", "help this video get found", "nobody is finding this".
---

# yt-seo

Search is a smaller lever than packaging and a bigger one than people think for evergreen videos.
For a video aimed at the subscriber feed, say so and spend the effort on `/yt-package` instead.

## Before you write

1. Use TubeForge's `pipeline.codex.voice_profiles` for the selected channel identity.
   Missing profiles use the documented default. Unattended jobs never wait for
   conversational input; interactive developers may request supplied voice examples.
2. Never invent a number, a result or a source. If a figure would strengthen it and you do not have
   one, ask for it or write the line without it.

## The description

- **The first two lines are the only ones anyone reads.** They show above "...more" and they are
  the search snippet. Say what the video gives them, in the words they would have typed.
- Then the link or the resource, if there is one, so it is above the fold.
- Then chapters (`/yt-chapters` writes them).
- Then the long version: what is covered, who it is for, what it assumes.

## Tags, honestly

Tags are a weak signal and YouTube has said so. Use them for disambiguation - spellings, the tool
names, the abbreviations people actually type - and stop. Fifteen is plenty. A wall of tags is not
a strategy and stuffing unrelated ones is against the terms.

## The query test

Before handing anything over, write the three search queries this video should win, and check the
title and first two description lines contain the words in those queries. If they do not, the
problem is the title, not the description.

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
