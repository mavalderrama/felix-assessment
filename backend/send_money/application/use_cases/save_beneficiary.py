"""SaveBeneficiaryUseCase — create or update a saved recipient."""

from __future__ import annotations

import uuid

from send_money.domain.entities import Beneficiary
from send_money.domain.enums import DeliveryMethod
from send_money.domain.errors import InvalidFieldError
from send_money.domain.repositories import BeneficiaryRepository


class SaveBeneficiaryUseCase:
    def __init__(self, beneficiary_repo: BeneficiaryRepository) -> None:
        self._repo = beneficiary_repo

    async def execute(
        self,
        user_id: str,
        name: str,
        account_number: str,
        country_code: str = "",
        delivery_method: str = "",
    ) -> Beneficiary:
        """Save or update a beneficiary for the given user.

        If a beneficiary with the same name already exists for this user,
        their account_number, country_code, and delivery_method are updated.
        Otherwise a new record is created.
        """
        name = name.strip()
        if len(name) < 2:
            raise InvalidFieldError(
                "beneficiary_name", "Name must be at least 2 characters."
            )

        account_number = account_number.strip()
        if not account_number:
            raise InvalidFieldError(
                "beneficiary_account", "Account number cannot be empty."
            )

        delivery: DeliveryMethod | None = None
        if delivery_method:
            try:
                delivery = DeliveryMethod(
                    delivery_method.strip().upper().replace(" ", "_")
                )
            except ValueError:
                pass

        # Find existing entry matching name + account_number + delivery_method exactly.
        # Different account or different delivery method → new entry.
        existing_entries = await self._repo.find_by_name_and_user(user_id, name)
        existing = next(
            (e for e in existing_entries if e.account_number == account_number),
            None,
        )
        if existing is not None:
            updated = existing.model_copy(
                update={
                    "country_code": country_code.upper() or existing.country_code,
                    "delivery_method": delivery or existing.delivery_method,
                }
            )
            return await self._repo.update(updated)

        beneficiary = Beneficiary(
            id=str(uuid.uuid4()),
            user_id=user_id,
            name=name,
            account_number=account_number,
            country_code=country_code.upper() or None,
            delivery_method=delivery,
        )
        try:
            return await self._repo.create(beneficiary)
        except Exception:
            # DB constraint caught a duplicate the dedup logic missed —
            # fall back to updating the existing entry.
            refreshed = await self._repo.find_by_name_and_user(user_id, name)
            if refreshed:
                target = refreshed[0]
                updated = target.model_copy(
                    update={
                        "account_number": account_number,
                        "country_code": country_code.upper() or target.country_code,
                        "delivery_method": delivery or target.delivery_method,
                    }
                )
                return await self._repo.update(updated)
            raise
