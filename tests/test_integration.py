"""Small integration tests that hit the real Oracle database.

These are read-only against the seeded CUSTOMERS/ACCOUNTS/TRANSACTIONS/CARDS
data, with one exception: VERIFICATION_SESSIONS rows, which these tests
create (via /verify) and sometimes directly edit to simulate expiry - that
table exists specifically to hold this kind of ephemeral session state, so
writing to it here is expected usage, not destructive test pollution.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.db.connection import get_connection
from app.services.verification_sessions import _hash_token


def _get_verified_token(client) -> str:
    resp = client.post(
        "/api/v1/verification/verify",
        json={
            "national_id": "9876543210",
            "account_number": "1002003001",
            "last_transaction_amount": 32.5,
            "last_transaction_merchant_or_type": "Carrefour",
        },
    )
    assert resp.status_code == 200
    return resp.json()["verification_token"]


def test_real_verification_success_issues_token(client):
    resp = client.post(
        "/api/v1/verification/verify",
        json={
            "national_id": "9876543210",
            "account_number": "1002003001",
            "last_transaction_amount": 32.5,
            "last_transaction_merchant_or_type": "Carrefour",
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["verified"] is True
    assert body["customer_id"] == 1
    assert body["account_id"] == 1
    assert body["reason"] is None
    assert isinstance(body["verification_token"], str)
    assert len(body["verification_token"]) >= 32


def test_real_verification_arabic_merchant_alias_resolves(client):
    # Real MERCHANT_ALIASES row maps "كارفور" -> CARREFOUR, which the seeded
    # transaction's merchant_or_type "Carrefour" also resolves to.
    resp = client.post(
        "/api/v1/verification/verify",
        json={
            "national_id": "9876543210",
            "account_number": "1002003001",
            "last_transaction_amount": 32.5,
            "last_transaction_merchant_or_type": "كارفور",
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["verified"] is True
    assert body["customer_id"] == 1
    assert body["account_id"] == 1


def test_real_verification_failure_issues_no_token(client):
    resp = client.post(
        "/api/v1/verification/verify",
        json={
            "national_id": "0000000000",
            "account_number": "1002003001",
            "last_transaction_amount": 32.5,
            "last_transaction_merchant_or_type": "Carrefour",
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "verified": False,
        "customer_id": None,
        "account_id": None,
        "verification_token": None,
        "reason": "verification_failed",
    }


def test_real_token_permits_balance_and_card_action(client):
    token = _get_verified_token(client)

    balance_resp = client.post(
        "/api/v1/accounts/balance", json={"verification_token": token}
    )
    assert balance_resp.status_code == 200
    assert Decimal(balance_resp.json()["balance"]) == Decimal("2450.750")

    iban_resp = client.post(
        "/api/v1/accounts/iban", json={"verification_token": token}
    )
    assert iban_resp.status_code == 200
    assert iban_resp.json() == {"iban": "JO71JHBK0000001002003001"}

    card_resp = client.post(
        "/api/v1/cards/delivery-status",
        json={"verification_token": token, "card_id": 1},
    )
    assert card_resp.status_code == 200
    assert card_resp.json() == {"delivery_status": "DELIVERED"}


def test_real_get_services_balance_and_iban(client):
    token = _get_verified_token(client)

    resp = client.post(
        "/api/v1/get-services",
        json={"verification_token": token, "get_balance": True, "get_iban": True},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"balance", "available_balance", "iban"}
    assert Decimal(body["balance"]) == Decimal("2450.750")
    assert body["iban"] == "JO71JHBK0000001002003001"


def test_real_get_services_card_delivery_status_single_card(client):
    # The seeded customer has exactly one card, so this must be the bare
    # string form, not a list.
    token = _get_verified_token(client)

    resp = client.post(
        "/api/v1/get-services",
        json={"verification_token": token, "get_card_delivery_status": True},
    )

    assert resp.status_code == 200
    assert resp.json() == {"card_delivery_status": "DELIVERED"}


def test_real_get_services_all_flags_false_returns_400(client):
    token = _get_verified_token(client)

    resp = client.post(
        "/api/v1/get-services", json={"verification_token": token}
    )

    assert resp.status_code == 400


def test_real_get_services_invalid_token_rejected(client):
    resp = client.post(
        "/api/v1/get-services",
        json={"verification_token": "not-a-real-token", "get_balance": True},
    )

    assert resp.status_code == 401
    assert resp.json() == {"detail": "Invalid or expired verification session"}


def test_real_get_services_missing_token_rejected(client):
    resp = client.post("/api/v1/get-services", json={"get_balance": True})

    assert resp.status_code == 401


def test_real_get_services_no_mutations(client):
    token = _get_verified_token(client)

    resp = client.post(
        "/api/v1/get-services",
        json={
            "verification_token": token,
            "get_balance": True,
            "get_iban": True,
            "get_account_status": True,
            "get_held_amount_details": True,
            "get_card_delivery_status": True,
        },
    )
    assert resp.status_code == 200

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT card_status FROM cards WHERE card_id = 1")
            assert cur.fetchone()[0] == "ACTIVE"
            cur.execute("SELECT balance FROM accounts WHERE account_id = 1")
            assert Decimal(str(cur.fetchone()[0])) == Decimal("2450.750")


def test_real_post_services_invalid_token_rejected(client):
    resp = client.post(
        "/api/v1/post-services",
        json={"verification_token": "not-a-real-token", "activate_card": True},
    )

    assert resp.status_code == 401
    assert resp.json() == {"detail": "Invalid or expired verification session"}


def test_real_post_services_numeric_card_last4_passes_request_validation(client):
    # HeyBreez sometimes serializes card_last4 as a JSON number. That used
    # to fail body validation with 422 ("Input should be a valid string");
    # now it must reach the service layer, where the fake token is 401.
    for card_last4 in (5454, 5454.0, "5454"):
        resp = client.post(
            "/api/v1/post-services",
            json={
                "verification_token": "not-a-real-token",
                "activate_card": True,
                "card_last4": card_last4,
            },
        )

        assert resp.status_code == 401


def test_real_post_services_all_flags_false_returns_400(client):
    token = _get_verified_token(client)

    resp = client.post("/api/v1/post-services", json={"verification_token": token})

    assert resp.status_code == 400


def test_real_post_services_online_purchases_toggle_roundtrip(client):
    # Real end-to-end direct-action wiring, restoring original state
    # afterward so the seeded card is left unchanged.
    token = _get_verified_token(client)

    off_resp = client.post(
        "/api/v1/post-services",
        json={
            "verification_token": token,
            "set_online_purchases": True,
            "online_purchases_enabled": False,
        },
    )
    assert off_resp.status_code == 200
    assert off_resp.json()["results"]["set_online_purchases"] == {
        "success": True,
        "status": "COMPLETED",
        "request_id": None,
        "reason": None,
    }

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT online_purchases_enabled FROM cards WHERE card_id = 1"
            )
            assert cur.fetchone()[0] == 0

    token2 = _get_verified_token(client)
    on_resp = client.post(
        "/api/v1/post-services",
        json={
            "verification_token": token2,
            "set_online_purchases": True,
            "online_purchases_enabled": True,
        },
    )
    assert on_resp.status_code == 200

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT online_purchases_enabled FROM cards WHERE card_id = 1"
            )
            assert cur.fetchone()[0] == 1


def test_real_missing_token_rejected(client):
    resp = client.post("/api/v1/accounts/balance", json={})

    assert resp.status_code == 401
    assert resp.json() == {"detail": "Invalid or expired verification session"}


def test_real_garbage_token_rejected(client):
    resp = client.post(
        "/api/v1/accounts/balance", json={"verification_token": "not-a-real-token"}
    )

    assert resp.status_code == 401


def test_real_token_cannot_access_nonexistent_card(client):
    token = _get_verified_token(client)

    resp = client.post(
        "/api/v1/cards/delivery-status",
        json={"verification_token": token, "card_id": 999},
    )

    assert resp.status_code == 404


def test_real_token_not_stored_raw_in_database(client):
    token = _get_verified_token(client)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT session_id FROM verification_sessions WHERE token_hash = :raw_token",
                raw_token=token,
            )
            assert cur.fetchone() is None, "raw token must never equal a stored hash"

            cur.execute(
                "SELECT token_hash FROM verification_sessions WHERE token_hash = :h",
                h=_hash_token(token),
            )
            row = cur.fetchone()
            assert row is not None
            assert row[0] != token
            assert len(row[0]) == 64  # sha256 hex digest


def test_real_expired_token_rejected(client):
    # Bind a Python-computed naive-UTC timestamp directly rather than using
    # SQL-side CURRENT_TIMESTAMP: the oracledb session's timezone need not
    # match Python's UTC clock, and the app itself only ever compares
    # against its own Python-side _utcnow() - never SQL CURRENT_TIMESTAMP -
    # so this is what actually reproduces "expired" from the app's point of
    # view.
    token = _get_verified_token(client)
    token_hash = _hash_token(token)
    past = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE verification_sessions SET expires_at = :expires_at WHERE token_hash = :h",
                expires_at=past,
                h=token_hash,
            )
        conn.commit()

    resp = client.post(
        "/api/v1/accounts/balance", json={"verification_token": token}
    )

    assert resp.status_code == 401
    assert resp.json() == {"detail": "Invalid or expired verification session"}


def test_real_inactive_token_rejected(client):
    token = _get_verified_token(client)
    token_hash = _hash_token(token)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE verification_sessions SET active = 0 WHERE token_hash = :h",
                h=token_hash,
            )
        conn.commit()

    resp = client.post(
        "/api/v1/accounts/balance", json={"verification_token": token}
    )

    assert resp.status_code == 401
    assert resp.json() == {"detail": "Invalid or expired verification session"}
