from decimal import Decimal

from pydantic import BaseModel

from app.models.common import TokenContext


class GetServicesRequest(TokenContext):
    get_balance: bool = False
    get_iban: bool = False
    get_account_status: bool = False
    get_held_amount_details: bool = False
    get_card_delivery_status: bool = False


class CardDeliveryInfo(BaseModel):
    card_id: int
    card_type: str
    masked_card_number: str
    delivery_status: str


class GetServicesResponse(BaseModel):
    balance: Decimal | None = None
    available_balance: Decimal | None = None
    iban: str | None = None
    account_status: str | None = None
    held_amount: Decimal | None = None
    # A single card returns its delivery_status directly; more than one
    # card returns a list of safely-identifying entries (never the full
    # card number). See app/services/aggregated.py.
    card_delivery_status: str | list[CardDeliveryInfo] | None = None
