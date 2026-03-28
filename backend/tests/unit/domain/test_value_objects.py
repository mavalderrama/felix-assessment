"""Unit tests for the Money value object."""
from __future__ import annotations

from decimal import Decimal

import pytest

from send_money.domain.value_objects import Money


def test_from_decimal_whole_amount():
    m = Money.from_decimal(Decimal("100"), "USD")
    assert m.units == 100
    assert m.nanos == 0
    assert m.currency_code == "USD"


def test_from_decimal_fractional_amount():
    m = Money.from_decimal(Decimal("42.99"), "USD")
    assert m.units == 42
    assert m.nanos == 990_000_000


def test_from_decimal_small_amount():
    m = Money.from_decimal(Decimal("0.01"), "USD")
    assert m.units == 0
    assert m.nanos == 10_000_000


def test_to_decimal_roundtrip():
    original = Decimal("123.456")
    m = Money.from_decimal(original, "EUR")
    assert m.to_decimal().quantize(Decimal("0.001")) == original


def test_no_float_rounding_error():
    # Classic float trap: 0.1 + 0.2 != 0.3 in IEEE 754
    # With Money this must be exact.
    m1 = Money.from_decimal(Decimal("0.1"), "USD")
    m2 = Money.from_decimal(Decimal("0.2"), "USD")
    total = m1.to_decimal() + m2.to_decimal()
    assert total == Decimal("0.3")


def test_from_dict_handles_string_units():
    # google.type.Money serialises units as string in some contexts
    m = Money.from_dict({"units": "42", "nanos": 990_000_000, "currency_code": "USD"})
    assert m.units == 42
    assert m.to_decimal().quantize(Decimal("0.01")) == Decimal("42.99")


def test_to_dict_roundtrip():
    m = Money.from_decimal(Decimal("500.50"), "MXN")
    d = m.to_dict()
    restored = Money.from_dict(d)
    assert restored == m


def test_currency_code_uppercased():
    m = Money.from_decimal(Decimal("10"), "usd")
    assert m.currency_code == "USD"


def test_negative_amount_raises():
    with pytest.raises(ValueError):
        Money.from_decimal(Decimal("-1"), "USD")


def test_str_representation():
    m = Money.from_decimal(Decimal("42.99"), "USD")
    assert "42.99" in str(m)
    assert "USD" in str(m)
