"""Build a real HyperFrames project for one ``hook`` scene (prototype; see package docstring).

Adding the next template means: write its own ``<name>.html`` string builder here, following
the same shape as ``hook_composition_html`` (the same four moves — background, scene content,
real-timed captions, one GSAP timeline — the same palette/font constants, the same contract
checks), and a ``build_<name>_project`` that writes it plus that scene's own assets. Nothing
about the caption pipeline, the font/asset vendoring or the CLI wrapper (``cli.py``) changes
per template.
"""
from __future__ import annotations

import html
import json
import shutil
from pathlib import Path

from tubeforge.rendering.shorts.icons import badge
from tubeforge.rendering.shorts.layout import CYAN, MUTED, PANEL, WHITE, caption_groups
from tubeforge.rendering.shorts.logos import logo_badge
from tubeforge.rendering.shorts.schema import Hook

ASSETS = Path(__file__).resolve().parents[2] / "assets"
FONTS = Path(__file__).resolve().parents[1] / "shorts" / "fonts"
WIDTH, HEIGHT, FPS = 1080, 1920, 30


def _word_groups(caption: str, words: list[tuple[float, float]]) -> list[dict]:
    """The same 2-3-word display groups the PIL renderer uses, mapped onto real measured
    timestamps (``words`` is one ``{start, end}`` per display token, scene-relative seconds)."""
    groups = caption_groups(caption)
    flat = [w for group in groups for w in group]
    if len(flat) != len(words):
        raise ValueError(f"caption has {len(flat)} display words but {len(words)} measured timings")
    out, cursor = [], 0
    for group in groups:
        span = words[cursor:cursor + len(group)]
        out.append({"words": list(group), "start": span[0][0], "end": span[-1][1]})
        cursor += len(group)
    return out


def hook_composition_html(scene: Hook, words: list[tuple[float, float]], duration: float) -> str:
    captions = _word_groups(scene.caption, words)
    headline_js = json.dumps([html.escape(line) for line in scene.headline])
    chips_js = json.dumps([html.escape(chip) for chip in scene.chips])
    captions_js = json.dumps(captions)
    has_badge = bool(scene.icon or scene.logo)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width={WIDTH}, height={HEIGHT}" />
