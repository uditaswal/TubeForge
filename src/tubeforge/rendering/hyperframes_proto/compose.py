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
from tubeforge.rendering.shorts.layout import AMBER, CYAN, MUTED, PANEL, WHITE, caption_groups
from tubeforge.rendering.shorts.logos import logo_badge
from tubeforge.rendering.shorts.schema import BigStat, Hook

# The count-up duration + easing the PIL renderer uses for a big_stat's newest figure
# (``motion.py``'s ``COUNT_SECONDS`` and ``ease_out_cubic``, which is exactly GSAP's
# ``power3.out``) — kept here so the two renderers animate the same number at the same speed.
COUNT_SECONDS = 0.8

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


def hook_composition_html(scene: Hook, words: list[tuple[float, float]], duration: float,
                          composition_id: str = "hook") -> str:
    """Builds the ``hook`` composition; also the ``loop`` scene's, unchanged — the PIL
    compositor's own comment explains why (``rendering/shorts/layout.py``): "the loop scene
    reuses the hook composition so the last frame matches the first". ``Loop`` is a `Hook`
    subclass with identical fields (schema.py), so no scene-shape change is needed here, only
    ``composition_id`` so the two don't collide if ever placed in one multi-scene project.
    """
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
<div id="root" class="clip" data-composition-id="{composition_id}" data-start="0" data-duration="{duration:.3f}"
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

  window.__timelines["{composition_id}"] = tl;
  tl.seek(0);
}})();
</script>
</body>
</html>
"""


def build_hook_project(scene: Hook, words: list[tuple[float, float]], duration: float, project_dir: Path) -> None:
    """Write a self-contained HyperFrames project for one ``hook`` or ``loop`` scene to
    ``project_dir`` (``scene.template`` names which — both use the identical composition;
    see ``hook_composition_html``'s docstring)."""
    assets = project_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    shutil.copy(ASSETS / "hyperframes" / "gsap.min.js", assets / "gsap.min.js")
    shutil.copy(FONTS / "Anton-Regular.ttf", assets / "Anton-Regular.ttf")
    shutil.copy(FONTS / "Inter-Variable.ttf", assets / "Inter-Variable.ttf")
    if scene.icon or scene.logo:
        sprite = logo_badge(scene.logo, 220) if scene.logo else badge(scene.icon, 220)
        sprite.save(assets / "badge.png")
    (project_dir / "index.html").write_text(
        hook_composition_html(scene, words, duration, composition_id=scene.template), encoding="utf-8")
    (project_dir / "hyperframes.json").write_text(json.dumps({
        "$schema": "https://hyperframes.heygen.com/schema/hyperframes.json",
        "paths": {"blocks": "compositions", "components": "compositions/components", "assets": "assets"},
        "media": {"autoProxy": False},
    }, indent=2), encoding="utf-8")


# A Loop IS a Hook with a different template literal (schema.py) and the PIL compositor
# already treats them identically ("the loop scene reuses the hook composition so the last
# frame matches the first", layout.py). Named alias for callers building a loop scene, so
# nothing reads as a hook-only function when it builds this one too.
build_loop_project = build_hook_project


def _format_stat(value: float, unit: str) -> str:
    """Same display rule as the PIL renderer's big_stat number (``layout.py``): one decimal
    only when the value isn't a whole number."""
    text = f"{value:.1f}".rstrip("0").rstrip(".") if value != int(value) else f"{value:g}"
    return text + unit


def big_stat_composition_html(scene: BigStat, words: list[tuple[float, float]], duration: float,
                              composition_id: str = "big_stat") -> str:
    """Builds the ``big_stat`` composition: a heading, two stacked stat figures (before/after)
    each with a proportional bar, an arrow once both are on screen, and a count-up on the
    newest figure — the one genuinely new motion idea this template needs (the PIL renderer's
    own count-up, ``motion.py``'s ``COUNT_SECONDS``/``ease_out_cubic``, reproduced here with
    GSAP's numeric tween of a plain JS counter object, same duration and easing)."""
    captions = _word_groups(scene.caption, words)
    captions_js = json.dumps(captions)
    has_badge = bool(scene.icon or scene.logo)
    scale = max(scene.before, scene.after, 1)
    reveal_before, reveal_after = (words[i][0] for i in scene.reveal_words)
    before_pct = max(0.0, min(100.0, 100 * scene.before / scale))
    after_pct = max(0.0, min(100.0, 100 * scene.after / scale))
    after_text = json.dumps(_format_stat(scene.after, scene.unit))
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
  .glow {{ position: absolute; inset: -10%; background:
    radial-gradient(ellipse 60% 45% at 20% 70%, rgba(83,224,239,.10), transparent 60%),
    radial-gradient(ellipse 55% 40% at 85% 30%, rgba(121,52,239,.08), transparent 60%); }}
  .rail {{ position: absolute; top: 212px; left: 70px; right: 160px; height: 7px; display: flex; gap: 12px; }}
  .rail span {{ flex: 1; height: 7px; border-radius: 3px; background: #29374d; }}
  .rail span.on {{ background: {CYAN}; }}
  #badge {{ position: absolute; left: 50%; top: 230px; width: 140px; height: 140px; transform: translateX(-50%); }}
  #badge img {{ width: 100%; height: 100%; }}
  #heading {{ position: absolute; left: 60px; right: 60px; top: 390px; text-align: center;
    font-family: "Inter"; font-weight: 800; font-size: 56px; line-height: 1.2; color: {WHITE}; }}
  .stat {{ position: absolute; left: 90px; right: 90px; opacity: 0; transform: translateY(16px); }}
  .stat.before {{ top: 525px; }}
  .stat.after {{ top: 915px; }}
  .stat .label {{ font-family: "Inter"; font-weight: 700; font-size: 36px; color: {MUTED}; text-align: center; }}
  .stat .number {{ font-family: "Anton"; text-transform: uppercase; font-size: 128px; line-height: 1.3;
    text-align: center; }}
  .stat.before .number {{ color: {AMBER}; }}
  .stat.after .number {{ color: {CYAN}; }}
  .bar {{ height: 28px; border-radius: 10px; background: #26364d; overflow: hidden; }}
  .bar .fill {{ height: 100%; min-width: 12px; border-radius: 10px; }}
  .stat.before .bar .fill {{ background: {AMBER}; width: 0%; }}
  .stat.after .bar .fill {{ background: {CYAN}; width: 0%; }}
  #arrow {{ position: absolute; left: 50%; top: 720px; width: 30px; height: 50px; transform: translateX(-50%);
    opacity: 0; }}
  #arrow .shaft {{ position: absolute; left: 12px; top: 0; width: 6px; height: 38px; background: {CYAN}; }}
  #arrow .head {{ position: absolute; left: 0; top: 32px; border-left: 15px solid transparent;
    border-right: 15px solid transparent; border-top: 18px solid {CYAN}; }}
  #captions {{ position: absolute; left: 40px; right: 40px; top: 1300px; text-align: center; }}
  .cap-group {{ position: absolute; left: 0; right: 0; font-family: "Anton"; text-transform: uppercase;
    font-size: 96px; line-height: 1; opacity: 0; }}
  .cap-word {{ color: {WHITE}; -webkit-text-stroke: 6px #0a0f1f; paint-order: stroke fill; }}
  .cap-word.active {{ color: {CYAN}; }}
</style>
</head>
<body>
<div id="root" class="clip" data-composition-id="{composition_id}" data-start="0" data-duration="{duration:.3f}"
     data-width="{WIDTH}" data-height="{HEIGHT}" data-fps="{FPS}">
  <div class="glow"></div>
  <div class="rail" id="rail"></div>
  <div id="badge" class="clip" data-start="0" data-duration="{duration:.3f}" data-track-index="1">
    {'<img src="assets/badge.png" alt="" />' if has_badge else ''}
  </div>
  <div id="heading" class="clip" data-start="0" data-duration="{duration:.3f}" data-track-index="2">
    {html.escape(scene.heading)}
  </div>
  <div class="stat before" id="before">
    <div class="label">{html.escape(scene.before_label)}</div>
    <div class="number" id="before-number">{html.escape(_format_stat(scene.before, scene.unit))}</div>
    <div class="bar"><div class="fill" id="before-fill" style="width: {before_pct:.1f}%"></div></div>
  </div>
  <div id="arrow"><div class="shaft"></div><div class="head"></div></div>
  <div class="stat after" id="after">
    <div class="label">{html.escape(scene.after_label)}</div>
    <div class="number" id="after-number">0{html.escape(scene.unit)}</div>
    <div class="bar"><div class="fill" id="after-fill" style="width: 0%"></div></div>
  </div>
  <div id="captions" class="clip" data-track-kind="captions" data-start="0" data-duration="{duration:.3f}" data-track-index="4"></div>
</div>
<script>
(function () {{
  window.__timelines = window.__timelines || {{}};
  var CAPTIONS = {captions_js};
  var AFTER_VALUE = {scene.after!r};
  var AFTER_PCT = {after_pct!r};
  var AFTER_TEXT = {after_text};
  var AFTER_UNIT = {json.dumps(scene.unit)};

  var rail = document.getElementById("rail");
  var dash = document.createElement("span"); dash.className = "on"; rail.appendChild(dash);

  var tl = gsap.timeline({{ paused: true }});

  // Heading and icon are on screen from frame 0, like the hook's own first line (HyperFrames
  // story.md §3: frame 0 is the thumbnail); only the two stat figures are reveal-gated.
  tl.to("#before", {{ opacity: 1, y: 0, duration: .3, ease: "back.out(1.2)" }}, {reveal_before:.3f});

  // The newest figure counts up over COUNT_SECONDS with the PIL renderer's own easing
  // (ease_out_cubic === power3.out), driving both the number text and the bar width from one
  // tween so they stay in lockstep.
  tl.to("#after", {{ opacity: 1, y: 0, duration: .3, ease: "back.out(1.2)" }}, {reveal_after:.3f});
  tl.to("#arrow", {{ opacity: 1, duration: .2 }}, {reveal_after:.3f});
  var counter = {{ v: 0 }};
  tl.to(counter, {{
    v: AFTER_VALUE, duration: {COUNT_SECONDS}, ease: "power3.out",
    onUpdate: function () {{
      var shown = counter.v;
      var whole = Math.abs(shown - Math.round(shown)) < 1e-6;
      document.getElementById("after-number").textContent =
        (counter.v >= AFTER_VALUE - 1e-6) ? AFTER_TEXT : (whole ? Math.round(shown) : shown.toFixed(1)) + AFTER_UNIT;
      document.getElementById("after-fill").style.width = (AFTER_PCT * (AFTER_VALUE ? shown / AFTER_VALUE : 1)) + "%";
    }},
  }}, {reveal_after:.3f});

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
    var nextStart = gi + 1 < CAPTIONS.length ? Math.max(0, CAPTIONS[gi + 1].start - .02) : Infinity;
    var end = Math.max(start + .08, Math.min(group.end, nextStart - .01));
    tl.set(el, {{ opacity: 1 }}, start);
    tl.to(el, {{ opacity: 0, duration: .12, ease: "power2.in" }}, end - .12);
    tl.set(el, {{ opacity: 0, visibility: "hidden" }}, end);
  }});

  window.__timelines["{composition_id}"] = tl;
  tl.seek(0);
}})();
</script>
</body>
</html>
"""


def build_big_stat_project(scene: BigStat, words: list[tuple[float, float]], duration: float, project_dir: Path) -> None:
    """Write a self-contained HyperFrames project for one ``big_stat`` scene to ``project_dir``."""
    assets = project_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    shutil.copy(ASSETS / "hyperframes" / "gsap.min.js", assets / "gsap.min.js")
    shutil.copy(FONTS / "Anton-Regular.ttf", assets / "Anton-Regular.ttf")
    shutil.copy(FONTS / "Inter-Variable.ttf", assets / "Inter-Variable.ttf")
    if scene.icon or scene.logo:
        sprite = logo_badge(scene.logo, 140) if scene.logo else badge(scene.icon, 140)
        sprite.save(assets / "badge.png")
    (project_dir / "index.html").write_text(
        big_stat_composition_html(scene, words, duration, composition_id=scene.template), encoding="utf-8")
    (project_dir / "hyperframes.json").write_text(json.dumps({
        "$schema": "https://hyperframes.heygen.com/schema/hyperframes.json",
        "paths": {"blocks": "compositions", "components": "compositions/components", "assets": "assets"},
        "media": {"autoProxy": False},
    }, indent=2), encoding="utf-8")
