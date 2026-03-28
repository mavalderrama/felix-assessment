"""Django ORM models for domain tables.

All monetary columns use DecimalField which maps to PostgreSQL NUMERIC — exact
decimal arithmetic, no floating-point representation.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from django.db import models


class Corridor(models.Model):
    """Supported country / delivery-method combinations."""

    country_code = models.CharField(max_length=2)
    delivery_method = models.CharField(max_length=20)
    currency_code = models.CharField(max_length=3)
    is_active = models.BooleanField(default=True)

    class Meta:
        app_label = "send_money"
        db_table = "corridors"
        unique_together = ("country_code", "delivery_method")

    def __str__(self) -> str:
        return f"{self.country_code}/{self.delivery_method} ({self.currency_code})"


class TransferRecord(models.Model):
    """Persisted transfer records — written once on confirmation."""

    # Primary key is a UUIDv4 generated in Python before INSERT
    id = models.CharField(max_length=36, primary_key=True)
    idempotency_key = models.CharField(max_length=128, unique=True)

    destination_country = models.CharField(max_length=2)

    # Send amount — NUMERIC(19,4) via DecimalField
    amount = models.DecimalField(max_digits=19, decimal_places=4)
    amount_currency = models.CharField(max_length=3)

    beneficiary_name = models.CharField(max_length=255)
    delivery_method = models.CharField(max_length=20)

    # Calculated fields
    fee = models.DecimalField(max_digits=19, decimal_places=4, default=Decimal("0"))
    exchange_rate = models.DecimalField(max_digits=19, decimal_places=9, null=True, blank=True)
    receive_amount = models.DecimalField(max_digits=19, decimal_places=4, null=True, blank=True)
    receive_currency = models.CharField(max_length=3, blank=True)

    status = models.CharField(max_length=20, default="CONFIRMED")
    confirmation_code = models.CharField(max_length=20, blank=True)

    session_id = models.CharField(max_length=128, blank=True)
    user_id = models.CharField(max_length=128, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "send_money"
        db_table = "transfers"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=Decimal("0")),
                name="transfer_amount_positive",
            ),
        ]

    def __str__(self) -> str:
        return f"Transfer {self.confirmation_code} — {self.amount} {self.amount_currency} → {self.destination_country}"


class ExchangeRate(models.Model):
    """Live exchange rates used by the FX service."""

    source_currency = models.CharField(max_length=3)
    destination_currency = models.CharField(max_length=3)
    rate = models.DecimalField(max_digits=19, decimal_places=9)
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "send_money"
        db_table = "exchange_rates"
        unique_together = ("source_currency", "destination_currency")

    def __str__(self) -> str:
        return f"{self.source_currency}/{self.destination_currency} = {self.rate}"


class TransferAuditLog(models.Model):
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
        db_table = "transfer_audit_logs"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"AuditLog {self.action} transfer={self.transfer_id} session={self.session_id}"
