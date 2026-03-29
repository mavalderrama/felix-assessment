"""User account repository implementation using Django ORM."""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Optional

from asgiref.sync import sync_to_async

from send_money.domain.entities import UserAccount
from send_money.domain.errors import InsufficientFundsError, UsernameAlreadyExistsError
from send_money.domain.repositories import UserAccountRepository
from send_money.domain.value_objects import Money


class DjangoUserAccountRepository(UserAccountRepository):
    async def create(self, account: UserAccount) -> UserAccount:
        @sync_to_async
        def _create() -> UserAccount:
            from django.db import IntegrityError
            from send_money.adapters.persistence.django_models import UserAccountRecord

            if not account.id:
                account.id = str(uuid.uuid4())
            try:
                record = UserAccountRecord.objects.create(
                    id=account.id,
                    username=account.username,
                    password_hash=account.password_hash,
                    balance=Decimal("0"),
                    balance_currency=account.balance_currency,
                )
            except IntegrityError:
                raise UsernameAlreadyExistsError(account.username)
            return _to_entity(record)

        return await _create()

    async def get_by_username(self, username: str) -> Optional[UserAccount]:
        @sync_to_async
        def _get() -> Optional[UserAccount]:
            from send_money.adapters.persistence.django_models import UserAccountRecord

            try:
                record = UserAccountRecord.objects.get(username=username)
                return _to_entity(record)
            except UserAccountRecord.DoesNotExist:
                return None

        return await _get()

    async def get_by_id(self, user_id: str) -> Optional[UserAccount]:
        @sync_to_async
        def _get() -> Optional[UserAccount]:
            from send_money.adapters.persistence.django_models import UserAccountRecord

            try:
                record = UserAccountRecord.objects.get(id=user_id)
                return _to_entity(record)
            except UserAccountRecord.DoesNotExist:
                return None

        return await _get()

    async def add_funds(self, user_id: str, units: int, nanos: int) -> UserAccount:
        @sync_to_async
        def _add() -> UserAccount:
            from django.db import transaction
            from send_money.adapters.persistence.django_models import UserAccountRecord

            with transaction.atomic():
                record = UserAccountRecord.objects.select_for_update().get(id=user_id)
                amount = _balance_to_decimal(units, nanos)
                record.balance += amount
                record.save(update_fields=["balance"])
                return _to_entity(record)

        return await _add()

    async def deduct_funds(self, user_id: str, units: int, nanos: int) -> UserAccount:
        @sync_to_async
        def _deduct() -> UserAccount:
            from django.db import transaction
            from send_money.adapters.persistence.django_models import UserAccountRecord

            with transaction.atomic():
                record = UserAccountRecord.objects.select_for_update().get(id=user_id)
                amount = _balance_to_decimal(units, nanos)
                if record.balance < amount:
                    raise InsufficientFundsError(str(amount), str(record.balance))
                record.balance -= amount
                record.save(update_fields=["balance"])
                return _to_entity(record)

        return await _deduct()


# ── Helpers ──────────────────────────────────────────────────────────────────

def _balance_to_decimal(units: int, nanos: int) -> Decimal:
    money = Money(units=units, nanos=nanos, currency_code="")
    return money.to_decimal().quantize(Decimal("0.000000001"))


def _to_entity(record: object) -> UserAccount:
    from send_money.adapters.persistence.django_models import UserAccountRecord

    r: UserAccountRecord = record  # type: ignore[assignment]
    balance_money = Money.from_decimal(r.balance, r.balance_currency)
    return UserAccount(
        id=r.id,
        username=r.username,
        password_hash=r.password_hash,
        balance_units=balance_money.units,
        balance_nanos=balance_money.nanos,
        balance_currency=r.balance_currency,
    )
