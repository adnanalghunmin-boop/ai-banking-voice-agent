from datetime import datetime
from decimal import Decimal
from typing import Any

import oracledb


def get_customer_by_national_id(
    conn: oracledb.Connection, national_id: str
) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT customer_id, national_id
            FROM customers
            WHERE national_id = :national_id
            """,
            national_id=national_id,
        )
        row = cur.fetchone()
        if row is None:
            return None
        return {"customer_id": row[0], "national_id": row[1]}


def get_account_by_number(
    conn: oracledb.Connection, account_number: str
) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT account_id, customer_id, account_number
            FROM accounts
            WHERE account_number = :account_number
            """,
            account_number=account_number,
        )
        row = cur.fetchone()
        if row is None:
            return None
        return {"account_id": row[0], "customer_id": row[1], "account_number": row[2]}


def get_latest_completed_transaction(
    conn: oracledb.Connection, account_id: int
) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT transaction_id, amount, merchant_or_type, transaction_type
            FROM transactions
            WHERE account_id = :account_id
              AND transaction_status = 'COMPLETED'
            ORDER BY transaction_date DESC
            FETCH FIRST 1 ROW ONLY
            """,
            account_id=account_id,
        )
        row = cur.fetchone()
        if row is None:
            return None
        return {
            "transaction_id": row[0],
            "amount": Decimal(str(row[1])),
            "merchant_or_type": row[2],
            "transaction_type": row[3],
        }


# ---------------------------------------------------------------------------
# Phase 2: account / card / request lookups and writes
# ---------------------------------------------------------------------------


def get_customer_by_id(
    conn: oracledb.Connection, customer_id: int
) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT customer_id FROM customers WHERE customer_id = :customer_id",
            customer_id=customer_id,
        )
        row = cur.fetchone()
        if row is None:
            return None
        return {"customer_id": row[0]}


def get_account_for_customer(
    conn: oracledb.Connection, customer_id: int, account_id: int
) -> dict[str, Any] | None:
    """Look up an account and, in the same query, confirm it belongs to the
    given customer_id. Returns None if the account does not exist OR does
    not belong to that customer - callers cannot distinguish the two, which
    is what prevents a caller-supplied (customer_id, account_id) pair from
    ever being trusted without independent verification.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT account_id, customer_id, account_number, iban, account_type,
                   balance, available_balance, held_amount, account_status
            FROM accounts
            WHERE account_id = :account_id
              AND customer_id = :customer_id
            """,
            account_id=account_id,
            customer_id=customer_id,
        )
        row = cur.fetchone()
        if row is None:
            return None
        return {
            "account_id": row[0],
            "customer_id": row[1],
            "account_number": row[2],
            "iban": row[3],
            "account_type": row[4],
            "balance": Decimal(str(row[5])) if row[5] is not None else None,
            "available_balance": Decimal(str(row[6])) if row[6] is not None else None,
            "held_amount": Decimal(str(row[7])) if row[7] is not None else None,
            "account_status": row[8],
        }


def get_recent_transactions(
    conn: oracledb.Connection, account_id: int, limit: int
) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT transaction_id, amount, merchant_or_type, transaction_type,
                   transaction_date, transaction_status
            FROM transactions
            WHERE account_id = :account_id
            ORDER BY transaction_date DESC
            FETCH FIRST :max_rows ROWS ONLY
            """,
            account_id=account_id,
            max_rows=limit,
        )
        rows = cur.fetchall()
        return [
            {
                "transaction_id": row[0],
                "amount": Decimal(str(row[1])),
                "merchant_or_type": row[2],
                "transaction_type": row[3],
                "transaction_date": row[4],
                "transaction_status": row[5],
            }
            for row in rows
        ]


