"""Add beneficiary_id to TransferRecord.

Links each confirmed transfer to the saved beneficiary record so the
recipient's account details can be looked up via a join, rather than
duplicating account data in the transfers table.
"""

from django.db import migrations, models


class Migration(migrations.Migration):  # type: ignore[misc]
    dependencies = [
        ("send_money", "0007_alter_beneficiary_unique_include_account"),
    ]

    operations = [
        migrations.AddField(
            model_name="transferrecord",
            name="beneficiary_id",
            field=models.CharField(blank=True, default="", max_length=36),
            preserve_default=False,
        ),
    ]
