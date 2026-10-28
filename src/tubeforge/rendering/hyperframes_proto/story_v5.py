"""Whole-video HyperFrames prototype ("story v5"): one composition per Short, a purpose-built
visual for every scene, driven by the real aligned word times of an existing reference job.

Design target is docs/video-quality/reference/cloudflare-pingora: a big stacked headline with one
accent word, one diagram per scene built up as the narration reaches each idea, captions
underneath, nothing inside the Shorts UI rails. Only facts already in the job's topic.json
(headings, quotes, code lines, items, numbers) are drawn; nothing is invented.
"""
from __future__ import annotations

import html
import json
import shutil
from pathlib import Path
from urllib.parse import urlparse

from tubeforge.rendering.hyperframes_proto.compose import ASSETS, FONTS, FPS, HEIGHT, WIDTH, _word_groups

BG, INK, MUTED = "#0a0b10", "#f4f6fb", "#8d93a6"
RED, AMBER, CYAN, GREEN = "#ff4d3d", "#ffb020", "#53e0ef", "#35d07f"

CSS = f"""
@font-face {{ font-family: Anton; src: url("assets/Anton-Regular.ttf"); }}
@font-face {{ font-family: Inter; src: url("assets/Inter-Variable.ttf"); font-weight: 100 900; }}
* {{ box-sizing:border-box; margin:0; padding:0; }}
html,body {{ width:{WIDTH}px; height:{HEIGHT}px; overflow:hidden; background:{BG}; }}
#root {{ position:relative; width:100%; height:100%; background:{BG}; }}
.glow {{ position:absolute; inset:0; background:radial-gradient(ellipse 70% 38% at 50% 28%,rgba(255,77,61,.16),transparent 70%),radial-gradient(ellipse 60% 30% at 50% 85%,rgba(83,224,239,.07),transparent 70%); }}
.scene {{ position:absolute; left:0; top:0; width:{WIDTH}px; height:1290px; opacity:0; }}
.h1 {{ position:absolute; left:60px; right:130px; top:150px; font:400 138px/1.0 Anton; text-transform:uppercase; color:{INK}; letter-spacing:1px; }}
.h1 b {{ font-weight:400; color:{RED}; }}
.h1.amber b {{ color:{AMBER}; }}
.h1.cyan b {{ color:{CYAN}; }}
.sub {{ position:absolute; left:60px; right:130px; font:700 38px/1.25 Inter; color:{MUTED}; }}
.card {{ position:absolute; background:#141724; border:2px solid #262b40; border-radius:28px; box-shadow:0 22px 60px rgba(0,0,0,.6); }}
.mono {{ font-family:'DejaVu Sans Mono',monospace; font-weight:700; }}
.pill {{ position:absolute; height:64px; padding:0 30px; border-radius:32px; display:flex; align-items:center; font:800 36px/1.2 Inter; white-space:nowrap; }}
#captions {{ position:absolute; left:40px; right:40px; top:1330px; }}
.cap-group {{ position:absolute; left:0; right:0; text-align:center; font:104px/1 Anton; text-transform:uppercase; opacity:0; }}
.cap-word {{ color:{INK}; -webkit-text-stroke:7px {BG}; paint-order:stroke fill; }}
"""

POP = ("function pop(sel,t,o){o=o||{};tl.fromTo(sel,{opacity:0,x:o.x||0,y:o.y===undefined?40:o.y,scale:o.s||.92},"
       "{opacity:1,x:0,y:0,scale:1,duration:o.d||.4,ease:'back.out(1.6)'},t);}")


def _t(words: list[tuple[float, float]], index: int, default: float) -> float:
    return words[index][0] if 0 <= index < len(words) else default


