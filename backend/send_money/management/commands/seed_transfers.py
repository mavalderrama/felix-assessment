"""Django management command: seed synthetic transfer records for demos.

Usage:
    python backend/manage.py seed_transfers         # seed all 10 transfers
    python backend/manage.py seed_transfers --clear  # wipe existing and re-seed

These are realistic past transfers that populate the DB so a live demo
can query the transfers table and show historical data alongside new
agent-created transfers.
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

# Simulated FX rates (must match simulated_services.py)
RATES = {
    "MXN": Decimal("17.45"),
    "COP": Decimal("4120.50"),
    "GTQ": Decimal("7.72"),
    "PHP": Decimal("56.30"),
    "INR": Decimal("83.12"),
    "GBP": Decimal("0.79"),
}

FEES = {
    ("MX", "BANK_DEPOSIT"): Decimal("2.99"),
    ("MX", "CASH_PICKUP"): Decimal("3.99"),
    ("MX", "MOBILE_WALLET"): Decimal("1.99"),
    ("CO", "BANK_DEPOSIT"): Decimal("3.49"),
    ("CO", "CASH_PICKUP"): Decimal("4.49"),
    ("GT", "BANK_DEPOSIT"): Decimal("3.99"),
    ("GT", "CASH_PICKUP"): Decimal("4.99"),
    ("PH", "BANK_DEPOSIT"): Decimal("2.49"),
    ("PH", "MOBILE_WALLET"): Decimal("1.49"),
    ("IN", "BANK_DEPOSIT"): Decimal("0.99"),
    ("GB", "BANK_DEPOSIT"): Decimal("1.99"),
}

# Synthetic transfers — diverse countries, methods, amounts, and recipients
TRANSFERS = [
    {
        "destination_country": "MX",
        "amount": Decimal("500.00"),
        "amount_currency": "USD",
        "beneficiary_name": "Maria Garcia Lopez",
        "delivery_method": "BANK_DEPOSIT",
        "user_id": "demo-user",
        "days_ago": 30,
    },
    {
        "destination_country": "MX",
        "amount": Decimal("200.00"),
        "amount_currency": "USD",
        "beneficiary_name": "Carlos Hernandez",
        "delivery_method": "CASH_PICKUP",
        "user_id": "demo-user",
        "days_ago": 25,
    },
    {
        "destination_country": "CO",
        "amount": Decimal("350.00"),
        "amount_currency": "USD",
        "beneficiary_name": "Sofia Rodriguez Mejia",
        "delivery_method": "BANK_DEPOSIT",
        "user_id": "demo-user",
        "days_ago": 21,
    },
    {
        "destination_country": "GT",
        "amount": Decimal("150.00"),
        "amount_currency": "USD",
        "beneficiary_name": "Jose Antonio Morales",
        "delivery_method": "CASH_PICKUP",
        "user_id": "demo-user",
        "days_ago": 18,
    },
    {
        "destination_country": "PH",
        "amount": Decimal("1000.00"),
        "amount_currency": "USD",
        "beneficiary_name": "Angelica Santos Cruz",
        "delivery_method": "BANK_DEPOSIT",
        "user_id": "demo-user",
        "days_ago": 14,
    },
    {
        "destination_country": "IN",
        "amount": Decimal("750.00"),
        "amount_currency": "USD",
        "beneficiary_name": "Priya Sharma",
        "delivery_method": "BANK_DEPOSIT",
        "user_id": "demo-user",
        "days_ago": 10,
    },
    {
        "destination_country": "GB",
        "amount": Decimal("2500.00"),
        "amount_currency": "USD",
        "beneficiary_name": "James Williams",
        "delivery_method": "BANK_DEPOSIT",
        "user_id": "demo-user",
        "days_ago": 7,
    },
    {
        "destination_country": "MX",
        "amount": Decimal("100.00"),
        "amount_currency": "USD",
        "beneficiary_name": "Maria Garcia Lopez",
        "delivery_method": "MOBILE_WALLET",
        "user_id": "demo-user",
        "days_ago": 5,
    },
    {
        "destination_country": "PH",
        "amount": Decimal("300.00"),
        "amount_currency": "USD",
        "beneficiary_name": "Marco Reyes",
        "delivery_method": "MOBILE_WALLET",
        "user_id": "demo-user",
        "days_ago": 3,
    },
    {
        "destination_country": "CO",
        "amount": Decimal("600.00"),
        "amount_currency": "USD",
        "beneficiary_name": "Valentina Torres",
        "delivery_method": "CASH_PICKUP",
        "user_id": "demo-user",
        "days_ago": 1,
    },
]


def _confirmation_code(index: int) -> str:
    return f"SM-{uuid.uuid4().hex[:6].upper()}"


def _dest_currency(country: str) -> str:
    mapping = {
        "MX": "MXN", "CO": "COP", "GT": "GTQ",
        "PH": "PHP", "IN": "INR", "GB": "GBP",
    }
    return mapping[country]


class Command(BaseCommand):
    help = "Seed the transfers table with synthetic historical records for demos."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete all existing transfers before seeding.",
        )

    def handle(self, *args, **options) -> None:
        from send_money.adapters.persistence.django_models import TransferRecord

        if options["clear"]:
            deleted, _ = TransferRecord.objects.all().delete()
            self.stdout.write(self.style.WARNING(f"Deleted {deleted} existing transfer(s)."))

        now = timezone.now()
        created = 0

        for i, t in enumerate(TRANSFERS):
            transfer_id = str(uuid.uuid4())
            country = t["destination_country"]
            method = t["delivery_method"]
            amount = t["amount"]
            dest_currency = _dest_currency(country)
            rate = RATES[dest_currency]
            fee = FEES.get((country, method), Decimal("2.99"))
            receive_amount = (amount * rate).quantize(Decimal("0.0001"))
            idempotency_key = f"demo-session:{country}:{int(amount)}:{t['beneficiary_name']}"

            _, was_created = TransferRecord.objects.get_or_create(
                idempotency_key=idempotency_key,
                defaults={
                    "id": transfer_id,
                    "destination_country": country,
                    "amount": amount,
                    "amount_currency": t["amount_currency"],
                    "beneficiary_name": t["beneficiary_name"],
                    "delivery_method": method,
                    "fee": fee,
                    "exchange_rate": rate.quantize(Decimal("0.000000001")),
                    "receive_amount": receive_amount,
                    "receive_currency": dest_currency,
                    "status": "CONFIRMED",
                    "confirmation_code": _confirmation_code(i),
                    "session_id": "demo-session",
                    "user_id": t["user_id"],
                    "created_at": now - timedelta(days=t["days_ago"]),
                },
            )
            if was_created:
                created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {created} new transfer(s). Total: {TransferRecord.objects.count()}."
            )
        )
