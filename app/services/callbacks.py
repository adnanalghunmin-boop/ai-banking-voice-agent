from app.db import repository
from app.db.connection import db_session
from app.models.callback import CallbackCreateRequest, CallbackResponse
from app.services import identity
from app.utils.exceptions import BusinessRuleError


def create_callback_request(request: CallbackCreateRequest) -> CallbackResponse:
    with db_session() as conn:
        if request.account_id is not None:
            if request.customer_id is None:
                raise BusinessRuleError(
                    "customer_id is required when account_id is provided."
                )
            identity.verify_account_ownership(
                conn, request.customer_id, request.account_id
            )
        elif request.customer_id is not None:
            identity.verify_customer_exists(conn, request.customer_id)

        callback_id = repository.create_callback_request(
            conn,
            customer_id=request.customer_id,
            account_id=request.account_id,
            request_type=request.request_type,
            request_summary=request.request_summary,
            reason_for_callback=request.reason_for_callback,
        )
        return CallbackResponse(callback_id=callback_id, callback_status="PENDING")
