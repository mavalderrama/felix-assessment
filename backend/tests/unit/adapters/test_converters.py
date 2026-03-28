"""Unit tests for proto converter functions."""
from __future__ import annotations

from decimal import Decimal

import pytest

from send_money.adapters.proto.converters import (
    decimal_to_money,
    decimal_to_proto,
    dict_to_money,
    money_to_decimal,
    money_to_dict,
    money_to_proto,
    proto_to_decimal,
    proto_to_money,
)
from send_money.domain.value_objects import Money


def test_decimal_to_money_whole():
    m = decimal_to_money(Decimal("100"), "USD")
    assert m.units == 100
    assert m.nanos == 0
    assert m.currency_code == "USD"


def test_decimal_to_money_fractional():
    m = decimal_to_money(Decimal("9.99"), "EUR")
    assert m.units == 9
    assert m.nanos == 990_000_000


def test_money_to_decimal_round_trip():
    original = Decimal("123.456")
    m = decimal_to_money(original, "USD")
    result = money_to_decimal(m)
    assert result.quantize(Decimal("0.001")) == original


def test_money_to_dict_and_back():
    m = Money.from_decimal(Decimal("42.99"), "MXN")
    d = money_to_dict(m)
    assert d["units"] == 42
    assert d["nanos"] == 990_000_000
    assert d["currency_code"] == "MXN"
    restored = dict_to_money(d)
    assert restored == m


def test_dict_to_money_string_units():
    """google.type.Money MessageToDict produces string units — must be handled."""
    d = {"units": "42", "nanos": 990_000_000, "currency_code": "USD"}
    m = dict_to_money(d)
    assert m.units == 42
    assert m.to_decimal().quantize(Decimal("0.01")) == Decimal("42.99")


def test_money_to_proto_round_trip():
    m = Money.from_decimal(Decimal("500.50"), "USD")
    proto = money_to_proto(m)
    restored = proto_to_money(proto)
    assert restored == m


def test_decimal_to_proto_round_trip():
    original = Decimal("99.99")
    proto = decimal_to_proto(original, "USD")
    result = proto_to_decimal(proto)
    assert result.quantize(Decimal("0.01")) == original


def test_no_float_rounding_in_conversion():
    """Critical: 0.1 + 0.2 must equal 0.3 through the converter."""
    m1 = decimal_to_money(Decimal("0.1"), "USD")
    m2 = decimal_to_money(Decimal("0.2"), "USD")
    total = money_to_decimal(m1) + money_to_decimal(m2)
    assert total == Decimal("0.3")
