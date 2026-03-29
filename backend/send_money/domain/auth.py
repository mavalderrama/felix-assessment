"""Password hashing utilities — pure stdlib, no framework imports."""
from __future__ import annotations

import hashlib
import os

_SALT_BYTES = 32
_ITERATIONS = 260_000
_ALGO = "sha256"


def hash_password(password: str) -> str:
    """Return 'salt_hex$hash_hex' string suitable for storage."""
    salt = os.urandom(_SALT_BYTES)
    dk = hashlib.pbkdf2_hmac(_ALGO, password.encode("utf-8"), salt, _ITERATIONS)
    return f"{salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Verify a plaintext password against a stored 'salt_hex$hash_hex' value."""
    try:
        salt_hex, hash_hex = stored.split("$", 1)
    except ValueError:
        return False
    salt = bytes.fromhex(salt_hex)
    dk = hashlib.pbkdf2_hmac(_ALGO, password.encode("utf-8"), salt, _ITERATIONS)
    return dk.hex() == hash_hex
