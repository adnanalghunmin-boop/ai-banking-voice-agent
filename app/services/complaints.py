import logging

from app.db import repository
from app.db.connection import db_session
from app.models.complaint import ComplaintCreateRequest, ComplaintResponse
from app.services import identity, verification_sessions
from app.utils.exceptions import BusinessRuleError

logger = logging.getLogger(__name__)


def create_complaint(request: ComplaintCreateRequest) -> ComplaintResponse:
    """General complaints need no verification_token. A complaint that
    concerns a specific account must supply a verification_token instead of
    a raw account_id - the resolved identity always overrides whatever
    customer_id/account_id may also be present in the body."""
    with db_session() as conn:
        customer_id = request.customer_id
        account_id = None

        if request.verification_token is not None:
            ident = verification_sessions.resolve_session(
                conn, request.verification_token
            )
            identity.verify_account_ownership(
                conn, ident["customer_id"], ident["account_id"]
            )
            customer_id = ident["customer_id"]
            account_id = ident["account_id"]
        elif request.account_id is not None:
            raise BusinessRuleError(
                "account_id requires a valid verification_token."
            )
        elif customer_id is not None:
            identity.verify_customer_exists(conn, customer_id)

        complaint_id = repository.create_complaint(
            conn,
            customer_id=customer_id,
            account_id=account_id,
            complaint_category=request.complaint_category,
            complaint_description=request.complaint_description,
            branch_or_channel=request.branch_or_channel,
        )
        reference = f"CMP-{complaint_id:06d}"
        logger.info(
            "Complaint created: complaint_id=%s reference=%s", complaint_id, reference
        )
        return ComplaintResponse(
            complaint_id=complaint_id,
            complaint_reference=reference,
            complaint_status="OPEN",
        )
