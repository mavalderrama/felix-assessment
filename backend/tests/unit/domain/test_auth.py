"""Unit tests for domain password hashing utilities."""
from __future__ import annotations

from send_money.domain.auth import hash_password, verify_password


def test_hash_and_verify_correct_password():
    stored = hash_password("my-secret-123")
    assert verify_password("my-secret-123", stored) is True


def test_verify_wrong_password_returns_false():
    stored = hash_password("correct-horse-battery")
    assert verify_password("wrong-password", stored) is False


def test_hash_produces_different_salts():
    h1 = hash_password("same-password")
    h2 = hash_password("same-password")
    assert h1 != h2  # different salts → different outputs


def test_hash_format_is_salt_dollar_hash():
    stored = hash_password("test")
    parts = stored.split("$")
    assert len(parts) == 2
    salt_hex, hash_hex = parts
    # 32 bytes of salt → 64 hex chars
    assert len(salt_hex) == 64
    # SHA-256 output → 64 hex chars
    assert len(hash_hex) == 64


def test_verify_empty_password():
    stored = hash_password("")
    assert verify_password("", stored) is True
    assert verify_password("anything", stored) is False


def test_verify_malformed_stored_value_returns_false():
    assert verify_password("test", "not-a-valid-hash") is False


def test_verify_unicode_password():
    stored = hash_password("contraseña-segura-日本語")
    assert verify_password("contraseña-segura-日本語", stored) is True
    assert verify_password("contrasena-segura", stored) is False
