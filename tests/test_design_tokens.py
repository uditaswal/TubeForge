import json
from pathlib import Path

import pytest
from tubeforge.rendering.shorts.design_tokens import VideoDesignTokens,decorate_project
from tubeforge.pipeline.reference_short import write_options,load_options,options_identity
from tubeforge.rendering.hyperframes_proto.compose import build_hook_project
from test_hyperframes_proto import _hook_scene,WORDS_10


def tokens(**updates):
    return VideoDesignTokens.from_data({'entity_colors':{'Railway':'#ffb870','OpenCode':'#79e8b0'},'anchor_headline':['SECURITY','EXPLAINED'],**updates})


def test_entity_identity_is_case_stable_and_not_a_substring_guess():
    value=tokens()
    assert value.entity_color('RAILWAY keys')=='#ffb870'
    assert value.entity_color('Railwayman') is None
    assert value.entity_color('OpenCode uses Railway')=='#79e8b0'
    assert tokens(entity_colors={'OpenCode':'#79e8b0','Railway':'#ffb870'}).identity==value.identity


@pytest.mark.parametrize('data',[
    {'entity_colors':{'PHP':'red; background:url(bad)'}},
    {'entity_colors':{'PHP':'#101010'}},
    {'entity_colors':{'PHP':'#ffffff','php':'#ffb870'}},
    {'anchor_headline':['x']}, {'dim_opacity':1}, {'dim_opacity':float('nan')},
    {'anchor_headline':['M'*24,'M'*24]}, {'version':'unknown'}, {'unsupported':True},
])
def test_invalid_or_unreadable_tokens_fail_before_render(data):
    with pytest.raises(ValueError):VideoDesignTokens.from_data(data)


def test_render_options_bind_the_map_and_keep_default_identity_unchanged(tmp_path):
    write_options(tmp_path,show_sources=False,watermark=None)
    assert options_identity(tmp_path)=='none' and load_options(tmp_path).design_tokens is None
    write_options(tmp_path,show_sources=False,watermark=None,design_tokens=tokens())
    first=options_identity(tmp_path)
    assert load_options(tmp_path).design_tokens==tokens()
    write_options(tmp_path,show_sources=False,watermark=None,design_tokens=tokens(entity_colors={'Railway':'#79e8b0'}))
    assert options_identity(tmp_path)!=first
    data=json.loads((tmp_path/'render_options.json').read_text());data['design_tokens']['entity_colors']['Railway']='#000000'
    (tmp_path/'render_options.json').write_text(json.dumps(data))
    with pytest.raises(ValueError):load_options(tmp_path)


def test_decoration_keeps_original_word_anchors_and_does_not_rewrite_narration(tmp_path):
    scene=_hook_scene();project=tmp_path/'hook'
    build_hook_project(scene,WORDS_10,3.63,project)
    original=(project/'index.html').read_text()
    record=decorate_project(project,scene,WORDS_10,tokens(),source_label='Source: captured fixture')
    result=(project/'index.html').read_text()
    assert scene.vo==_hook_scene().vo
    assert record['reveal_seconds']==[WORDS_10[scene.reveal_words[0]][0]]
    assert original.replace('</head>','').replace('</body>','') in result.replace(result[result.index('<style id="reference-design-tokens"'):result.index('</head>')],'').replace(result[result.rindex('<script>(function(){'):result.index('</body>')],'').replace('</head>','').replace('</body>','')
    assert record['identity']==tokens().identity
    with pytest.raises(ValueError,match='already applied'):decorate_project(project,scene,WORDS_10,tokens(),source_label='same')
