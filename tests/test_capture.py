from PIL import Image

from tubeforge.pipeline.capture import CARD_HEIGHT, CARD_WIDTH, _public, draw_highlight, plan_clip


def test_plan_clip_uses_full_width_and_never_exceeds_the_card_aspect():
    rects = [{"x": 40, "y": 800, "w": 450, "h": 26}, {"x": 40, "y": 826, "w": 300, "h": 26}]
    x, y, w, h = plan_clip(rects, 540, 5000)
    assert (x, w) == (0, 540) and h <= 540 * CARD_HEIGHT / CARD_WIDTH + 1e-6
    assert y <= 800 and y + h >= 852  # the whole match stays inside the crop


def test_plan_clip_aligns_to_the_paragraph_when_it_fits():
    rects = [{"x": 40, "y": 830, "w": 450, "h": 26}]
    block = {"y": 800.0, "h": 150.0}
    x, y, w, h = plan_clip(rects, 540, 5000, block)
    assert y == 790.0 and y + h == 960.0  # block top/bottom plus 10 px padding, no partial extra lines


def test_plan_clip_falls_back_to_matched_lines_for_tall_blocks():
    rects = [{"x": 40, "y": 830, "w": 450, "h": 26}, {"x": 40, "y": 856, "w": 450, "h": 26}]
    x, y, w, h = plan_clip(rects, 540, 5000, {"y": 100.0, "h": 2000.0})
    assert y == 830.0 and y + h == 882.0  # exactly the complete matched line boxes


def test_plan_clip_ignores_a_container_that_is_not_the_paragraph():
    rects = [{"x": 40, "y": 830, "w": 450, "h": 26}]
    x, y, w, h = plan_clip(rects, 540, 5000, {"y": 700.0, "h": 400.0})
    assert y == 830.0 and h == 26.0


def test_plan_clip_stays_inside_short_documents():
    x, y, w, h = plan_clip([{"x": 10, "y": 20, "w": 100, "h": 20}], 540, 150)
    assert y >= 0 and y + h <= 150 + 1e-6


def test_highlight_changes_only_the_matched_region():
    base = Image.new("RGB", (810, 400), "white")
    marked = draw_highlight(base, [{"x": 100, "y": 100, "w": 200, "h": 30}], (0, 0, 810, 400))
    assert marked.getpixel((150, 115)) != (255, 255, 255) and marked.getpixel((600, 300)) == (255, 255, 255)


def test_private_and_unresolvable_hosts_are_rejected():
    cache = {}
    assert not _public("localhost", cache) and not _public("127.0.0.1", cache) and not _public("10.0.0.5", cache)
    assert not _public("does-not-exist.invalid", cache)


def test_capture_cleanup_preserves_quote_and_records_controls_in_chromium():
    import os
    from pathlib import Path
    import pytest
    if os.environ.get('TUBEFORGE_CAPTURE_BROWSER') != '1':
        pytest.skip('opt-in real Chromium source capture check')
    from playwright.sync_api import sync_playwright
    from tubeforge.pipeline.capture import CLEAN_CONTROLS, DARK_READER, FIND
    out = Path(os.environ.get('TUBEFORGE_CAPTURE_EVIDENCE', 'artifacts/review/reference-motion-capture-dark-reader'))
    out.mkdir(parents=True, exist_ok=True)
    quote = 'The bucket refills at a constant rate over time.'
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/usr/bin/chromium', headless=True,
            args=['--no-sandbox','--disable-dev-shm-usage'])
        try:
            page = browser.new_page(viewport={'width':810,'height':300})
            page.set_content('''<style>body{font:24px sans-serif;padding:20px}button{position:absolute;right:20px;top:20px}</style>
                <article><p id="claim">The bucket refills at a constant rate over time.</p>
                <p id="prose">Ask AI and Copy link are literal words in this article.</p>
                <a href="#article">Ask AI</a></article><button>Ask AI</button>
                <button style="top:60px" aria-label="Copy page">icon</button>
                <button style="top:100px">Ask   AI</button><button style="top:140px">Run example</button>''')
            page.evaluate("""() => {
              const host=document.createElement('div');host.id='shadow-ui';document.body.append(host);
              host.attachShadow({mode:'open'}).innerHTML='<button style="position:absolute;right:20px;top:180px">Ask AI</button>';
            }""")
            before = page.evaluate(FIND, quote)
            assert before['complete']
            page.evaluate('getSelection().removeAllRanges()')
            page.screenshot(path=str(out/'fixture-before.png'))
            labels = page.evaluate(CLEAN_CONTROLS)
            assert labels == ['Ask AI','Copy page','Ask AI','Ask AI']
            assert not page.locator('#shadow-ui').get_by_role('button',name='Ask AI').is_visible()
            assert not page.get_by_role('button',name='Copy page',exact=True).is_visible()
            after = page.evaluate(FIND, quote)
            assert after['complete'] and before['rects'] == after['rects']
            assert before['block'] == after['block']
            assert page.locator('#claim').inner_text() == quote
            assert page.locator('#prose').is_visible()
            assert page.get_by_role('link',name='Ask AI',exact=True).is_visible()
            assert page.get_by_role('button',name='Run example',exact=True).is_visible()
            page.evaluate('getSelection().removeAllRanges()')
            # Light and pre-existing dark page styles, including inline !important,
            # get the same reader paint without changing text or range geometry.
            page.locator('#claim').evaluate("el=>{el.style.setProperty('color','black','important');el.style.setProperty('background-color','white','important')}")
            page.locator('#prose').evaluate("el=>{el.style.backgroundColor='#222';el.style.color='#eee'}")
            before_theme = page.evaluate(FIND, quote)
            themed = page.evaluate(DARK_READER)
            after_theme = page.evaluate(FIND, quote)
            assert themed == {'appearance':'dark-reader-v1','themed_roots':2}
            assert before_theme == after_theme
            assert page.locator('#claim').inner_text() == quote
            assert page.locator('#claim').evaluate("el=>getComputedStyle(el).color") == 'rgb(229, 237, 248)'
            assert page.locator('#prose').evaluate("el=>getComputedStyle(el).color") == 'rgb(229, 237, 248)'
            assert page.locator('body').evaluate("el=>getComputedStyle(el).backgroundColor") == 'rgb(16, 24, 39)'
            assert page.locator('#shadow-ui').get_by_role('button',name='Ask AI',include_hidden=True).evaluate("el=>getComputedStyle(el).color") == 'rgb(229, 237, 248)'
            page.evaluate('getSelection().removeAllRanges()')
            page.screenshot(path=str(out/'fixture-after.png'))
        finally:
            browser.close()
