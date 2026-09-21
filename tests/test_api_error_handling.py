from app.api import accounts as accounts_api
from app.api import cards as cards_api
from app.api import verification as verification_api
from app.utils.exceptions import (
    BusinessRuleError,
    DatabaseUnavailableError,
    InvalidSessionError,
    NotFoundError,
)


def test_verification_db_error_returns_503_without_leaking(client, monkeypatch):
    def raise_db_error(request):
        raise DatabaseUnavailableError()

    monkeypatch.setattr(verification_api, "verify_customer", raise_db_error)

    resp = client.post(
        "/api/v1/verification/verify",
        json={
            "national_id": "9876543210",
            "account_number": "1002003001",
            "last_transaction_amount": 32.5,
            "last_transaction_merchant_or_type": "Carrefour",
        },
    )

    assert resp.status_code == 503
    body = resp.json()
    assert "detail" in body
    text = resp.text.lower()
    assert "banking123" not in text
    assert "oracledb" not in text
    assert "traceback" not in text


def test_account_db_error_returns_503_without_leaking(client, monkeypatch):
    def raise_db_error(request):
        raise DatabaseUnavailableError()

    monkeypatch.setattr(accounts_api.accounts_service, "get_balance", raise_db_error)

    resp = client.post(
        "/api/v1/accounts/balance", json={"customer_id": 1, "account_id": 1}
    )

    assert resp.status_code == 503
    text = resp.text.lower()
    assert "banking123" not in text
    assert "oracledb" not in text


def test_not_found_error_returns_404_with_message(client, monkeypatch):
    def raise_not_found(request):
        raise NotFoundError("Account not found for this customer.")

    monkeypatch.setattr(accounts_api.accounts_service, "get_balance", raise_not_found)

    resp = client.post(
        "/api/v1/accounts/balance", json={"customer_id": 1, "account_id": 999}
    )

    assert resp.status_code == 404
    assert resp.json() == {"detail": "Account not found for this customer."}


def test_business_rule_error_returns_400_with_message(client, monkeypatch):
    def raise_rule_error(request):
        raise BusinessRuleError("This action requires explicit customer confirmation.")

    monkeypatch.setattr(cards_api.cards_service, "activate_card", raise_rule_error)

    resp = client.post(
        "/api/v1/cards/activate",
        json={"customer_id": 1, "account_id": 1, "card_id": 1, "confirmed": False},
    )

    assert resp.status_code == 400
    assert resp.json() == {
        "detail": "This action requires explicit customer confirmation."
    }


def test_invalid_session_error_returns_401_with_generic_message(client, monkeypatch):
    def raise_invalid(request):
        raise InvalidSessionError()

    monkeypatch.setattr(accounts_api.accounts_service, "get_balance", raise_invalid)

    resp = client.post(
        "/api/v1/accounts/balance", json={"verification_token": "garbage"}
    )

    assert resp.status_code == 401
    assert resp.json() == {"detail": "Invalid or expired verification session"}


def test_missing_token_field_returns_401(client):
    """No verification_token key at all in the body still reaches the
    service (the field is optional so Pydantic doesn't 422 it) and gets
    rejected as an invalid session, not treated as an anonymous/public call."""
    resp = client.post("/api/v1/accounts/balance", json={})

    assert resp.status_code == 401
    assert resp.json() == {"detail": "Invalid or expired verification session"}
