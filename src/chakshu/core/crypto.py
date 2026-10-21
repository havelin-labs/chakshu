"""Encryption for secrets stored in the database.

The GitHub App private key, its OAuth client secret, model API keys and user
tokens are encrypted with a key derived from CHAKSHU_SECRET_KEY. Someone with
a database dump but not the environment can't read them.
"""

import base64
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from chakshu.core.config import get_settings

MIN_SECRET_KEY_LENGTH = 32


class SecretKeyError(RuntimeError):
    pass


@lru_cache
def _fernet(secret_key: str) -> Fernet:
    if len(secret_key) < MIN_SECRET_KEY_LENGTH:
        raise SecretKeyError(
            f"CHAKSHU_SECRET_KEY must be at least {MIN_SECRET_KEY_LENGTH} characters. "
            'Generate one with: python -c "import secrets; print(secrets.token_urlsafe(48))"'
        )
    derived = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"chakshu:secrets:v1").derive(
        secret_key.encode()
    )
    return Fernet(base64.urlsafe_b64encode(derived))


def encrypt(plaintext: str) -> str:
    return _fernet(get_settings().secret_key).encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str | None) -> str | None:
    """Return the plaintext, or None if the value is missing or the key has changed."""
    if not ciphertext:
        return None
    try:
        return _fernet(get_settings().secret_key).decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        return None


def mask(value: str | None) -> str:
    """Show enough of a secret to recognise it in the UI, never the whole thing."""
    if not value:
        return ""
    if len(value) <= 12:
        return "•" * 8
    return f"{value[:6]}…{value[-4:]}"
