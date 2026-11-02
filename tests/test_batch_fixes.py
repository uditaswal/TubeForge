"""Batch plans use their own sources; built-in music beds no longer fail publication prep."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from tubeforge.batch_plans import BatchShort
from tubeforge.core.config import load_settings
from tubeforge.core.errors import ProviderValidationError
from tubeforge.pipeline.music import NO_MUSIC_NAME, SYNTHESIZED_MUSIC_NAME, catalog_track
from tubeforge.scheduling.batch_requests import build_batch_request, rotated_music_track

TEXT = "Load balancing spreads incoming requests across several servers so no single server is overwhelmed. " * 6


def short(**changes):
    values = dict(id="lb-1", title="Why Load Balancers Exist", concept="How traffic is spread", beats=[{"t": 0, "point": "Hook"}],
                  sources=["https://en.wikipedia.org/wiki/Load_balancing_(computing)"])
    return BatchShort(**(values | changes))


@pytest.fixture
def settings():
    return load_settings(Path("config/default.yaml"))


class Fake:
    def __init__(self, hosts, **kwargs):
        self.hosts = hosts

    def ingest(self, source):
        return SimpleNamespace(excerpt=TEXT)


def test_plan_sources_become_the_evidence_and_no_notes_source_is_needed(settings, monkeypatch):
    monkeypatch.setattr("tubeforge.pipeline.sources.SourceIngestor", Fake)
    request = build_batch_request(short(), settings)
    assert [s.source_id for s in request.sources] == ["plan-source-1"]
    assert request.sources[0].excerpt.startswith("Load balancing spreads") and str(request.sources[0].url).endswith("Load_balancing_(computing)")
    assert request.script_owner in {"codex", "claude"}


def test_an_unreadable_plan_source_falls_back_to_the_research_path(settings, monkeypatch):
    class Broken(Fake):
        def ingest(self, source):
            raise ProviderValidationError("source redirects are not permitted")
    monkeypatch.setattr("tubeforge.pipeline.sources.SourceIngestor", Broken)
    request = build_batch_request(short(), settings)
    assert [s.source_id for s in request.sources] == ["operator-notes"]
    assert request.sources[0].title == "Unverified operator batch brief"


def test_a_plan_without_sources_keeps_the_brief_only_path(settings):
    request = build_batch_request(short(sources=[]), settings)
    assert [s.source_id for s in request.sources] == ["operator-notes"]


def test_built_in_music_beds_are_not_catalog_tracks():
    assert catalog_track(None, None) is None
    assert catalog_track(None, SYNTHESIZED_MUSIC_NAME) is None and catalog_track(None, NO_MUSIC_NAME) is None
    with pytest.raises(ProviderValidationError, match="no approved catalog"):
        catalog_track(None, "Some Track")
    catalog = SimpleNamespace(resolve=lambda name: (_ for _ in ()).throw(ProviderValidationError(f"approved music track is unavailable: {name}")))
    with pytest.raises(ProviderValidationError, match="unavailable"):
        catalog_track(catalog, "Missing Track")
    assert catalog_track(SimpleNamespace(resolve=lambda name: f"record:{name}"), "Real Track") == "record:Real Track"


def test_batch_requests_render_in_the_story_style(settings):
    assert build_batch_request(short(sources=[]), settings).video_style == "story"


def _settings_with_catalog(*names):
    tracks = [SimpleNamespace(name=name) for name in names]
    return SimpleNamespace(pipeline=SimpleNamespace(video_generation=SimpleNamespace(music_catalog=tracks)))


def test_music_rotation_is_none_without_a_real_catalog_to_rotate_into():
    # The synthesized bed alone is not "rotation" (nothing to vary against) — keep today's
    # unset/default behavior rather than forcing a pointless explicit choice.
    settings = _settings_with_catalog()
    assert rotated_music_track(short(), settings) is None


def test_music_rotation_is_deterministic_and_varies_across_shorts_on_the_same_day():
    settings = _settings_with_catalog("Track A", "Track B", "Track C")
    first = rotated_music_track(short(id="short-a", publish_at="2026-11-04T09:00:00+05:30"), settings)
    again = rotated_music_track(short(id="short-a", publish_at="2026-11-04T09:00:00+05:30"), settings)
    other = rotated_music_track(short(id="short-b", publish_at="2026-11-04T09:00:00+05:30"), settings)
    assert first == again  # reproducible for the same short, not random per call
    assert first in {SYNTHESIZED_MUSIC_NAME, "Track A", "Track B", "Track C"}
    assert other in {SYNTHESIZED_MUSIC_NAME, "Track A", "Track B", "Track C"}
    assert first != other  # distinct shorts land on different picks, not an endless loop of one bed


def test_music_rotation_differs_across_publish_days_for_the_same_short_id():
    settings = _settings_with_catalog("Track A", "Track B", "Track C")
    day1 = rotated_music_track(short(id="short-a", publish_at="2026-11-04T09:00:00+05:30"), settings)
    day2 = rotated_music_track(short(id="short-a", publish_at="2026-11-05T09:00:00+05:30"), settings)
    assert day1 != day2


def test_music_rotation_is_actually_wired_into_the_batch_request(settings, monkeypatch):
    monkeypatch.setattr("tubeforge.pipeline.sources.SourceIngestor", Fake)
    # default.yaml's catalog is empty, so there is nothing to rotate into: request.music_track
    # stays unset, same as before M-AU4, and resolves to the synthesized bed at render time.
    request = build_batch_request(short(sources=[], publish_at="2026-11-04T09:00:00+05:30"), settings)
    assert request.music_track is None
