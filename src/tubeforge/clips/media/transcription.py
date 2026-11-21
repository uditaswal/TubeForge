"""Transcription helpers for the video pipeline."""

from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from pathlib import Path
from .. import decisions
from ..config import get_config
import httpx
import json
import re
import time
from .common import (
    ANALYSIS_LONG_UTTERANCE_MAX_DURATION_MS,
    ANALYSIS_LONG_UTTERANCE_MAX_WORDS,
    ANALYSIS_SEGMENT_MAX_DURATION_MS,
    ANALYSIS_SEGMENT_MAX_WORDS,
    ANALYSIS_SEGMENT_MIN_WORDS,
    ANALYSIS_UTTERANCE_SPLIT_THRESHOLD_MS,
    ANALYSIS_UTTERANCE_SPLIT_THRESHOLD_WORDS,
    TRANSCRIPT_CACHE_SCHEMA_VERSION,
    _WHISPER_AVAILABLE,
    _WHISPER_MODEL_CACHE,
    _whisper,
    logger,
)
from .ffmpeg import (
    ffprobe_duration,
    run_ffmpeg_command,
    select_audio_stream_index,
)


def _prepare_audio_for_transcription(video_path: Path) -> Path:
    """Extract a compact audio-only file for transcription."""
    audio_path = video_path.with_name(f"{video_path.stem}.transcription.mp3")
    if audio_path.exists() and audio_path.stat().st_size > 0:
        return audio_path

    # Transcribe the same track the renderer cuts, not ffmpeg's implicit pick.
    audio_stream = select_audio_stream_index(video_path)
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        *(["-map", f"0:a:{audio_stream}"] if audio_stream is not None else []),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-b:a",
        "64k",
        str(audio_path),
    ]
    try:
        result = run_ffmpeg_command(command, timeout=900)
    except FileNotFoundError:
        logger.warning(
            "ffmpeg is not available; falling back to source video for transcription"
        )
        return video_path

    if result.returncode != 0 or not audio_path.exists() or audio_path.stat().st_size == 0:
        logger.warning(
            "Failed to extract transcription audio with ffmpeg; falling back to source video"
        )
        return video_path

    logger.info(
        "Prepared transcription audio: %s (%.2f MB)",
        audio_path,
        audio_path.stat().st_size / (1024 * 1024),
    )
    return audio_path


def _get_whisper_model(model_name: str = "base.en"):
    """Load and cache a faster-whisper model (int8 on CPU by default)."""
    if not _WHISPER_AVAILABLE:
        raise RuntimeError(
            "faster-whisper is not installed. Install it with: uv add faster-whisper"
        )
    config = get_config()
    key = (model_name, config.whisper_compute_type, config.whisper_threads)
    if key not in _WHISPER_MODEL_CACHE:
        # One model at a time: on a 4 GB machine a second resident model is an OOM.
        _WHISPER_MODEL_CACHE.clear()
        logger.info("Loading faster-whisper model: %s (%s)", model_name, key[1])
        _WHISPER_MODEL_CACHE[key] = _whisper.WhisperModel(
            model_name,
            device="cpu",
            compute_type=config.whisper_compute_type,
            cpu_threads=config.whisper_threads,
        )
    return _WHISPER_MODEL_CACHE[key]


def _extract_audio_range(video_path: Path, start: float, end: float) -> Path:
    """Write ``[start, end]`` of the source audio as 16 kHz mono for Whisper."""
    out = video_path.with_name(f"{video_path.stem}.win_{int(start * 1000)}_{int(end * 1000)}.wav")
    if out.exists() and out.stat().st_size > 0:
        return out
    command = [
        "ffmpeg", "-y", "-ss", f"{start:.3f}", "-t", f"{max(0.1, end - start):.3f}",
        "-i", str(video_path), "-vn", "-ac", "1", "-ar", "16000", str(out),
    ]
    result = run_ffmpeg_command(command, timeout=900)
    if result.returncode != 0 or not out.exists() or out.stat().st_size == 0:
        raise RuntimeError(f"Could not extract audio window {start:.1f}-{end:.1f}s")
    return out


