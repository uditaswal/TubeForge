"""Settings come from the host application, not a database table."""

from __future__ import annotations


def apply_settings_to_process_env(settings: dict | None) -> None:
    return None


def get_cached_setting(key: str) -> str | None:
    return None


def setting_prefers_admin(key: str) -> bool:
    return False
