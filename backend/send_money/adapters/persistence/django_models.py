"""Django ORM models for domain tables.

All monetary columns use DecimalField which maps to PostgreSQL NUMERIC — exact
decimal arithmetic, no floating-point representation.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.db import models


class Corridor(models.Model):  # type: ignore[misc]
    """Supported country / delivery-method combinations."""

    country_code = models.CharField(max_length=2)
    delivery_method = models.CharField(max_length=20)
    currency_code = models.CharField(max_length=3)
    is_active = models.BooleanField(default=True)

    class Meta:
        app_label = "send_money"
        db_table = "send_money_corridors"
        unique_together = ("country_code", "delivery_method")

    def __str__(self) -> str:
        return f"{self.country_code}/{self.delivery_method} ({self.currency_code})"


class TransferRecord(models.Model):  # type: ignore[misc]
    """Persisted transfer records — written once on confirmation."""

    # Primary key is a UUIDv4 generated in Python before INSERT
    id = models.CharField(max_length=36, primary_key=True)
    idempotency_key = models.CharField(max_length=128, unique=True)

    destination_country = models.CharField(max_length=2)

    # Send amount — NUMERIC(19,9) via DecimalField (9 decimal places = nano precision)
    amount = models.DecimalField(max_digits=19, decimal_places=9)
    amount_currency = models.CharField(max_length=3)

    beneficiary_name = models.CharField(max_length=255)
    delivery_method = models.CharField(max_length=20)

    # Calculated fields
    fee = models.DecimalField(max_digits=19, decimal_places=9, default=Decimal("0"))
    exchange_rate = models.DecimalField(
        max_digits=19, decimal_places=9, null=True, blank=True
    )
    receive_amount = models.DecimalField(
        max_digits=19, decimal_places=9, null=True, blank=True
    )
    receive_currency = models.CharField(max_length=3, blank=True)

    status = models.CharField(max_length=20, default="CONFIRMED")
    confirmation_code = models.CharField(max_length=20, blank=True)

    session_id = models.CharField(max_length=128, blank=True)
    user_id = models.CharField(max_length=128, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "send_money"
        db_table = "send_money_transfers"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=Decimal("0")),
                name="transfer_amount_positive",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"Transfer {self.confirmation_code} — "
            f"{self.amount} {self.amount_currency} → {self.destination_country}"
        )


class ExchangeRate(models.Model):  # type: ignore[misc]
    """Live exchange rates used by the FX service."""

    source_currency = models.CharField(max_length=3)
    destination_currency = models.CharField(max_length=3)
    rate = models.DecimalField(max_digits=19, decimal_places=9)
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "send_money"
        db_table = "send_money_exchange_rates"
        unique_together = ("source_currency", "destination_currency")

    def __str__(self) -> str:
        return f"{self.source_currency}/{self.destination_currency} = {self.rate}"


class UserAccountRecord(models.Model):  # type: ignore[misc]
    """User account with balance for funding transfers."""

    id = models.CharField(max_length=36, primary_key=True)  # UUIDv4 set in Python
    username = models.CharField(max_length=128, unique=True)
    password_hash = models.CharField(max_length=512)
    balance = models.DecimalField(max_digits=19, decimal_places=9, default=Decimal("0"))
    balance_currency = models.CharField(max_length=3, default="USD")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "send_money"
        db_table = "send_money_user_accounts"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(balance__gte=Decimal("0")),
                name="account_balance_non_negative",
            ),
        ]

    def __str__(self) -> str:
        return f"Account {self.username} ({self.balance} {self.balance_currency})"


class BeneficiaryRecord(models.Model):  # type: ignore[misc]
    """Saved recipients for recurring money transfers."""

    id = models.CharField(max_length=36, primary_key=True)  # UUIDv4 set in Python
    user_id = models.CharField(max_length=128, db_index=True)
    name = models.CharField(max_length=255)
    account_number = models.CharField(max_length=255)
    country_code = models.CharField(max_length=2, blank=True)
    delivery_method = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "send_money"
        db_table = "send_money_beneficiaries"
        unique_together = ("user_id", "name", "account_number", "delivery_method")
        ordering = ["name"]

    def __str__(self) -> str:
        return f"Beneficiary {self.name} (user={self.user_id})"


class TransferAuditLog(models.Model):  # type: ignore[misc]
    """Audit log entry written on every confirmed transfer."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    transfer = models.ForeignKey(
        TransferRecord,
        on_delete=models.CASCADE,
        related_name="audit_logs",
        db_column="transfer_id",
    )
    session_id = models.CharField(max_length=128)
    user_id = models.CharField(max_length=128, blank=True)
    action = models.CharField(max_length=50)
    langfuse_trace_id = models.CharField(max_length=128, blank=True)
    langfuse_observation_id = models.CharField(max_length=128, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "send_money"
        db_table = "send_money_transfer_audit_logs"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return (
            f"AuditLog {self.action} "
            f"transfer={self.transfer_id} session={self.session_id}"
        )
