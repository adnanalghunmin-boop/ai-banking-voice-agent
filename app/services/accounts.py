from app.db import repository
from app.db.connection import db_session
from app.models.account import (
    AccountStatusResponse,
    BalanceResponse,
    HeldAmountResponse,
    IbanResponse,
    RecentTransactionsRequest,
    RecentTransactionsResponse,
    TransactionItem,
)
from app.models.common import TokenContext
from app.services import identity, verification_sessions


def get_balance(context: TokenContext) -> BalanceResponse:
    with db_session() as conn:
        ident = verification_sessions.resolve_session(
            conn, context.verification_token
        )
        account = identity.verify_account_ownership(
            conn, ident["customer_id"], ident["account_id"]
        )
        return BalanceResponse(
            balance=account["balance"], available_balance=account["available_balance"]
        )


def get_iban(context: TokenContext) -> IbanResponse:
    with db_session() as conn:
        ident = verification_sessions.resolve_session(
            conn, context.verification_token
        )
        account = identity.verify_account_ownership(
            conn, ident["customer_id"], ident["account_id"]
        )
        return IbanResponse(iban=account["iban"])


def get_account_status(context: TokenContext) -> AccountStatusResponse:
    with db_session() as conn:
        ident = verification_sessions.resolve_session(
            conn, context.verification_token
        )
        account = identity.verify_account_ownership(
            conn, ident["customer_id"], ident["account_id"]
        )
        return AccountStatusResponse(account_status=account["account_status"])


def get_held_amount_details(context: TokenContext) -> HeldAmountResponse:
    with db_session() as conn:
        ident = verification_sessions.resolve_session(
            conn, context.verification_token
        )
        account = identity.verify_account_ownership(
            conn, ident["customer_id"], ident["account_id"]
        )
        return HeldAmountResponse(held_amount=account["held_amount"])


def get_recent_transactions(
    request: RecentTransactionsRequest,
) -> RecentTransactionsResponse:
    with db_session() as conn:
        ident = verification_sessions.resolve_session(
            conn, request.verification_token
        )
        identity.verify_account_ownership(
            conn, ident["customer_id"], ident["account_id"]
        )
        rows = repository.get_recent_transactions(
            conn, ident["account_id"], request.limit
        )
        return RecentTransactionsResponse(
            transactions=[TransactionItem(**row) for row in rows]
        )