def get_card_for_customer_account(
    conn: oracledb.Connection, customer_id: int, account_id: int, card_id: int
) -> dict[str, Any] | None:
    """Look up a card and confirm, in the same query, that it belongs to the
    given customer_id AND account_id. Same non-distinguishable-failure
    property as get_account_for_customer.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT card_id, customer_id, account_id, card_type, card_status,
                   online_purchases_enabled, international_usage_enabled,
                   spending_limit, atm_withdrawal_limit, delivery_status
            FROM cards
            WHERE card_id = :card_id
              AND account_id = :account_id
              AND customer_id = :customer_id
            """,
            card_id=card_id,
            account_id=account_id,
            customer_id=customer_id,
        )
        row = cur.fetchone()
        if row is None:
            return None
        return {
            "card_id": row[0],
            "customer_id": row[1],
            "account_id": row[2],
            "card_type": row[3],
            "card_status": row[4],
            "online_purchases_enabled": bool(row[5]),
            "international_usage_enabled": bool(row[6]),
            "spending_limit": Decimal(str(row[7])) if row[7] is not None else None,
            "atm_withdrawal_limit": Decimal(str(row[8])) if row[8] is not None else None,
            "delivery_status": row[9],
        }


def get_cards_for_account(
    conn: oracledb.Connection, customer_id: int, account_id: int
) -> list[dict[str, Any]]:
    """List every card belonging to the given (already-verified)
    customer/account pair, without requiring a card_id - used to answer
    "what's my card delivery status" when the caller doesn't know or need
    to know internal card_id values."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT card_id, card_type, card_number, delivery_status
            FROM cards
            WHERE customer_id = :customer_id
              AND account_id = :account_id
            ORDER BY card_id
            """,
            customer_id=customer_id,
            account_id=account_id,
        )
        return [
            {
                "card_id": row[0],
                "card_type": row[1],
                "card_number": row[2],
                "delivery_status": row[3],
            }
            for row in cur.fetchall()
        ]


def update_card_status(conn: oracledb.Connection, card_id: int, new_status: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE cards SET card_status = :new_status WHERE card_id = :card_id",
            new_status=new_status,
            card_id=card_id,
        )
    conn.commit()


def update_card_online_purchases(
    conn: oracledb.Connection, card_id: int, enabled: bool
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE cards SET online_purchases_enabled = :enabled
            WHERE card_id = :card_id
            """,
            enabled=1 if enabled else 0,
            card_id=card_id,
        )
    conn.commit()


def update_card_international_usage(
    conn: oracledb.Connection, card_id: int, enabled: bool
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE cards SET international_usage_enabled = :enabled
            WHERE card_id = :card_id
            """,
            enabled=1 if enabled else 0,
            card_id=card_id,
        )
    conn.commit()


def update_card_spending_limit(
    conn: oracledb.Connection, card_id: int, new_limit: Decimal
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE cards SET spending_limit = :new_limit WHERE card_id = :card_id",
            new_limit=new_limit,
            card_id=card_id,
        )
    conn.commit()


