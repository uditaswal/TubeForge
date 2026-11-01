"""Batch plans use their own sources; built-in music beds no longer fail publication prep."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from tubeforge.batch_plans import BatchShort
from tubeforge.core.config import load_settings
from tubeforge.core.errors import ProviderValidationError
from tubeforge.pipeline.music import NO_MUSIC_NAME, SYNTHESIZED_MUSIC_NAME, catalog_track
from tubeforge.scheduling.batch_requests import build_batch_request

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
