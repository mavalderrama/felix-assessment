"""Unit tests for enum display-name helpers."""
from __future__ import annotations

import pytest

from send_money.domain.enums import (
    CURRENCY_NAMES,
    Country,
    DeliveryMethod,
    format_country,
    format_currency,
    format_delivery_method,
)


# ── Country.display_name ──────────────────────────────────────────────────────

class TestCountryDisplayName:
    def test_mexico(self):
        assert Country.MX.display_name == "Mexico"

    def test_colombia(self):
        assert Country.CO.display_name == "Colombia"

    def test_guatemala(self):
        assert Country.GT.display_name == "Guatemala"

    def test_philippines(self):
        assert Country.PH.display_name == "Philippines"

    def test_india(self):
        assert Country.IN.display_name == "India"

    def test_united_kingdom(self):
        assert Country.GB.display_name == "United Kingdom"

    def test_all_countries_have_display_name(self):
        for country in Country:
            assert country.display_name, f"{country} has no display name"


# ── DeliveryMethod.display_name ───────────────────────────────────────────────

class TestDeliveryMethodDisplayName:
    def test_bank_deposit(self):
        assert DeliveryMethod.BANK_DEPOSIT.display_name == "Bank Deposit"

    def test_mobile_wallet(self):
        assert DeliveryMethod.MOBILE_WALLET.display_name == "Mobile Wallet"

    def test_cash_pickup(self):
        assert DeliveryMethod.CASH_PICKUP.display_name == "Cash Pickup"

    def test_all_methods_have_display_name(self):
        for method in DeliveryMethod:
            assert method.display_name, f"{method} has no display name"


# ── format_country ────────────────────────────────────────────────────────────

class TestFormatCountry:
    def test_known_code_includes_name_and_code(self):
        assert format_country("MX") == "Mexico (MX)"

    def test_known_code_gb(self):
        assert format_country("GB") == "United Kingdom (GB)"

    def test_unknown_code_returns_bare_code(self):
        assert format_country("XX") == "XX"

    def test_all_enum_values_format_correctly(self):
        for country in Country:
            result = format_country(country.value)
            assert country.display_name in result
            assert f"({country.value})" in result


# ── format_currency ───────────────────────────────────────────────────────────

class TestFormatCurrency:
    def test_usd(self):
        assert format_currency("USD") == "United States Dollar (USD)"

    def test_mxn(self):
        assert format_currency("MXN") == "Mexican Peso (MXN)"

    def test_eur(self):
        assert format_currency("EUR") == "Euro (EUR)"

    def test_gbp(self):
        assert format_currency("GBP") == "British Pound (GBP)"

    def test_unknown_code_returns_bare_code(self):
        assert format_currency("XYZ") == "XYZ"


# ── format_delivery_method ────────────────────────────────────────────────────

class TestFormatDeliveryMethod:
    def test_bank_deposit(self):
        assert format_delivery_method("BANK_DEPOSIT") == "Bank Deposit"

    def test_mobile_wallet(self):
        assert format_delivery_method("MOBILE_WALLET") == "Mobile Wallet"

    def test_cash_pickup(self):
        assert format_delivery_method("CASH_PICKUP") == "Cash Pickup"

    def test_unknown_code_returns_bare_code(self):
        assert format_delivery_method("CARRIER_PIGEON") == "CARRIER_PIGEON"


# ── CURRENCY_NAMES completeness ───────────────────────────────────────────────

class TestCurrencyNamesCompleteness:
    """All destination currencies seeded in the system must have display names."""

    _SEEDED_CURRENCIES = {"USD", "EUR", "MXN", "COP", "GTQ", "PHP", "INR", "GBP"}

    def test_all_seeded_currencies_present(self):
        for code in self._SEEDED_CURRENCIES:
            assert code in CURRENCY_NAMES, f"Missing display name for {code}"

    def test_display_names_are_non_empty(self):
        for code, name in CURRENCY_NAMES.items():
            assert name.strip(), f"Empty display name for {code}"
