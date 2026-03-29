"""Domain entities — Pydantic runtime models.

These are the in-memory representations used throughout the application.
Money is stored as (units, nanos, currency_code) triplets to avoid any
floating-point representation.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .enums import DeliveryMethod, TransferStatus


class UserAccount(BaseModel):
    """A user account with a balance used to fund transfers."""

    id: str | None = None
    username: str = ""
    password_hash: str = ""
    balance_units: int = 0
    balance_nanos: int = 0
    balance_currency: str = "USD"


class Beneficiary(BaseModel):
    """A saved recipient for recurring money transfers."""

    id: str | None = None
    user_id: str = ""
    name: str = ""
    account_number: str = ""
    country_code: str | None = None
    delivery_method: DeliveryMethod | None = None


class TransferDraft(BaseModel):
    """Represents a transfer being assembled across conversation turns.

    Money fields are stored as separate (units, nanos, currency_code) fields
    mirroring google.type.Money so no float is ever introduced.
    """

    id: str | None = None
    destination_country: str | None = None

    # Send amount (google.type.Money layout)
    amount_units: int | None = None
    amount_nanos: int | None = None
    amount_currency: str | None = None

    beneficiary_name: str | None = None
    beneficiary_account: str | None = None
    beneficiary_id: str | None = None
    delivery_method: DeliveryMethod | None = None
    status: TransferStatus = TransferStatus.COLLECTING

    # Calculated during validation
    source_currency: str | None = None
    destination_currency: str | None = None

    fee_units: int | None = None
    fee_nanos: int | None = None

    exchange_rate_units: int | None = None
    exchange_rate_nanos: int | None = None

    receive_amount_units: int | None = None
    receive_amount_nanos: int | None = None

    idempotency_key: str | None = None
    confirmation_code: str | None = None

    # Session linkage
    session_id: str | None = None
    user_id: str | None = None

    # ── Derived helpers ──────────────────────────────────────

    REQUIRED_FIELDS: list[str] = Field(
        default=[
            "destination_country",
            "amount_units",
            "amount_currency",
            "beneficiary_name",
            "beneficiary_account",
            "delivery_method",
        ],
        exclude=True,
    )

    @property
    def missing_fields(self) -> list[str]:
        required = [
            "destination_country",
            "amount_units",
            "amount_currency",
            "beneficiary_name",
            "beneficiary_account",
            "delivery_method",
        ]
        return [f for f in required if getattr(self, f) is None]

    @property
    def is_complete(self) -> bool:
        return len(self.missing_fields) == 0

    @property
    def amount_display(self) -> str:
        if self.amount_units is None or self.amount_currency is None:
            return "not set"
        from .value_objects import Money

        m = Money(
            units=self.amount_units,
            nanos=self.amount_nanos or 0,
            currency_code=self.amount_currency,
        )
        return str(m)

    def to_state_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-safe dict for ADK session state."""
        return self.model_dump(mode="json")

    @classmethod
    def from_state_dict(cls, d: dict[str, Any]) -> TransferDraft:
        """Reconstruct from ADK session state dict."""
        return cls.model_validate(d)
