import contextlib
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.db import repository
from app.models.card import CardBlockRequest, CardReplacementRequest
from app.services import cards as cards_service
from app.services import verification_sessions
from app.utils.exceptions import BusinessRuleError

CARD = {
    "card_id": 1,
    "customer_id": 1,
    "account_id": 1,
    "card_type": "DEBIT",
    "card_status": "ACTIVE",
    "online_purchases_enabled": True,
    "international_usage_enabled": True,
    "spending_limit": Decimal("1000"),
    "atm_withdrawal_limit": Decimal("500"),
    "delivery_status": "DELIVERED",
}

IDENTITY = {"customer_id": 1, "account_id": 1}


@pytest.fixture(autouse=True)
def patch_db_session(monkeypatch):
    monkeypatch.setattr(
        cards_service, "db_session", lambda: contextlib.nullcontext(MagicMock())
    )
    monkeypatch.setattr(
        verification_sessions, "resolve_session", lambda conn, token: IDENTITY
    )
    monkeypatch.setattr(
        repository, "get_card_for_customer_account", lambda conn, cid, aid, card_id: CARD
    )


def test_card_block_request_creates_service_request(monkeypatch):
    create_mock = MagicMock(return_value=42)
    monkeypatch.setattr(repository, "create_service_request", create_mock)
    status_mock = MagicMock()
    monkeypatch.setattr(repository, "update_card_status", status_mock)

    result = cards_service.create_card_block_request(
        CardBlockRequest(
            verification_token="tok", card_id=1, reason="LOST", confirmed=True
        )
    )

    assert result.request_id == 42
    assert result.request_status == "PENDING"
    create_mock.assert_called_once()
    _, kwargs = create_mock.call_args
    assert kwargs["request_type"] == "CARD_BLOCK"
    assert kwargs["request_reason"] == "LOST"
    assert kwargs["card_id"] == 1
    assert kwargs["customer_id"] == 1
    assert kwargs["account_id"] == 1


def test_card_block_request_never_touches_card_status(monkeypatch):
    create_mock = MagicMock(return_value=1)
    monkeypatch.setattr(repository, "create_service_request", create_mock)
    status_mock = MagicMock()
    monkeypatch.setattr(repository, "update_card_status", status_mock)

    cards_service.create_card_block_request(
        CardBlockRequest(
            verification_token="tok", card_id=1, reason="STOLEN", confirmed=True
        )
    )

    status_mock.assert_not_called()


def test_card_block_request_rejected_when_not_confirmed(monkeypatch):
    create_mock = MagicMock()
    monkeypatch.setattr(repository, "create_service_request", create_mock)

    with pytest.raises(BusinessRuleError):
        cards_service.create_card_block_request(
            CardBlockRequest(
                verification_token="tok",
                card_id=1,
                reason="CUSTOMER_REQUEST",
                confirmed=False,
            )
        )

    create_mock.assert_not_called()


def test_card_block_request_invalid_reason_rejected():
    with pytest.raises(Exception):
        CardBlockRequest(
            verification_token="tok", card_id=1, reason="FORGOT", confirmed=True
        )


def test_card_replacement_request_creates_service_request(monkeypatch):
    create_mock = MagicMock(return_value=7)
    monkeypatch.setattr(repository, "create_service_request", create_mock)

    result = cards_service.create_card_replacement_request(
        CardReplacementRequest(
            verification_token="tok", card_id=1, reason="DAMAGED", confirmed=True
        )
    )

    assert result.request_id == 7
    assert result.request_status == "PENDING"
    _, kwargs = create_mock.call_args
    assert kwargs["request_type"] == "CARD_REPLACEMENT"
    assert kwargs["request_reason"] == "DAMAGED"


def test_card_replacement_request_invalid_reason_rejected():
    with pytest.raises(Exception):
        CardReplacementRequest(
            verification_token="tok", card_id=1, reason="BROKEN", confirmed=True
        )