def update_card_atm_limit(
    conn: oracledb.Connection, card_id: int, new_limit: Decimal
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE cards SET atm_withdrawal_limit = :new_limit
            WHERE card_id = :card_id
            """,
            new_limit=new_limit,
            card_id=card_id,
        )
    conn.commit()


def create_service_request(
    conn: oracledb.Connection,
    customer_id: int,
    account_id: int | None,
    card_id: int | None,
    request_type: str,
    request_reason: str | None,
    requested_value: str | None,
) -> int:
    with conn.cursor() as cur:
        request_id_var = cur.var(int)
        cur.execute(
            """
            INSERT INTO service_requests
                (customer_id, account_id, card_id, request_type,
                 request_reason, requested_value)
            VALUES
                (:customer_id, :account_id, :card_id, :request_type,
                 :request_reason, :requested_value)
            RETURNING request_id INTO :request_id
            """,
            customer_id=customer_id,
            account_id=account_id,
            card_id=card_id,
            request_type=request_type,
            request_reason=request_reason,
            requested_value=requested_value,
            request_id=request_id_var,
        )
    conn.commit()
    return int(request_id_var.getvalue()[0])


def create_complaint(
    conn: oracledb.Connection,
    customer_id: int | None,
    account_id: int | None,
    complaint_category: str,
    complaint_description: str,
    branch_or_channel: str | None,
) -> int:
    with conn.cursor() as cur:
        complaint_id_var = cur.var(int)
        cur.execute(
            """
            INSERT INTO complaints
                (customer_id, account_id, complaint_category,
                 complaint_description, branch_or_channel)
            VALUES
                (:customer_id, :account_id, :complaint_category,
                 :complaint_description, :branch_or_channel)
            RETURNING complaint_id INTO :complaint_id
            """,
            customer_id=customer_id,
            account_id=account_id,
            complaint_category=complaint_category,
            complaint_description=complaint_description,
            branch_or_channel=branch_or_channel,
            complaint_id=complaint_id_var,
        )
    conn.commit()
    return int(complaint_id_var.getvalue()[0])


def create_callback_request(
    conn: oracledb.Connection,
    customer_id: int | None,
    account_id: int | None,
    request_type: str,
    request_summary: str | None,
    reason_for_callback: str,
) -> int:
    with conn.cursor() as cur:
        callback_id_var = cur.var(int)
        cur.execute(
            """
            INSERT INTO callback_requests
                (customer_id, account_id, request_type, request_summary,
                 reason_for_callback)
            VALUES
                (:customer_id, :account_id, :request_type, :request_summary,
                 :reason_for_callback)
            RETURNING callback_id INTO :callback_id
            """,
            customer_id=customer_id,
            account_id=account_id,
            request_type=request_type,
            request_summary=request_summary,
            reason_for_callback=reason_for_callback,
            callback_id=callback_id_var,
        )
    conn.commit()
    return int(callback_id_var.getvalue()[0])


def create_document_request(
    conn: oracledb.Connection,
    customer_id: int,
    account_id: int | None,
    document_type: str,
    delivery_method: str | None,
) -> int:
    with conn.cursor() as cur:
        document_request_id_var = cur.var(int)
        cur.execute(
            """
            INSERT INTO document_requests
                (customer_id, account_id, document_type, delivery_method)
            VALUES
                (:customer_id, :account_id, :document_type, :delivery_method)
            RETURNING document_request_id INTO :document_request_id
            """,
            customer_id=customer_id,
            account_id=account_id,
            document_type=document_type,
            delivery_method=delivery_method,
            document_request_id=document_request_id_var,
        )
    conn.commit()
    return int(document_request_id_var.getvalue()[0])


# ---------------------------------------------------------------------------
# Verification sessions (opaque token -> verified customer/account context)
# ---------------------------------------------------------------------------


def create_verification_session(
    conn: oracledb.Connection,
    token_hash: str,
    customer_id: int,
    account_id: int,
    expires_at: datetime,
) -> int:
    with conn.cursor() as cur:
        session_id_var = cur.var(int)
        cur.execute(
            """
            INSERT INTO verification_sessions
                (token_hash, customer_id, account_id, expires_at)
            VALUES
                (:token_hash, :customer_id, :account_id, :expires_at)
            RETURNING session_id INTO :session_id
            """,
            token_hash=token_hash,
            customer_id=customer_id,
            account_id=account_id,
            expires_at=expires_at,
            session_id=session_id_var,
        )
    conn.commit()
    return int(session_id_var.getvalue()[0])


def get_verification_session_by_token_hash(
    conn: oracledb.Connection, token_hash: str
) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT session_id, customer_id, account_id, expires_at, active
            FROM verification_sessions
            WHERE token_hash = :token_hash
            """,
            token_hash=token_hash,
        )
        row = cur.fetchone()
        if row is None:
            return None
        return {
            "session_id": row[0],
            "customer_id": row[1],
            "account_id": row[2],
            "expires_at": row[3],
            "active": bool(row[4]),
        }


# ---------------------------------------------------------------------------
# Merchant aliases (deterministic merchant/type equivalence for verification)
# ---------------------------------------------------------------------------


def get_active_merchant_aliases(
    conn: oracledb.Connection,
) -> list[tuple[str, str]]:
    """Return every active (alias_value, canonical_value) pair. Small,
    static-ish reference data - fetched in full rather than looked up by a
    single value, so callers can resolve several strings per verification
    attempt (spoken value, merchant_or_type, transaction_type) against one
    consistent snapshot without repeated queries."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT alias_value, canonical_value
            FROM merchant_aliases
            WHERE active = 1
            """
        )
        return [(row[0], row[1]) for row in cur.fetchall()]
