"""Domain entities — Pydantic runtime models.

These are the in-memory representations used throughout the application.
Money is stored as (units, nanos, currency_code) triplets to avoid any
floating-point representation.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from .enums import DeliveryMethod, TransferStatus


class TransferDraft(BaseModel):
    """Represents a transfer being assembled across conversation turns.

    Money fields are stored as separate (units, nanos, currency_code) fields
    mirroring google.type.Money so no float is ever introduced.
    """

    id: Optional[str] = None
    destination_country: Optional[str] = None

    # Send amount (google.type.Money layout)
    amount_units: Optional[int] = None
    amount_nanos: Optional[int] = None
    amount_currency: Optional[str] = None

    beneficiary_name: Optional[str] = None
    beneficiary_id: Optional[str] = None
    delivery_method: Optional[DeliveryMethod] = None
    status: TransferStatus = TransferStatus.COLLECTING

    # Calculated during validation
    source_currency: Optional[str] = None
    destination_currency: Optional[str] = None

    fee_units: Optional[int] = None
    fee_nanos: Optional[int] = None

    exchange_rate_units: Optional[int] = None
    exchange_rate_nanos: Optional[int] = None

    receive_amount_units: Optional[int] = None
    receive_amount_nanos: Optional[int] = None

    idempotency_key: Optional[str] = None
    confirmation_code: Optional[str] = None

    # Session linkage
    session_id: Optional[str] = None
    user_id: Optional[str] = None

    # ── Derived helpers ──────────────────────────────────────

    REQUIRED_FIELDS: list[str] = Field(
        default=[
            "destination_country",
            "amount_units",
            "amount_currency",
            "beneficiary_name",
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

    def to_state_dict(self) -> dict:
        """Serialise to a JSON-safe dict for ADK session state."""
        return self.model_dump(mode="json")

    @classmethod
    def from_state_dict(cls, d: dict) -> "TransferDraft":
        """Reconstruct from ADK session state dict."""
        return cls.model_validate(d)
