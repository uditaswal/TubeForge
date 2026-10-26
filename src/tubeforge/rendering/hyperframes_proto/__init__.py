"""Prototype: one reference-short scene template (``hook``) rendered through HyperFrames
instead of the PIL compositor in ``rendering/shorts``.

**Status: prototype, not wired into production rendering.** It proves the technical chain
(Python scene data -> a generated HyperFrames HTML/GSAP composition -> a real render on this
host -> muxed with the already-mastered audio -> the existing QA pipeline) for one template,
with real content, real word-level caption timing and a real inspected artifact
(video-quality review §4.2-§4.3, phase 4). The other six templates (``big_stat``,
``before_after``, ``flow``, ``checklist``, ``terminal``, ``cta``/``loop``) are not built —
each follows the same pattern (see ``compose.py``'s module docstring) and is the next,
now-proven slice of work, not a redesign.

Nothing here runs as part of a real job: ``pipeline.reference_short`` and ``pipeline.orchestrator``
are untouched, and the existing PIL renderer remains the only one a production render uses.
"""
