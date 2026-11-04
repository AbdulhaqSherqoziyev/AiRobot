"""Single-owner authentication: scrypt password, HMAC-signed expiring session cookie,
login lockout. Mutating routes also need a custom header, which a cross-site form cannot send."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from datetime import timedelta

from quantlab.models import User, utcnow

SESSION_SECONDS = 12 * 3600
MAX_FAILED = 5
LOCK_MINUTES = 15


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt, _ = stored.split("$")
    except ValueError:
        return False
    return hmac.compare_digest(hash_password(password, bytes.fromhex(salt)), stored)


def make_token(secret: str, username: str, now: int | None = None) -> str:
    body = base64.urlsafe_b64encode(json.dumps({"u": username, "exp": (now or int(time.time())) + SESSION_SECONDS}).encode()).decode()
    return body + "." + hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()


def read_token(secret: str, token: str | None, now: int | None = None) -> str | None:
    if not token or "." not in token:
        return None
    body, sig = token.rsplit(".", 1)
    if not hmac.compare_digest(sig, hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()):
        return None
    try:
        data = json.loads(base64.urlsafe_b64decode(body))
    except ValueError:
        return None
    return data["u"] if data.get("exp", 0) > (now or int(time.time())) else None


def attempt_login(s, username: str, password: str) -> tuple[User | None, str]:
    user = s.query(User).filter_by(username=username).one_or_none()
    now = utcnow()
    if user is None:
        verify_password(password, hash_password("x"))  # same work as a real check
        return None, "invalid"
    if user.locked_until and user.locked_until > now:
        return None, "locked"
    if not verify_password(password, user.password_hash):
        user.failed_logins += 1
        if user.failed_logins >= MAX_FAILED:
            user.locked_until, user.failed_logins = now + timedelta(minutes=LOCK_MINUTES), 0
        return None, "invalid"
    user.failed_logins, user.locked_until = 0, None
    return user, "ok"
