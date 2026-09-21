import contextlib
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.db import repository
from app.models.account import RecentTransactionsRequest
from app.models.common import TokenContext
from app.services import accounts as accounts_service
from app.services import verification_sessions
from app.services.verification_sessions import resolve_session as real_resolve_session
from app.utils.exceptions import InvalidSessionError, NotFoundError

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

TRANSACTIONS = [
    {
        "transaction_id": 1,
        "amount": Decimal("32.5"),
        "merchant_or_type": "Carrefour",
        "transaction_type": "CARD_PURCHASE",
        "transaction_date": "2026-09-16T10:08:46.965952",
        "transaction_status": "COMPLETED",
    }
]

IDENTITY = {"customer_id": 1, "account_id": 1}


@pytest.fixture(autouse=True)
def patch_db_session(monkeypatch):
    monkeypatch.setattr(
        accounts_service, "db_session", lambda: contextlib.nullcontext(MagicMock())
    )
    monkeypatch.setattr(
        verification_sessions, "resolve_session", lambda conn, token: IDENTITY
    )


def test_get_balance(monkeypatch):
    monkeypatch.setattr(
        repository, "get_account_for_customer", lambda conn, cid, aid: ACCOUNT
    )

    result = accounts_service.get_balance(TokenContext(verification_token="tok"))

    assert result.balance == Decimal("2450.750")
    assert result.available_balance == Decimal("2300.750")


def test_get_iban(monkeypatch):
    monkeypatch.setattr(
        repository, "get_account_for_customer", lambda conn, cid, aid: ACCOUNT
    )

    result = accounts_service.get_iban(TokenContext(verification_token="tok"))

    assert result.iban == "JO71JHBK0000001002003001"


def test_get_account_status(monkeypatch):
    monkeypatch.setattr(
        repository, "get_account_for_customer", lambda conn, cid, aid: ACCOUNT
    )

    result = accounts_service.get_account_status(TokenContext(verification_token="tok"))

    assert result.account_status == "ACTIVE"


def test_get_held_amount_details(monkeypatch):
    monkeypatch.setattr(
        repository, "get_account_for_customer", lambda conn, cid, aid: ACCOUNT
    )

    result = accounts_service.get_held_amount_details(
        TokenContext(verification_token="tok")
    )

    assert result.held_amount == Decimal("150.000")


def test_get_recent_transactions_passes_limit_through(monkeypatch):
    monkeypatch.setattr(
        repository, "get_account_for_customer", lambda conn, cid, aid: ACCOUNT
    )
    captured = {}

    def fake_get_transactions(conn, account_id, limit):
        captured["account_id"] = account_id
        captured["limit"] = limit
        return TRANSACTIONS

    monkeypatch.setattr(repository, "get_recent_transactions", fake_get_transactions)

    result = accounts_service.get_recent_transactions(
        RecentTransactionsRequest(verification_token="tok", limit=5)
    )

    assert len(result.transactions) == 1
    assert result.transactions[0].merchant_or_type == "Carrefour"
    assert captured == {"account_id": 1, "limit": 5}


def test_recent_transactions_default_limit_is_five():
    request = RecentTransactionsRequest(verification_token="tok")
    assert request.limit == 5


def test_recent_transactions_limit_above_ten_rejected():
    with pytest.raises(Exception):
        RecentTransactionsRequest(verification_token="tok", limit=11)


def test_invalid_token_rejects_protected_action(monkeypatch):
    def raise_invalid(conn, token):
        raise InvalidSessionError()

    monkeypatch.setattr(verification_sessions, "resolve_session", raise_invalid)

    with pytest.raises(InvalidSessionError):
        accounts_service.get_balance(TokenContext(verification_token="garbage"))


def test_missing_token_rejects_protected_action(monkeypatch):
    # Use the real resolve_session (not the autouse mock) so a None token
    # actually exercises the "missing token" short-circuit.
    monkeypatch.setattr(verification_sessions, "resolve_session", real_resolve_session)

    with pytest.raises(InvalidSessionError):
        accounts_service.get_balance(TokenContext(verification_token=None))


def test_account_ownership_still_validated_after_token_resolution(monkeypatch):
    # Even once the token resolves, the resolved account_id must still
    # exist and belong to the resolved customer_id - ownership validation
    # is not weakened, only fed a trusted source instead of caller input.
    monkeypatch.setattr(
        repository, "get_account_for_customer", lambda conn, cid, aid: None
    )

    with pytest.raises(NotFoundError):
        accounts_service.get_balance(TokenContext(verification_token="tok"))
