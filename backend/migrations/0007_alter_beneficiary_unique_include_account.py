from django.db import migrations


class Migration(migrations.Migration):  # type: ignore[misc]
    dependencies = [
        ("send_money", "0006_alter_beneficiary_unique_constraint"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="beneficiaryrecord",
            unique_together={("user_id", "name", "account_number", "delivery_method")},
        ),
    ]
