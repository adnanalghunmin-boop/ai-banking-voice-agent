from pydantic import BaseModel, Field


class TokenContext(BaseModel):
    """Base of every protected (verification-required) action request.

    The caller supplies only the opaque verification_token issued by a prior
    successful POST /api/v1/verification/verify call. customer_id/account_id
    are never accepted directly from the caller for a protected action - the
    backend resolves them itself from the token/session
    (see app/services/verification_sessions.py) and that resolved identity
    is what every ownership check runs against.
    """

    verification_token: str | None = Field(default=None)


class ResolvedIdentity(BaseModel):
    """A verification token successfully resolved to a trusted
    customer_id/account_id pair. Only ever constructed by
    verification_sessions.resolve_session() - never from caller input."""

    customer_id: int
    account_id: int


class ServiceRequestResponse(BaseModel):
    """Shared response shape for any action that creates a human-reviewed
    SERVICE_REQUESTS row instead of applying a change directly."""

    request_id: int
    request_status: str
