import contextlib
from unittest.mock import MagicMock

import pytest

from app.db import repository
from app.models.callback import CallbackCreateRequest
from app.services import callbacks as callbacks_service
from app.utils.exceptions import BusinessRuleError, NotFoundError

ACCOUNT = {"account_id": 1, "customer_id": 1}


@pytest.fixture(autouse=True)
def patch_db_session(monkeypatch):
    monkeypatch.setattr(
        callbacks_service, "db_session", lambda: contextlib.nullcontext(MagicMock())
    )


def test_callback_request_fully_anonymous(monkeypatch):
    monkeypatch.setattr(repository, "create_callback_request", MagicMock(return_value=1))

    result = callbacks_service.create_callback_request(
        CallbackCreateRequest(
            request_type="GENERAL_INQUIRY", reason_for_callback="Need help."
        )
    )

    assert result.callback_id == 1
    assert result.callback_status == "PENDING"


def test_callback_request_with_customer_only(monkeypatch):
    monkeypatch.setattr(
        repository, "get_customer_by_id", lambda conn, cid: {"customer_id": 1}
    )
    monkeypatch.setattr(repository, "create_callback_request", MagicMock(return_value=2))

    result = callbacks_service.create_callback_request(
        CallbackCreateRequest(
            customer_id=1,
            request_type="VERIFICATION_FAILED",
            reason_for_callback="Failed verification 3 times.",
        )
    )

    assert result.callback_id == 2


def test_callback_request_with_customer_and_account(monkeypatch):
    monkeypatch.setattr(
        repository, "get_account_for_customer", lambda conn, cid, aid: ACCOUNT
    )
    monkeypatch.setattr(repository, "create_callback_request", MagicMock(return_value=3))

    result = callbacks_service.create_callback_request(
        CallbackCreateRequest(
            customer_id=1,
            account_id=1,
            request_type="ACCOUNT_ACTION",
            reason_for_callback="Wants to discuss a hold.",
        )
    )

    assert result.callback_id == 3


def test_callback_request_account_without_customer_rejected():
    with pytest.raises(BusinessRuleError):
        callbacks_service.create_callback_request(
            CallbackCreateRequest(
                account_id=1, request_type="OTHER", reason_for_callback="test"
            )
        )


def test_callback_request_account_not_owned_by_customer_rejected(monkeypatch):
    monkeypatch.setattr(
        repository, "get_account_for_customer", lambda conn, cid, aid: None
    )

    with pytest.raises(NotFoundError):
        callbacks_service.create_callback_request(
            CallbackCreateRequest(
                customer_id=1,
                account_id=999,
                request_type="OTHER",
                reason_for_callback="test",
            )
        )
