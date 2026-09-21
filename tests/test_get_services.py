import contextlib
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.db import repository
from app.models.get_services import GetServicesRequest
from app.services import aggregated as aggregated_service
from app.services import verification_sessions
from app.utils.exceptions import BusinessRuleError, InvalidSessionError

ACCOUNT = {
    "account_id": 1,
    "customer_id": 1,
    "account_number": "1002003001",
    "iban": "JO71JHBK0000001002003001",
    "account_type": "CURRENT",
    "balance": Decimal("2450.750"),
    "available_balance": Decimal("2300.750"),
    "held_amount": Decimal("150.000"),
    "account_status": "ACTIVE",
}

SINGLE_CARD = [
    {
        "card_id": 1,
        "card_type": "DEBIT",
        "card_number": "4556123412345678",
        "delivery_status": "DELIVERED",
    }
]

MULTIPLE_CARDS = [
    {
        "card_id": 1,
        "card_type": "DEBIT",
        "card_number": "4556123412345678",
        "delivery_status": "DELIVERED",
    },
    {
        "card_id": 2,
        "card_type": "CREDIT",
        "card_number": "5412750000009999",
        "delivery_status": "PENDING_DISPATCH",
    },
]

IDENTITY = {"customer_id": 1, "account_id": 1}


@pytest.fixture(autouse=True)
def patch_db_session(monkeypatch):
    monkeypatch.setattr(
        aggregated_service, "db_session", lambda: contextlib.nullcontext(MagicMock())
    )
    monkeypatch.setattr(
        verification_sessions, "resolve_session", lambda conn, token: IDENTITY
    )
    monkeypatch.setattr(
        repository, "get_account_for_customer", lambda conn, cid, aid: ACCOUNT
    )
    monkeypatch.setattr(
        repository, "get_cards_for_account", lambda conn, cid, aid: SINGLE_CARD
    )


def test_balance_only():
    result = aggregated_service.get_services(
        GetServicesRequest(verification_token="tok", get_balance=True)
    )

    assert result.balance == Decimal("2450.750")
    assert result.available_balance == Decimal("2300.750")
    assert result.iban is None
    assert result.account_status is None
    assert result.held_amount is None
    assert result.card_delivery_status is None


def test_iban_only():
    result = aggregated_service.get_services(
        GetServicesRequest(verification_token="tok", get_iban=True)
    )

    assert result.iban == "JO71JHBK0000001002003001"
    assert result.balance is None
    assert result.account_status is None
    assert result.held_amount is None
    assert result.card_delivery_status is None


def test_account_status_only():
    result = aggregated_service.get_services(
        GetServicesRequest(verification_token="tok", get_account_status=True)
    )

    assert result.account_status == "ACTIVE"
    assert result.balance is None
    assert result.iban is None
    assert result.held_amount is None
    assert result.card_delivery_status is None


def test_held_amount_only():
    result = aggregated_service.get_services(
        GetServicesRequest(verification_token="tok", get_held_amount_details=True)
    )

    assert result.held_amount == Decimal("150.000")
    assert result.balance is None
    assert result.iban is None
    assert result.account_status is None
    assert result.card_delivery_status is None


def test_card_delivery_status_only_single_card():
    result = aggregated_service.get_services(
        GetServicesRequest(verification_token="tok", get_card_delivery_status=True)
    )

    assert result.card_delivery_status == "DELIVERED"
    assert result.balance is None
    assert result.iban is None
    assert result.account_status is None
    assert result.held_amount is None


def test_card_delivery_status_multiple_cards_masks_numbers(monkeypatch):
    monkeypatch.setattr(
        repository, "get_cards_for_account", lambda conn, cid, aid: MULTIPLE_CARDS
    )

    result = aggregated_service.get_services(
        GetServicesRequest(verification_token="tok", get_card_delivery_status=True)
    )

    assert isinstance(result.card_delivery_status, list)
    assert len(result.card_delivery_status) == 2

    for card, entry in zip(MULTIPLE_CARDS, result.card_delivery_status):
        assert entry.card_id == card["card_id"]
        assert entry.card_type == card["card_type"]
        assert entry.delivery_status == card["delivery_status"]
        # Never the full card number - only "****" + last 4 digits.
        assert entry.masked_card_number == "****" + card["card_number"][-4:]
        assert card["card_number"] not in entry.masked_card_number
        assert card["card_number"] != entry.masked_card_number


