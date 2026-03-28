"""Unit tests for the TransferDraft entity."""
from __future__ import annotations

import pytest

from send_money.domain.entities import TransferDraft
from send_money.domain.enums import DeliveryMethod, TransferStatus


def _complete_draft() -> TransferDraft:
    return TransferDraft(
        destination_country="MX",
        amount_units=500,
        amount_nanos=0,
        amount_currency="USD",
        beneficiary_name="Maria Garcia",
        delivery_method=DeliveryMethod.BANK_DEPOSIT,
    )


def test_missing_fields_all_required_absent():
    draft = TransferDraft()
    assert set(draft.missing_fields) == {
        "destination_country",
        "amount_units",
        "amount_currency",
        "beneficiary_name",
        "delivery_method",
    }


def test_missing_fields_partial():
    draft = TransferDraft(destination_country="MX", amount_units=100, amount_currency="USD")
    assert "destination_country" not in draft.missing_fields
    assert "beneficiary_name" in draft.missing_fields
    assert "delivery_method" in draft.missing_fields


def test_is_complete_when_all_required_set():
    draft = _complete_draft()
    assert draft.is_complete is True


def test_is_complete_false_when_field_missing():
    draft = _complete_draft()
    draft.beneficiary_name = None
    assert draft.is_complete is False


def test_default_status_is_collecting():
    draft = TransferDraft()
    assert draft.status == TransferStatus.COLLECTING


def test_amount_display_not_set():
    draft = TransferDraft()
    assert draft.amount_display == "not set"


def test_amount_display_shows_formatted_value():
    draft = TransferDraft(amount_units=42, amount_nanos=990_000_000, amount_currency="USD")
    display = draft.amount_display
    assert "42.99" in display
    assert "USD" in display


def test_to_state_dict_round_trip():
    draft = _complete_draft()
    draft.status = TransferStatus.VALIDATED
    state = draft.to_state_dict()
    restored = TransferDraft.from_state_dict(state)
    assert restored == draft


def test_from_state_dict_empty_dict():
    draft = TransferDraft.from_state_dict({})
    assert draft.destination_country is None
    assert draft.status == TransferStatus.COLLECTING


def test_to_state_dict_json_serialisable():
    """to_state_dict() must produce only JSON-safe types (no Decimal, no enum objects)."""
    import json

    draft = _complete_draft()
    state = draft.to_state_dict()
    # Must not raise
    serialised = json.dumps(state)
    assert "BANK_DEPOSIT" in serialised


def test_id_defaults_to_none():
    draft = TransferDraft()
    assert draft.id is None
