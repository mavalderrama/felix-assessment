"""Beneficiary repository implementations."""
from __future__ import annotations

import uuid
from typing import Optional

from asgiref.sync import sync_to_async

from send_money.domain.entities import Beneficiary
from send_money.domain.enums import DeliveryMethod
from send_money.domain.repositories import BeneficiaryRepository


def _to_entity(record) -> Beneficiary:
    delivery = None
    if record.delivery_method:
        try:
            delivery = DeliveryMethod(record.delivery_method)
        except ValueError:
            pass
    return Beneficiary(
        id=record.id,
        user_id=record.user_id,
        name=record.name,
        account_number=record.account_number,
        country_code=record.country_code or None,
        delivery_method=delivery,
    )


class DjangoBeneficiaryRepository(BeneficiaryRepository):
    """Django ORM implementation of BeneficiaryRepository."""

    async def create(self, beneficiary: Beneficiary) -> Beneficiary:
        @sync_to_async
        def _create():
            from send_money.adapters.persistence.django_models import BeneficiaryRecord
            record = BeneficiaryRecord.objects.create(
                id=beneficiary.id or str(uuid.uuid4()),
                user_id=beneficiary.user_id,
                name=beneficiary.name,
                account_number=beneficiary.account_number,
                country_code=beneficiary.country_code or "",
                delivery_method=str(beneficiary.delivery_method) if beneficiary.delivery_method else "",
            )
            return _to_entity(record)

        return await _create()

    async def get_by_id(self, beneficiary_id: str) -> Optional[Beneficiary]:
        @sync_to_async
        def _get():
            from send_money.adapters.persistence.django_models import BeneficiaryRecord
            try:
                return _to_entity(BeneficiaryRecord.objects.get(id=beneficiary_id))
            except BeneficiaryRecord.DoesNotExist:
                return None

        return await _get()

    async def list_for_user(self, user_id: str) -> list[Beneficiary]:
        @sync_to_async
        def _list():
            from send_money.adapters.persistence.django_models import BeneficiaryRecord
            return [_to_entity(r) for r in BeneficiaryRecord.objects.filter(user_id=user_id)]

        return await _list()

    async def find_by_name_and_user(self, user_id: str, name: str) -> Optional[Beneficiary]:
        @sync_to_async
        def _find():
            from send_money.adapters.persistence.django_models import BeneficiaryRecord
            try:
                return _to_entity(BeneficiaryRecord.objects.get(user_id=user_id, name__iexact=name))
            except BeneficiaryRecord.DoesNotExist:
                return None

        return await _find()

    async def update(self, beneficiary: Beneficiary) -> Beneficiary:
        @sync_to_async
        def _update():
            from send_money.adapters.persistence.django_models import BeneficiaryRecord
            BeneficiaryRecord.objects.filter(id=beneficiary.id).update(
                account_number=beneficiary.account_number,
                country_code=beneficiary.country_code or "",
                delivery_method=str(beneficiary.delivery_method) if beneficiary.delivery_method else "",
            )
            return beneficiary

        return await _update()


class InMemoryBeneficiaryRepository(BeneficiaryRepository):
    """In-memory implementation for unit tests."""

    def __init__(self) -> None:
        self._store: dict[str, Beneficiary] = {}

    async def create(self, beneficiary: Beneficiary) -> Beneficiary:
        record = beneficiary.model_copy(update={"id": beneficiary.id or str(uuid.uuid4())})
        self._store[record.id] = record
        return record

    async def get_by_id(self, beneficiary_id: str) -> Optional[Beneficiary]:
        return self._store.get(beneficiary_id)

    async def list_for_user(self, user_id: str) -> list[Beneficiary]:
        return sorted(
            [b for b in self._store.values() if b.user_id == user_id],
            key=lambda b: b.name.lower(),
        )

    async def find_by_name_and_user(self, user_id: str, name: str) -> Optional[Beneficiary]:
        name_lower = name.strip().lower()
        for b in self._store.values():
            if b.user_id == user_id and b.name.lower() == name_lower:
                return b
        return None

    async def update(self, beneficiary: Beneficiary) -> Beneficiary:
        self._store[beneficiary.id] = beneficiary
        return beneficiary
