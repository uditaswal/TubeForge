"""Story video style: one HyperFrames composition per Short with a purpose-built picture per scene.

Design target is doc-internal/video-quality/reference/cloudflare-pingora: a big stacked headline with one
accent word, one diagram per scene built up as the narration reaches each idea, captions
underneath, nothing inside the Shorts UI rails. Scenes are laid out from their *template* and
*visual* (never from a scene number), and only text already in the approved topic is drawn:
headings, nodes, items, quotes, code lines, figures. Captured source plates are shown as a hero
card with the highlight sweeping in on the real reveal-word times; without a plate a source
quote is typeset as a labelled quote, never faked as a screenshot.
"""
from __future__ import annotations

import html
import json
import math
import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlparse

from tubeforge.rendering.hyperframes_proto import cli
from tubeforge.rendering.hyperframes_proto.compose import ASSETS, FONTS, FPS, HEIGHT, WIDTH, _word_groups
from tubeforge.rendering.shorts.encode import checked
from tubeforge.rendering.shorts.hyperframes_compose import source_treatment
from tubeforge.rendering.shorts.plates import load_manifest
from tubeforge.rendering.shorts.schema import CodeVisual, SourceVisual

BG, INK, MUTED = "#0a0b10", "#f4f6fb", "#8d93a6"
RED, AMBER, CYAN, GREEN = "#ff4d3d", "#ffb020", "#53e0ef", "#35d07f"
ACCENTS = [RED, AMBER, CYAN]

# M-S1: three layout families, picked deterministically from a short's own scene mix (never
# random), so a batch of videos has visible structural/motion variety that tracks its actual
# content instead of a fixed house style. Each family only changes accent rotation, caption
# highlight colour, and motion pacing/ease — the per-template body markup (headline, diagram,
# terminal, etc.) stays the single shared implementation below; this is deliberately not a
# second full rendering pipeline per family.
LAYOUT_FAMILIES = ("terminal_led", "cinematic_code", "walkthrough_statement")

_FAMILY_STYLE = {
    "terminal_led": {"accents": [GREEN, CYAN, AMBER], "mark": GREEN,
                      "pop_duration": .28, "pop_ease": "power4.out", "zoom_scale": 1.06},
    "cinematic_code": {"accents": [CYAN, AMBER, RED], "mark": CYAN,
                        "pop_duration": .55, "pop_ease": "power1.out", "zoom_scale": 1.16},
    "walkthrough_statement": {"accents": [RED, AMBER, CYAN], "mark": AMBER,
                               "pop_duration": .4, "pop_ease": "back.out(1.6)", "zoom_scale": 1.1},
}


def select_layout_family(topic) -> str:
    """Pick one of LAYOUT_FAMILIES from the short's own scene templates and visuals.

    Pure function of the approved script (template names + CodeVisual presence); no randomness,
    so the same topic always renders the same family. Terminal/code-heavy scripts lead with
    "terminal_led"; diagram-heavy scripts (without being terminal-led) get the slower,
    wider-panning "cinematic_code" treatment; anything else (checklists, before/after, stat
    reveals, plain statements) gets "walkthrough_statement", the default house style.
    """
    scenes = list(topic.scenes)
    if not scenes:
        return "walkthrough_statement"
    terminal = sum(1 for s in scenes if s.template == "terminal" or isinstance(getattr(s, "visual", None), CodeVisual))
    diagram = sum(1 for s in scenes if s.template == "flow")
    if terminal and terminal / len(scenes) >= 0.25:
        return "terminal_led"
    if diagram and diagram / len(scenes) >= 0.25:
        return "cinematic_code"
    return "walkthrough_statement"

CSS = f"""
@font-face {{ font-family: Anton; src: url("assets/Anton-Regular.ttf"); }}
@font-face {{ font-family: Inter; src: url("assets/Inter-Variable.ttf"); font-weight: 100 900; }}
* {{ box-sizing:border-box; margin:0; padding:0; }}
html,body {{ width:{WIDTH}px; height:{HEIGHT}px; overflow:hidden; background:{BG}; }}
#root {{ position:relative; width:100%; height:100%; background:{BG}; }}
.glow {{ position:absolute; inset:0; background:radial-gradient(ellipse 70% 38% at 50% 28%,rgba(255,77,61,.16),transparent 70%),radial-gradient(ellipse 60% 30% at 50% 85%,rgba(83,224,239,.07),transparent 70%); }}
.scene {{ position:absolute; left:0; top:0; width:{WIDTH}px; height:1290px; opacity:0; }}
.h1 {{ position:absolute; left:60px; right:130px; top:150px; font-family:Anton; font-weight:400; line-height:1.0; text-transform:uppercase; color:{INK}; letter-spacing:1px; }}
.card {{ position:absolute; background:#141724; border:2px solid #262b40; border-radius:28px; box-shadow:0 22px 60px rgba(0,0,0,.6); }}
.mono {{ font-family:'DejaVu Sans Mono',monospace; font-weight:700; }}
.pill {{ position:absolute; height:64px; padding:0 30px; border-radius:32px; display:flex; align-items:center; font:800 36px/1.2 Inter; white-space:nowrap; }}
.note {{ position:absolute; left:60px; right:130px; font:700 32px/1.3 Inter; color:{MUTED}; }}
#captions {{ position:absolute; left:40px; right:40px; top:1330px; }}
.cap-group {{ position:absolute; left:0; right:0; text-align:center; font:104px/1 Anton; text-transform:uppercase; opacity:0; }}
.cap-word {{ color:{INK}; -webkit-text-stroke:7px {BG}; paint-order:stroke fill; position:relative; display:inline-block; }}
.cap-word .mark {{ position:absolute; left:2px; right:2px; bottom:-10px; height:8px; background:#ffb020; border-radius:4px; transform:scaleX(0); transform-origin:0 50%; }}
"""

