from decimal import Decimal

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies: list = []

    operations = [
        migrations.CreateModel(
            name="Corridor",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("country_code", models.CharField(max_length=2)),
                ("delivery_method", models.CharField(max_length=20)),
                ("currency_code", models.CharField(max_length=3)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={
                "db_table": "corridors",
                "unique_together": {("country_code", "delivery_method")},
            },
        ),
        migrations.CreateModel(
            name="TransferRecord",
            fields=[
                ("id", models.CharField(max_length=36, primary_key=True, serialize=False)),
                ("idempotency_key", models.CharField(max_length=128, unique=True)),
                ("destination_country", models.CharField(max_length=2)),
                ("amount", models.DecimalField(decimal_places=4, max_digits=19)),
                ("amount_currency", models.CharField(max_length=3)),
                ("beneficiary_name", models.CharField(max_length=255)),
                ("delivery_method", models.CharField(max_length=20)),
                ("fee", models.DecimalField(decimal_places=4, default=Decimal("0"), max_digits=19)),
                ("exchange_rate", models.DecimalField(blank=True, decimal_places=9, max_digits=19, null=True)),
                ("receive_amount", models.DecimalField(blank=True, decimal_places=4, max_digits=19, null=True)),
                ("receive_currency", models.CharField(blank=True, max_length=3)),
                ("status", models.CharField(default="CONFIRMED", max_length=20)),
                ("confirmation_code", models.CharField(blank=True, max_length=20)),
                ("session_id", models.CharField(blank=True, max_length=128)),
                ("user_id", models.CharField(blank=True, max_length=128)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "transfers",
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(amount__gt=Decimal("0")),
                        name="transfer_amount_positive",
                    )
                ],
            },
        ),
    ]