def transcribe_with_whisper(
    video_path: Path,
    model_name: str = "base.en",
    language: Optional[str] = None,
    start: Optional[float] = None,
    end: Optional[float] = None,
) -> Dict[str, Any]:
    """Transcribe with local faster-whisper, word-level timestamps.

    ``start``/``end`` (seconds) transcribe only that window; every timestamp in
    the result is shifted back onto the source timeline. ``language`` None lets
    Whisper detect it; AssemblyAI-style codes such as ``en_us`` are reduced to
    the ISO 639-1 base. ``.en`` models are English-only, so no language is passed.
    """
    windowed = start is not None and end is not None
    audio_path = (
        _extract_audio_range(video_path, float(start), float(end))
        if windowed
        else _prepare_audio_for_transcription(video_path)
    )
    offset = float(start) if windowed else 0.0
    model = _get_whisper_model(model_name)
    whisper_language = None if model_name.endswith(".en") else (
        language.split("_", 1)[0] if language else None
    )
    logger.info(
        "Starting Whisper transcription with model: %s (language: %s, window: %s)",
        model_name,
        whisper_language or "auto",
        f"{start:.0f}-{end:.0f}s" if windowed else "full",
    )
    segments, info = model.transcribe(
        str(audio_path),
        word_timestamps=True,
        language=whisper_language,
        vad_filter=True,
        beam_size=1,
        condition_on_previous_text=False,
    )
    out_segments: List[Dict[str, Any]] = []
    texts: List[str] = []
    for seg in segments:  # lazy generator: this is where the decoding happens
        words = [
            {
                "word": w.word,
                "start": float(w.start) + offset,
                "end": float(w.end) + offset,
                "probability": float(w.probability),
            }
            for w in (seg.words or [])
        ]
        out_segments.append(
            {
                "text": seg.text,
                "start": float(seg.start) + offset,
                "end": float(seg.end) + offset,
                "words": words,
            }
        )
        texts.append(seg.text.strip())
    return {"segments": out_segments, "text": " ".join(texts), "language": info.language}


