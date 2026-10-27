"""Seven single-scene HyperFrames compositions for the opt-in Shorts renderer.

The production adapter uses these builders only when
``pipeline.reference_short.renderer`` is ``hyperframes``; ``pil`` remains the default.
Six templates have real-job single-scene evidence. ``terminal`` has only a labelled
SYNTHETIC Kokoro/Whisper fixture, so the path remains a prototype pending operator
review and parity with PIL's image plates and display options. See the Phase 4
implementation log for inspected artifacts and limits.
"""
