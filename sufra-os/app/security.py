"""
Security primitives: PIN hashing, session tokens, lockout policy.

PINs are hashed before storage. Admin provisioning reveals a generated PIN
once for secure distribution; QR badges never contain the PIN.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

MAX_ATTEMPTS = 5          # failures allowed before a lockout
LOCKOUT_SECONDS = 30      # length of the first lockout
SESSION_HOURS = 12        # absolute session lifetime
IDLE_LOCK_MINUTES = 8     # enforced on the server and by the client


def hash_pin(pin: str) -> str:
    """salt$hash, both hex. PBKDF2-HMAC-SHA256, stdlib only."""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt), 200_000)
    return f"{salt}${digest.hex()}"


def verify_pin(pin: str, stored: str) -> bool:
    if not stored or "$" not in stored:
        return False
    salt, digest = stored.split("$", 1)
    check = hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt), 200_000)
    return hmac.compare_digest(check.hex(), digest)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def lockout_seconds_for(failed_attempts: int) -> int:
    """Escalating lockout: 30s, 60s, 120s... after every MAX_ATTEMPTS block."""
    blocks = failed_attempts // MAX_ATTEMPTS
    return LOCKOUT_SECONDS * (2 ** min(7, max(0, blocks - 1)))


def session_expiry() -> datetime:
    return datetime.now() + timedelta(hours=SESSION_HOURS)
