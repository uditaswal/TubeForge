---
name: om-thumbnail-craft
description: Critique checklist and text rules for TubeForge thumbnails (Shorts and long-form). Use when reviewing or choosing a thumbnail, never to generate images.
---

# Thumbnail craft (review checklist)

Reference for the **review** of thumbnails that TubeForge composes locally (`pipeline/thumbnail.py`,
Publishing page). It does not generate images, call any paid image API or install an MCP server. Text
is owned by `yt-package` (titles and thumbnail text, with its checker); this skill only adds a
critique pass and the rules of thumb below. It is not part of the hashed prompt resources, so editing
it needs no host redeploy.

Attribution: adapted from `skills/nanothumbnail/references/craft.md` in NanoThumbnail
(https://github.com/yoanbernabeu/NanoThumbnail, MIT, copyright 2025 Yoan Bernabeu). Reviewed for
safety on 5 Nov 2026; only this checklist was taken, none of the app or MCP code.

## Critique checklist (answer each honestly, with the real preview open)

1. **Glance test**: at phone size (about 168 x 94 px) is it obvious in under a second what the video is about?
2. **One focal point**: does the eye land on one thing?
3. **Reason to click**: stakes, surprise or a question, not a topic label.
4. **Text**: spelled right, readable, 2 to 3 words (the Publishing standard in `om-social-delivery`), never repeating the title, not covering the focal point. Numbers, stakes and contrasts work; sentences do not (title "I tried every AI coding tool" -> text "ONLY 1 WORKS").
5. **Contrast**: it must pop against both YouTube's white and dark UI.
6. **Corners**: keep the bottom-right free (duration badge); check the Shorts `safe_region` for the Shorts feed.
7. **Matches the title**: no promise the video does not deliver.
8. **Real subjects only**: a real person's likeness only from supplied photos; logos only from the approved logo set.

## Process rules

- Compare two or three candidates side by side at phone size before choosing; record why the winner won in one line.
- Change one thing per revision (text, colour, crop, emotion), so the cause of an improvement is known.
- If the same fix fails twice, change the concept instead of insisting.
- A passing checklist is a review signal, not a prediction of clicks. Never claim analytics.
