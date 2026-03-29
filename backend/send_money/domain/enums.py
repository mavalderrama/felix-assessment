from __future__ import annotations

from enum import StrEnum


class DeliveryMethod(StrEnum):
    BANK_DEPOSIT = "BANK_DEPOSIT"
    MOBILE_WALLET = "MOBILE_WALLET"
    CASH_PICKUP = "CASH_PICKUP"

    @property
    def display_name(self) -> str:
        return _DELIVERY_METHOD_NAMES[self]


_DELIVERY_METHOD_NAMES: dict[DeliveryMethod, str] = {
    DeliveryMethod.BANK_DEPOSIT: "Bank Deposit",
    DeliveryMethod.MOBILE_WALLET: "Mobile Wallet",
    DeliveryMethod.CASH_PICKUP: "Cash Pickup",
}


class TransferStatus(StrEnum):
    COLLECTING = "COLLECTING"
    VALIDATED = "VALIDATED"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"


class Country(StrEnum):
    MX = "MX"
    CO = "CO"
    GT = "GT"
    PH = "PH"
    IN = "IN"
    GB = "GB"

    @property
    def display_name(self) -> str:
        return _COUNTRY_NAMES[self]


_COUNTRY_NAMES: dict[Country, str] = {
    Country.MX: "Mexico",
    Country.CO: "Colombia",
    Country.GT: "Guatemala",
    Country.PH: "Philippines",
    Country.IN: "India",
    Country.GB: "United Kingdom",
}

# ISO 4217 currency display names for currencies used in the system.
CURRENCY_NAMES: dict[str, str] = {
    "USD": "United States Dollar",
    "EUR": "Euro",
    "MXN": "Mexican Peso",
    "COP": "Colombian Peso",
    "GTQ": "Guatemalan Quetzal",
    "PHP": "Philippine Peso",
    "INR": "Indian Rupee",
    "GBP": "British Pound",
}


def format_country(code: str) -> str:
    """Return 'Mexico (MX)'. Falls back to the bare code for unknown values."""
    try:
        return f"{Country(code).display_name} ({code})"
    except ValueError:
        return code


def format_currency(code: str) -> str:
    """Return 'United States Dollar (USD)'. Falls back to the bare code."""
    name = CURRENCY_NAMES.get(code.upper())
    return f"{name} ({code})" if name else code


def format_delivery_method(code: str) -> str:
    """Return 'Bank Deposit'. Falls back to the bare code for unknown values."""
    try:
        return DeliveryMethod(code).display_name
    except ValueError:
        return code