<script src="assets/gsap.min.js"></script>
<style>
  @font-face {{ font-family: "Anton"; src: url("assets/Anton-Regular.ttf"); }}
  @font-face {{ font-family: "Inter"; src: url("assets/Inter-Variable.ttf"); font-weight: 100 900; }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  html, body {{ width: {WIDTH}px; height: {HEIGHT}px; overflow: hidden; background: #080f1f; }}
  #root {{ position: relative; width: 100%; height: 100%; }}
  /* A radial glow, not a full-screen linear gradient: linear gradients on dark grounds band
     under H.264 (HyperFrames look.md "Video facts"). */
  .glow {{ position: absolute; inset: -10%; background:
    radial-gradient(ellipse 60% 45% at 20% 70%, rgba(83,224,239,.10), transparent 60%),
    radial-gradient(ellipse 55% 40% at 85% 30%, rgba(121,52,239,.08), transparent 60%); }}
  .rail {{ position: absolute; top: 212px; left: 70px; right: 160px; height: 7px; display: flex; gap: 12px; }}
  .rail span {{ flex: 1; height: 7px; border-radius: 3px; background: #29374d; }}
  .rail span.on {{ background: {CYAN}; }}
  #badge {{ position: absolute; left: 50%; top: 270px; width: 220px; height: 220px; transform: translateX(-50%);
    opacity: 0; }}
  #badge img {{ width: 100%; height: 100%; }}
  #headlines {{ position: absolute; left: 60px; right: 60px; top: 500px; text-align: center; }}
  .headline {{ font-family: "Anton"; text-transform: uppercase; font-size: 124px; line-height: 1.12;
    letter-spacing: -.01em; color: {WHITE}; opacity: 0; filter: blur(8px); }}
  .headline.accent {{ color: {CYAN}; }}
  #chips {{ position: absolute; left: 90px; right: 90px; display: flex; gap: 20px; justify-content: center; }}
  .chip {{ flex: 1; max-width: 300px; height: 100px; border-radius: 14px; background: {PANEL};
    border: 1px solid rgba(83,224,239,.35); color: {MUTED}; font-family: "Inter"; font-weight: 800;
    font-size: 40px; display: flex; align-items: center; justify-content: center; text-align: center;
    padding: 0 16px; opacity: 0; transform: scale(.85); }}
  #captions {{ position: absolute; left: 40px; right: 40px; top: 1300px; text-align: center; }}
  .cap-group {{ position: absolute; left: 0; right: 0; font-family: "Anton"; text-transform: uppercase;
    font-size: 96px; line-height: 1; opacity: 0; }}
  .cap-word {{ color: {WHITE}; -webkit-text-stroke: 6px #0a0f1f; paint-order: stroke fill; }}
  .cap-word.active {{ color: {CYAN}; }}
</style>
</head>
<body>
<div id="root" class="clip" data-composition-id="hook" data-start="0" data-duration="{duration:.3f}"
     data-width="{WIDTH}" data-height="{HEIGHT}" data-fps="{FPS}">
  <div class="glow"></div>
  <div class="rail" id="rail"></div>
  <div id="badge" class="clip" data-start="0" data-duration="{duration:.3f}" data-track-index="1">
    {'<img src="assets/badge.png" alt="" />' if has_badge else ''}
  </div>
  <div id="headlines" class="clip" data-start="0" data-duration="{duration:.3f}" data-track-index="2"></div>
  <div id="chips" class="clip" data-start="0" data-duration="{duration:.3f}" data-track-index="3"></div>
  <div id="captions" class="clip" data-track-kind="captions" data-start="0" data-duration="{duration:.3f}" data-track-index="4"></div>
</div>
<script>
(function () {{
  window.__timelines = window.__timelines || {{}};
  var HEADLINES = {headline_js};
  var CHIPS = {chips_js};
  var CAPTIONS = {captions_js};
  var HAS_BADGE = {str(has_badge).lower()};

  // Progress rail: a static dash per scene is meaningless for a one-scene clip; show one on.
  var rail = document.getElementById("rail");
  var dash = document.createElement("span"); dash.className = "on"; rail.appendChild(dash);

  var tl = gsap.timeline({{ paused: true }});

  // Frame 0 is the thumbnail (HyperFrames story.md §3): the badge and the hook's own first
  // line are already on screen at t=0, not entering from nothing. Only the accent line (the
  // punchline) and chips animate in, so the clip still has motion.
  if (HAS_BADGE) {{
    tl.set("#badge", {{ opacity: 1, scale: .96 }}, 0);
    tl.to("#badge", {{ scale: 1, duration: .3, ease: "power2.out" }}, 0);
  }}

  var headlinesHost = document.getElementById("headlines");
  HEADLINES.forEach(function (line, i) {{
    var el = document.createElement("div");
    var isLast = i === HEADLINES.length - 1;
    el.className = "headline" + (isLast ? " accent" : "");
    el.textContent = line;
    headlinesHost.appendChild(el);
    if (isLast) {{
      tl.to(el, {{ opacity: 1, filter: "blur(0px)", duration: .18, ease: "power4.out" }}, (HAS_BADGE ? .35 : .05) + i * .1);
    }} else {{
      tl.set(el, {{ opacity: 1, filter: "blur(0px)" }}, 0);
    }}
  }});

  var chipsHost = document.getElementById("chips");
  CHIPS.forEach(function (label, i) {{
    var el = document.createElement("div");
    el.className = "chip"; el.textContent = label;
    chipsHost.appendChild(el);
    tl.to(el, {{ opacity: 1, scale: 1, duration: .3, ease: "back.out(1.2)" }}, .6 + HEADLINES.length * .1 + i * .06);
  }});

  var capHost = document.getElementById("captions");
  CAPTIONS.forEach(function (group, gi) {{
    var el = document.createElement("div");
    el.className = "cap-group";
    group.words.forEach(function (word, wi) {{
      var span = document.createElement("span");
      span.className = "cap-word"; span.textContent = word + (wi < group.words.length - 1 ? " " : "");
      span.dataset.wordIndex = wi;
      el.appendChild(span);
    }});
    capHost.appendChild(el);
    var start = Math.max(0, group.start - .02);
    // Clamp this group's exit to strictly before the next one's entrance, or a back-to-back
    // pair (no pause between them) briefly shows both at once (found by `hyperframes check`'s
    // content_overlap finding on a real render; captions.md: "every group ends with a hard
    // kill after its exit").
    var nextStart = gi + 1 < CAPTIONS.length ? Math.max(0, CAPTIONS[gi + 1].start - .02) : Infinity;
    var end = Math.max(start + .08, Math.min(group.end, nextStart - .01));
    tl.set(el, {{ opacity: 1 }}, start);
    tl.to(el, {{ opacity: 0, duration: .12, ease: "power2.in" }}, end - .12);
    tl.set(el, {{ opacity: 0, visibility: "hidden" }}, end);
  }});

  window.__timelines["hook"] = tl;
  tl.seek(0);
}})();
</script>
</body>
</html>
"""


def build_hook_project(scene: Hook, words: list[tuple[float, float]], duration: float, project_dir: Path) -> None:
    """Write a self-contained HyperFrames project for this one scene to ``project_dir``."""
    assets = project_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    shutil.copy(ASSETS / "hyperframes" / "gsap.min.js", assets / "gsap.min.js")
    shutil.copy(FONTS / "Anton-Regular.ttf", assets / "Anton-Regular.ttf")
    shutil.copy(FONTS / "Inter-Variable.ttf", assets / "Inter-Variable.ttf")
    if scene.icon or scene.logo:
        sprite = logo_badge(scene.logo, 220) if scene.logo else badge(scene.icon, 220)
        sprite.save(assets / "badge.png")
    (project_dir / "index.html").write_text(hook_composition_html(scene, words, duration), encoding="utf-8")
    (project_dir / "hyperframes.json").write_text(json.dumps({
        "$schema": "https://hyperframes.heygen.com/schema/hyperframes.json",
        "paths": {"blocks": "compositions", "components": "compositions/components", "assets": "assets"},
        "media": {"autoProxy": False},
    }, indent=2), encoding="utf-8")
