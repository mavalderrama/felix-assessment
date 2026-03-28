"""Django management command: seed exchange_rates table.

Usage:
    python backend/manage.py seed_exchange_rates
"""
from __future__ import annotations

from decimal import Decimal

from django.core.management.base import BaseCommand

# All rates are USD → destination currency.
# To add cross-rates, add extra entries below.
RATES = [
    ("USD", "MXN", Decimal("17.45")),
    ("USD", "COP", Decimal("4120.50")),
    ("USD", "GTQ", Decimal("7.72")),
    ("USD", "PHP", Decimal("56.30")),
    ("USD", "INR", Decimal("83.12")),
    ("USD", "GBP", Decimal("0.79")),
    ("USD", "USD", Decimal("1.00")),
]


class Command(BaseCommand):
    help = "Seed the exchange_rates table with default USD→X rates."

    def handle(self, *args, **options) -> None:
        from send_money.adapters.persistence.django_models import ExchangeRate

        created = updated = 0
        for source, destination, rate in RATES:
            _, was_created = ExchangeRate.objects.update_or_create(
                source_currency=source,
                destination_currency=destination,
                defaults={"rate": rate, "is_active": True},
            )
            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Exchange rates: {created} created, {updated} updated. "
                f"Total: {ExchangeRate.objects.count()}."
            )
        )
