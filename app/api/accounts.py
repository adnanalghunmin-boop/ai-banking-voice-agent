from fastapi import APIRouter

from app.models.account import (
    AccountStatusResponse,
    BalanceResponse,
    HeldAmountResponse,
    IbanResponse,
    RecentTransactionsRequest,
    RecentTransactionsResponse,
)
from app.models.common import TokenContext
from app.services import accounts as accounts_service

router = APIRouter(prefix="/api/v1/accounts", tags=["accounts"])


@router.post("/balance", response_model=BalanceResponse)
def get_balance(request: TokenContext) -> BalanceResponse:
    return accounts_service.get_balance(request)


@router.post("/iban", response_model=IbanResponse)
def get_iban(request: TokenContext) -> IbanResponse:
    return accounts_service.get_iban(request)


@router.post("/status", response_model=AccountStatusResponse)
def get_account_status(request: TokenContext) -> AccountStatusResponse:
    return accounts_service.get_account_status(request)


@router.post("/held-amount", response_model=HeldAmountResponse)
def get_held_amount_details(request: TokenContext) -> HeldAmountResponse:
    return accounts_service.get_held_amount_details(request)


@router.post("/transactions", response_model=RecentTransactionsResponse)
def get_recent_transactions(
    request: RecentTransactionsRequest,
) -> RecentTransactionsResponse:
    return accounts_service.get_recent_transactions(request)
