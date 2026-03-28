"""Converters between Python Decimal, google.type.Money, and session-state dicts.

All monetary conversions go through integer (units, nanos) arithmetic — no
float is introduced at any conversion boundary.
"""
from __future__ import annotations

from decimal import Decimal

from send_money.domain.value_objects import Money


# ── Decimal  ←→  Money ──────────────────────────────────────────────────────

def decimal_to_money(amount: Decimal, currency_code: str) -> Money:
    """Convert a Python Decimal to a Money value object."""
    return Money.from_decimal(amount, currency_code)


def money_to_decimal(money: Money) -> Decimal:
    """Convert a Money value object to a Python Decimal."""
    return money.to_decimal()


# ── Money  ←→  proto ────────────────────────────────────────────────────────

def money_to_proto(money: Money) -> object:
    """Convert a Money value object to a google.type.Money protobuf message."""
    return money.to_proto()


def proto_to_money(proto_money: object) -> Money:
    """Convert a google.type.Money protobuf message to a Money value object."""
    return Money.from_proto(proto_money)


# ── Money  ←→  session-state dict ───────────────────────────────────────────

def money_to_dict(money: Money) -> dict:
    """Serialise Money to a JSON-safe dict for ADK session state."""
    return money.to_dict()


def dict_to_money(d: dict) -> Money:
    """Deserialise Money from an ADK session-state dict.

    google.type.Money serialises ``units`` as a string when going through
    MessageToDict (e.g. ``{"units": "42", "nanos": 990000000}``).  We
    normalise both fields to int to handle both representations safely.
    """
    return Money.from_dict(d)


# ── Convenience: Decimal  ←→  proto (round-trip) ────────────────────────────

def decimal_to_proto(amount: Decimal, currency_code: str) -> object:
    return money_to_proto(decimal_to_money(amount, currency_code))


def proto_to_decimal(proto_money: object) -> Decimal:
    return money_to_decimal(proto_to_money(proto_money))
