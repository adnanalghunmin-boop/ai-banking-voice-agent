"""Aggregated read-only banking services for a single HeyBreez call.

Reuses the exact same building blocks as the individual Phase 2 endpoints -
verification_sessions.resolve_session for the token, identity.
verify_account_ownership for the account - rather than duplicating that
logic or calling through each individual accounts.py/cards.py service
function (which would each redundantly re-resolve the token and re-run the
ownership query). One token resolution and one account lookup per call
answers every account-level flag; card delivery status additionally lists
the verified account's cards without ever requiring the caller to know an
internal card_id.
"""

from app.db import repository
from app.db.connection import db_session
from app.models.get_services import (
    CardDeliveryInfo,
    GetServicesRequest,
    GetServicesResponse,
)
from app.services import identity, verification_sessions
from app.utils.exceptions import BusinessRuleError
from app.utils.masking import mask_card_number


def get_services(request: GetServicesRequest) -> GetServicesResponse:
    if not any(
        (
            request.get_balance,
            request.get_iban,
            request.get_account_status,
            request.get_held_amount_details,
            request.get_card_delivery_status,
        )
    ):
        raise BusinessRuleError("At least one service flag must be true.")

    with db_session() as conn:
        ident = verification_sessions.resolve_session(
            conn, request.verification_token
        )
        account = identity.verify_account_ownership(
            conn, ident["customer_id"], ident["account_id"]
        )

        fields: dict = {}

        if request.get_balance:
            fields["balance"] = account["balance"]
            fields["available_balance"] = account["available_balance"]

        if request.get_iban:
            fields["iban"] = account["iban"]

        if request.get_account_status:
            fields["account_status"] = account["account_status"]

        if request.get_held_amount_details:
            fields["held_amount"] = account["held_amount"]

        if request.get_card_delivery_status:
            fields["card_delivery_status"] = _resolve_card_delivery_status(
                conn, ident["customer_id"], ident["account_id"]
            )

        return GetServicesResponse(**fields)


def _resolve_card_delivery_status(
    conn, customer_id: int, account_id: int
) -> str | list[CardDeliveryInfo]:
    cards = repository.get_cards_for_account(conn, customer_id, account_id)
    if len(cards) == 1:
        return cards[0]["delivery_status"]
    return [
        CardDeliveryInfo(
            card_id=card["card_id"],
            card_type=card["card_type"],
            masked_card_number=mask_card_number(card["card_number"]),
            delivery_status=card["delivery_status"],
        )
        for card in cards
    ]