def _pop_js(duration: float, ease: str) -> str:
    """The pop-in helper, with this layout family's default duration/ease baked in
    (a call site can still override duration via o.d, as before)."""
    return ("function pop(sel,t,o){o=o||{};tl.fromTo(sel,{opacity:0,x:o.x||0,y:o.y===undefined?40:o.y,scale:o.s||.92},"
            f"{{opacity:1,x:0,y:0,scale:1,duration:o.d||{duration},ease:'{ease}'}},t);}}")


def _heading(text: str | tuple[str, ...], accent: str, *, top: int = 150, size: int | None = None) -> str:
    """Stacked uppercase headline; the last line takes the accent colour."""
    lines = list(text) if isinstance(text, tuple | list) else _split(text)
    size = size or (138 if max(len(l) for l in lines) <= 13 else 112 if max(len(l) for l in lines) <= 17 else 92)
    rows = [html.escape(l) for l in lines]
    rows[-1] = f'<span style="color:{accent}">{rows[-1]}</span>'
    return f'<div class="h1" style="top:{top}px;font-size:{size}px">{"<br>".join(rows)}</div>'


def _split(text: str) -> list[str]:
    words = text.split()
    if len(words) < 2:
        return words or [""]
    best, cut = 10 ** 9, 1
    for k in range(1, len(words)):
        gap = abs(len(" ".join(words[:k])) - len(" ".join(words[k:])))
        if gap < best:
            best, cut = gap, k
    return [" ".join(words[:cut]), " ".join(words[cut:])]


def _domain(url: str | None) -> str | None:
    host = urlparse(url or "").hostname
    return host.removeprefix("www.") if host else None


def _caption_groups(scene, words: list[tuple[float, float]]) -> list[dict]:
    """Caption groups plus per-word times and key-word flags (the scene's reveal words)."""
    groups = _word_groups(scene.caption, words)
    keys, cursor = set(scene.reveal_words), 0
    for group in groups:
        count = len(group["words"])
        group["times"] = [[round(start, 3), round(end, 3)] for start, end in words[cursor:cursor + count]]
        group["keys"] = [(cursor + offset) in keys for offset in range(count)]
        cursor += count
    return groups


def _node_fit(text: str, width: int) -> int:
    """Largest Anton size (<=52px) at which the node text wraps to at most two lines."""
    for size in range(52, 31, -2):
        if len(text) * size * .5 <= (width - 44) * 2 * .92:
            return size
    return 32


def diagram_packet_times(scene, reveal: list[float], a: float, b: float) -> list[float]:
    """Arrival time of each diagram connector's travelling packet (one per edge, node 1..N-1).

    Mirrors ``_diagram``'s own ``arrive`` pacing math exactly, so a caller that needs these
    instants before the visual renderer runs — mastering audio happens before ``render_silent``
    builds the diagram markup — gets identical timing, not an approximation that could drift
    from what actually appears on screen. Keep in sync with ``_diagram``'s own ``arrive`` formula
    by hand; it is duplicated rather than shared because ``_diagram`` also needs ``begin``
    (clamped to the scene start) for the connector-draw animation, which this caller does not.
    """
    count = len(scene.nodes)
    return [reveal[min(k, len(reveal) - 1)] if len(reveal) > 1 else a + .3 + k * (b - a) * .22
            for k in range(1, count)]


