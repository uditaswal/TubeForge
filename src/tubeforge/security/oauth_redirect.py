"""Validate OAuth callbacks without permitting non-loopback cleartext."""
from urllib.parse import urlsplit


def valid_oauth_redirect(uri: str, *, platform: str) -> bool:
    try:
        parsed = urlsplit(uri)
        _ = parsed.port  # Reject malformed or out-of-range ports.
        return bool(
            parsed.hostname and parsed.username is None and parsed.password is None
            and not parsed.fragment
            and (parsed.scheme == "https" or (
                platform == "youtube" and parsed.scheme == "http"
                and parsed.hostname in {"127.0.0.1", "localhost"}
            ))
        )
    except ValueError:
        return False
