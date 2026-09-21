"""Aggregated write/action endpoint for HeyBreez: POST /api/v1/post-services.

Reuses the exact same Phase 2 service functions each direct/human-reviewed
action already has (cards.py, customer_requests.py, documents.py) rather
than duplicating their business logic - this module's only new
responsibility is resolving which card an action applies to without
requiring the caller to know an internal card_id, and turning each
requested action into an independent, structured result so one failing
action never hides or blocks the others.

Two kinds of failure are treated very differently:
- A malformed REQUEST (no action flag set, or a flag set without its
  required companion value) is rejected before anything runs, as a single
  whole-request 400/401 - nothing executes, symmetric with how a missing
  verification_token is a whole-request 401.
- A failure that depends on database/account state (ambiguous card,
  ownership mismatch, a business rule like "card already active") is
  captured per action. Every other requested action still runs and gets
  its own result; the overall HTTP response is still 200.
"""

import logging

from pydantic import ValidationError

from app.db import repository
from app.db.connection import db_session
from app.models.card import (
    CardBlockReason,
    CardBlockRequest,
    CardReplacementReason,
    CardReplacementRequest,
    ChangeAtmLimitRequest,
    ChangeSpendingLimitRequest,
    ConfirmedCardAction,
    SetInternationalUsageRequest,
    SetOnlinePurchasesRequest,
)
from app.models.customer_request import CustomerDetailChangeRequest, CustomerDetailField
from app.models.document import DocumentRequestCreateRequest, DocumentType
from app.models.post_services import (
    ActionResult,
    PostServicesRequest,
    PostServicesResponse,
)
from app.services import cards, customer_requests, documents, verification_sessions
from app.utils.exceptions import BusinessRuleError, DatabaseUnavailableError, NotFoundError

logger = logging.getLogger(__name__)

_ALL_ACTION_FLAGS = (
    "freeze_card",
    "stolen_card",
    "lost_card",
    "replacement_card",
    "damaged_card",
    "activate_card",
    "unfreeze_card",
    "set_online_purchases",
    "set_international_usage",
    "change_spending_limit",
    "change_atm_limit",
    "request_account_statement",
    "change_address",
    "change_email",
    "change_mobile_number",
    "update_employment_details",
)

_CARD_ACTION_FLAGS = (
    "freeze_card",
    "stolen_card",
    "lost_card",
    "replacement_card",
    "damaged_card",
    "activate_card",
    "unfreeze_card",
    "set_online_purchases",
    "set_international_usage",
    "change_spending_limit",
    "change_atm_limit",
)


