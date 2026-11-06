"""First-frame promise and loop continuity in the actual Pillow compositor."""
from test_reference_shorts import fixture_timeline
from tubeforge.rendering.shorts.motion import Animator
from tubeforge.rendering.shorts.schema import ShortsTopic
from tubeforge.rendering.shorts.timeline import FrameState, Timeline


def loop_timeline():
    original = fixture_timeline()
    data = original.topic.model_dump(mode='json')
    data['scenes'][-1] = {**data['scenes'][0], 'template':'loop', 'scene_id':'loop-fixture',
        'vo':'This synthetic example tests graphics and safe caption placement',
        'caption':'This synthetic example tests graphics and safe caption placement'}
    from dataclasses import replace
    timings = (*original.timings[:-1], replace(original.timings[-1], end=original.duration+.011))
    return Timeline(ShortsTopic.model_validate(data), timings)


def test_hook_is_fully_visible_on_frame_one():
    timeline = loop_timeline()
    animator = Animator(timeline.renderer, first_state=timeline.state(0))
    state = timeline.state(0)
    # The opening hook must not start as a fully transparent entrance layer.
    from PIL import ImageStat
    alpha = animator.content(state).getchannel('A')
    expected = animator.layer(0, state.revealed).getchannel('A')
    assert alpha.getbbox() == expected.getbbox()
    assert ImageStat.Stat(alpha).sum[0] >= ImageStat.Stat(expected).sum[0] * .99


def test_loop_endpoint_reuses_exact_opening_state_at_noninteger_duration():
    timeline = loop_timeline()
    animator = Animator(timeline.renderer, first_state=timeline.state(0))
    initial = animator.frame(timeline.state(0), 0)
    # Same endpoint condition used by ceil(duration*30) encoding.
    import math
    last_time = (math.ceil(timeline.duration*30)-1)/30
    ending = animator.frame(timeline.state(last_time), last_time)
    assert ending.tobytes() == initial.tobytes()
    # Seeking to the ending after another rendered scene remains deterministic.
    animator.frame(timeline.state(5),5)
    assert animator.frame(timeline.state(last_time),last_time).tobytes() == initial.tobytes()
