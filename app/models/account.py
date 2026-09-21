from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.common import TokenContext


class RecentTransactionsRequest(TokenContext):
    limit: int = Field(default=5, ge=1, le=10)


class BalanceResponse(BaseModel):
    balance: Decimal
    available_balance: Decimal


class IbanResponse(BaseModel):
    iban: str


class TransactionItem(BaseModel):
    transaction_id: int
    amount: Decimal
    merchant_or_type: str
    transaction_type: str | None
    transaction_date: datetime
    transaction_status: str


class RecentTransactionsResponse(BaseModel):
    transactions: list[TransactionItem]


class AccountStatusResponse(BaseModel):
    account_status: str


class HeldAmountResponse(BaseModel):
    held_amount: Decimal