def execute_actions(request: PostServicesRequest) -> PostServicesResponse:
    if not any(getattr(request, flag) for flag in _ALL_ACTION_FLAGS):
        raise BusinessRuleError("At least one action flag must be true.")

    _validate_required_values(request)

    with db_session() as conn:
        ident = verification_sessions.resolve_session(
            conn, request.verification_token
        )

        card_id: int | None = None
        card_failure_reason: str | None = None
        if any(getattr(request, flag) for flag in _CARD_ACTION_FLAGS):
            account_cards = repository.get_cards_for_account(
                conn, ident["customer_id"], ident["account_id"]
            )
            card_id, card_failure_reason = _resolve_card_id(
                account_cards, request.card_last4, request.card_number
            )

        token = request.verification_token
        # Stripped once, per the freeze_card requirement that the stored
        # reason never carries leading/trailing whitespace; None if not
        # given, in which case create_card_block_request falls back to
        # the bare category (LOST/STOLEN/CUSTOMER_REQUEST) as before.
        stripped_reason = (
            request.request_reason.strip() if request.request_reason else None
        )
        results: dict[str, ActionResult] = {}

        if request.activate_card:
            results["activate_card"] = _run_card_direct(
                card_failure_reason,
                lambda: cards.activate_card(
                    ConfirmedCardAction(
                        verification_token=token, card_id=card_id, confirmed=True
                    )
                ),
            )

        if request.unfreeze_card:
            results["unfreeze_card"] = _run_card_direct(
                card_failure_reason,
                lambda: cards.unfreeze_card(
                    ConfirmedCardAction(
                        verification_token=token, card_id=card_id, confirmed=True
                    )
                ),
            )

        if request.set_online_purchases:
            results["set_online_purchases"] = _run_card_direct(
                card_failure_reason,
                lambda: cards.set_online_purchases(
                    SetOnlinePurchasesRequest(
                        verification_token=token,
                        card_id=card_id,
                        enabled=request.online_purchases_enabled,
                        confirmed=True,
                    )
                ),
            )

        if request.set_international_usage:
            results["set_international_usage"] = _run_card_direct(
                card_failure_reason,
                lambda: cards.set_international_usage(
                    SetInternationalUsageRequest(
                        verification_token=token,
                        card_id=card_id,
                        enabled=request.international_usage_enabled,
                        confirmed=True,
                    )
                ),
            )

        if request.change_spending_limit:
            results["change_spending_limit"] = _run_card_direct(
                card_failure_reason,
                lambda: cards.change_card_spending_limit(
                    ChangeSpendingLimitRequest(
                        verification_token=token,
                        card_id=card_id,
                        new_limit=request.new_spending_limit,
                        confirmed=True,
                    )
                ),
            )

        if request.change_atm_limit:
            results["change_atm_limit"] = _run_card_direct(
                card_failure_reason,
                lambda: cards.change_atm_withdrawal_limit(
                    ChangeAtmLimitRequest(
                        verification_token=token,
                        card_id=card_id,
                        new_limit=request.new_atm_limit,
                        confirmed=True,
                    )
                ),
            )

        if request.freeze_card:
            results["freeze_card"] = _run_card_request(
                card_failure_reason,
                lambda: cards.create_card_block_request(
                    CardBlockRequest(
                        verification_token=token,
                        card_id=card_id,
                        reason=CardBlockReason.CUSTOMER_REQUEST,
                        request_reason=stripped_reason,
                        confirmed=True,
                    )
                ),
            )

        if request.stolen_card:
            results["stolen_card"] = _run_card_request(
                card_failure_reason,
                lambda: cards.create_card_block_request(
                    CardBlockRequest(
                        verification_token=token,
                        card_id=card_id,
                        reason=CardBlockReason.STOLEN,
                        request_reason=stripped_reason,
                        confirmed=True,
                    )
                ),
            )

        if request.lost_card:
            results["lost_card"] = _run_card_request(
                card_failure_reason,
                lambda: cards.create_card_block_request(
                    CardBlockRequest(
                        verification_token=token,
                        card_id=card_id,
                        reason=CardBlockReason.LOST,
                        request_reason=stripped_reason,
                        confirmed=True,
                    )
                ),
            )

        if request.replacement_card:
            results["replacement_card"] = _run_card_request(
                card_failure_reason,
                lambda: cards.create_card_replacement_request(
                    CardReplacementRequest(
                        verification_token=token,
                        card_id=card_id,
                        reason=CardReplacementReason.OTHER,
                        confirmed=True,
                    )
                ),
            )

        if request.damaged_card:
            results["damaged_card"] = _run_card_request(
                card_failure_reason,
                lambda: cards.create_card_replacement_request(
                    CardReplacementRequest(
                        verification_token=token,
                        card_id=card_id,
                        reason=CardReplacementReason.DAMAGED,
                        confirmed=True,
                    )
                ),
            )

        if request.change_address:
            results["change_address"] = _run_detail_change(
                token, CustomerDetailField.ADDRESS, request.new_address
            )

        if request.change_email:
            results["change_email"] = _run_detail_change(
                token, CustomerDetailField.EMAIL, request.new_email
            )

        if request.change_mobile_number:
            results["change_mobile_number"] = _run_detail_change(
                token, CustomerDetailField.MOBILE_NUMBER, request.new_mobile_number
            )

        if request.update_employment_details:
            results["update_employment_details"] = _run_detail_change(
                token,
                CustomerDetailField.EMPLOYMENT_DETAILS,
                request.new_employment_details,
            )

        if request.request_account_statement:
            results["request_account_statement"] = _run(
                lambda: _account_statement_result(
                    documents.create_document_request(
                        DocumentRequestCreateRequest(
                            verification_token=token,
                            document_type=DocumentType.ACCOUNT_STATEMENT,
                        )
                    )
                )
            )

        return PostServicesResponse(results=results)