def build_story(timeline, out: Path, *, hero_plate: Path, hero_highlight: Path, manifest: dict) -> dict:
    """Write one self-contained HyperFrames project for the whole Short and return its summary."""
    assets = out / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    shutil.copy(ASSETS / "hyperframes" / "gsap.min.js", assets / "gsap.min.js")
    shutil.copy(FONTS / "Anton-Regular.ttf", assets / "Anton-Regular.ttf")
    shutil.copy(FONTS / "Inter-Variable.ttf", assets / "Inter-Variable.ttf")
    shutil.copy(hero_plate, assets / "hero.png")
    shutil.copy(hero_highlight, assets / "hero-hl.png")
    scenes = timeline.topic.scenes
    total = timeline.duration
    domain = "techcrunch.com"
    for entry in manifest.get("scenes", {}).values():
        host = urlparse(entry.get("url", "")).hostname
        if host:
            domain = host.removeprefix("www.")
            break
    quotes = {int(k): v.get("quote") for k, v in manifest.get("scenes", {}).items() if v.get("quote")}

    divs: list[str] = []
    js: list[str] = ["var tl=gsap.timeline({paused:true});",
                     "function show(id,a,b){tl.set('#'+id,{opacity:1},a);tl.set('#'+id,{opacity:0},b);}", POP]
    captions: list[dict] = []

    for i, scene in enumerate(scenes):
        timing = timeline.timings[i]
        a, b = timing.start, timing.end
        words = [(w.start, w.end) for w in timing.words]
        captions += _word_groups(scene.caption, words)
        sid = f"s{i}"
        reveal = [words[r][0] for r in scene.reveal_words if r < len(words)] or [a + .5]
        body = anim = ""
        if i in (0, 9):
            label = "BREACHED" if i == 0 else "THE REAL QUESTION"
            body = (f'<div class="h1" style="top:300px;font-size:176px">You host on<br><b>Railway?</b></div>'
                    f'<div id="{sid}stamp" style="position:absolute;left:60px;top:860px;background:{RED};color:#fff;font:400 84px/1 Anton;padding:20px 44px;border-radius:14px;transform:rotate(-4deg)">{label}</div>')
            anim = (f'tl.fromTo("#{sid} .h1",{{opacity:0,y:60}},{{opacity:1,y:0,duration:.5,ease:"power3.out"}},{a:.3f});'
                    f'tl.fromTo("#{sid}stamp",{{opacity:0,scale:2.4,rotation:-14}},{{opacity:1,scale:1,rotation:-4,duration:.35,ease:"power4.in"}},{reveal[0]:.3f});')
            if i == 0:
                chips = list(getattr(scene, "chips", None) or [])
                body += "".join(f'<div class="pill" id="{sid}c{k}" style="left:{60 + k * 300}px;top:1060px;background:#1b2036;border:2px solid #333a58;color:{INK}">{html.escape(c.upper())}</div>'
                                for k, c in enumerate(chips))
                anim += "".join(f'pop("#{sid}c{k}",{_t(words, len(words) - 3 + k, a + 2):.3f});' for k in range(len(chips)))
        elif i == 1:
            body = ('<div class="h1">What<br><b>happened</b></div>'
                    '<div class="card" id="s1card" style="left:50px;top:560px;width:900px;height:560px;overflow:hidden;border:3px solid rgba(83,224,239,.55)">'
                    '<div id="s1zoom" style="position:absolute;inset:0"><div style="position:absolute;inset:0;background:url(assets/hero.png) 0 0/100% 100%"></div>'
                    '<div id="s1hl" style="position:absolute;inset:0;background:url(assets/hero-hl.png) 0 0/100% 100%;clip-path:inset(0 100% 0 0)"></div></div></div>'
                    f'<div class="pill" id="s1pill" style="left:60px;top:1150px;background:rgba(83,224,239,.14);border:2px solid rgba(83,224,239,.6);color:{INK}">SOURCE · {html.escape(domain)}</div>')
            anim = (f'tl.fromTo("#s1card",{{opacity:0,y:80,scale:.94}},{{opacity:1,y:0,scale:1,duration:.5,ease:"power3.out"}},{a + .15:.3f});'
                    f'tl.fromTo("#s1zoom",{{scale:1}},{{scale:1.12,transformOrigin:"50% 40%",duration:{b - a:.2f},ease:"power1.inOut"}},{a:.3f});'
                    + "".join(f'tl.set("#s1hl",{{clipPath:"inset(0 100% 0 0)"}},{r:.3f});tl.to("#s1hl",{{clipPath:"inset(0 0% 0 0)",duration:.5,ease:"none"}},{r:.3f});' for r in reveal)
                    + f'pop("#s1pill",{a + .8:.3f});')
        elif i == 2:
            lines = list(scene.visual.lines)
            term = "".join(f'<div class="mono" id="s2l{k}" style="font-size:42px;line-height:1.6;color:{GREEN if k == 0 else AMBER};white-space:nowrap">$ {html.escape(l)}</div>'
                           for k, l in enumerate(lines))
            items = "".join(f'<div class="pill" id="s2i{k}" style="left:60px;top:{800 + k * 100}px;background:#1b2036;border:2px solid #333a58;color:{INK}"><span style="color:{RED};margin-right:20px">●</span>{html.escape(it)}</div>'
                            for k, it in enumerate(scene.items))
            body = ('<div class="h1">Inside <b>env</b><br>variables</div>'
                    f'<div class="card" id="s2term" style="left:50px;top:520px;width:900px;padding:30px 40px;height:240px"><div class="mono" style="font-size:26px;color:{MUTED};margin-bottom:6px">.env · example</div>{term}</div>{items}')
            anim = (f'pop("#s2term",{a + .1:.3f});'
                    + "".join(f'pop("#s2l{k}",{a + .4 + k * .5:.3f},{{y:14}});' for k in range(len(lines)))
                    + "".join(f'pop("#s2i{k}",{reveal[min(k, len(reveal) - 1)]:.3f});' for k in range(len(scene.items))))
        elif i == 3:
            body = ('<div class="h1 amber"><b>Encrypted</b><br>vs decrypted</div>'
                    f'<div class="card" id="s3a" style="left:50px;top:540px;width:900px;height:170px;padding:26px 40px"><div class="mono" style="font-size:26px;color:{MUTED}">ENCRYPTED · UNREADABLE</div>'
                    f'<div class="mono" style="font-size:44px;margin-top:12px;color:#6c7390;white-space:nowrap">x9$kQ#2@pL!vR7&amp;zT^m4w</div></div>'
                    f'<div class="mono" id="s3arrow" style="position:absolute;left:470px;top:722px;font-size:64px;color:{AMBER}">▼</div>'
                    f'<div class="card" id="s3b" style="left:50px;top:820px;width:900px;height:170px;padding:26px 40px;border-color:{RED}"><div class="mono" style="font-size:26px;color:{RED}">DECRYPTED · READABLE</div>'
                    f'<div class="mono" id="s3dec" style="font-size:44px;margin-top:12px;color:{INK};white-space:nowrap">DATABASE_URL=postgres://…</div></div>'
                    f'<div class="sub" id="s3q" style="top:1030px;font-size:32px;font-style:italic">“…{html.escape(quotes.get(3, ""))}”<br><span style="font-style:normal;font-size:30px">— {html.escape(domain)}</span></div>')
            anim = (f'pop("#s3a",{a + .1:.3f});pop("#s3arrow",{reveal[0]:.3f},{{y:-20}});pop("#s3b",{reveal[0]:.3f});'
                    f'tl.fromTo("#s3dec",{{opacity:.15}},{{opacity:1,duration:.5}},{reveal[-1]:.3f});pop("#s3q",{reveal[-1] + .3:.3f},{{y:20}});')
        elif i == 4:
            body = '<div class="h1 cyan">Why <b>keys</b><br>matter</div>'
            for k, label in enumerate(["ATTACKER", "YOUR KEYS", "YOUR DATA"]):
                col = [RED, AMBER, CYAN][k]
                body += (f'<div class="card" id="s4n{k}" style="left:80px;top:{520 + k * 190}px;width:620px;height:130px;border-color:{col};display:flex;align-items:center;padding:0 36px">'
                         f'<span style="font:400 64px/1 Anton;color:{col}">{label}</span></div>')
                if k < 2:
                    body += f'<div id="s4a{k}" class="mono" style="position:absolute;left:360px;top:{640 + k * 190}px;font-size:44px;color:{MUTED}">▼</div>'
            body += f'<div id="s4r" style="position:absolute;left:60px;top:1110px;background:{RED};color:#fff;font:400 54px/1 Anton;padding:18px 34px;border-radius:14px">READS YOUR DATA AS YOU</div>'
            span = b - a
            anim = ("".join(f'pop("#s4n{k}",{a + .3 + k * span * .22:.3f},{{x:-60,y:0}});' for k in range(3))
                    + "".join(f'pop("#s4a{k}",{a + .5 + k * span * .22:.3f},{{y:-10}});' for k in range(2))
                    + f'pop("#s4r",{_t(words, len(words) - 4, a + 2):.3f});')
        elif i == 5:
            hit = {3, 7, 12, 18, 21, 26, 33}  # illustrative; the source gives no figure
            dots = "".join(f'<div id="d{n}" style="position:absolute;left:{78 + (n % 9) * 98}px;top:{590 + (n // 9) * 98}px;width:70px;height:70px;border-radius:50%;background:{RED if n in hit else "#262b40"}"></div>'
                           for n in range(45))
            body = (f'<div class="h1 amber">Scope <b>vs.</b><br>advice</div>{dots}'
                    f'<div class="sub" style="left:60px;top:1100px;font-size:32px"><span style="color:{RED}">●</span> hit: “a subset” of users (no figure given, dots illustrative)<br><span style="color:{AMBER}">●</span> told to rotate: all users</div>')
            anim = ("".join(f'tl.fromTo("#d{n}",{{scale:0}},{{scale:1,duration:.3,ease:"back.out(2)"}},{a + .2 + n * .012:.3f});' for n in range(45))
                    + "".join(f'tl.to("#d{n}",{{backgroundColor:"{AMBER}",duration:.25}},{reveal[-1] + (n % 9) * .04 + (n // 9) * .04:.3f});' for n in range(45)))
        elif i == 6:
            body = '<div class="h1">Still<br><b>unknown</b></div>'
            for k, label in enumerate(["USERS HIT", "ROOT CAUSE"]):
                body += (f'<div class="card" id="s6c{k}" style="left:50px;top:{560 + k * 290}px;width:900px;height:240px;display:flex;align-items:center;justify-content:space-between;padding:0 50px">'
                         f'<span style="font:400 78px/1 Anton;color:{INK}">{label}</span><span id="s6q{k}" style="font:400 180px/1 Anton;color:{RED}">?</span></div>')
            anim = "".join(f'pop("#s6c{k}",{reveal[min(k, len(reveal) - 1)]:.3f});'
                           f'tl.fromTo("#s6q{k}",{{rotation:-30,scale:.5}},{{rotation:0,scale:1,duration:.5,ease:"elastic.out(1,.4)"}},{reveal[min(k, len(reveal) - 1)] + .1:.3f});'
                           for k in range(2))
        elif i == 7:
            body = ('<div class="h1 amber">OpenCode<br><b>days earlier</b></div>'
                    f'<div id="s7n" style="position:absolute;left:60px;top:470px;font:400 420px/1 Anton;color:{AMBER};white-space:nowrap"><span id="s7v">0.0</span><span style="font-size:240px">%</span></div>'
                    f'<div id="s7l" style="position:absolute;left:60px;top:960px;font:800 46px/1.2 Inter;color:{INK}">of OpenCode’s customer keys taken</div>'
                    f'<div class="card" id="s7bar" style="left:60px;top:1060px;width:900px;height:44px;border-radius:22px;overflow:hidden"><div id="s7f" style="width:100%;height:100%;border-radius:22px;background:{AMBER}"></div></div>')
            anim = (f'var o={{v:0}};tl.to(o,{{v:1,duration:.8,ease:"power3.out",onUpdate:function(){{document.querySelector("#s7v").textContent=o.v.toFixed(1)}}}},{reveal[-1]:.3f});'
                    f'tl.fromTo("#s7f",{{width:"0%"}},{{width:"1%",duration:.8}},{reveal[-1]:.3f});pop("#s7l",{reveal[-1] + .3:.3f});')
        elif i == 8:
            body = '<div class="h1 cyan">Do this<br><b>now</b></div>'
            for k, it in enumerate(scene.items):
                body += (f'<div class="card" id="s8r{k}" style="left:50px;top:{540 + k * 190}px;width:900px;height:150px;display:flex;align-items:center;padding:0 44px;gap:34px">'
                         f'<div id="s8t{k}" style="width:86px;height:86px;border-radius:22px;border:4px solid #3a4163;display:flex;align-items:center;justify-content:center;font:900 60px/1 Inter;color:#0a0b10">✓</div>'
                         f'<span style="font:400 62px/1 Anton;color:{INK};text-transform:uppercase;white-space:nowrap">{html.escape(it)}</span></div>')
            anim = "".join(f'pop("#s8r{k}",{a + .2 + k * .15:.3f},{{x:-50,y:0}});'
                           f'tl.to("#s8t{k}",{{backgroundColor:"{GREEN}",borderColor:"{GREEN}",duration:.2}},{reveal[min(k, len(reveal) - 1)]:.3f});'
                           for k in range(len(scene.items)))
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
    return {"duration": total, "scenes": len(scenes)}
