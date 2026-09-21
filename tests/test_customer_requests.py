import contextlib
from unittest.mock import MagicMock

import pytest

from app.db import repository
from app.models.customer_request import CustomerDetailChangeRequest
from app.services import customer_requests as customer_requests_service
from app.services import verification_sessions
from app.utils.exceptions import BusinessRuleError

ACCOUNT = {"account_id": 1, "customer_id": 1}
IDENTITY = {"customer_id": 1, "account_id": 1}


@pytest.fixture(autouse=True)
def patch_db_session(monkeypatch):
    monkeypatch.setattr(
        customer_requests_service,
        "db_session",
        lambda: contextlib.nullcontext(MagicMock()),
    )
    monkeypatch.setattr(
        verification_sessions, "resolve_session", lambda conn, token: IDENTITY
    )
    monkeypatch.setattr(
        repository, "get_account_for_customer", lambda conn, cid, aid: ACCOUNT
    )


def test_customer_detail_change_creates_service_request(monkeypatch):
    create_mock = MagicMock(return_value=5)
    monkeypatch.setattr(repository, "create_service_request", create_mock)

    result = customer_requests_service.create_customer_detail_change_request(
        CustomerDetailChangeRequest(
            verification_token="tok",
            field="EMAIL",
            requested_value="new@example.com",
            confirmed=True,
        )
    )

    assert result.request_id == 5
    assert result.request_status == "PENDING"
    _, kwargs = create_mock.call_args
    assert kwargs["request_type"] == "CUSTOMER_DETAIL_CHANGE"
    assert kwargs["request_reason"] == "EMAIL"
    assert kwargs["requested_value"] == "new@example.com"
    assert kwargs["customer_id"] == 1
    assert kwargs["account_id"] == 1


def test_customer_detail_change_rejected_when_not_confirmed(monkeypatch):
    create_mock = MagicMock()
    monkeypatch.setattr(repository, "create_service_request", create_mock)

    with pytest.raises(BusinessRuleError):
        customer_requests_service.create_customer_detail_change_request(
            CustomerDetailChangeRequest(
                verification_token="tok",
                field="MOBILE_NUMBER",
                requested_value="0790000001",
                confirmed=False,
            )
        )

    create_mock.assert_not_called()


def test_customer_detail_change_invalid_field_rejected():
    with pytest.raises(Exception):
        CustomerDetailChangeRequest(
            verification_token="tok",
            field="NATIONAL_ID",
            requested_value="123",
            confirmed=True,
        )

