"""Money value object — lossless bridge between Python Decimal and
google.type.Money (units: int64, nanos: int32).

No float arithmetic ever touches a monetary value.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


@dataclass(frozen=True)
class Money:
    """Immutable monetary value.

    Internally stores amount as (units, nanos) — the same layout as
    google.type.Money — so there is no floating-point representation at any
    point.  The currency_code follows ISO 4217.

    Example: $42.99 USD → Money(units=42, nanos=990_000_000, currency_code="USD")
    """

    units: int
    nanos: int
    currency_code: str

    # ── Construction ────────────────────────────────────────

    @classmethod
    def from_decimal(cls, amount: Decimal, currency_code: str) -> "Money":
        """Create a Money value from a Python Decimal.

        The Decimal is quantised to nano precision (9 decimal places) before
        conversion so the result is always exact.
        """
        if amount < 0:
            raise ValueError("Monetary amount must be non-negative.")
        quantized = amount.quantize(Decimal("0.000000001"), rounding=ROUND_HALF_UP)
        units = int(quantized)
        nanos = int((quantized - units) * Decimal("1000000000"))
        return cls(units=units, nanos=nanos, currency_code=currency_code.upper())

    @classmethod
    def from_proto(cls, proto_money: object) -> "Money":
        """Construct from a google.type.Money protobuf message."""
        return cls(
            units=int(proto_money.units),  # type: ignore[attr-defined]
            nanos=int(proto_money.nanos),  # type: ignore[attr-defined]
            currency_code=proto_money.currency_code,  # type: ignore[attr-defined]
        )

    @classmethod
    def from_dict(cls, d: dict) -> "Money":
        """Reconstruct from a JSON-safe dict (as stored in ADK session state)."""
        return cls(
            units=int(d.get("units", 0)),
            nanos=int(d.get("nanos", 0)),
            currency_code=str(d.get("currency_code", "")),
        )

    # ── Conversion ──────────────────────────────────────────

    def to_decimal(self) -> Decimal:
        """Return exact Decimal representation."""
        return Decimal(self.units) + Decimal(self.nanos) / Decimal("1000000000")

    def to_proto(self) -> object:
        """Return a google.type.Money protobuf message."""
        from google.type.money_pb2 import Money as MoneyProto  # type: ignore[import-untyped]

        return MoneyProto(
            units=self.units,
            nanos=self.nanos,
            currency_code=self.currency_code,
        )

    def to_dict(self) -> dict:
        """Return a JSON-safe dict suitable for ADK session state."""
        return {
            "units": self.units,
            "nanos": self.nanos,
            "currency_code": self.currency_code,
        }

    # ── Display ─────────────────────────────────────────────

    def __str__(self) -> str:
        amount = self.to_decimal().normalize()
        return f"{amount} {self.currency_code}"
