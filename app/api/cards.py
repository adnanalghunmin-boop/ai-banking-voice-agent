from fastapi import APIRouter, status

from app.models.card import (
    AtmLimitResponse,
    CardBlockRequest,
    CardContext,
    CardDeliveryStatusResponse,
    CardReplacementRequest,
    CardStatusResponse,
    ChangeAtmLimitRequest,
    ChangeSpendingLimitRequest,
    ConfirmedCardAction,
    InternationalUsageResponse,
    OnlinePurchasesResponse,
    SetInternationalUsageRequest,
    SetOnlinePurchasesRequest,
    SpendingLimitResponse,
)
from app.models.common import ServiceRequestResponse
from app.services import cards as cards_service

router = APIRouter(prefix="/api/v1/cards", tags=["cards"])


@router.post("/delivery-status", response_model=CardDeliveryStatusResponse)
def get_card_delivery_status(request: CardContext) -> CardDeliveryStatusResponse:
    return cards_service.get_card_delivery_status(request)


@router.post("/activate", response_model=CardStatusResponse)
def activate_card(request: ConfirmedCardAction) -> CardStatusResponse:
    return cards_service.activate_card(request)


@router.post("/unfreeze", response_model=CardStatusResponse)
def unfreeze_card(request: ConfirmedCardAction) -> CardStatusResponse:
    return cards_service.unfreeze_card(request)


@router.post("/online-purchases", response_model=OnlinePurchasesResponse)
def set_online_purchases(
    request: SetOnlinePurchasesRequest,
) -> OnlinePurchasesResponse:
    return cards_service.set_online_purchases(request)


@router.post("/international-usage", response_model=InternationalUsageResponse)
def set_international_usage(
    request: SetInternationalUsageRequest,
) -> InternationalUsageResponse:
    return cards_service.set_international_usage(request)


@router.post("/spending-limit", response_model=SpendingLimitResponse)
def change_card_spending_limit(
    request: ChangeSpendingLimitRequest,
) -> SpendingLimitResponse:
    return cards_service.change_card_spending_limit(request)


@router.post("/atm-withdrawal-limit", response_model=AtmLimitResponse)
def change_atm_withdrawal_limit(
    request: ChangeAtmLimitRequest,
) -> AtmLimitResponse:
    return cards_service.change_atm_withdrawal_limit(request)


@router.post(
    "/block-request",
    response_model=ServiceRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_card_block_request(request: CardBlockRequest) -> ServiceRequestResponse:
    return cards_service.create_card_block_request(request)


@router.post(
    "/replacement-request",
    response_model=ServiceRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_card_replacement_request(
    request: CardReplacementRequest,
) -> ServiceRequestResponse:
    return cards_service.create_card_replacement_request(request)
