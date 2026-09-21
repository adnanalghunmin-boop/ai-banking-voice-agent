from decimal import Decimal

from pydantic import BaseModel, Field


class VerificationRequest(BaseModel):
    national_id: str = Field(..., min_length=1)
    account_number: str = Field(..., min_length=1)
    last_transaction_amount: Decimal
    last_transaction_merchant_or_type: str = Field(..., min_length=1)


class VerificationResponse(BaseModel):
    verified: bool
    customer_id: int | None = None
    account_id: int | None = None
    verification_token: str | None = None
    reason: str | None = None
