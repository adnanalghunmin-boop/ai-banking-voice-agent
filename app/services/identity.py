"""Ownership-verification helpers shared by every account-scoped service.

Design note (see README for the full write-up): action requests carry a
customer_id/account_id "verified context" that the caller (HeyBreez, via the
prior /api/v1/verification/verify call) is expected to supply. The backend
never trusts that pairing at face value - every single call re-checks it
against the database, in one query that cannot distinguish "doesn't exist"
from "doesn't belong to this customer". This is what stands in for a real
auth token in this POC: it costs one indexed lookup per call and makes it
impossible for a caller to act on an account/card that isn't actually linked
to the customer_id it supplied, no matter what IDs it sends.
"""

import oracledb

from app.db import repository
from app.utils.exceptions import NotFoundError


def verify_customer_exists(conn: oracledb.Connection, customer_id: int) -> dict:
    customer = repository.get_customer_by_id(conn, customer_id)
    if customer is None:
        raise NotFoundError("Customer not found.")
    return customer


def verify_account_ownership(
    conn: oracledb.Connection, customer_id: int, account_id: int
) -> dict:
    account = repository.get_account_for_customer(conn, customer_id, account_id)
    if account is None:
        raise NotFoundError("Account not found for this customer.")
    return account


def verify_card_ownership(
    conn: oracledb.Connection, customer_id: int, account_id: int, card_id: int
) -> dict:
    card = repository.get_card_for_customer_account(
        conn, customer_id, account_id, card_id
    )
    if card is None:
        raise NotFoundError("Card not found for this customer/account.")
    return card
