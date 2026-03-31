"""Narrow BeneficiaryRecord unique constraint to (user_id, name, account_number).

Previously the constraint was (user_id, name, account_number, delivery_method),
which allowed duplicate rows for the same account with different delivery methods.
Same person + same account = same beneficiary; the delivery_method should be
updated in-place, not create a second row.

A RunPython step removes any existing duplicates first (keeping the most recently
created row for each (user_id, name, account_number) group) so the constraint
can be applied cleanly.
"""

from typing import Any

from django.db import migrations


def _deduplicate_beneficiaries(apps: Any, schema_editor: Any) -> None:
    BeneficiaryRecord = apps.get_model("send_money", "BeneficiaryRecord")
    seen: set[tuple[str, str, str]] = set()
    # Order newest-first so we keep the latest entry.
    for record in BeneficiaryRecord.objects.order_by("-created_at"):
        key = (record.user_id, record.name.lower(), record.account_number)
        if key in seen:
            record.delete()
        else:
            seen.add(key)


class Migration(migrations.Migration):  # type: ignore[misc]
    dependencies = [
        ("send_money", "0008_transfer_beneficiary_fields"),
    ]

    operations = [
        migrations.RunPython(
            _deduplicate_beneficiaries,
            migrations.RunPython.noop,
        ),
        migrations.AlterUniqueTogether(
            name="beneficiaryrecord",
            unique_together={("user_id", "name", "account_number")},
        ),
    ]