def _validate_required_values(request: PostServicesRequest) -> None:
    missing: list[str] = []
    if request.freeze_card and (
        request.request_reason is None or not request.request_reason.strip()
    ):
        missing.append("request_reason")
    if request.set_online_purchases and request.online_purchases_enabled is None:
        missing.append("online_purchases_enabled")
    if (
        request.set_international_usage
        and request.international_usage_enabled is None
    ):
        missing.append("international_usage_enabled")
    if request.change_spending_limit and request.new_spending_limit is None:
        missing.append("new_spending_limit")
    if request.change_atm_limit and request.new_atm_limit is None:
        missing.append("new_atm_limit")
    if request.change_address and not request.new_address:
        missing.append("new_address")
    if request.change_email and not request.new_email:
        missing.append("new_email")
    if request.change_mobile_number and not request.new_mobile_number:
        missing.append("new_mobile_number")
    if request.update_employment_details and not request.new_employment_details:
        missing.append("new_employment_details")
    if missing:
        raise BusinessRuleError(
            "Missing required value(s) for requested action(s): "
            + ", ".join(missing)
        )


def _resolve_card_id(
    cards_list: list[dict], card_last4: str | None, card_number: str | None
) -> tuple[int | None, str | None]:
    """Resolve which card an action applies to without requiring the
    caller to know an internal card_id or expose a full card number.

    card_last4 is the preferred identifier and takes priority whenever
    given; card_number is kept only for backward compatibility with
    existing callers and is only consulted when card_last4 is absent.
    cards_list is always pre-scoped by the caller to the token-verified
    customer/account (repository.get_cards_for_account), so matching here
    can never reach a card belonging to anyone else.

    Returns (card_id, failure_reason) - exactly one of the two is None.
    """
    if not cards_list:
        return None, "no_card_found"

    if card_last4:
        matches = [c for c in cards_list if c["card_number"][-4:] == card_last4]
        if not matches:
            return None, "card_not_found"
        if len(matches) > 1:
            return None, "card_identification_ambiguous"
        return matches[0]["card_id"], None

    if len(cards_list) == 1:
        card = cards_list[0]
        if card_number and card_number.strip() != card["card_number"]:
            # A card number was given but doesn't match the account's only
            # card - never silently act on that one card anyway.
            return None, "card_not_found"
        return card["card_id"], None

    if not card_number:
        return None, "card_identification_required"

    matches = [c for c in cards_list if c["card_number"] == card_number.strip()]
    if len(matches) != 1:
        return None, "card_not_found"
    return matches[0]["card_id"], None


def _run(fn) -> ActionResult:
    try:
        return fn()
    except DatabaseUnavailableError:
        # Infrastructure failure, not a per-action business outcome - let
        # it propagate to the same global 503 every other endpoint uses.
        raise
    except (BusinessRuleError, NotFoundError) as exc:
        return ActionResult(success=False, status="FAILED", reason=str(exc))
    except ValidationError:
        return ActionResult(success=False, status="FAILED", reason="invalid_value")
    except Exception:
        logger.exception("post-services action failed unexpectedly")
        return ActionResult(success=False, status="FAILED", reason="internal_error")


def _run_card_direct(card_failure_reason: str | None, fn) -> ActionResult:
    if card_failure_reason is not None:
        return ActionResult(success=False, status="FAILED", reason=card_failure_reason)

    def do() -> ActionResult:
        fn()
        return ActionResult(success=True, status="COMPLETED")

    return _run(do)


def _run_card_request(card_failure_reason: str | None, fn) -> ActionResult:
    if card_failure_reason is not None:
        return ActionResult(success=False, status="FAILED", reason=card_failure_reason)

    def do() -> ActionResult:
        response = fn()
        return ActionResult(
            success=True, status="PENDING_REVIEW", request_id=response.request_id
        )

    return _run(do)


def _run_detail_change(
    token: str | None, field: CustomerDetailField, value: str | None
) -> ActionResult:
    def do() -> ActionResult:
        response = customer_requests.create_customer_detail_change_request(
            CustomerDetailChangeRequest(
                verification_token=token,
                field=field,
                requested_value=value,
                confirmed=True,
            )
        )
        return ActionResult(
            success=True, status="PENDING_REVIEW", request_id=response.request_id
        )

    return _run(do)


def _account_statement_result(response) -> ActionResult:
    return ActionResult(
        success=True,
        status="PENDING_REVIEW",
        request_id=response.document_request_id,
    )
