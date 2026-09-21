from app.db import repository
from app.db.connection import db_session
from app.models.common import ServiceRequestResponse
from app.models.customer_request import CustomerDetailChangeRequest
from app.services import identity, verification_sessions
from app.utils.exceptions import BusinessRuleError


def create_customer_detail_change_request(
    request: CustomerDetailChangeRequest,
) -> ServiceRequestResponse:
    """Never updates CUSTOMERS directly - always creates a PENDING
    SERVICE_REQUESTS row for human review, per bank policy."""
    if not request.confirmed:
        raise BusinessRuleError(
            "This action requires explicit customer confirmation."
        )
    with db_session() as conn:
        ident = verification_sessions.resolve_session(
            conn, request.verification_token
        )
        identity.verify_account_ownership(
            conn, ident["customer_id"], ident["account_id"]
        )
        request_id = repository.create_service_request(
            conn,
            customer_id=ident["customer_id"],
            account_id=ident["account_id"],
            card_id=None,
            request_type="CUSTOMER_DETAIL_CHANGE",
            request_reason=request.field.value,
            requested_value=request.requested_value,
        )
        return ServiceRequestResponse(request_id=request_id, request_status="PENDING")
