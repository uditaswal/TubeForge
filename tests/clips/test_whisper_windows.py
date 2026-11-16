"""faster-whisper adapter: window offsets, result shape, and the cache format."""

from pathlib import Path
from types import SimpleNamespace

from tubeforge.clips.media import transcription as t


class FakeModel:
    def transcribe(self, path, **kwargs):
        self.kwargs = kwargs
        word = SimpleNamespace(word=" hello", start=1.0, end=1.5, probability=0.9)
        seg = SimpleNamespace(text=" hello there", start=1.0, end=2.0, words=[word])
        return iter([seg]), SimpleNamespace(language="en")


def test_window_timestamps_land_on_the_source_timeline(monkeypatch, tmp_path):
    model = FakeModel()
    monkeypatch.setattr(t, "_get_whisper_model", lambda name: model)
    monkeypatch.setattr(t, "_extract_audio_range", lambda path, s, e: tmp_path / "w.wav")
    result = t.transcribe_with_whisper(Path("/x/video.mp4"), "base.en", "en_us", start=1860.0, end=2010.0)
    seg = result["segments"][0]
    assert (seg["start"], seg["end"]) == (1861.0, 1862.0)
    assert (seg["words"][0]["start"], seg["words"][0]["end"]) == (1861.0, 1861.5)
    assert model.kwargs["word_timestamps"] is True and model.kwargs["language"] is None  # .en model: no language


def test_cache_format_keeps_millisecond_words_for_the_renderer():
    data = t._whisper_result_to_transcript_data(
        {"segments": [{"text": "hi", "start": 1861.0, "end": 1862.0, "words": [{"word": "hi", "start": 1861.0, "end": 1861.5, "probability": 0.9}]}], "text": "hi", "language": "en"}
    )
    assert data["words"][0]["start"] == 1861000 and data["language_code"] == "en"


def test_multilingual_model_gets_the_iso_language(monkeypatch, tmp_path):
    model = FakeModel()
    monkeypatch.setattr(t, "_get_whisper_model", lambda name: model)
    monkeypatch.setattr(t, "_prepare_audio_for_transcription", lambda p: tmp_path / "a.mp3")
    t.transcribe_with_whisper(Path("/x/video.mp4"), "small", "es_mx")
    assert model.kwargs["language"] == "es"


def test_provider_defaults_to_local_whisper(monkeypatch):
    from tubeforge.clips.config import Config

    monkeypatch.delenv("TRANSCRIPTION_PROVIDER", raising=False)
    monkeypatch.delenv("ASSEMBLY_AI_API_KEY", raising=False)
    assert Config().transcription_provider == "whisper"
    monkeypatch.setenv("ASSEMBLY_AI_API_KEY", "x")
    assert Config().transcription_provider == "whisper"
    monkeypatch.setenv("TRANSCRIPTION_PROVIDER", "faster-whisper")
    assert Config().transcription_provider == "whisper"
