import logging
from decimal import Decimal

import oracledb

from app.db import repository
from app.db.connection import get_connection
from app.models.verification import VerificationRequest, VerificationResponse
from app.services import merchant_alias, verification_sessions
from app.utils.exceptions import DatabaseUnavailableError
from app.utils.masking import mask

logger = logging.getLogger(__name__)

FAILURE_REASON = "verification_failed"


def verify_customer(request: VerificationRequest) -> VerificationResponse:
    """Deterministically verify a customer against stored records.

    All four factors (national ID, account ownership, transaction amount,
    and merchant/type) must match. On any mismatch or missing record, a
    generic failure is returned without indicating which factor failed.
    """
    try:
        with get_connection() as conn:
            return _run_verification(conn, request)
    except oracledb.Error:
        logger.exception("Database error during verification")
        raise DatabaseUnavailableError() from None


def _run_verification(
    conn: oracledb.Connection, request: VerificationRequest
) -> VerificationResponse:
    logger.info(
        "Verification attempt: national_id=%s account_number=%s",
        mask(request.national_id),
        mask(request.account_number),
    )

    customer = repository.get_customer_by_national_id(conn, request.national_id)
    if customer is None:
        return _failed()

    account = repository.get_account_by_number(conn, request.account_number)
    if account is None or account["customer_id"] != customer["customer_id"]:
        return _failed()

    transaction = repository.get_latest_completed_transaction(
        conn, account["account_id"]
    )
    if transaction is None:
        return _failed()

    if not _amount_matches(request.last_transaction_amount, transaction["amount"]):
        return _failed()

    alias_map = merchant_alias.build_alias_map(conn)
    if not _merchant_or_type_matches(
        request.last_transaction_merchant_or_type,
        transaction["merchant_or_type"],
        transaction["transaction_type"],
        alias_map,
    ):
        return _failed()

    logger.info("Verification succeeded: customer_id=%s", customer["customer_id"])
    token = verification_sessions.create_session(
        conn, customer["customer_id"], account["account_id"]
    )
    return VerificationResponse(
        verified=True,
        customer_id=customer["customer_id"],
        account_id=account["account_id"],
        verification_token=token,
        reason=None,
    )


def _amount_matches(supplied: Decimal, actual: Decimal) -> bool:
    return supplied == actual


def _merchant_or_type_matches(
    supplied: str,
    merchant_or_type: str | None,
    transaction_type: str | None,
    alias_map: dict[str, str],
) -> bool:
    """The spoken value may match either merchant_or_type or
    transaction_type (unchanged rule). Each side is resolved through the
    same deterministic alias map before comparing, so e.g. the customer
    saying the Arabic name of a merchant stored in Latin script still
    matches - falling back to plain normalized string equality wherever no
    alias is configured."""
    resolved_supplied = merchant_alias.resolve(supplied, alias_map)
    if merchant_or_type and merchant_alias.resolve(merchant_or_type, alias_map) == resolved_supplied:
        return True
    if transaction_type and merchant_alias.resolve(transaction_type, alias_map) == resolved_supplied:
        return True
    return False


def _failed() -> VerificationResponse:
    logger.info("Verification failed")
    return VerificationResponse(
        verified=False, customer_id=None, account_id=None, reason=FAILURE_REASON
    )
