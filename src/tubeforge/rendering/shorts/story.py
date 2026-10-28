"""Story video style: one HyperFrames composition per Short with a purpose-built picture per scene.

Design target is docs/video-quality/reference/cloudflare-pingora: a big stacked headline with one
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
import os
import shutil
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
.cap-word {{ color:{INK}; -webkit-text-stroke:7px {BG}; paint-order:stroke fill; }}
"""

POP = ("function pop(sel,t,o){o=o||{};tl.fromTo(sel,{opacity:0,x:o.x||0,y:o.y===undefined?40:o.y,scale:o.s||.92},"
       "{opacity:1,x:0,y:0,scale:1,duration:o.d||.4,ease:'back.out(1.6)'},t);}")


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


def build_story(timeline, out: Path, *, plates_directory: Path | None, manifest: dict) -> dict:
    """Write one self-contained HyperFrames project for the whole Short and report what it used."""
    assets = out / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    shutil.copy(ASSETS / "hyperframes" / "gsap.min.js", assets / "gsap.min.js")
    shutil.copy(FONTS / "Anton-Regular.ttf", assets / "Anton-Regular.ttf")
    shutil.copy(FONTS / "Inter-Variable.ttf", assets / "Inter-Variable.ttf")
    topic, total = timeline.topic, timeline.duration
    source_urls = {s.source_id: str(s.url) for s in topic.sources}
    divs: list[str] = []
    js = ["var tl=gsap.timeline({paused:true});",
          "function show(id,a,b){tl.set('#'+id,{opacity:1},a);tl.set('#'+id,{opacity:0},b);}", POP]
    captions: list[dict] = []
    heroes: list[dict] = []

    for i, scene in enumerate(topic.scenes):
        timing = timeline.timings[i]
        a, b = timing.start, timing.end
        words = [(w.start, w.end) for w in timing.words]
        captions += _word_groups(scene.caption, words)
        reveal = [words[r][0] for r in scene.reveal_words if r < len(words)] or [a + .5]
        sid, accent = f"s{i}", ACCENTS[i % 3]
        visual = getattr(scene, "visual", None)
        template = scene.template
        label = next((_domain(source_urls.get(s)) for s in scene.source_ids if source_urls.get(s)), None)
        treatment, _ = source_treatment(scene, i, topic, plates_directory, manifest)
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
                    f'tl.fromTo("#{sid}zoom",{{scale:1}},{{scale:1.1,transformOrigin:"50% 40%",duration:{b - a:.2f},ease:"power1.inOut"}},{a:.3f});'
                    + ("".join(f'tl.set("#{sid}hl",{{clipPath:"inset(0 100% 0 0)"}},{r:.3f});tl.to("#{sid}hl",{{clipPath:"inset(0 0% 0 0)",duration:.5,ease:"none"}},{r:.3f});'
                               for r in reveal) if hl else "")
                    + f'pop("#{sid}pill",{a + .8:.3f});')
        elif template in ("hook", "loop"):
            body = _heading(scene.headline, RED, top=280, size=176)
            chips = list(scene.chips)
            anim = f'tl.fromTo("#{sid} .h1",{{opacity:0,y:60}},{{opacity:1,y:0,duration:.5,ease:"power3.out"}},{a:.3f});'
            for k, chip in enumerate(chips):
                body += (f'<div class="pill" id="{sid}c{k}" style="left:60px;top:{880 + k * 100}px;background:{RED if k == 0 else "#1b2036"};'
                         f'border:2px solid {RED if k == 0 else "#333a58"};color:#fff;font:400 60px/1 Anton;height:84px;border-radius:14px;text-transform:uppercase">{html.escape(chip)}</div>')
                anim += f'pop("#{sid}c{k}",{reveal[min(k, len(reveal) - 1)]:.3f},{{x:-60,y:0}});'
        elif template == "flow":
            body = _heading(scene.heading, accent)
            nodes = list(scene.nodes)
            for k, node in enumerate(nodes):
                col = ACCENTS[k % 3]
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
                lines = list(visual.lines)[:3]
                term = "".join(f'<div class="mono" id="{sid}l{k}" style="font-size:42px;line-height:1.6;color:{GREEN if k == 0 else AMBER};white-space:nowrap">$ {html.escape(l)}</div>' for k, l in enumerate(lines))
                body += (f'<div class="card" id="{sid}term" style="left:50px;top:520px;width:900px;padding:28px 40px;height:{110 + 68 * len(lines)}px">'
                         f'<div class="mono" style="font-size:26px;color:{MUTED};margin-bottom:6px">{html.escape(visual.language)} · example</div>{term}</div>')
                anim += f'pop("#{sid}term",{a + .1:.3f});' + "".join(f'pop("#{sid}l{k}",{a + .4 + k * .5:.3f},{{y:14}});' for k in range(len(lines)))
                top = 520 + 110 + 68 * len(lines) + 40
            items = list(scene.items)
            step = 150 if top < 700 else 110
            for k, item in enumerate(items):
                body += (f'<div class="card" id="{sid}r{k}" style="left:50px;top:{top + k * step}px;width:900px;height:{step - 24}px;display:flex;align-items:center;padding:0 44px;gap:34px">'
                         f'<div id="{sid}t{k}" style="width:70px;height:70px;border-radius:18px;border:4px solid #3a4163;display:flex;align-items:center;justify-content:center;font:900 48px/1 Inter;color:#0a0b10">✓</div>'
                         f'<span style="font:400 56px/1 Anton;color:{INK};text-transform:uppercase;white-space:nowrap">{html.escape(item)}</span></div>')
                r = reveal[min(k, len(reveal) - 1)]
                anim += (f'pop("#{sid}r{k}",{a + .2 + k * .15:.3f},{{x:-50,y:0}});'
                         f'tl.to("#{sid}t{k}",{{backgroundColor:"{GREEN}",borderColor:"{GREEN}",duration:.2}},{r:.3f});')
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
        else:  # terminal, cta or anything new: heading plus its chips, never a crash
            heading = getattr(scene, "heading", None) or " ".join(getattr(scene, "headline", ())) or scene.caption
            body = _heading(heading, accent)
            for k, chip in enumerate(getattr(scene, "chips", ())):
                body += f'<div class="pill" id="{sid}c{k}" style="left:60px;top:{600 + k * 100}px;background:#1b2036;border:2px solid #333a58;color:{INK}">{html.escape(chip)}</div>'
                anim += f'pop("#{sid}c{k}",{reveal[min(k, len(reveal) - 1)]:.3f});'
        # A source quote with no captured plate is shown as a labelled quote, never as a screenshot.
        if treatment is None and isinstance(visual, SourceVisual) and template in ("flow", "checklist", "big_stat", "hook", "loop"):
            body += f'<div class="note" id="{sid}q" style="top:1130px;font-size:30px;font-style:italic">“{html.escape(visual.quote)}”<br><span style="font-style:normal;font-size:26px">— {html.escape(label or "source")}</span></div>'
            anim += f'pop("#{sid}q",{reveal[-1] + .3:.3f},{{y:20}});'
        divs.append(f'<div id="{sid}" class="scene">{body}</div>')
        js.append(f'show("{sid}",{a:.3f},{b:.3f});{anim}')

    capjs = f"""
var CAPTIONS={json.dumps(captions)}; var host=document.getElementById("captions");
CAPTIONS.forEach(function(g,gi) {{
 var el=document.createElement("div"); el.className="cap-group";
 g.words.forEach(function(w,wi) {{ var s=document.createElement("span"); s.className="cap-word"; s.textContent=w+(wi<g.words.length-1?" ":""); el.appendChild(s); }});
 host.appendChild(el);
 var st=Math.max(0,g.start-.02), nx=gi+1<CAPTIONS.length?Math.max(0,CAPTIONS[gi+1].start-.02):Infinity;
 var en=Math.max(st+.08,Math.min(g.end,nx-.01));
 tl.set(el,{{opacity:1}},st); tl.set(el,{{opacity:0,visibility:"hidden"}},en);
}});
window.__timelines=window.__timelines||{{}}; window.__timelines["story"]=tl; tl.seek(0);"""
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="UTF-8" /><meta name="viewport" content="width={WIDTH}, height={HEIGHT}" />
<script src="assets/gsap.min.js"></script><style>{CSS}</style></head><body>
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
    return {"evidence_quote": heroes}


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
    with tempfile.TemporaryDirectory(prefix="story-render-", dir=destination.parent) as scratch:
        root = Path(scratch)
        env = {"TMPDIR": str(root), "HYPERFRAMES_EXTRACT_CACHE_DIR": str(root / "cache")}
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
            "duration": timeline.duration, "checks": [check], "evidence_quote": report["evidence_quote"],
            "source_fallbacks": [], "style": "story", "render_seconds": time.monotonic() - started}
