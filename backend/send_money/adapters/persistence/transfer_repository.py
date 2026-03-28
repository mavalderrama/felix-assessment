"""Transfer repository implementation using Django ORM.

Uses select_for_update() + transaction.atomic() for atomic idempotency — the
same guarantee as a raw SELECT FOR UPDATE in PostgreSQL.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from asgiref.sync import sync_to_async

from send_money.domain.entities import TransferDraft
from send_money.domain.repositories import TransferRepository
from send_money.domain.value_objects import Money


class DjangoTransferRepository(TransferRepository):
    async def save(self, draft: TransferDraft) -> TransferDraft:
        @sync_to_async
        def _save() -> TransferDraft:
            from django.db import transaction
            from send_money.adapters.persistence.django_models import TransferRecord

            with transaction.atomic():
                # SELECT FOR UPDATE on idempotency key prevents double-submission
                existing_qs = TransferRecord.objects.select_for_update().filter(
                    idempotency_key=draft.idempotency_key
                )
                if existing_qs.exists():
                    return _to_entity(existing_qs.first())

                record = TransferRecord.objects.create(
                    id=draft.id,
                    idempotency_key=draft.idempotency_key,
                    destination_country=draft.destination_country,
                    amount=_money_to_decimal(draft.amount_units, draft.amount_nanos),
                    amount_currency=draft.amount_currency or "",
                    beneficiary_name=draft.beneficiary_name or "",
                    delivery_method=str(draft.delivery_method or ""),
                    fee=_money_to_decimal(draft.fee_units, draft.fee_nanos),
                    exchange_rate=_exchange_rate_decimal(draft),
                    receive_amount=_money_to_decimal(
                        draft.receive_amount_units, draft.receive_amount_nanos
                    ),
                    receive_currency=draft.destination_currency or "",
                    status=str(draft.status),
                    confirmation_code=draft.confirmation_code or "",
                    session_id=draft.session_id or "",
                    user_id=draft.user_id or "",
                )
                return _to_entity(record)

        return await _save()

    async def get_by_id(self, transfer_id: str) -> Optional[TransferDraft]:
        @sync_to_async
        def _get() -> Optional[TransferDraft]:
            from send_money.adapters.persistence.django_models import TransferRecord

            try:
                record = TransferRecord.objects.get(id=transfer_id)
                return _to_entity(record)
            except TransferRecord.DoesNotExist:
                return None

        return await _get()


# ── Helpers ──────────────────────────────────────────────────────────────────

def _money_to_decimal(units: Optional[int], nanos: Optional[int]) -> Decimal:
    if units is None:
        return Decimal("0")
    money = Money(units=units, nanos=nanos or 0, currency_code="")
    return money.to_decimal().quantize(Decimal("0.0001"))


def _exchange_rate_decimal(draft: TransferDraft) -> Optional[Decimal]:
    if draft.exchange_rate_units is None:
        return None
    money = Money(
        units=draft.exchange_rate_units,
        nanos=draft.exchange_rate_nanos or 0,
        currency_code="",
    )
    return money.to_decimal().quantize(Decimal("0.000000001"))


def _to_entity(record: object) -> TransferDraft:
    from send_money.adapters.persistence.django_models import TransferRecord

    r: TransferRecord = record  # type: ignore[assignment]
    amount_money = Money.from_decimal(r.amount, r.amount_currency)
    fee_money = Money.from_decimal(r.fee, r.amount_currency)
    receive_money = (
        Money.from_decimal(r.receive_amount, r.receive_currency)
        if r.receive_amount is not None
        else None
    )
    return TransferDraft(
        id=r.id,
        idempotency_key=r.idempotency_key,
        destination_country=r.destination_country,
        amount_units=amount_money.units,
        amount_nanos=amount_money.nanos,
        amount_currency=r.amount_currency,
        beneficiary_name=r.beneficiary_name,
        delivery_method=r.delivery_method,  # type: ignore[arg-type]
        fee_units=fee_money.units,
        fee_nanos=fee_money.nanos,
        receive_amount_units=receive_money.units if receive_money else None,
        receive_amount_nanos=receive_money.nanos if receive_money else None,
        destination_currency=r.receive_currency or None,
        status=r.status,  # type: ignore[arg-type]
        confirmation_code=r.confirmation_code or None,
        session_id=r.session_id or None,
        user_id=r.user_id or None,
    )
