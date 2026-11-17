"""Options every yt-dlp call shares: the operator's YouTube cookies, when they provided any.

YouTube sometimes answers "Sign in to confirm you're not a bot". The remedy is a cookies file exported from a logged-in browser
(Netscape format). It is a credential: it is only passed to yt-dlp, never logged, and lives in the git-ignored data folder.
"""

from __future__ import annotations

from pathlib import Path

from .config import get_config

BOT_CHECK_MARKER = "confirm you\u2019re not a bot"  # yt-dlp prints a typographic apostrophe
COOKIES_HINT = (
    "YouTube asked to confirm this is not a bot. Export your YouTube cookies from a logged-in browser as a Netscape cookies.txt file, "
    "save it as data/config/youtube-cookies.txt, and retry (see docs/clips.md)."
)


def is_bot_check(message: str) -> bool:
    text = str(message).replace("\u2019", "'").lower()
    return "confirm you're not a bot" in text or "sign in to confirm" in text


def cookie_options(config=None) -> dict:
    """``{"cookiefile": path}`` when the cookies file exists, else nothing."""
    path = getattr(config or get_config(), "youtube_cookies_file", None)
    try:
        return {"cookiefile": str(path)} if path and Path(path).is_file() else {}
    except OSError:
        return {}