def _diagram(sid: str, scene, reveal: list[float], a: float, b: float, accent: str) -> tuple[str, str]:
    """Minimalist architecture diagram: nodes pop in as the narration reaches them; connectors draw
    and a packet travels along each, so the viewer sees the path the attack takes."""
    nodes, danger = list(scene.nodes), set(scene.danger)
    count = len(nodes)
    colour = lambda k: RED if k in danger else CYAN
    boxes: list[tuple[int, int, int, int]] = []          # left, top, width, height
    if scene.diagram == "branch":
        children = count - 1
        entry_width = 560
        boxes.append((505 - entry_width // 2, 590, entry_width, 140))
        width = (890 - (children - 1) * 30) // children
        for k in range(children):
            boxes.append((60 + k * (width + 30), 900, width, 170))
    else:  # zigzag ladder
        quote = isinstance(getattr(scene, "visual", None), SourceVisual)  # a source quote sits under the diagram
        height, bottom = (112, 1070) if quote else (128, 1230)
        step = min(200, (bottom - 590 - height) // max(1, count - 1))
        for k in range(count):
            boxes.append((60 if k % 2 == 0 else 540, 590 + k * step, 410, height))
    body = _heading(scene.heading, accent)
    anim = ""
    setters = ""
    for k, (left, top, width, height) in enumerate(boxes):
        col = colour(k)
        body += (f'<div class="card" id="{sid}n{k}" style="left:{left}px;top:{top}px;width:{width}px;height:{height}px;'
                 f'border-color:{col};border-width:3px;display:flex;align-items:center;justify-content:center;padding:0 22px;text-align:center">'
                 f'<span style="font:400 {_node_fit(nodes[k], width)}px/1.05 Anton;color:{col};text-transform:uppercase">{html.escape(nodes[k])}</span></div>')
        at = reveal[min(k, len(reveal) - 1)] if len(reveal) > 1 else a + .3 + k * (b - a) * .22
        anim += f'pop("#{sid}n{k}",{at:.3f},{{x:0,y:30}});'
        if k in danger:
            anim += (f'tl.fromTo("#{sid}n{k}",{{boxShadow:"0 0 0 0 rgba(255,77,61,.75)"}},'
                     f'{{boxShadow:"0 0 0 30px rgba(255,77,61,0)",duration:.8,ease:"power2.out"}},{at + .15:.3f});')
    for k in range(1, count):
        source = boxes[0] if scene.diagram == "branch" else boxes[k - 1]
        target = boxes[k]
        if scene.diagram == "branch":
            x0, y0 = source[0] + source[2] / 2, source[1] + source[3]
            x1, y1 = target[0] + target[2] / 2, target[1]
        else:
            right = target[0] > source[0]
            x0, y0 = (source[0] + source[2] if right else source[0]), source[1] + source[3] / 2
            x1, y1 = (target[0] if right else target[0] + target[2]), target[1] + target[3] / 2
        length = math.hypot(x1 - x0, y1 - y0)
        angle = math.degrees(math.atan2(y1 - y0, x1 - x0))
        col = colour(k)
        arrive = reveal[min(k, len(reveal) - 1)] if len(reveal) > 1 else a + .3 + k * (b - a) * .22
        travel = min(.7, max(.35, arrive - a - .2))
        begin = max(a + .05, arrive - travel)
        ux, uy = (x1 - x0) / length, (y1 - y0) / length
        body += (f'<div id="{sid}l{k}" style="position:absolute;left:{x0:.1f}px;top:{y0 - 2:.1f}px;width:{length - 14:.1f}px;height:4px;'
                 f'background:{col};border-radius:2px;opacity:.9"></div>'
                 f'<div id="{sid}h{k}" style="position:absolute;left:{x1 - ux * 12 - 14:.1f}px;top:{y1 - uy * 12 - 12:.1f}px;width:0;height:0;'
                 f'border-left:14px solid transparent;border-right:14px solid transparent;border-bottom:24px solid {col};opacity:0"></div>'
                 f'<div id="{sid}p{k}" style="position:absolute;left:{x0 - 13:.1f}px;top:{y0 - 13:.1f}px;width:26px;height:26px;border-radius:13px;'
                 f'background:{col};box-shadow:0 0 22px 6px {col};opacity:0"></div>')
        setters += (f'gsap.set("#{sid}l{k}",{{rotation:{angle:.2f},transformOrigin:"0 50%",scaleX:0}});'
                    f'gsap.set("#{sid}h{k}",{{rotation:{angle + 90:.2f}}});')
        anim += (f'tl.to("#{sid}l{k}",{{scaleX:1,duration:{travel:.3f},ease:"power1.inOut"}},{begin:.3f});'
                 f'tl.set("#{sid}p{k}",{{opacity:1}},{begin:.3f});'
                 f'tl.fromTo("#{sid}p{k}",{{x:0,y:0}},{{x:{x1 - x0:.1f},y:{y1 - y0:.1f},duration:{travel:.3f},ease:"power1.inOut"}},{begin:.3f});'
                 f'tl.set("#{sid}p{k}",{{opacity:0}},{begin + travel:.3f});'
                 f'tl.set("#{sid}h{k}",{{opacity:1}},{begin + travel - .05:.3f});')
    return body, setters + anim


def _js_data(value) -> str:
    """JSON data inside a script element must never terminate that element."""
    return json.dumps(value).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')


def _code_editor(sid, visual, timing):
    from .editor import compile_code_scene, coloured_characters
    editor = compile_code_scene(visual.lines, visual.language, timing, visual.line_reveal_words)
    height = 120 + 68 * len(visual.lines)
    body = (f'<div class="card" id="{sid}term" style="left:60px;top:520px;width:870px;height:{height}px">'
            f'<div class="mono" style="position:absolute;left:28px;top:20px;font-size:28px;color:{MUTED}">{html.escape(visual.language.upper())}</div>')
    anim = f'pop("#{sid}term",{timing.start:.3f},{{x:0,y:0,s:1,d:.1}});'
    chars = coloured_characters(editor.text, visual.language)
    windows, offset = [], 0
    for k, line in enumerate(visual.lines):
        if editor.line_windows:
            begin, end = editor.line_windows[k]
        else:
            begin = editor.start + offset / len(editor.text) * editor.typing_seconds
            end = begin + len(line) / len(editor.text) * editor.typing_seconds
        windows.append((timing.start + begin, timing.start + end))
        offset += len(line) + 1
    offset = 0
    for k, (line, (begin, end)) in enumerate(zip(visual.lines, windows, strict=True)):
        runs = []
        for char, color in chars[offset:offset+len(line)]:
            if runs and runs[-1][0] == color:
                runs[-1][1] += char
            else:
                runs.append([color, char])
        offset += len(line)+1
        prefix = f'{sid}code{k}'
        tokens = ''.join(f'<span id="{prefix}t{j}" style="color:{color}"></span>' for j,(color,_) in enumerate(runs))
        body += (f'<div class="mono" id="{prefix}" style="position:absolute;left:24px;right:24px;top:{70+k*68}px;'
                 f'height:68px;font-size:42px;line-height:68px;white-space:pre">'
                 f'<span style="display:inline-block;width:36px;margin-right:14px;color:{MUTED};font-size:28px">{k+1}</span>'
                 f'{tokens}<span id="{prefix}cursor" style="display:inline-block;width:3px;height:44px;margin-left:5px;vertical-align:middle;background:#65ead4;opacity:0"></span></div>')
        anim += (f'var {prefix}={{n:0}};var {prefix}runs={_js_data(runs)}.map(function(run){{return [run[0],Array.from(run[1])]}});'
                 f'tl.to({prefix},{{n:{len(line)},duration:{end-begin:.6f},ease:"none",onUpdate:function(){{'
                 f'var left=Math.floor({prefix}.n);{prefix}runs.forEach(function(run,j){{'
                 f'document.getElementById("{prefix}t"+j).textContent=run[1].slice(0,Math.max(0,left)).join("");left-=run[1].length;}});}}}},{begin:.6f});'
                 f'tl.set("#{prefix}cursor",{{opacity:1}},{begin:.6f});'
                 f'tl.set("#{prefix}",{{backgroundColor:"rgba(83,224,239,.08)"}},{begin:.6f});'
                 f'tl.to("#{prefix}",{{backgroundColor:"rgba(83,224,239,0)",duration:.2}},{end:.6f});')
        limit = windows[k+1][0] if k+1 < len(windows) else timing.end
        at, visible = end+.4, False
        while at < limit:
            anim += f'tl.set("#{prefix}cursor",{{opacity:{1 if visible else 0}}},{at:.6f});'
            at, visible = at+.4, not visible
        anim += f'tl.set("#{prefix}cursor",{{opacity:0}},{limit:.6f});'
    body += f'<div class="mono" style="position:absolute;left:28px;bottom:14px;font-size:28px;color:{MUTED}">ILLUSTRATIVE CODE</div></div>'
    report = dict(scene_id=sid, mode='word_anchored' if visual.line_reveal_words else 'proportional',
                  alignment=timing.alignment, line_windows=[(a-timing.start,b-timing.start) for a,b in windows],
                  timeline_windows=windows, scene_start=timing.start, version='story-code-v1')
    return body, anim, 520 + height + 24, report


def _terminal(sid: str, scene, reveal: list[float], a: float, b: float, accent: str) -> tuple[str, str]:
    """A terminal window: commands type out when the narration reaches them, output lines appear whole."""
    size, per_row, row_h = 44, 30, 64
    rows = [max(1, math.ceil((len(line.text) + (2 if line.kind == "command" else 0)) / per_row)) for line in scene.lines]
    inner = sum(r * row_h + 24 for r in rows)
    card_h = max(560, 96 + inner + 90)
    body = _heading(scene.heading, accent)
    body += (f'<div class="card" id="{sid}term" style="left:50px;top:520px;width:900px;height:{card_h}px;overflow:hidden;background:#0d1019">'
             f'<div style="position:absolute;left:0;right:0;top:0;height:72px;background:#1a1e2e;border-bottom:2px solid #262b40"></div>'
             + "".join(f'<div style="position:absolute;left:{34 + 34 * i}px;top:26px;width:20px;height:20px;border-radius:10px;background:{c}"></div>'
                       for i, c in enumerate((RED, AMBER, GREEN)))
             + f'<div class="mono" style="position:absolute;left:0;right:0;top:20px;text-align:center;font-size:26px;color:{MUTED}">bash</div>')
    anim = f'pop("#{sid}term",{a + .1:.3f},{{y:30}});'
    top = 96
    for k, (line, row_count) in enumerate(zip(scene.lines, rows, strict=True)):
        at = reveal[min(k, len(reveal) - 1)] if len(reveal) > 1 else a + .5 + k * (b - a) * .25
        nxt = reveal[min(k + 1, len(reveal) - 1)] if k + 1 < len(scene.lines) and len(reveal) > 1 else b - .3
        style = (f'position:absolute;left:40px;right:40px;top:{top}px;font-size:{size}px;line-height:{row_h}px;'
                 f'white-space:pre-wrap;word-break:break-all;opacity:0')
        if line.kind == "command":
            text = line.text
            duration = min(2.2, max(.6, (nxt - at) * .6))
            body += (f'<div class="mono" id="{sid}c{k}" style="{style};color:{INK}"><span style="color:{GREEN}">$ </span>'
                     f'<span id="{sid}t{k}"></span><span id="{sid}u{k}" style="color:{CYAN};opacity:0">█</span></div>')
            anim += (f'tl.set("#{sid}c{k}",{{opacity:1}},{at:.3f});tl.set("#{sid}u{k}",{{opacity:1}},{at:.3f});'
                     f'var ty{sid}{k}={{n:0}};var tx{sid}{k}={json.dumps(text)};'
                     f'tl.to(ty{sid}{k},{{n:{len(text)},duration:{duration:.3f},ease:"none",onUpdate:function(){{'
                     f'document.querySelector("#{sid}t{k}").textContent=tx{sid}{k}.slice(0,Math.round(ty{sid}{k}.n))}}}},{at:.3f});'
                     f'tl.set("#{sid}u{k}",{{opacity:0}},{at + duration + .35:.3f});')
        else:
            body += f'<div class="mono" id="{sid}c{k}" style="{style};color:{GREEN}">{html.escape(line.text)}</div>'
            anim += f'pop("#{sid}c{k}",{at:.3f},{{x:0,y:10,s:1}});'
        top += row_count * row_h + 24
    body += (f'<div class="pill" id="{sid}ev" style="left:40px;top:{card_h - 76}px;height:48px;font-size:24px;'
             f'background:rgba(83,224,239,.12);border:2px solid rgba(83,224,239,.5);color:{INK}">{html.escape(scene.evidence_label)}</div></div>')
    anim += f'pop("#{sid}ev",{a + .5:.3f},{{y:10}});'
    return body, anim


def _backdrop(index: int, scene, topic, plates_directory: Path | None, manifest: dict, assets: Path, ffmpeg: str = "ffmpeg") -> dict | None:
    """A blurred, darkened still from the scene's acquired stock plate (hook, and the loop scene reuses the hook's).

    The still is prepared once with FFmpeg (blur and dim baked in, so Chromium does no filtering) and pushed in slowly.
    Returns None when there is no usable plate, and the scene keeps its plain background. The plate's licence evidence
    is returned so it can be recorded in the render report.
    """
    if plates_directory is None:
        return None
    source_index = 0 if scene.template == "loop" else index
    entry = manifest.get("scenes", {}).get(str(source_index), {})
    if entry.get("kind") != "stock" or not entry.get("file"):
        return None
    path = (plates_directory / entry["file"]).resolve()
    if not path.is_relative_to(plates_directory.resolve()) or not path.is_file():
        return None
    target = assets / f"backdrop-{source_index}.jpg"
    if not target.exists():
        filters = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma=12,eq=brightness=-0.10:saturation=0.9"
        command = [ffmpeg, "-y", "-v", "error", *(["-ss", "1.0"] if entry.get("media") == "video" else []), "-i", str(path),
                   "-frames:v", "1", "-vf", filters, "-q:v", "4", str(target)]
        try:
            subprocess.run(command, check=True, timeout=60, capture_output=True)
        except (OSError, subprocess.SubprocessError):
            return None
    evidence = entry.get("evidence", {})
    return {"file": target.name, "scene_index": index, "plate": entry["file"], "provider": evidence.get("provider"),
            "asset_id": evidence.get("asset_id"), "license": evidence.get("license_name"), "query": entry.get("query")}


def build_story(timeline, out: Path, *, plates_directory: Path | None, manifest: dict) -> dict:
    """Write one self-contained HyperFrames project for the whole Short and report what it used."""
    assets = out / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    shutil.copy(ASSETS / "hyperframes" / "gsap.min.js", assets / "gsap.min.js")
    shutil.copy(FONTS / "Anton-Regular.ttf", assets / "Anton-Regular.ttf")
    shutil.copy(FONTS / "Inter-Variable.ttf", assets / "Inter-Variable.ttf")
    topic, total = timeline.topic, timeline.duration
    family = select_layout_family(topic)
    style = _FAMILY_STYLE[family]
    source_urls = {s.source_id: str(s.url) for s in topic.sources}
    divs: list[str] = []
    js = ["var tl=gsap.timeline({paused:true});",
          "function show(id,a,b){tl.set('#'+id,{opacity:1},a);tl.set('#'+id,{opacity:0},b);}",
          _pop_js(style["pop_duration"], style["pop_ease"])]
    captions: list[dict] = []
    heroes: list[dict] = []
    backdrops: list[dict] = []
    code_animation = []

    for i, scene in enumerate(topic.scenes):
        timing = timeline.timings[i]
        a, b = timing.start, timing.end
        words = [(w.start, w.end) for w in timing.words]
        captions += _caption_groups(scene, words)
        reveal = [words[r][0] for r in scene.reveal_words if r < len(words)] or [a + .5]
        sid, accent = f"s{i}", style["accents"][i % 3]
        visual = getattr(scene, "visual", None)
        template = scene.template
        if isinstance(visual, CodeVisual) and visual.line_reveal_words and template != 'checklist':
            raise ValueError('Story code-line anchors currently require a checklist code scene')
        label = next((_domain(source_urls.get(s)) for s in scene.source_ids if source_urls.get(s)), None)
        treatment, _ = source_treatment(scene, i, topic, plates_directory, manifest)
        if template == "terminal" or (template == "flow" and scene.diagram != "stack"):
            treatment = None  # the diagram or terminal is the picture; the source rides underneath as a quote
        body = anim = ""

        def rows(items, top, step, build):
            nonlocal body, anim
            for k, item in enumerate(items):
                body += build(k, item, top + k * step)

        if treatment is not None:  # captured source: hero card with the real highlight sweep
            from PIL import Image
            with Image.open(treatment["plate"]) as image:
                pw, ph = image.size
            width = min(900, round(560 * pw / ph)); height = round(width * ph / pw)
            shutil.copy(treatment["plate"], assets / f"hero-{i}.png")
            hl = treatment["highlight"]
            if hl is not None:
                shutil.copy(hl, assets / f"hero-{i}-hl.png")
            heroes.append({"scene_index": i, "scene_id": scene.scene_id, "plate": treatment["manifest_file"],
                           "highlight_status": treatment["highlight_status"], "source_label": treatment["source_label"]})
            head = getattr(scene, "heading", None) or " ".join(getattr(scene, "headline", ()))
            top = 560
            extra = ""
            if template == "big_stat":  # keep the figure; the real capture backs it up underneath
                top = 940
                fmt = "0" if float(scene.after).is_integer() else "1"
                extra = (f'<div style="position:absolute;left:60px;top:400px;font:400 340px/1 Anton;color:{AMBER};white-space:nowrap"><span id="{sid}v">{scene.before:.{fmt}f}</span><span style="font-size:200px">{html.escape(scene.unit)}</span></div>')
                anim += (f'var o={{v:{scene.before}}};tl.to(o,{{v:{scene.after},duration:.8,ease:"power3.out",onUpdate:function(){{document.querySelector("#{sid}v").textContent=o.v.toFixed({fmt})}}}},{reveal[-1]:.3f});')
            body = (_heading(head, accent) + extra
                    + f'<div class="card" id="{sid}card" style="left:{round(490 - width / 2)}px;top:{top}px;width:{width}px;height:{height}px;overflow:hidden;border:3px solid rgba(83,224,239,.55)">'
                    f'<div id="{sid}zoom" style="position:absolute;inset:0"><div style="position:absolute;inset:0;background:url(assets/hero-{i}.png) 0 0/100% 100%"></div>'
                    + (f'<div id="{sid}hl" style="position:absolute;inset:0;background:url(assets/hero-{i}-hl.png) 0 0/100% 100%;clip-path:inset(0 100% 0 0)"></div>' if hl else "")
                    + '</div></div>'
                    f'<div class="pill" id="{sid}pill" style="left:60px;top:{top + height + 40}px;background:rgba(83,224,239,.14);border:2px solid rgba(83,224,239,.6);color:{INK}">SOURCE · {html.escape(treatment["source_label"])}</div>')
            anim += (f'tl.fromTo("#{sid}card",{{opacity:0,y:80,scale:.94}},{{opacity:1,y:0,scale:1,duration:.5,ease:"power3.out"}},{a + .15:.3f});'
                    f'tl.fromTo("#{sid}zoom",{{scale:1}},{{scale:{style["zoom_scale"]},transformOrigin:"50% 40%",duration:{b - a:.2f},ease:"power1.inOut"}},{a:.3f});'
                    + ("".join(f'tl.set("#{sid}hl",{{clipPath:"inset(0 100% 0 0)"}},{r:.3f});tl.to("#{sid}hl",{{clipPath:"inset(0 0% 0 0)",duration:.5,ease:"none"}},{r:.3f});'
                               for r in reveal) if hl else "")
                    + f'pop("#{sid}pill",{a + .8:.3f});')
        elif template in ("hook", "loop"):
            lines = list(scene.headline)
            # Anton caps are about 0.46 em wide: shrink the headline until its longest line fits the 890 px column,
            # and start the chips below the (possibly taller) headline, so a long line never wraps into them.
            size = max(84, min(176, int(890 / (0.46 * max(len(line) for line in lines)))))
            chips_top = max(880, 280 + round(len(lines) * size * 1.02) + 70)
            body = _heading(scene.headline, RED, top=280, size=size)
            backdrop = _backdrop(i, scene, topic, plates_directory, manifest, assets)
            if backdrop is not None:
                backdrops.append(backdrop)
                body = (f'<div id="{sid}bg" style="position:absolute;left:-60px;top:-60px;width:1200px;height:2040px;'
                        f'background:url(assets/{backdrop["file"]}) center/cover"></div>'
                        f'<div style="position:absolute;left:0;top:0;width:1080px;height:1920px;'
                        f'background:linear-gradient(180deg,rgba(10,11,16,.40) 0%,rgba(10,11,16,.10) 45%,rgba(10,11,16,.55) 100%)"></div>' + body)
                backdrop_anim = f'tl.fromTo("#{sid}bg",{{scale:1}},{{scale:1.12,duration:{b - a:.2f},ease:"none"}},{a:.3f});'
            else:
                backdrop_anim = ""
            chips = list(scene.chips)
            anim = backdrop_anim + f'tl.fromTo("#{sid} .h1",{{opacity:0,y:60}},{{opacity:1,y:0,duration:.5,ease:"power3.out"}},{a:.3f});'
            for k, chip in enumerate(chips):
                body += (f'<div class="pill" id="{sid}c{k}" style="left:60px;top:{chips_top + k * 100}px;background:{RED if k == 0 else "#1b2036"};'
                         f'border:2px solid {RED if k == 0 else "#333a58"};color:#fff;font:400 60px/1 Anton;height:84px;border-radius:14px;text-transform:uppercase">{html.escape(chip)}</div>')
                anim += f'pop("#{sid}c{k}",{reveal[min(k, len(reveal) - 1)]:.3f},{{x:-60,y:0}});'
        elif template == "flow" and scene.diagram != "stack":
            body, anim = _diagram(sid, scene, reveal, a, b, accent)
        elif template == "terminal":
            body, anim = _terminal(sid, scene, reveal, a, b, accent)
        elif template == "flow":
            body = _heading(scene.heading, accent)
            nodes = list(scene.nodes)
            for k, node in enumerate(nodes):
                col = style["accents"][k % 3]
                body += (f'<div class="card" id="{sid}n{k}" style="left:60px;top:{540 + k * 200}px;width:840px;height:136px;border-color:{col};display:flex;align-items:center;padding:0 36px">'
                         f'<span style="font:400 56px/1.05 Anton;color:{col};text-transform:uppercase;white-space:nowrap">{html.escape(node)}</span></div>')
                if k < len(nodes) - 1:
                    body += f'<div id="{sid}a{k}" class="mono" style="position:absolute;left:440px;top:{676 + k * 200}px;font-size:44px;color:{MUTED}">▼</div>'
            span = b - a
            anim = ("".join(f'pop("#{sid}n{k}",{reveal[min(k, len(reveal) - 1)] if len(reveal) > 1 else a + .3 + k * span * .22:.3f},{{x:-60,y:0}});' for k in range(len(nodes)))
                    + "".join(f'pop("#{sid}a{k}",{a + .5 + k * span * .22:.3f},{{y:-10}});' for k in range(len(nodes) - 1)))
        elif template == "checklist":
            body = _heading(scene.heading, accent)
            top = 540
            if isinstance(visual, CodeVisual):
                editor_body, editor_anim, top, code_report = _code_editor(sid, visual, timing)
                body += editor_body
                anim += editor_anim
                code_report.update(scene_id=scene.scene_id, scene_index=i)
                code_animation.append(code_report)
            items = list(scene.items)
            step = 150 if top < 700 else 110
            if isinstance(visual, CodeVisual):
                if top + len(items) * step > 1260:
                    raise ValueError('Story code and checklist exceed the caption-safe visual zone; revise the scene')
            for k, item in enumerate(items):
                body += (f'<div class="card" id="{sid}r{k}" style="left:50px;top:{top + k * step}px;width:900px;height:{step - 24}px;display:flex;align-items:center;padding:0 44px;gap:34px">'
                         f'<div id="{sid}t{k}" style="width:70px;height:70px;border-radius:18px;border:4px solid #3a4163;display:flex;align-items:center;justify-content:center;font:900 48px/1 Inter;color:#0a0b10"><span id="{sid}tick{k}" style="opacity:0">✓</span></div>'
                         f'<span style="font:400 56px/1 Anton;color:{INK};text-transform:uppercase;white-space:nowrap">{html.escape(item)}</span></div>')
                r = reveal[min(k, len(reveal) - 1)]
                anim += (f'pop("#{sid}r{k}",{a + .2 + k * .15:.3f},{{x:-50,y:0}});'
                         f'tl.to("#{sid}t{k}",{{backgroundColor:"{GREEN}",borderColor:"{GREEN}",duration:.2}},{r:.3f});'
                         f'tl.set("#{sid}tick{k}",{{opacity:1}},{r + .2:.3f});')
        elif template == "before_after":
            body = _heading(scene.heading, accent)
            body += (f'<div class="card" id="{sid}a" style="left:50px;top:540px;width:900px;height:190px;padding:26px 40px;display:flex;align-items:center"><span style="font:400 58px/1.1 Anton;color:{MUTED};text-transform:uppercase">{html.escape(scene.before)}</span></div>'
                     f'<div id="{sid}arrow" class="mono" style="position:absolute;left:470px;top:744px;font-size:56px;color:{accent}">▼</div>'
                     f'<div class="card" id="{sid}b" style="left:50px;top:830px;width:900px;height:190px;padding:26px 40px;border-color:{accent};display:flex;align-items:center"><span style="font:400 58px/1.1 Anton;color:{INK};text-transform:uppercase">{html.escape(scene.after)}</span></div>')
            anim = f'pop("#{sid}a",{a + .1:.3f});pop("#{sid}arrow",{reveal[0]:.3f},{{y:-20}});pop("#{sid}b",{reveal[0]:.3f});'
            if isinstance(visual, SourceVisual):
                body += f'<div class="note" id="{sid}q" style="top:1060px;font-style:italic">“{html.escape(visual.quote)}”<br><span style="font-style:normal;font-size:28px">— {html.escape(label or "source")}</span></div>'
                anim += f'pop("#{sid}q",{reveal[-1] + .3:.3f},{{y:20}});'
        elif template == "big_stat":
            unit = html.escape(scene.unit)
            fmt = "0" if float(scene.after).is_integer() else "1"
            body = _heading(scene.heading, accent)
            body += (f'<div style="position:absolute;left:60px;top:470px;font:400 380px/1 Anton;color:{AMBER};white-space:nowrap"><span id="{sid}v">{scene.before:.{fmt}f}</span><span style="font-size:220px">{unit}</span></div>'
                     f'<div id="{sid}l" style="position:absolute;left:60px;top:930px;font:800 44px/1.2 Inter;color:{INK}">{html.escape(scene.after_label)}</div>')
            anim = (f'var o={{v:{scene.before}}};tl.to(o,{{v:{scene.after},duration:.8,ease:"power3.out",onUpdate:function(){{document.querySelector("#{sid}v").textContent=o.v.toFixed({fmt})}}}},{reveal[-1]:.3f});'
                    f'pop("#{sid}l",{reveal[-1] + .3:.3f});')
        else:  # cta or anything new: heading plus its chips, never a crash
            heading = getattr(scene, "heading", None) or " ".join(getattr(scene, "headline", ())) or scene.caption
            body = _heading(heading, accent)
            for k, chip in enumerate(getattr(scene, "chips", ())):
                body += f'<div class="pill" id="{sid}c{k}" style="left:60px;top:{600 + k * 100}px;background:#1b2036;border:2px solid #333a58;color:{INK}">{html.escape(chip)}</div>'
                anim += f'pop("#{sid}c{k}",{reveal[min(k, len(reveal) - 1)]:.3f});'
        # A source quote with no captured plate is shown as a labelled quote, never as a screenshot.
        if treatment is None and isinstance(visual, SourceVisual) and template in ("flow", "checklist", "big_stat", "hook", "loop", "terminal"):
            body += f'<div class="note" id="{sid}q" style="top:1130px;font-size:30px;font-style:italic">“{html.escape(visual.quote)}”<br><span style="font-style:normal;font-size:26px">— {html.escape(label or "source")}</span></div>'
            anim += f'pop("#{sid}q",{reveal[-1] + .3:.3f},{{y:20}});'
        divs.append(f'<div id="{sid}" class="scene">{body}</div>')
        js.append(f'show("{sid}",{a:.3f},{b:.3f});{anim}')

    capjs = f"""
var CAPTIONS={json.dumps(captions)}; var host=document.getElementById("captions");
CAPTIONS.forEach(function(g,gi) {{
 var el=document.createElement("div"); el.className="cap-group";
 g.words.forEach(function(w,wi) {{
  var s=document.createElement("span"); s.className="cap-word"; s.appendChild(document.createTextNode(w));
  if (g.keys && g.keys[wi]) {{ var m=document.createElement("i"); m.className="mark"; s.appendChild(m);
   tl.fromTo(m,{{scaleX:0}},{{scaleX:1,duration:Math.max(.16,g.times[wi][1]-g.times[wi][0]),ease:"power1.out"}},g.times[wi][0]);
   tl.to(s,{{color:"{style['mark']}",duration:.1}},g.times[wi][0]); }}
  el.appendChild(s); if (wi<g.words.length-1) el.appendChild(document.createTextNode(" "));
 }});
 host.appendChild(el);
 var st=Math.max(0,g.start-.02), nx=gi+1<CAPTIONS.length?Math.max(0,CAPTIONS[gi+1].start-.02):Infinity;
 var en=Math.max(st+.08,Math.min(g.end,nx-.01));
 tl.set(el,{{opacity:1}},st); tl.set(el,{{opacity:0,visibility:"hidden"}},en);
}});
window.__timelines=window.__timelines||{{}}; window.__timelines["story"]=tl; tl.seek(0);"""
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="UTF-8" /><meta name="viewport" content="width={WIDTH}, height={HEIGHT}" />
<script src="assets/gsap.min.js"></script><style>{CSS}.cap-word .mark{{background:{style['mark']}}}</style></head><body>
<div id="root" class="clip" data-composition-id="story" data-start="0" data-duration="{total:.3f}" data-width="{WIDTH}" data-height="{HEIGHT}" data-fps="{FPS}">
<div class="glow"></div>
{''.join(divs)}
<div id="captions" class="clip" data-track-kind="captions" data-start="0" data-duration="{total:.3f}" data-track-index="9"></div>
</div><script>(function() {{
{chr(10).join(js)}
{capjs}
}})();</script></body></html>"""
    (out / "index.html").write_text(page, encoding="utf-8")
    (out / "hyperframes.json").write_text(json.dumps({
        "$schema": "https://hyperframes.heygen.com/schema/hyperframes.json",
        "paths": {"blocks": "compositions", "components": "compositions/components", "assets": "assets"},
        "media": {"autoProxy": False}}, indent=2), encoding="utf-8")
    return {"evidence_quote": heroes, "stock_backdrops": backdrops, "layout_family": family, "code_animation": code_animation}


def render_silent(timeline, destination: Path, *, draft: bool, cancelled: Callable[[], bool] = lambda: False,
                  budget_rtf: float = 20, ffmpeg: str = "ffmpeg", hyperframes_bin: str | None = None,
                  plates_directory: Path | None = None) -> dict:
    """Render the whole Short as one silent MP4; same report shape as the per-scene HyperFrames path."""
    binary = hyperframes_bin or os.environ.get("TUBEFORGE_HYPERFRAMES_BIN") or shutil.which("hyperframes")
    if not binary:
        raise ValueError("hyperframes binary is unavailable; set TUBEFORGE_HYPERFRAMES_BIN")
    manifest = load_manifest(plates_directory) if plates_directory is not None else {"scenes": {}}
    destination.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    deadline = started + max(60, timeline.duration * budget_rtf)
    with tempfile.TemporaryDirectory(prefix="story-render-", dir=destination.parent) as scratch, \
            cli.short_scratch(Path(scratch)) as short:
        root = Path(scratch)
        # The worker runs as an arbitrary uid with HOME=/, which Chromium cannot write a profile into
        # ("Target closed"); give it the private scratch directory instead.
        env = {"TMPDIR": str(short), "HOME": str(short), "XDG_CONFIG_HOME": str(short), "XDG_CACHE_HOME": str(short),
               "HYPERFRAMES_EXTRACT_CACHE_DIR": str(root / "cache")}
        project = root / "story"
        report = build_story(timeline, project, plates_directory=plates_directory, manifest=manifest)
        check = cli.check(project, hyperframes_bin=binary, timeout=max(1, deadline - time.monotonic()),
                          extra_env=env, cancelled=cancelled)
        clip = root / "story.mp4"
        cli.render(project, clip, quality="draft" if draft else "high", hyperframes_bin=binary,
                   timeout=max(1, deadline - time.monotonic()), workers=1, extra_env=env, cancelled=cancelled)
        # Match the PIL path's output sizes: 720x1280 draft, 1080x1920 final.
        scaled = root / "story-scaled.mp4"
        width, height = (720, 1280) if draft else (1080, 1920)
        checked([ffmpeg, "-y", "-v", "error", "-i", str(clip), "-an", "-vf",
                 f"fps={FPS},scale={width}:{height}:flags=lanczos,format=yuv420p", "-c:v", "libx264",
                 "-threads", "2", "-preset", "veryfast", "-crf", "20", "-r", str(FPS),
                 "-movflags", "+faststart", str(scaled)], deadline=deadline, cancelled=cancelled)
        checked([ffmpeg, "-v", "error", "-xerror", "-i", str(scaled), "-f", "null", "-"],
                deadline=deadline, cancelled=cancelled)
        scaled.replace(destination)
    return {"scene_count": len(timeline.topic.scenes), "frames": round(timeline.duration * FPS),
            "duration": timeline.duration, "checks": [check], "evidence_quote": report["evidence_quote"], "stock_backdrops": report.get("stock_backdrops", []),
            "source_fallbacks": [], "style": "story", "layout_family": report["layout_family"], "code_animation": report["code_animation"], "render_seconds": time.monotonic() - started}
