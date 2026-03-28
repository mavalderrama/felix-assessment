from enum import StrEnum


class DeliveryMethod(StrEnum):
    BANK_DEPOSIT = "BANK_DEPOSIT"
    MOBILE_WALLET = "MOBILE_WALLET"
    CASH_PICKUP = "CASH_PICKUP"


class TransferStatus(StrEnum):
    COLLECTING = "COLLECTING"
    VALIDATED = "VALIDATED"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"


class Country(StrEnum):
    MX = "MX"  # Mexico
    CO = "CO"  # Colombia
    GT = "GT"  # Guatemala
    PH = "PH"  # Philippines
    IN = "IN"  # India
    GB = "GB"  # United Kingdom
