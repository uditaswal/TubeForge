"""Lightweight JS/DOM integration; deliberately no Chromium or media playback.

Optional test interpreter: pip install quickjs (or use a temporary target).
"""
import json
import re
import pytest

quickjs = pytest.importorskip('quickjs')

DOM = r'''
class Element {
 constructor(tag='div'){this.tagName=tag;this.children=[];this.dataset={};this.value='';this.textContent='';this.disabled=false;this._html='';this.files=[];}
 append(...items){this.children.push(...items);}
 replaceChildren(...items){this.children=[...items];}
 set innerHTML(value){this._html=value;}
 get innerHTML(){return this._html;}
 querySelectorAll(selector){let result=[];function walk(el,inside){inside=inside||el.id==='actions';for(const child of el.children){if(!(child instanceof Element))continue;if(selector==='#actions button'&&inside&&child.tagName==='button')result.push(child);walk(child,inside);}}walk(this,false);return result;}
 querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
}
const elements={};
const document={cookie:COOKIE,querySelector:s=>elements[s]||(elements[s]=new Element()),querySelectorAll:s=>[],createElement:t=>new Element(t)};
const intervals=[];function setInterval(fn){intervals.push(fn);}
function fetch(url,options={}){const response=JSON.parse(_http(url,JSON.stringify(options)));return Promise.resolve({ok:response.status>=200&&response.status<300,status:response.status,json:async()=>JSON.parse(response.body),text:async()=>response.body});}
'''


def runtime(client, html):
    context = quickjs.Context()
    errors = []
    def http(url, options):
        options = json.loads(options)
        response = client.request(options.get('method', 'GET'), url, headers=options.get('headers'), content=options.get('body'))
        return json.dumps({'status': response.status_code, 'body': response.text})
    context.add_callable('_http', http)
    context.add_callable('_error', lambda message: errors.append(message))
    cookie = 'tubeforge_csrf=' + client.cookies.get('tubeforge_csrf', '')
    context.eval(DOM.replace('COOKIE', json.dumps(cookie)))
    script = re.search(r'<script>(.*?)</script>', html, re.S).group(1)
    context.eval(script)
    def run(expression=None):
        if expression:
            context.eval(f'Promise.resolve({expression}).catch(e=>_error(String(e)))')
        while context.execute_pending_job():
            pass
        assert not errors, errors
    run()
    return context, run


def test_upload_validate_commit_with_real_authenticated_api(tmp_path):
    from fastapi.testclient import TestClient
    from tubeforge.api.app import create_app
    from tubeforge.core.config import AppConfig, AuthConfig, DatabaseConfig, Settings
    from tubeforge.db.models import Base
    from tubeforge.db.session import create_database
    settings = Settings(app=AppConfig(name='test', environment='test'), database=DatabaseConfig(url=f"sqlite:///{tmp_path / 'js.db'}"), auth=AuthConfig(enabled=True))
    db = create_database(settings.database)
    Base.metadata.create_all(db.engine)
    with TestClient(create_app(settings)) as client:
        client.app.state.runtime.auth.create_admin('operator', 'correct-horse-battery-staple')
        client.post('/login', json={'username':'operator', 'password':'correct-horse-battery-staple'})
        context, run = runtime(client, client.get('/batch').text)
        plan = '## One\n```yaml\nid: one\ntitle: One\nconcept: Concept\nbeats: [{t: 0, point: Hook}]\n```\n'
        context.eval('file.files=[{text:async()=>'+json.dumps(plan)+'}]')
        run('file.onchange()')
        run('submit(false)')
        assert context.eval('commit.disabled') is False
        assert context.eval('rows.innerHTML.includes("One")')
        assert client.get('/api/batch-plans').json() == []
        run('commit.onclick()')
        assert len(client.get('/api/batch-plans').json()) == 1
        assert context.eval('result.textContent.includes("Import saved")')
        context.eval('input.value="bad";input.oninput()')
        assert context.eval('commit.disabled') is True
    db.dispose()
