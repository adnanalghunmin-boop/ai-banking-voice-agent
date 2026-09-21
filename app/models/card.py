from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field

from app.models.common import TokenContext


class CardContext(TokenContext):
    card_id: int = Field(..., gt=0)


class ConfirmedCardAction(CardContext):
    confirmed: bool


class SetOnlinePurchasesRequest(ConfirmedCardAction):
    enabled: bool


class SetInternationalUsageRequest(ConfirmedCardAction):
    enabled: bool


class ChangeSpendingLimitRequest(ConfirmedCardAction):
    new_limit: Decimal = Field(..., gt=0)


class ChangeAtmLimitRequest(ConfirmedCardAction):
    new_limit: Decimal = Field(..., gt=0)


class CardBlockReason(str, Enum):
    LOST = "LOST"
    STOLEN = "STOLEN"
    CUSTOMER_REQUEST = "CUSTOMER_REQUEST"


class CardBlockRequest(ConfirmedCardAction):
    reason: CardBlockReason
    # Optional free-text explanation from the customer, stored in
    # SERVICE_REQUESTS.REQUEST_REASON in place of the bare enum value when
    # given (see app/services/cards.py:create_card_block_request). Not
    # required by this model itself - callers that must require it for a
    # specific action (e.g. post_services' freeze_card) enforce that
    # before constructing this model.
    request_reason: str | None = None


class CardReplacementReason(str, Enum):
    LOST = "LOST"
    STOLEN = "STOLEN"
    DAMAGED = "DAMAGED"
    OTHER = "OTHER"


class CardReplacementRequest(ConfirmedCardAction):
    reason: CardReplacementReason


class CardDeliveryStatusResponse(BaseModel):
    delivery_status: str


class CardStatusResponse(BaseModel):
    card_status: str


class OnlinePurchasesResponse(BaseModel):
    online_purchases_enabled: bool


class InternationalUsageResponse(BaseModel):
    international_usage_enabled: bool


class SpendingLimitResponse(BaseModel):
    spending_limit: Decimal


class AtmLimitResponse(BaseModel):
    atm_withdrawal_limit: Decimal
