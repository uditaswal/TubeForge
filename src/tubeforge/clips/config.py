import math
import os

from .runtime_settings import get_cached_setting, setting_prefers_admin


_config_override = None
LOCAL_OLLAMA_BASE_URL = "http://localhost:11434/v1"
DOCKER_OLLAMA_BASE_URL = "http://host.docker.internal:11434/v1"


class Config:
    def __init__(self):
        self.youtube_data_api_key = self._get_runtime_setting("YOUTUBE_DATA_API_KEY")

        self.whisper_model = os.getenv("WHISPER_MODEL") or os.getenv("WHISPER_MODEL_SIZE", "base.en")
        # "signals": transcribe only the windows viewers engaged with (heatmap, timestamped
        # comments, chapters) instead of the whole video. "full": the original behaviour.
        self.analysis_strategy = (os.getenv("ANALYSIS_STRATEGY", "full") or "full").strip().lower()
        self.signal_windows = int(os.getenv("SIGNAL_WINDOWS", "8") or 8)
        self.signal_window_before = float(os.getenv("SIGNAL_WINDOW_BEFORE", "60") or 60)
        self.signal_window_after = float(os.getenv("SIGNAL_WINDOW_AFTER", "90") or 90)
        self.whisper_compute_type = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
        self.whisper_threads = int(os.getenv("WHISPER_THREADS", "4") or 4)
        self.transcription_provider = self._normalize_transcription_provider(
            os.getenv("TRANSCRIPTION_PROVIDER")
            or "whisper"
        )
        # Empty means auto-detect the spoken language; otherwise an AssemblyAI
        # language code such as "es" or "en_us" forces it.
        self.transcription_language = self._normalize_transcription_language(
            os.getenv("TRANSCRIPTION_LANGUAGE")
        )
        self.llm = self._get_runtime_setting("LLM") or self._infer_default_llm()
        # Optional separate model for the cross-window candidate rerank pass.
        self.rerank_llm = self._get_optional_env("RERANK_LLM") or self.llm
        # Tried in order when the primary provider fails or hits a usage limit.
        self.llm_fallbacks = [
            name.strip()
            for name in (self._get_optional_env("LLM_FALLBACKS") or "").split(",")
            if name.strip()
        ]
        self.assembly_ai_api_key = self._get_runtime_setting("ASSEMBLY_AI_API_KEY")
        # An explicit deployment choice overrides the model for every processing mode.
        self.pexels_api_key = self._get_runtime_setting("PEXELS_API_KEY")
        self.apify_api_token = self._get_runtime_setting("APIFY_API_TOKEN")
        self.youtube_download_provider = self._normalize_youtube_download_provider(
            os.getenv("YOUTUBE_DOWNLOAD_PROVIDER", "yt_dlp")
        )
        self.youtube_metadata_provider = self._normalize_youtube_metadata_provider(
            os.getenv("YOUTUBE_METADATA_PROVIDER", "yt_dlp")
        )
        # Task creation waits this long for YouTube length metadata. 30s matches
        # the Twitch/Kick preflight deadline and covers yt-dlp's deno step when
        # the backend runs under amd64 emulation.
        self.youtube_preflight_timeout_seconds = self._get_positive_float_env(
            "YOUTUBE_PREFLIGHT_TIMEOUT_SECONDS",
            30.0,
            maximum=180.0,
        )
        # Empty disables the residential-proxy yt-dlp path. Nothing in the
        # download chain changes until this template is set.
        self.youtube_proxy_url = os.getenv("YOUTUBE_PROXY_URL", "").strip()
        # Same audio-first + section-only download as the proxy flow, from this machine's own
        # connection: transcribe the audio, then fetch only the ranges the clips use.
        self.youtube_direct_sections = self._get_bool_env("YOUTUBE_DIRECT_SECTIONS", False)
        self.youtube_proxy_timeout_seconds = self._get_int_env("YOUTUBE_PROXY_TIMEOUT_SECONDS", 300)
        # Twitch/Kick: YOUTUBE_PROXY_TIMEOUT_SECONDS is how long a download may go
        # without receiving data. This is the shortest overall cap for one call.
        # A long VOD is allowed longer, up to an hour, while data is still arriving.
        # Do not use the idle timeout as that cap.
        self.stream_download_max_seconds = self._get_int_env("STREAM_DOWNLOAD_MAX_SECONDS", 2400)
        self.youtube_proxy_country = os.getenv("YOUTUBE_PROXY_COUNTRY", "").strip()
        self.youtube_pot_provider_url = os.getenv("YOUTUBE_POT_PROVIDER_URL", "").strip()
        self.youtube_download_max_bytes = self._get_int_env("YOUTUBE_DOWNLOAD_MAX_BYTES", 2_000_000_000)
        self.youtube_section_padding_seconds = self._get_float_env("YOUTUBE_SECTION_PADDING_SECONDS", 10.0)
        self.youtube_max_height = self._get_int_env("YOUTUBE_MAX_HEIGHT", 1080)
        self.youtube_source_cache = self._get_bool_env("YOUTUBE_SOURCE_CACHE", True)
        self.youtube_source_cache_ttl_seconds = self._get_int_env(
            "YOUTUBE_SOURCE_CACHE_TTL_SECONDS", 604800
        )
        self.apify_twitch_actor = os.getenv("APIFY_TWITCH_ACTOR", "abotapi/twitch-scraper").strip()
        self.apify_kick_hls_actor = os.getenv("APIFY_KICK_HLS_ACTOR", "hipersoft/kick-downloader").strip()
        self.apify_kick_mp4_actor = os.getenv("APIFY_KICK_MP4_ACTOR", "parsebird/kick-video-downloader").strip()
        self.apify_stream_enabled = self._get_bool_env("APIFY_STREAM_PROVIDERS", True)
        self.apify_stream_timeout_seconds = self._get_int_env("APIFY_STREAM_TIMEOUT_SECONDS", 300)
        self.apify_kick_max_video_size_mb = self._get_int_env("APIFY_KICK_MAX_VIDEO_SIZE_MB", 2000)

        self.max_video_duration = int(os.getenv("MAX_VIDEO_DURATION", "5400"))

        self.max_clips = int(os.getenv("MAX_CLIPS", "10"))
        self.clip_duration = int(os.getenv("CLIP_DURATION", "30"))  # seconds

        self.temp_dir = os.getenv("TEMP_DIR", "temp")
        # (start, end) seconds when only part of the source is used; the engine sets it per run.
        self.source_window = None
        # A folder shared by every run, so a retry or a second job on the same video does not download it again.
        self.youtube_source_cache_dir = None
        self.youtube_fragment_concurrency = self._get_int_env("YOUTUBE_FRAGMENT_CONCURRENCY", 1)
        self.youtube_cookies_file = self._get_optional_env("YOUTUBE_COOKIES_FILE") or "data/config/youtube-cookies.txt"
        self.analysis_window_max_chars = 24_000  # transcript characters per AI call when neighbouring windows are merged
        self.media_storage = "local"

        # Redis configuration
        self.redis_host = os.getenv("REDIS_HOST", "localhost")
        self.redis_port = int(os.getenv("REDIS_PORT", "6379"))
        self.redis_password = self._get_optional_env("REDIS_PASSWORD")




        # Social publishing. Each provider needs an OAuth app registered by the
        # operator; users then connect their own accounts through that app.
        # Until TikTok audits the app, Direct Post only accepts SELF_ONLY posts
        # from accounts set to private. Set true only after the audit passes.
        # OAuth callbacks and public media fetches (Instagram pulls the video
        # from a URL) both go through the frontend, so they default to the
        # public app URL.
        # Who may use social publishing: "off" (default; nav and pages stay
        # hidden), "admins" (admins plus the allowlist, for a gated rollout)
        # or "all".
        # Platform rollout is separate from credentials and user access. An
        # explicitly empty list disables every platform; existing self-hosted
        # installations retain all platforms unless they set this variable.
        # Who may use workflows (series, topic, recap, trailer) and creator
        # instructions: "admins" (default; admins plus the allowlist, also
        # covers deploys where an old worker could take a new task), "all" or
        # "off". Self-hosters set "all".
        # With access "admins", these workflows are open to every user too, so
        # they can launch one at a time. Ignored by "off" and "all".
        self.workflow_topic_max_clips = max(1, self._get_int_env("WORKFLOW_TOPIC_MAX_CLIPS", 15))
        self.workflow_plan_timeout_seconds = self._get_positive_float_env(
            "WORKFLOW_PLAN_TIMEOUT_SECONDS", 1800.0, maximum=6 * 60 * 60
        )
        # Word budget for sending the whole transcript in one outline call.
        # None uses the provider default.
        self.workflow_full_context_max_words = (
            max(0, self._get_int_env("WORKFLOW_FULL_CONTEXT_MAX_WORDS", 0)) or None
        )
        self.fast_mode_max_clips = int(os.getenv("FAST_MODE_MAX_CLIPS", "10"))
        # Replay a later punchline before the clip. Off: the same line was
        # playing twice (teaser, then again inside the clip) and the opening
        # has to stand on its own. Set HOOK_FIRST_TEASER=true to opt back in.
        self.hook_first_teaser = self._get_bool_env("HOOK_FIRST_TEASER", False)
        # Cut between speakers on multi-person wide shots using diarization.
        self.speaker_framing = self._get_bool_env("SPEAKER_FRAMING", True)


    @staticmethod
    def _get_optional_env(name: str):
        value = os.getenv(name)
        if value is None:
            return None

        normalized = value.strip()
        return normalized or None

    @classmethod
    def _get_runtime_setting(cls, name: str):
        env_value = cls._get_optional_env(name)
        admin_value = get_cached_setting(name)
        if admin_value and setting_prefers_admin(name):
            return admin_value
        return env_value or admin_value

    def as_runtime_settings(self) -> dict[str, str | None]:
        return {}

    @staticmethod
    def _get_int_env(name: str, default: int) -> int:
        try:
            return int(os.getenv(name, str(default)))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _get_float_env(name: str, default: float) -> float:
        try:
            return float(os.getenv(name, str(default)))
        except (TypeError, ValueError):
            return default

    @classmethod
    def _get_positive_float_env(cls, name: str, default: float, *, maximum: float) -> float:
        """Parse a positive float. Blank or invalid values use ``default``.

        Values above ``maximum`` are capped so a typo cannot hold a request open.
        """
        raw = os.getenv(name)
        if raw is None or not raw.strip():
            return default
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return default
        if not math.isfinite(value) or value <= 0:
            return default
        return min(value, maximum)

    @staticmethod
    def _get_bool_env(name: str, default: bool) -> bool:
        value = os.getenv(name)
        if value is None:
            return default
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
        return default

    @staticmethod
    def _get_csv_env(name: str, default: list[str]) -> list[str]:
        value = os.getenv(name)
        if not value:
            return default
        return [item.strip() for item in value.split(",") if item.strip()]

    @staticmethod
    def _normalize_apify_quality(value: str | None) -> str:
        normalized = (value or "").strip()
        if normalized in {"360", "480", "720", "1080", "1440", "2160"}:
            return normalized
        return "1080"

    @staticmethod
    def _normalize_transcription_provider(value: str | None) -> str:
        normalized = (value or "").strip().lower().replace("-", "_")
        if normalized in ("whisper", "faster_whisper"):
            return "whisper"
        if normalized == "youtube_captions":
            return normalized
        return "whisper"

    @staticmethod
    def _normalize_transcription_language(value: str | None) -> str:
        normalized = (value or "").strip().lower().replace("-", "_")
        return "" if normalized in ("", "auto") else normalized

    @staticmethod
    def _normalize_youtube_metadata_provider(value: str | None) -> str:
        normalized = (value or "").strip().lower()
        if normalized == "youtube_data_api":
            return "youtube_data_api"
        return "yt_dlp"

    @staticmethod
    def _normalize_youtube_download_provider(value: str | None) -> str:
        normalized = (value or "").strip().lower().replace("-", "_")
        if normalized in {"apify", "rapidapi"}:
            return normalized
        return "yt_dlp"

    def resolve_youtube_data_api_key(self) -> str | None:
        return self.youtube_data_api_key

    def _infer_default_llm(self) -> str:
        return "runner"


def get_config() -> Config:
    override = _config_override
    if override is not None:
        return override
    return Config()


def set_config_override(config: Config | None) -> None:
    global _config_override
    _config_override = config