def _whisper_result_to_transcript_data(whisper_result: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a Whisper result dict to the standard transcript-cache format.

    Whisper reports timings in seconds; the cache (and AssemblyAI path) stores
    milliseconds, so each timestamp is multiplied by 1000 here.
    """
    words_data: List[Dict[str, Any]] = []
    utterances_data: List[Dict[str, Any]] = []

    for segment in whisper_result.get("segments") or []:
        seg_words = [
            {
                "text": w.get("word", w.get("text", "")),
                "start": int(w["start"] * 1000) if isinstance(w.get("start"), float) else int(w.get("start", 0)),
                "end": int(w["end"] * 1000) if isinstance(w.get("end"), float) else int(w.get("end", 0)),
                "confidence": w.get("probability", w.get("confidence", 1.0)),
                "speaker": None,
            }
            for w in segment.get("words") or []
        ]
        utterances_data.append(
            {
                "text": segment.get("text", ""),
                "start": int(segment["start"] * 1000) if "start" in segment else 0,
                "end": int(segment["end"] * 1000) if "end" in segment else 0,
                "speaker": None,
                "words": seg_words,
            }
        )
        words_data.extend(seg_words)

    return {
        "version": TRANSCRIPT_CACHE_SCHEMA_VERSION,
        "words": words_data,
        "utterances": utterances_data,
        "text": whisper_result.get("text", ""),
        "language_code": whisper_result.get("language"),
    }


def transcribe_with_youtube_captions(video_url: str) -> Optional[str]:
    """Extract a plain-text transcript from a YouTube video's captions via yt-dlp.

    Only valid for YouTube-sourced videos. Returns plain text without word-level
    timestamps, so subtitle generation is not supported on this path.
    """
    try:
        import yt_dlp
    except ImportError:
        logger.error("yt-dlp is required for YouTube caption extraction")
        return None

    video_id = None
    match = re.search(r"(?:v=|youtu\.be/|shorts/)([A-Za-z0-9_-]{11})", video_url)
    if match:
        video_id = match.group(1)

    if not video_id:
        logger.error("Could not extract YouTube video ID from URL: %s", video_url)
        return None

    temp_dir = Path(get_config().temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)
    subs_path = temp_dir / f"{video_id}.en.vtt"

    try:
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["en"],
            "subtitlesformat": "vtt",
            "skip_download": True,
            "outtmpl": str(temp_dir / video_id),
        }
        from ..ytdlp_options import cookie_options
        with yt_dlp.YoutubeDL({**ydl_opts, **cookie_options()}) as ydl:
            ydl.download([video_url])

        if subs_path.exists():
            text = subs_path.read_text(encoding="utf-8")
            lines = []
            for line in text.splitlines():
                stripped = line.strip()
                if (
                    stripped
                    and not stripped.startswith("WEBVTT")
                    and not stripped.startswith("Kind:")
                    and not stripped.startswith("Language:")
                    and "-->" not in line
                    and not stripped.startswith("NOTE")
                    and not re.match(r"^\d+$", stripped)
                ):
                    lines.append(stripped)
            return " ".join(lines)

        logger.warning("No English captions found for video %s", video_id)
        return None

    except Exception as e:
        logger.error("Failed to extract YouTube captions: %s", e)
        return None
    finally:
        for f in temp_dir.glob(f"{video_id}.*"):
            if f.suffix in (".vtt", ".srt", ".ttml", ".json"):
                try:
                    f.unlink()
                except OSError:
                    pass


def get_video_transcript(
    video_path: Path,
    speech_model: str = "universal",
    source_url: Optional[str] = None,
) -> str:
    """Get a video transcript using the configured provider.

    Dispatches to local Whisper or YouTube captions. ``source_url`` enables the youtube_captions
    provider, which needs the original URL rather than a local file path.
    """
    logger.info(f"Getting transcript for: {video_path}")
    runtime_config = get_config()
    provider = runtime_config.transcription_provider

    if provider == "whisper":
        if source_url and (getattr(runtime_config, "analysis_strategy", "full") == "signals" or getattr(runtime_config, "source_window", None)):
            return _get_transcript_with_signals(video_path, source_url, runtime_config)
        return _get_transcript_with_whisper(video_path, runtime_config)
    if provider == "youtube_captions":
        if not source_url:
            raise ValueError(
                "youtube_captions provider requires a YouTube URL. "
                "Pass source_url to get_video_transcript()."
            )
        return _get_transcript_with_youtube_captions(source_url)
    raise ValueError(f"Unsupported transcription provider: {provider}")


def _get_transcript_with_whisper(video_path: Path, runtime_config) -> str:
    """Get transcript using local Whisper with word-level timestamps."""
    model_name = runtime_config.whisper_model
    decisions.record("windows", "whole-video", "the whole video is transcribed", model=model_name)
    logger.info("Starting Whisper transcription with model: %s", model_name)
    whisper_result = transcribe_with_whisper(
        video_path, model_name, runtime_config.transcription_language or None
    )

    formatted_lines = format_transcript_for_analysis(whisper_result)
    cache_transcript_data(video_path, whisper_result)

    result = "\n".join(formatted_lines)
    logger.info(
        "Whisper transcript formatted: %d segments, %d chars",
        len(formatted_lines),
        len(result),
    )
    return result


def merge_whisper_windows(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Join per-window Whisper results (already on the source timeline) in time order."""
    segments = sorted(
        (seg for result in results for seg in result["segments"]), key=lambda seg: seg["start"]
    )
    # Neighbouring windows can both decode the same overlap; keep the first copy.
    unique: List[Dict[str, Any]] = []
    for seg in segments:
        if unique and seg["start"] < unique[-1]["end"] - 0.25:
            continue
        unique.append(seg)
    return {
        "segments": unique,
        "text": " ".join(seg["text"].strip() for seg in unique),
        "language": next((r.get("language") for r in results if r.get("language")), None),
    }


def _get_transcript_with_signals(video_path: Path, source_url: str, runtime_config) -> str:
    """Transcribe only the windows viewers engaged with, not the whole video."""
    from ..signals import choose_windows, load_or_fetch_signals, measure_audio_energy

    duration = ffprobe_duration(video_path)
    signals = dict(load_or_fetch_signals(source_url, video_path.with_suffix(".signals.json")) or {})
    if "audio_energy" not in signals:
        signals["audio_energy"] = measure_audio_energy(video_path, video_path.with_suffix(".audio-energy.json"))
    windows = choose_windows(
        duration,
        signals,
        count=runtime_config.signal_windows,
        before=runtime_config.signal_window_before,
        after=runtime_config.signal_window_after,
        window=getattr(runtime_config, "source_window", None),
    )
    counts = {name: len(signals.get(name) or []) for name in ("heatmap", "chapters", "caption_cues", "comments")}
    counts["chat_messages"] = int((signals.get("chat") or {}).get("messages") or 0)
    counts["loudness_points"] = len((signals.get("audio_energy") or {}).get("values") or [])
    decisions.record(
        "signals", "read", ("most-replayed heatmap: " + ("yes" if counts["heatmap"] else "none (live streams and small videos have none)")
         + "; live chat: " + (f'{counts["chat_messages"]} messages' if counts["chat_messages"] else "none")
         + "; loudness: " + ("measured" if counts["loudness_points"] else "not measured")),
        source_seconds=round(duration), **counts,
    )
    if not windows:
        decisions.record("windows", "whole-video", "no busy parts were found, so everything is transcribed")
        logger.warning("No signal windows for %s; transcribing the whole video", video_path)
        return _get_transcript_with_whisper(video_path, runtime_config)

    covered = sum(w.end - w.start for w in windows)
    for window in windows:
        decisions.record(
            "windows", "transcribe", f"picked from: {window.reason}" if window.score else "evenly spread, there was no stronger evidence",
            start=round(window.start), end=round(window.end), score=round(window.score, 2),
        )
    decisions.record("windows", "coverage", "the AI only reads what was transcribed, so it can only pick from these parts",
                     seconds=round(covered), of_seconds=round(duration), percent=round(100 * covered / max(duration, 1), 1))
    logger.info(
        "Signals strategy: %d windows, %.0f of %.0f s (%.0f%%): %s",
        len(windows), covered, duration, 100 * covered / max(duration, 1),
        ", ".join(f"{w.start:.0f}-{w.end:.0f}s[{w.reason}]" for w in windows),
    )
    results = [
        transcribe_with_whisper(
            video_path,
            runtime_config.whisper_model,
            runtime_config.transcription_language or None,
            start=window.start,
            end=window.end,
        )
        for window in windows
    ]
    merged = merge_whisper_windows(results)
    lines = format_transcript_for_analysis(merged)
    if not lines:
        raise RuntimeError("No speech was found in the selected windows")
    cache_transcript_data(video_path, merged)
    return "\n".join(lines)


def _get_transcript_with_youtube_captions(source_url: str) -> str:
    """Get transcript from YouTube captions (plain text, no word timings)."""
    logger.info("Extracting YouTube captions for: %s", source_url)
    transcript = transcribe_with_youtube_captions(source_url)
    if not transcript:
        raise RuntimeError(
            "YouTube caption extraction failed or returned no captions. "
            "Falling back requires a different TRANSCRIPTION_PROVIDER."
        )
    logger.info("YouTube caption transcript: %d chars", len(transcript))
    return transcript


def cache_transcript_data(video_path: Path, transcript) -> None:
    """Cache transcript data for subtitle generation.

    Handles both AssemblyAI transcript objects and Whisper result dicts.
    """
    cache_path = video_path.with_suffix(".transcript_cache.json")

    if isinstance(transcript, dict):
        cache_data = _whisper_result_to_transcript_data(transcript)
        with open(cache_path, "w") as f:
            json.dump(cache_data, f)
        logger.info("Cached %d words to %s", len(cache_data["words"]), cache_path)
        return

    words_data = []
    if transcript.words:
        words_data = [_serialize_transcript_word(word) for word in transcript.words]

    utterances_data = []
    if getattr(transcript, "utterances", None):
        utterances_data = [
            {
                "text": utterance.text,
                "start": utterance.start,
                "end": utterance.end,
                "speaker": getattr(utterance, "speaker", None),
                "words": [
                    _serialize_transcript_word(word)
                    for word in getattr(utterance, "words", []) or []
                ],
            }
            for utterance in transcript.utterances
        ]

    response = getattr(transcript, "json_response", None)
    language_code = response.get("language_code") if isinstance(response, dict) else None
    if not language_code:
        language_code = getattr(getattr(transcript, "config", None), "language_code", None)

    cache_data = {
        "version": TRANSCRIPT_CACHE_SCHEMA_VERSION,
        "words": words_data,
        "utterances": utterances_data,
        "text": transcript.text,
        # Lets language-specific cleanup (e.g. default filler words) avoid
        # cutting ordinary words in other languages.
        "language_code": language_code if isinstance(language_code, str) else None,
    }

    with open(cache_path, "w") as f:
        json.dump(cache_data, f)

    logger.info(f"Cached {len(words_data)} words to {cache_path}")


def load_cached_transcript_data(video_path: Path) -> Optional[Dict]:
    """Load cached AssemblyAI transcript data."""
    cache_path = video_path.with_suffix(".transcript_cache.json")

    if not cache_path.exists():
        return None

    try:
        with open(cache_path, "r") as f:
            payload = json.load(f)
            if "version" not in payload:
                payload["version"] = TRANSCRIPT_CACHE_SCHEMA_VERSION
                payload.setdefault("utterances", [])
            return payload
    except Exception as e:
        logger.warning(f"Failed to load transcript cache: {e}")
        return None


def _serialize_transcript_word(word) -> Dict[str, Any]:
    if isinstance(word, dict):
        return {
            "text": word.get("word", word.get("text", "")),
            "start": int(word["start"] * 1000) if isinstance(word.get("start"), float) else int(word.get("start", 0)),
            "end": int(word["end"] * 1000) if isinstance(word.get("end"), float) else int(word.get("end", 0)),
            "confidence": word.get("probability", word.get("confidence", 1.0)),
            "speaker": word.get("speaker"),
        }
    return {
        "text": word.text,
        "start": word.start,
        "end": word.end,
        "confidence": word.confidence if hasattr(word, "confidence") else 1.0,
        "speaker": getattr(word, "speaker", None),
    }


def _join_transcript_tokens(tokens: List[str]) -> str:
    text = " ".join(token.strip() for token in tokens if token and token.strip())
    for before, after in (
        (" ,", ","),
        (" .", "."),
        (" !", "!"),
        (" ?", "?"),
        (" ;", ";"),
        (" :", ":"),
        (" n't", "n't"),
        (" 're", "'re"),
        (" 've", "'ve"),
        (" 'll", "'ll"),
        (" 'd", "'d"),
        (" 'm", "'m"),
        (" 's", "'s"),
    ):
        text = text.replace(before, after)
    return text.strip()


def _format_words_for_analysis(
    words: List[Any],
    speaker: Optional[str] = None,
    *,
    min_words_per_segment: int = ANALYSIS_SEGMENT_MIN_WORDS,
    max_words_per_segment: int = ANALYSIS_SEGMENT_MAX_WORDS,
    max_duration_ms: int = ANALYSIS_SEGMENT_MAX_DURATION_MS,
) -> List[str]:
    if not words:
        return []

    formatted_lines: List[str] = []
    current_words: List[Any] = []
    current_start: Optional[int] = None

    def flush_segment() -> None:
        nonlocal current_words, current_start
        if not current_words:
            return
        start_time = format_ms_to_timestamp(current_words[0].start)
        end_time = format_ms_to_timestamp(current_words[-1].end)
        text = _join_transcript_tokens([word.text for word in current_words])
        if text:
            speaker_prefix = f"Speaker {speaker}: " if speaker else ""
            formatted_lines.append(f"[{start_time} - {end_time}] {speaker_prefix}{text}")
        current_words = []
        current_start = None

    for word in words:
        if current_start is None:
            current_start = word.start

        current_words.append(word)
        duration_ms = word.end - current_start
        segment_word_count = len(current_words)
        ends_sentence = str(word.text).endswith((".", "!", "?"))

        should_flush = False
        if segment_word_count >= max_words_per_segment:
            should_flush = True
        elif (
            ends_sentence
            and segment_word_count >= min_words_per_segment
        ):
            should_flush = True
        elif (
            duration_ms >= max_duration_ms
            and segment_word_count >= min_words_per_segment
        ):
            should_flush = True

        if should_flush:
            flush_segment()

    flush_segment()
    return formatted_lines


def format_transcript_for_analysis(transcript) -> List[str]:
    """Format transcripts into readable timestamped segments for AI analysis.

    Handles both AssemblyAI transcript objects (utterances/words with ms
    timings) and Whisper result dicts (segments with second-based timings).
    """
    # Whisper result dict: treat each segment as an utterance, converting the
    # second-based timings to milliseconds to match the timestamp formatter.
    if isinstance(transcript, dict):
        formatted_lines = []
        for segment in transcript.get("segments") or []:
            start_ms = int(segment.get("start", 0) * 1000)
            end_ms = int(segment.get("end", 0) * 1000)
            formatted_lines.append(
                f"[{format_ms_to_timestamp(start_ms)} - {format_ms_to_timestamp(end_ms)}] "
                f"{segment.get('text', '').strip()}"
            )
        return formatted_lines

    utterances = getattr(transcript, "utterances", None) or []
    if utterances:
        formatted_lines = []
        for utterance in utterances:
            utterance_words = list(getattr(utterance, "words", []) or [])
            utterance_duration = max(0, int(utterance.end) - int(utterance.start))
            if utterance_words and (
                utterance_duration > ANALYSIS_UTTERANCE_SPLIT_THRESHOLD_MS
                or len(utterance_words) > ANALYSIS_UTTERANCE_SPLIT_THRESHOLD_WORDS
            ):
                formatted_lines.extend(
                    _format_words_for_analysis(
                        utterance_words,
                        getattr(utterance, "speaker", None),
                        max_words_per_segment=ANALYSIS_LONG_UTTERANCE_MAX_WORDS,
                        max_duration_ms=ANALYSIS_LONG_UTTERANCE_MAX_DURATION_MS,
                    )
                )
                continue

            start_time = format_ms_to_timestamp(utterance.start)
            end_time = format_ms_to_timestamp(utterance.end)
            speaker = getattr(utterance, "speaker", None)
            speaker_prefix = f"Speaker {speaker}: " if speaker else ""
            formatted_lines.append(
                f"[{start_time} - {end_time}] {speaker_prefix}{utterance.text}"
            )
        return formatted_lines

    formatted_lines = []
    words = getattr(transcript, "words", None) or []
    if not words:
        return formatted_lines

    logger.info(f"Processing {len(words)} words with precise timing")
    return _format_words_for_analysis(words)


def format_ms_to_timestamp(ms: int) -> str:
    """Format milliseconds to MM:SS format."""
    seconds = ms // 1000
    minutes = seconds // 60
    seconds = seconds % 60
    return f"{minutes:02d}:{seconds:02d}"
