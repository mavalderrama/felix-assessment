"""Django management command: seed corridor data.

Usage:
    python backend/manage.py seed_corridors
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

CORRIDORS = [
    ("MX", "BANK_DEPOSIT", "MXN"),
    ("MX", "CASH_PICKUP", "MXN"),
    ("MX", "MOBILE_WALLET", "MXN"),
    ("CO", "BANK_DEPOSIT", "COP"),
    ("CO", "CASH_PICKUP", "COP"),
    ("GT", "BANK_DEPOSIT", "GTQ"),
    ("GT", "CASH_PICKUP", "GTQ"),
    ("PH", "BANK_DEPOSIT", "PHP"),
    ("PH", "MOBILE_WALLET", "PHP"),
    ("IN", "BANK_DEPOSIT", "INR"),
    ("GB", "BANK_DEPOSIT", "GBP"),
]


class Command(BaseCommand):
    help = "Seed the corridors table with supported country/delivery-method combinations."

    def handle(self, *args, **options) -> None:
        from send_money.adapters.persistence.django_models import Corridor

        created = 0
        for country_code, delivery_method, currency_code in CORRIDORS:
            _, was_created = Corridor.objects.get_or_create(
                country_code=country_code,
                delivery_method=delivery_method,
                defaults={"currency_code": currency_code, "is_active": True},
            )
            if was_created:
                created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {created} new corridor(s). Total: {Corridor.objects.count()}."
            )
        )
