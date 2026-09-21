import contextlib
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.db import repository
from app.models.card import (
    CardContext,
    ChangeAtmLimitRequest,
    ChangeSpendingLimitRequest,
    ConfirmedCardAction,
    SetInternationalUsageRequest,
    SetOnlinePurchasesRequest,
)
from app.services import cards as cards_service
from app.services import verification_sessions
from app.utils.exceptions import BusinessRuleError, NotFoundError

CARD_ACTIVE = {
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

CARD_INACTIVE = {**CARD_ACTIVE, "card_status": "INACTIVE"}
CARD_FROZEN = {**CARD_ACTIVE, "card_status": "FROZEN"}

# Token resolves to customer_id=1/account_id=1 in every test unless overridden.
IDENTITY = {"customer_id": 1, "account_id": 1}


@pytest.fixture(autouse=True)
def patch_db_session(monkeypatch):
    monkeypatch.setattr(
        cards_service, "db_session", lambda: contextlib.nullcontext(MagicMock())
    )
    monkeypatch.setattr(
        verification_sessions, "resolve_session", lambda conn, token: IDENTITY
    )


def test_get_card_delivery_status(monkeypatch):
    monkeypatch.setattr(
        repository,
        "get_card_for_customer_account",
        lambda conn, cid, aid, card_id: CARD_ACTIVE,
    )

    result = cards_service.get_card_delivery_status(
        CardContext(verification_token="tok", card_id=1)
    )

    assert result.delivery_status == "DELIVERED"


def test_card_ownership_validation_rejects_mismatched_card(monkeypatch):
    monkeypatch.setattr(
        repository, "get_card_for_customer_account", lambda conn, cid, aid, card_id: None
    )

    with pytest.raises(NotFoundError):
        cards_service.get_card_delivery_status(
            CardContext(verification_token="tok", card_id=999)
        )


def test_token_cannot_access_another_customers_card(monkeypatch):
    """Token resolves to customer 1 / account 1, but the supplied card_id
    belongs to a different customer/account entirely - the ownership query
    (scoped by the resolved customer_id+account_id, not caller input) must
    return nothing, and the action must be rejected."""

    def fake_get_card(conn, customer_id, account_id, card_id):
        # Simulates a real query: card_id=42 only exists under customer 2 /
        # account 2, so it never matches the resolved (1, 1) pair.
        if (customer_id, account_id, card_id) == (2, 2, 42):
            return {**CARD_ACTIVE, "card_id": 42, "customer_id": 2, "account_id": 2}
        return None

    monkeypatch.setattr(repository, "get_card_for_customer_account", fake_get_card)

    with pytest.raises(NotFoundError):
        cards_service.get_card_delivery_status(
            CardContext(verification_token="customer-1-token", card_id=42)
        )


def test_activate_card_success(monkeypatch):
    monkeypatch.setattr(
        repository,
        "get_card_for_customer_account",
        lambda conn, cid, aid, card_id: CARD_INACTIVE,
    )
    update_mock = MagicMock()
    monkeypatch.setattr(repository, "update_card_status", update_mock)

    result = cards_service.activate_card(
        ConfirmedCardAction(verification_token="tok", card_id=1, confirmed=True)
    )

    assert result.card_status == "ACTIVE"
    update_mock.assert_called_once_with(update_mock.call_args[0][0], 1, "ACTIVE")


def test_activate_card_rejected_when_not_confirmed(monkeypatch):
    monkeypatch.setattr(
        repository,
        "get_card_for_customer_account",
        lambda conn, cid, aid, card_id: CARD_INACTIVE,
    )
    update_mock = MagicMock()
    monkeypatch.setattr(repository, "update_card_status", update_mock)

    with pytest.raises(BusinessRuleError):
        cards_service.activate_card(
            ConfirmedCardAction(verification_token="tok", card_id=1, confirmed=False)
        )

    update_mock.assert_not_called()


def test_activate_card_already_active_is_business_error(monkeypatch):
    monkeypatch.setattr(
        repository,
        "get_card_for_customer_account",
        lambda conn, cid, aid, card_id: CARD_ACTIVE,
    )

    with pytest.raises(BusinessRuleError):
        cards_service.activate_card(
            ConfirmedCardAction(verification_token="tok", card_id=1, confirmed=True)
        )


def test_unfreeze_card_success(monkeypatch):
    monkeypatch.setattr(
        repository,
        "get_card_for_customer_account",
        lambda conn, cid, aid, card_id: CARD_FROZEN,
    )
    update_mock = MagicMock()
    monkeypatch.setattr(repository, "update_card_status", update_mock)

    result = cards_service.unfreeze_card(
        ConfirmedCardAction(verification_token="tok", card_id=1, confirmed=True)
    )

    assert result.card_status == "ACTIVE"
    update_mock.assert_called_once()


def test_unfreeze_card_when_not_frozen_is_business_error(monkeypatch):
    monkeypatch.setattr(
        repository,
        "get_card_for_customer_account",
        lambda conn, cid, aid, card_id: CARD_ACTIVE,
    )

    with pytest.raises(BusinessRuleError):
        cards_service.unfreeze_card(
            ConfirmedCardAction(verification_token="tok", card_id=1, confirmed=True)
        )


def test_set_online_purchases_disable(monkeypatch):
    monkeypatch.setattr(
        repository,
        "get_card_for_customer_account",
        lambda conn, cid, aid, card_id: CARD_ACTIVE,
    )
    update_mock = MagicMock()
    monkeypatch.setattr(repository, "update_card_online_purchases", update_mock)

    result = cards_service.set_online_purchases(
        SetOnlinePurchasesRequest(
            verification_token="tok", card_id=1, enabled=False, confirmed=True
        )
    )

    assert result.online_purchases_enabled is False
    update_mock.assert_called_once_with(update_mock.call_args[0][0], 1, False)


def test_set_online_purchases_rejected_when_not_confirmed(monkeypatch):
    monkeypatch.setattr(
        repository,
        "get_card_for_customer_account",
        lambda conn, cid, aid, card_id: CARD_ACTIVE,
    )
    update_mock = MagicMock()
    monkeypatch.setattr(repository, "update_card_online_purchases", update_mock)

    with pytest.raises(BusinessRuleError):
        cards_service.set_online_purchases(
            SetOnlinePurchasesRequest(
                verification_token="tok", card_id=1, enabled=False, confirmed=False
            )
        )

    update_mock.assert_not_called()


def test_set_international_usage_disable(monkeypatch):
    monkeypatch.setattr(
        repository,
        "get_card_for_customer_account",
        lambda conn, cid, aid, card_id: CARD_ACTIVE,
    )
    update_mock = MagicMock()
    monkeypatch.setattr(repository, "update_card_international_usage", update_mock)

    result = cards_service.set_international_usage(
        SetInternationalUsageRequest(
            verification_token="tok", card_id=1, enabled=False, confirmed=True
        )
    )

    assert result.international_usage_enabled is False
    update_mock.assert_called_once()


def test_change_card_spending_limit_success(monkeypatch):
    monkeypatch.setattr(
        repository,
        "get_card_for_customer_account",
        lambda conn, cid, aid, card_id: CARD_ACTIVE,
    )
    update_mock = MagicMock()
    monkeypatch.setattr(repository, "update_card_spending_limit", update_mock)

    result = cards_service.change_card_spending_limit(
        ChangeSpendingLimitRequest(
            verification_token="tok", card_id=1, new_limit=Decimal("1500"), confirmed=True
        )
    )

    assert result.spending_limit == Decimal("1500")
    update_mock.assert_called_once_with(update_mock.call_args[0][0], 1, Decimal("1500"))


def test_change_card_spending_limit_rejects_non_positive():
    with pytest.raises(Exception):
        ChangeSpendingLimitRequest(
            verification_token="tok", card_id=1, new_limit=Decimal("-1"), confirmed=True
        )
    with pytest.raises(Exception):
        ChangeSpendingLimitRequest(
            verification_token="tok", card_id=1, new_limit=Decimal("0"), confirmed=True
        )


def test_change_atm_withdrawal_limit_success(monkeypatch):
    monkeypatch.setattr(
        repository,
        "get_card_for_customer_account",
        lambda conn, cid, aid, card_id: CARD_ACTIVE,
    )
    update_mock = MagicMock()
    monkeypatch.setattr(repository, "update_card_atm_limit", update_mock)

    result = cards_service.change_atm_withdrawal_limit(
        ChangeAtmLimitRequest(
            verification_token="tok", card_id=1, new_limit=Decimal("600"), confirmed=True
        )
    )

    assert result.atm_withdrawal_limit == Decimal("600")
    update_mock.assert_called_once()


def test_change_atm_withdrawal_limit_rejects_non_positive():
    with pytest.raises(Exception):
        ChangeAtmLimitRequest(
            verification_token="tok", card_id=1, new_limit=Decimal("-5"), confirmed=True
        )