def test_balance_and_iban_together():
    result = aggregated_service.get_services(
        GetServicesRequest(verification_token="tok", get_balance=True, get_iban=True)
    )

    assert result.balance == Decimal("2450.750")
    assert result.available_balance == Decimal("2300.750")
    assert result.iban == "JO71JHBK0000001002003001"
    assert result.account_status is None
    assert result.held_amount is None
    assert result.card_delivery_status is None


def test_all_services_in_one_request():
    result = aggregated_service.get_services(
        GetServicesRequest(
            verification_token="tok",
            get_balance=True,
            get_iban=True,
            get_account_status=True,
            get_held_amount_details=True,
            get_card_delivery_status=True,
        )
    )

    assert result.balance == Decimal("2450.750")
    assert result.available_balance == Decimal("2300.750")
    assert result.iban == "JO71JHBK0000001002003001"
    assert result.account_status == "ACTIVE"
    assert result.held_amount == Decimal("150.000")
    assert result.card_delivery_status == "DELIVERED"


def test_all_flags_false_rejected():
    with pytest.raises(BusinessRuleError):
        aggregated_service.get_services(GetServicesRequest(verification_token="tok"))


def test_invalid_token_rejected(monkeypatch):
    def raise_invalid(conn, token):
        raise InvalidSessionError()

    monkeypatch.setattr(verification_sessions, "resolve_session", raise_invalid)

    with pytest.raises(InvalidSessionError):
        aggregated_service.get_services(
            GetServicesRequest(verification_token="garbage", get_balance=True)
        )


def test_expired_token_rejected(monkeypatch):
    # resolve_session itself is what enforces expiry (see
    # test_verification_sessions.py); here we only need to confirm the
    # aggregated endpoint propagates that failure the same way.
    def raise_expired(conn, token):
        raise InvalidSessionError()

    monkeypatch.setattr(verification_sessions, "resolve_session", raise_expired)

    with pytest.raises(InvalidSessionError):
        aggregated_service.get_services(
            GetServicesRequest(verification_token="expired-tok", get_iban=True)
        )


def test_response_contains_only_requested_fields():
    result = aggregated_service.get_services(
        GetServicesRequest(verification_token="tok", get_held_amount_details=True)
    )

    dumped = result.model_dump(exclude_none=True)

    assert dumped == {"held_amount": Decimal("150.000")}


def test_no_database_mutations_occur(monkeypatch):
    write_functions = [
        "update_card_status",
        "update_card_online_purchases",
        "update_card_international_usage",
        "update_card_spending_limit",
        "update_card_atm_limit",
        "create_service_request",
        "create_complaint",
        "create_callback_request",
        "create_document_request",
        "create_verification_session",
    ]
    mocks = {}
    for name in write_functions:
        mock = MagicMock()
        monkeypatch.setattr(repository, name, mock)
        mocks[name] = mock

    aggregated_service.get_services(
        GetServicesRequest(
            verification_token="tok",
            get_balance=True,
            get_iban=True,
            get_account_status=True,
            get_held_amount_details=True,
            get_card_delivery_status=True,
        )
    )

    for name, mock in mocks.items():
        mock.assert_not_called()


def test_api_all_flags_false_returns_400(client):
    # The all-flags-false check happens before token resolution, so this
    # doesn't depend on (and isn't affected by) the autouse resolve_session
    # mock above - real end-to-end 400 behavior via the actual route/handler.
    resp = client.post(
        "/api/v1/get-services", json={"verification_token": "tok"}
    )

    assert resp.status_code == 400
