from __future__ import annotations

from cryptography.fernet import Fernet

from tubeforge.security.secrets import TokenCipher


def test_token_cipher_round_trip_and_tamper_rejection() -> None:
    cipher = TokenCipher(Fernet.generate_key().decode("ascii"))
    encrypted = cipher.encrypt({"refresh_token": "secret-token", "access_token": "short-lived"})
    assert "secret-token" not in encrypted
    assert cipher.decrypt(encrypted) == {"access_token": "short-lived", "refresh_token": "secret-token"}
    try:
        cipher.decrypt(encrypted[:-1] + ("A" if encrypted[-1] != "A" else "B"))
    except ValueError:
        pass
    else:
        raise AssertionError("tampered ciphertext must fail")
