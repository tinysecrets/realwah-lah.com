"""Symmetric credential encryption for distributor proxy passwords.

Fernet (AES-128-CBC + HMAC-SHA256) wrapper. Key lives in PROXY_ENCRYPTION_KEY.
Rotating the key invalidates all stored proxy passwords — requires admin re-entry.
"""
from __future__ import annotations

import os
from cryptography.fernet import Fernet, InvalidToken


def _get_fernet() -> Fernet:
    key = os.environ.get("PROXY_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("PROXY_ENCRYPTION_KEY is not set in backend/.env")
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(plaintext: str) -> str:
    """Return urlsafe base64 ciphertext for storage."""
    if plaintext is None:
        return ""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt ciphertext; raises ValueError on bad/rotated key."""
    if not ciphertext:
        return ""
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as e:
        raise ValueError("Unable to decrypt — key may have been rotated") from e
