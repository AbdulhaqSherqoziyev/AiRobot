"""Exchange secrets at rest: Fernet with a key derived from QL_SECRET_KEY."""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet


def _fernet(secret_key: str) -> Fernet:
    if len(secret_key) < 32:
        raise ValueError("QL_SECRET_KEY must be at least 32 characters")
    return Fernet(base64.urlsafe_b64encode(hashlib.scrypt(secret_key.encode(), salt=b"quantlab-credentials", n=2**14, r=8, p=1, dklen=32)))


def encrypt(secret_key: str, value: str) -> str:
    return _fernet(secret_key).encrypt(value.encode()).decode()


def decrypt(secret_key: str, token: str) -> str:
    return _fernet(secret_key).decrypt(token.encode()).decode()
