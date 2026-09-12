"""Encryption boundary for OAuth refresh/access token envelopes."""
from __future__ import annotations

import json
from cryptography.fernet import Fernet, InvalidToken


class TokenCipher:
    def __init__(self, key: str) -> None: self._fernet = Fernet(key.encode("ascii"))
    def encrypt(self, value: dict[str, object]) -> str: return self._fernet.encrypt(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).decode("ascii")
    def decrypt(self, value: str) -> dict[str, object]:
        try: decoded = json.loads(self._fernet.decrypt(value.encode("ascii")).decode("utf-8"))
        except (InvalidToken, UnicodeDecodeError, json.JSONDecodeError) as error: raise ValueError("encrypted credential cannot be decrypted") from error
        if not isinstance(decoded, dict): raise ValueError("credential envelope must be an object")
        return decoded
