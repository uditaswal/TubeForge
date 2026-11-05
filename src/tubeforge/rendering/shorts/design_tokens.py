"""Opt-in, per-video visual tokens for the classic HyperFrames scene family.

Narration and semantic layouts remain immutable. This decorates the existing
projects rather than introducing another renderer or writer-facing geometry.
"""
from __future__ import annotations

import hashlib
import html
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

from PIL import ImageFont

VERSION = 'reference-design-v1'
SAFE = (60, 200, 930, 1500)
BACKGROUND, INK, MUTED, ACCENT = '#090d14', '#f4f7ff', '#b5c0d0', '#53e0ef'


def _contrast(color):
    def luminance(value):
        parts = [int(value[i:i+2], 16) / 255 for i in (1, 3, 5)]
        values = [v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4 for v in parts]
        return sum(v*w for v, w in zip(values, (.2126, .7152, .0722)))
    a, b = sorted([luminance(color), luminance(BACKGROUND)])
    return (b+.05)/(a+.05)


@dataclass(frozen=True)
class VideoDesignTokens:
    entity_colors: tuple[tuple[str, str], ...] = ()
    anchor_headline: tuple[str, str] = ('UNDERSTAND', 'THE MECHANISM')
    dim_opacity: float = .22

    def __post_init__(self):
        if len(self.entity_colors) > 12:
            raise ValueError('declare at most twelve distinct entity names')
        for name, color in self.entity_colors:
            if not isinstance(name, str) or not name.strip() or len(name) > 60:
                raise ValueError('entity names must be nonblank and at most sixty characters')
            if not isinstance(color, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', color) or _contrast(color) < 4.5:
                raise ValueError('entity colour requires a readable six-digit hex colour')
        if len({name.casefold().strip() for name, _ in self.entity_colors}) != len(self.entity_colors):
            raise ValueError('entity names must be distinct ignoring case')
        if len(self.anchor_headline) != 2 or any(not isinstance(v, str) or not v.strip() or len(v) > 24 for v in self.anchor_headline):
            raise ValueError('anchor headline requires two short text chunks')
        font = ImageFont.truetype(str(Path(__file__).with_name('fonts')/'Anton-Regular.ttf'), 44)
        if font.getlength(' '.join(self.anchor_headline)) > 850:
            raise ValueError('anchor headline exceeds the safe horizontal measure')
        if not isinstance(self.dim_opacity, (int, float)) or isinstance(self.dim_opacity, bool) or not math.isfinite(self.dim_opacity) or not .12 <= self.dim_opacity <= .35:
            raise ValueError('dim opacity must be within .12–.35')

    @classmethod
    def from_data(cls, data):
        if isinstance(data, cls):
            return data
        if not isinstance(data, dict) or set(data) - {'version', 'entity_colors', 'anchor_headline', 'dim_opacity'}:
            raise ValueError('invalid design-token declaration')
        if data.get('version', VERSION) != VERSION:
            raise ValueError('unsupported design-token version')
        colors = data.get('entity_colors', {})
        if not isinstance(colors, dict) or any(not isinstance(name, str) for name in colors):
            raise ValueError('entity colours must be a name-to-colour mapping')
        return cls(tuple(sorted(colors.items(), key=lambda p: p[0].casefold())),
                   tuple(data.get('anchor_headline', ('UNDERSTAND', 'THE MECHANISM'))), data.get('dim_opacity', .22))

    def to_data(self):
        return {'version': VERSION, 'entity_colors': dict(self.entity_colors),
                'anchor_headline': list(self.anchor_headline), 'dim_opacity': self.dim_opacity}

    @property
    def identity(self):
        return hashlib.sha256(json.dumps(self.to_data(), sort_keys=True).encode()).hexdigest()

    def entity_color(self, value):
        value = str(value).casefold()
        for name, color in sorted(self.entity_colors, key=lambda p: -len(p[0])):
            if re.search(r'(?<!\w)'+re.escape(name.casefold())+r'(?!\w)', value):
                return color
        return None


def decorate_project(project, scene, words, tokens, *, source_label):
    """Apply one shared declaration; keep actual word anchors and the original GSAP timeline."""
    tokens = VideoDesignTokens.from_data(tokens)
    project = Path(project)
    path = project/'index.html'
    original = path.read_text(encoding='utf-8')
    if 'id="reference-design-tokens"' in original:
        raise ValueError('design tokens already applied to this project')
    primary = tokens.entity_color(' '.join([getattr(scene, 'logo', '') or '',
        getattr(scene, 'heading', ''), *getattr(scene, 'headline', ())])) or ACCENT
    anchor = ' '.join(html.escape(v) for v in tokens.anchor_headline)
    styles = f'''<style id="reference-design-tokens">
:root{{--token-accent:{primary};--token-dim:{tokens.dim_opacity}}}
html,body,#root{{background:{BACKGROUND}!important}} .glow,.rail{{display:none!important}}
#token-anchor{{position:absolute;left:60px;top:218px;width:870px;height:58px;font:44px/1.2 Anton;text-align:center;color:{INK};white-space:nowrap}}
#token-anchor .anchor-second{{color:var(--token-accent)}}
#badge{{left:824px!important;top:290px!important;width:104px!important;height:104px!important;transform:none!important}}
#heading{{left:60px!important;right:260px!important;top:350px!important;font-size:56px!important;line-height:1.12!important}}
#headlines{{left:60px!important;right:150px!important;top:420px!important}}
#headlines .headline,#chips .chip{{opacity:1!important;filter:none!important;transform:none!important}}
#chips{{left:60px!important;right:150px!important;top:960px!important}} .chip{{min-width:0}}
#captions{{left:60px!important;right:150px!important;top:1300px!important}}
.cap-group{{left:50%!important;right:auto!important;transform:translateX(-50%)!important;width:max-content;max-width:870px;padding:10px 18px;background:#101824f5;border-radius:18px;white-space:pre;font-size:96px!important;line-height:1!important}}
.cap-word{{-webkit-text-stroke:0!important}} .cap-word.active{{text-decoration:underline;text-underline-offset:10px}}
#token-footnote{{position:absolute;left:60px;top:1450px;width:870px;height:40px;font:26px/1.3 Inter;color:{MUTED};white-space:nowrap;overflow:hidden;text-overflow:ellipsis;text-align:center}}
.stat{{right:150px!important}}
.item,.line,.stat{{opacity:var(--token-opacity,var(--token-dim))!important}}
[data-token-entity]{{border-color:var(--entity-color)!important}}
.stat[data-token-entity] .number,.stat[data-token-entity] .label{{color:var(--entity-color)!important}}
.stat[data-token-entity] .fill{{background:var(--entity-color)!important}}
.token-entity{{color:var(--entity-color)!important}}
</style>'''
    reveals = [words[i][0] for i in scene.reveal_words]
    data = {'entities': dict(tokens.entity_colors), 'anchor': list(tokens.anchor_headline),
            'source': source_label, 'template': scene.template, 'reveals': reveals, 'dim': tokens.dim_opacity}
    payload = json.dumps(data, ensure_ascii=True).replace('<', r'\u003c')
    script = r'''<script>(function(){
const data=TOKEN_DATA,root=document.querySelector('#root');
const header=document.createElement('div');header.id='token-anchor';header.dataset.tokenOwned='anchor';
data.anchor.forEach((part,i)=>{if(i)header.append(document.createTextNode(' '));const span=document.createElement('span');span.className=i?'anchor-second':'';span.textContent=part;header.append(span);});root.append(header);
const foot=document.createElement('div');foot.id='token-footnote';foot.dataset.tokenOwned='footnote';foot.textContent=data.source;root.append(foot);
const entities=Object.entries(data.entities).sort((a,b)=>b[0].length-a[0].length);
function matching(text){const lower=text.toLowerCase();return entities.find(([name])=>lower.includes(name.toLowerCase()));}
for(const card of root.querySelectorAll('.item')){const copy=document.createElement('span');copy.className='token-copy';copy.append(...card.childNodes);card.append(copy);}
for(const node of root.querySelectorAll('.item,.stat,.line')){const match=matching(node.textContent);if(match){node.dataset.tokenEntity=match[0];node.style.setProperty('--entity-color',match[1]);}}
const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT),nodes=[];let node;while(node=walker.nextNode())if(!['SCRIPT','STYLE'].includes(node.parentElement.tagName))nodes.push(node);
for(const textNode of nodes){const value=textNode.nodeValue,lower=value.toLowerCase();let cursor=0,fragments=[],changed=false;while(cursor<value.length){let found=null;for(const [name,color]of entities){let at=lower.indexOf(name.toLowerCase(),cursor);while(at>=0&&(/[a-z0-9_]/i.test(value[at-1]||'')||/[a-z0-9_]/i.test(value[at+name.length]||'')))at=lower.indexOf(name.toLowerCase(),at+1);if(at>=0&&(!found||at<found.at))found={at,name,color};}if(!found){fragments.push(document.createTextNode(value.slice(cursor)));break;}if(found.at>cursor)fragments.push(document.createTextNode(value.slice(cursor,found.at)));const span=document.createElement('span');span.className='token-entity';span.dataset.tokenEntity=found.name;span.style.setProperty('--entity-color',found.color);span.textContent=value.slice(found.at,found.at+found.name.length);fragments.push(span);cursor=found.at+found.name.length;changed=true;}if(changed)textNode.replaceWith(...fragments);}
if(matching(data.anchor[0])&&!matching(data.anchor[1]))header.querySelector('.anchor-second').style.color='''' + INK + r'''';
const tl=Object.values(window.__timelines||{})[0];
if(tl){const selectors=data.template==='big_stat'?['.stat.before','.stat.after']:['terminal','flow','before_after','checklist'].includes(data.template)?Array.from(root.querySelectorAll(data.template==='terminal'?'.line':'.item')).map(el=>'#'+el.id):[];selectors.forEach((selector,i)=>{const el=root.querySelector(selector);if(!el)return;const at=data.reveals[Math.min(i,data.reveals.length-1)]||0;el.dataset.tokenReveal=String(at);tl.fromTo(el,{'--token-opacity':data.dim},{'--token-opacity':1,duration:.25,ease:'power2.out'},at);});tl.seek(0);}
})();</script>'''.replace('TOKEN_DATA', payload)
    path.write_text(original.replace('</head>', styles+'</head>', 1).replace('</body>', script+'</body>', 1), encoding='utf-8')
    record = {'version': VERSION, 'identity': tokens.identity, 'entity_colors': dict(tokens.entity_colors),
              'source_label': source_label, 'safe': SAFE, 'reveal_seconds': reveals, 'anchor_text': anchor}
    (project/'design-tokens.json').write_text(json.dumps(record, sort_keys=True, indent=2)+'\n')
    return record
