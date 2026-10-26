"""Prototype: three reference-short scene templates (``hook``, ``loop``, ``big_stat``) rendered
through HyperFrames instead of the PIL compositor in ``rendering/shorts``.

**Status: prototype, not wired into production rendering.** It proves the technical chain
(Python scene data -> a generated HyperFrames HTML/GSAP composition -> a real render on this
host -> muxed with the already-mastered audio -> the existing QA pipeline) for three templates,
with real content, real word-level caption timing and a real inspected artifact
(video-quality review §4.2-§4.3, phase 4). ``loop`` reuses ``hook``'s own composition (a
``Loop`` scene is a ``Hook`` subclass with identical fields; the PIL compositor already treats
them the same, so the last frame matches the first). ``big_stat`` is its own composition — the
one template with a genuinely new motion idea, a count-up on its newest figure, timed and eased
to match the PIL renderer's own (``motion.py``'s ``COUNT_SECONDS``/``ease_out_cubic``). The
remaining four templates (``before_after``, ``flow``, ``checklist``, ``terminal``) are not
built — each is a layout variation on the same contract (see ``compose.py``'s module docstring)
and is the next, now-proven slice of work, not a redesign.

Nothing here runs as part of a real job: ``pipeline.reference_short`` and ``pipeline.orchestrator``
are untouched, and the existing PIL renderer remains the only one a production render uses.
"""
