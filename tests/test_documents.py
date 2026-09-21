import contextlib
from unittest.mock import MagicMock

import pytest

from app.db import repository
from app.models.document import DocumentRequestCreateRequest
from app.services import documents as documents_service
from app.services import verification_sessions
from app.utils.exceptions import BusinessRuleError, NotFoundError

ACCOUNT = {"account_id": 1, "customer_id": 1}
IDENTITY = {"customer_id": 1, "account_id": 1}


@pytest.fixture(autouse=True)
def patch_db_session(monkeypatch):
    monkeypatch.setattr(
        documents_service, "db_session", lambda: contextlib.nullcontext(MagicMock())
    )


def test_document_request_with_account_requires_token(monkeypatch):
    monkeypatch.setattr(
        verification_sessions, "resolve_session", lambda conn, token: IDENTITY
    )
    monkeypatch.setattr(
        repository, "get_account_for_customer", lambda conn, cid, aid: ACCOUNT
    )
    monkeypatch.setattr(
        repository, "create_document_request", MagicMock(return_value=1)
    )

    result = documents_service.create_document_request(
        DocumentRequestCreateRequest(
            verification_token="tok",
            document_type="IBAN_CERTIFICATE",
            delivery_method="EMAIL",
        )
    )

    assert result.document_request_id == 1
    assert result.request_status == "PENDING"


def test_document_request_account_id_without_token_rejected():
    with pytest.raises(BusinessRuleError):
        documents_service.create_document_request(
            DocumentRequestCreateRequest(
                customer_id=1, account_id=1, document_type="ACCOUNT_STATEMENT"
            )
        )


def test_document_request_without_account_verifies_customer_exists(monkeypatch):
    monkeypatch.setattr(
        repository, "get_customer_by_id", lambda conn, cid: {"customer_id": 1}
    )
    monkeypatch.setattr(
        repository, "create_document_request", MagicMock(return_value=2)
    )

    result = documents_service.create_document_request(
        DocumentRequestCreateRequest(customer_id=1, document_type="BANK_CERTIFICATE")
    )

    assert result.document_request_id == 2


def test_document_request_unknown_customer_rejected(monkeypatch):
    monkeypatch.setattr(repository, "get_customer_by_id", lambda conn, cid: None)

    with pytest.raises(NotFoundError):
        documents_service.create_document_request(
            DocumentRequestCreateRequest(
                customer_id=999, document_type="LOAN_STATEMENT"
            )
        )


def test_document_request_no_customer_or_token_rejected():
    with pytest.raises(BusinessRuleError):
        documents_service.create_document_request(
            DocumentRequestCreateRequest(document_type="LOAN_STATEMENT")
        )


def test_document_request_invalid_type_rejected():
    with pytest.raises(Exception):
        DocumentRequestCreateRequest(customer_id=1, document_type="X_RAY")
