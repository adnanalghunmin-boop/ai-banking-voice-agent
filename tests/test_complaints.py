import contextlib
from unittest.mock import MagicMock

import pytest

from app.db import repository
from app.models.complaint import ComplaintCreateRequest
from app.services import complaints as complaints_service
from app.services import verification_sessions
from app.utils.exceptions import BusinessRuleError, InvalidSessionError, NotFoundError

ACCOUNT = {"account_id": 1, "customer_id": 1}
IDENTITY = {"customer_id": 1, "account_id": 1}


@pytest.fixture(autouse=True)
def patch_db_session(monkeypatch):
    monkeypatch.setattr(
        complaints_service, "db_session", lambda: contextlib.nullcontext(MagicMock())
    )


def test_general_complaint_without_customer_or_account(monkeypatch):
    monkeypatch.setattr(repository, "create_complaint", MagicMock(return_value=1))

    result = complaints_service.create_complaint(
        ComplaintCreateRequest(
            complaint_category="SERVICE",
            complaint_description="Branch was closed early.",
        )
    )

    assert result.complaint_id == 1
    assert result.complaint_reference == "CMP-000001"
    assert result.complaint_status == "OPEN"


def test_complaint_reference_formatting_pads_to_six_digits(monkeypatch):
    monkeypatch.setattr(repository, "create_complaint", MagicMock(return_value=123))

    result = complaints_service.create_complaint(
        ComplaintCreateRequest(
            complaint_category="FEES", complaint_description="Unexpected fee."
        )
    )

    assert result.complaint_reference == "CMP-000123"


def test_account_specific_complaint_requires_token(monkeypatch):
    monkeypatch.setattr(
        verification_sessions, "resolve_session", lambda conn, token: IDENTITY
    )
    monkeypatch.setattr(
        repository, "get_account_for_customer", lambda conn, cid, aid: ACCOUNT
    )
    monkeypatch.setattr(repository, "create_complaint", MagicMock(return_value=2))

    result = complaints_service.create_complaint(
        ComplaintCreateRequest(
            verification_token="tok",
            complaint_category="FEES",
            complaint_description="Unexpected fee charged.",
        )
    )

    assert result.complaint_id == 2


def test_complaint_account_id_without_token_rejected():
    with pytest.raises(BusinessRuleError):
        complaints_service.create_complaint(
            ComplaintCreateRequest(
                customer_id=1,
                account_id=1,
                complaint_category="FEES",
                complaint_description="Unexpected fee.",
            )
        )


def test_complaint_invalid_token_rejected(monkeypatch):
    def raise_invalid(conn, token):
        raise InvalidSessionError()

    monkeypatch.setattr(verification_sessions, "resolve_session", raise_invalid)

    with pytest.raises(InvalidSessionError):
        complaints_service.create_complaint(
            ComplaintCreateRequest(
                verification_token="garbage",
                complaint_category="FEES",
                complaint_description="Unexpected fee.",
            )
        )


def test_complaint_unknown_customer_hint_rejected(monkeypatch):
    monkeypatch.setattr(repository, "get_customer_by_id", lambda conn, cid: None)

    with pytest.raises(NotFoundError):
        complaints_service.create_complaint(
            ComplaintCreateRequest(
                customer_id=999,
                complaint_category="FEES",
                complaint_description="Unexpected fee.",
            )
        )
