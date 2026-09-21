import logging

from app.db import repository
from app.db.connection import db_session
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
from app.services import identity, verification_sessions
from app.utils.exceptions import BusinessRuleError

logger = logging.getLogger(__name__)


def _require_confirmation(confirmed: bool) -> None:
    if not confirmed:
        raise BusinessRuleError(
            "This action requires explicit customer confirmation."
        )


def get_card_delivery_status(context: CardContext) -> CardDeliveryStatusResponse:
    with db_session() as conn:
        ident = verification_sessions.resolve_session(
            conn, context.verification_token
        )
        card = identity.verify_card_ownership(
            conn, ident["customer_id"], ident["account_id"], context.card_id
        )
        return CardDeliveryStatusResponse(delivery_status=card["delivery_status"])


def activate_card(request: ConfirmedCardAction) -> CardStatusResponse:
    _require_confirmation(request.confirmed)
    with db_session() as conn:
        ident = verification_sessions.resolve_session(
            conn, request.verification_token
        )
        card = identity.verify_card_ownership(
            conn, ident["customer_id"], ident["account_id"], request.card_id
        )
        if card["card_status"] == "ACTIVE":
            raise BusinessRuleError("Card is already active.")
        repository.update_card_status(conn, request.card_id, "ACTIVE")
        return CardStatusResponse(card_status="ACTIVE")


def unfreeze_card(request: ConfirmedCardAction) -> CardStatusResponse:
    _require_confirmation(request.confirmed)
    with db_session() as conn:
        ident = verification_sessions.resolve_session(
            conn, request.verification_token
        )
        card = identity.verify_card_ownership(
            conn, ident["customer_id"], ident["account_id"], request.card_id
        )
        if card["card_status"] != "FROZEN":
            raise BusinessRuleError("Card is not currently frozen.")
        repository.update_card_status(conn, request.card_id, "ACTIVE")
        return CardStatusResponse(card_status="ACTIVE")


def set_online_purchases(
    request: SetOnlinePurchasesRequest,
) -> OnlinePurchasesResponse:
    _require_confirmation(request.confirmed)
    with db_session() as conn:
        ident = verification_sessions.resolve_session(
            conn, request.verification_token
        )
        identity.verify_card_ownership(
            conn, ident["customer_id"], ident["account_id"], request.card_id
        )
        repository.update_card_online_purchases(
            conn, request.card_id, request.enabled
        )
        return OnlinePurchasesResponse(online_purchases_enabled=request.enabled)


def set_international_usage(
    request: SetInternationalUsageRequest,
) -> InternationalUsageResponse:
    _require_confirmation(request.confirmed)
    with db_session() as conn:
        ident = verification_sessions.resolve_session(
            conn, request.verification_token
        )
        identity.verify_card_ownership(
            conn, ident["customer_id"], ident["account_id"], request.card_id
        )
        repository.update_card_international_usage(
            conn, request.card_id, request.enabled
        )
        return InternationalUsageResponse(
            international_usage_enabled=request.enabled
        )


def change_card_spending_limit(
    request: ChangeSpendingLimitRequest,
) -> SpendingLimitResponse:
    _require_confirmation(request.confirmed)
    with db_session() as conn:
        ident = verification_sessions.resolve_session(
            conn, request.verification_token
        )
        identity.verify_card_ownership(
            conn, ident["customer_id"], ident["account_id"], request.card_id
        )
        repository.update_card_spending_limit(
            conn, request.card_id, request.new_limit
        )
        return SpendingLimitResponse(spending_limit=request.new_limit)


def change_atm_withdrawal_limit(
    request: ChangeAtmLimitRequest,
) -> AtmLimitResponse:
    _require_confirmation(request.confirmed)
    with db_session() as conn:
        ident = verification_sessions.resolve_session(
            conn, request.verification_token
        )
        identity.verify_card_ownership(
            conn, ident["customer_id"], ident["account_id"], request.card_id
        )
        repository.update_card_atm_limit(conn, request.card_id, request.new_limit)
        return AtmLimitResponse(atm_withdrawal_limit=request.new_limit)


def create_card_block_request(request: CardBlockRequest) -> ServiceRequestResponse:
    """Never touches CARDS.card_status - only ever creates a PENDING
    SERVICE_REQUESTS row for a human employee to act on.

    REQUEST_REASON stores the customer's own free-text explanation
    (request.request_reason) when one was given; otherwise it falls back
    to the bare category enum (LOST/STOLEN/CUSTOMER_REQUEST), exactly as
    before this field existed - so callers that never pass it (e.g.
    existing stolen_card/lost_card flows with no explanation) are
    unaffected.
    """
    _require_confirmation(request.confirmed)
    stored_reason = (
        request.request_reason if request.request_reason else request.reason.value
    )
    with db_session() as conn:
        ident = verification_sessions.resolve_session(
            conn, request.verification_token
        )
        identity.verify_card_ownership(
            conn, ident["customer_id"], ident["account_id"], request.card_id
        )
        request_id = repository.create_service_request(
            conn,
            customer_id=ident["customer_id"],
            account_id=ident["account_id"],
            card_id=request.card_id,
            request_type="CARD_BLOCK",
            request_reason=stored_reason,
            requested_value=None,
        )
        logger.info(
            "Card block request created: request_id=%s card_id=%s category=%s",
            request_id,
            request.card_id,
            request.reason.value,
        )
        return ServiceRequestResponse(request_id=request_id, request_status="PENDING")


def create_card_replacement_request(
    request: CardReplacementRequest,
) -> ServiceRequestResponse:
    _require_confirmation(request.confirmed)
    with db_session() as conn:
        ident = verification_sessions.resolve_session(
            conn, request.verification_token
        )
        identity.verify_card_ownership(
            conn, ident["customer_id"], ident["account_id"], request.card_id
        )
        request_id = repository.create_service_request(
            conn,
            customer_id=ident["customer_id"],
            account_id=ident["account_id"],
            card_id=request.card_id,
            request_type="CARD_REPLACEMENT",
            request_reason=request.reason.value,
            requested_value=None,
        )
        return ServiceRequestResponse(request_id=request_id, request_status="PENDING")
