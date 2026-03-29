from django.db import migrations


class Migration(migrations.Migration):  # type: ignore[misc]
    dependencies = [
        ("send_money", "0005_beneficiaryrecord"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="beneficiaryrecord",
            unique_together={("user_id", "name", "delivery_method")},
        ),
    ]
