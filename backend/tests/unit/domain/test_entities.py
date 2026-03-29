"""Unit tests for domain entities (TransferDraft, UserAccount)."""

from __future__ import annotations

from send_money.domain.entities import Beneficiary, TransferDraft, UserAccount
from send_money.domain.enums import DeliveryMethod, TransferStatus


def _complete_draft() -> TransferDraft:
    return TransferDraft(
        destination_country="MX",
        amount_units=500,
        amount_nanos=0,
        amount_currency="USD",
        beneficiary_name="Maria Garcia",
        beneficiary_account="1234567890",
        delivery_method=DeliveryMethod.BANK_DEPOSIT,
    )


def test_missing_fields_all_required_absent() -> None:
    draft = TransferDraft()
    assert set(draft.missing_fields) == {
        "destination_country",
        "amount_units",
        "amount_currency",
        "beneficiary_name",
        "beneficiary_account",
        "delivery_method",
    }


def test_missing_fields_partial() -> None:
    draft = TransferDraft(
        destination_country="MX", amount_units=100, amount_currency="USD"
    )
    assert "destination_country" not in draft.missing_fields
    assert "beneficiary_name" in draft.missing_fields
    assert "delivery_method" in draft.missing_fields


def test_is_complete_when_all_required_set() -> None:
    draft = _complete_draft()
    assert draft.is_complete is True


def test_is_complete_false_when_field_missing() -> None:
    draft = _complete_draft()
    draft.beneficiary_name = None
    assert draft.is_complete is False


def test_default_status_is_collecting() -> None:
    draft = TransferDraft()
    assert draft.status == TransferStatus.COLLECTING


def test_amount_display_not_set() -> None:
    draft = TransferDraft()
    assert draft.amount_display == "not set"


def test_amount_display_shows_formatted_value() -> None:
    draft = TransferDraft(
        amount_units=42, amount_nanos=990_000_000, amount_currency="USD"
    )
    display = draft.amount_display
    assert "42.99" in display
    assert "USD" in display


def test_to_state_dict_round_trip() -> None:
    draft = _complete_draft()
    draft.status = TransferStatus.VALIDATED
    state = draft.to_state_dict()
    restored = TransferDraft.from_state_dict(state)
    assert restored == draft


def test_from_state_dict_empty_dict() -> None:
    draft = TransferDraft.from_state_dict({})
    assert draft.destination_country is None
    assert draft.status == TransferStatus.COLLECTING


def test_to_state_dict_json_serialisable() -> None:
    """to_state_dict() must produce only JSON-safe types (no Decimal, no enums)."""
    import json

    draft = _complete_draft()
    state = draft.to_state_dict()
    # Must not raise
    serialised = json.dumps(state)
    assert "BANK_DEPOSIT" in serialised


def test_id_defaults_to_none() -> None:
    draft = TransferDraft()
    assert draft.id is None


# ── UserAccount ───────────────────────────────────────────────────────────────


def test_user_account_default_balance_is_zero() -> None:
    account = UserAccount(username="alice", password_hash="x")
    assert account.balance_units == 0
    assert account.balance_nanos == 0


def test_user_account_default_currency_is_usd() -> None:
    account = UserAccount(username="alice", password_hash="x")
    assert account.balance_currency == "USD"


def test_user_account_id_defaults_to_none() -> None:
    account = UserAccount(username="bob", password_hash="y")
    assert account.id is None


def test_user_account_stores_custom_balance() -> None:
    account = UserAccount(
        username="carol",
        password_hash="z",
        balance_units=1000,
        balance_nanos=500_000_000,
        balance_currency="USD",
    )
    assert account.balance_units == 1000
    assert account.balance_nanos == 500_000_000


# ── Beneficiary ───────────────────────────────────────────────────────────────


def test_beneficiary_defaults() -> None:
    b = Beneficiary()
    assert b.id is None
    assert b.user_id == ""
    assert b.name == ""
    assert b.account_number == ""
    assert b.country_code is None
    assert b.delivery_method is None


def test_beneficiary_stores_fields() -> None:
    b = Beneficiary(
        id="uuid-1",
        user_id="user-1",
        name="Maria Garcia",
        account_number="1234567890",
        country_code="MX",
        delivery_method=DeliveryMethod.BANK_DEPOSIT,
    )
    assert b.id == "uuid-1"
    assert b.user_id == "user-1"
    assert b.name == "Maria Garcia"
    assert b.account_number == "1234567890"
    assert b.country_code == "MX"
    assert b.delivery_method == DeliveryMethod.BANK_DEPOSIT


def test_beneficiary_account_in_transfer_draft_missing_fields() -> None:
    draft = TransferDraft(
        destination_country="MX",
        amount_units=100,
        amount_currency="USD",
        beneficiary_name="Maria Garcia",
        delivery_method=DeliveryMethod.BANK_DEPOSIT,
    )
    assert "beneficiary_account" in draft.missing_fields


def test_transfer_draft_complete_with_beneficiary_account() -> None:
    draft = _complete_draft()
    assert draft.is_complete is True
