from tubeforge.clips.services.video_service import _segment_payload_from_dict


def test_nested_virality_from_a_fresh_analysis():
    out = _segment_payload_from_dict({
        "start_time": "01:00", "end_time": "01:30", "text": "t",
        "virality": {"total_score": 84, "hook_score": 22, "hook_type": "question"},
        "hook_title": "A title",
    })
    assert (out["virality_score"], out["hook_score"], out["hook_type"]) == (84, 22, "question")


def test_flat_scores_from_a_cache_replay_are_kept():
    out = _segment_payload_from_dict({
        "start_time": "01:00", "end_time": "01:30", "text": "t",
        "virality_score": 80, "hook_score": 14, "engagement_score": 20, "value_score": 23,
        "shareability_score": 23, "hook_type": "story", "hook_title": "A title",
    })
    assert (out["virality_score"], out["hook_score"], out["shareability_score"], out["hook_type"]) == (80, 14, 23, "story")


def test_no_scores_at_all_is_zero_not_a_crash():
    assert _segment_payload_from_dict({"start_time": "0:00", "end_time": "0:30"})["virality_score"] == 0
