from app.db import repository
from app.models.document import DocumentRequestCreateRequest, DocumentRequestResponse
from app.db.connection import db_session
from app.services import identity, verification_sessions
from app.utils.exceptions import BusinessRuleError


def create_document_request(
    request: DocumentRequestCreateRequest,
) -> DocumentRequestResponse:
    """Only ever creates a PENDING DOCUMENT_REQUESTS row - the document
    itself is generated and delivered out of band by a human/downstream
    process, never fabricated by this API.

    A request involving an account is protected: it must supply
    verification_token instead of a raw account_id, and the resolved
    identity always overrides any customer_id/account_id also present in
    the body. A request with no account (e.g. a general bank certificate)
    may supply customer_id directly.
    """
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
        else:
            if customer_id is None:
                raise BusinessRuleError(
                    "customer_id or verification_token is required."
                )
            identity.verify_customer_exists(conn, customer_id)

        document_request_id = repository.create_document_request(
            conn,
            customer_id=customer_id,
            account_id=account_id,
            document_type=request.document_type.value,
            delivery_method=request.delivery_method,
        )
        return DocumentRequestResponse(
            document_request_id=document_request_id, request_status="PENDING"
        )
