"""Quote images must stay inside their card throughout the highlight animation."""
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark=pytest.mark.skipif(os.environ.get('TUBEFORGE_STORY_BROWSER')!='1' or not os.environ.get('TUBEFORGE_STORY_REFERENCE'),reason='requires opt-in Chromium and captured reference path')


def test_source_image_does_not_zoom_outside_its_card(tmp_path):
    from playwright.sync_api import sync_playwright
    from tubeforge.rendering.shorts.schema import ShortsTopic
    from tubeforge.rendering.shorts.story import build_story
    from tubeforge.rendering.shorts.timeline import SceneTiming,Word
    from tubeforge.rendering.shorts.plates import load_manifest
    reference=Path(os.environ['TUBEFORGE_STORY_REFERENCE'])
    topic=ShortsTopic.model_validate_json((reference/'topic.json').read_bytes())
    row=json.loads((reference/'timeline.json').read_text())['scenes'][3]
    start=row['start']
    timing=SceneTiming(0,row['end']-start,tuple(Word(w['start']-start,w['end']-start) for w in row['words']),row['alignment'],row['voice_end']-start)
    timeline=SimpleNamespace(topic=SimpleNamespace(scenes=(topic.scenes[3],),sources=topic.sources),timings=(timing,),duration=timing.end)
    project=tmp_path/'project'
    report=build_story(timeline,project,plates_directory=reference,manifest={'scenes':{'0':load_manifest(reference)['scenes']['3']}})
    assert report['evidence_quote'][0]['image_motion']=='fixed'
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
        try:
            page=browser.new_page(viewport={'width':1080,'height':1920})
            page.goto((project/'index.html').as_uri())
            page.wait_for_function('Boolean(window.__timelines?.story)')
            for at in (.8,timing.end/2,timing.end-.1):
                page.evaluate('(t)=>{window.__timelines.story.seek(t,false)}',at)
                bounds=page.evaluate('''() => ({card:document.querySelector('#s0card').getBoundingClientRect().toJSON(),
                    image:document.querySelector('#s0zoom').getBoundingClientRect().toJSON()})''')
                card,image=bounds['card'],bounds['image']
                assert image['left']>=card['left'] and image['right']<=card['right']
                assert image['top']>=card['top'] and image['bottom']<=card['bottom']
            evidence=Path(os.environ.get('TUBEFORGE_STORY_SOURCE_EVIDENCE',str(tmp_path/'evidence')))
            evidence.mkdir(parents=True,exist_ok=True)
            page.screenshot(path=str(evidence/'source-fixed.png'))
        finally:browser.close()
