from pydantic import BaseModel, Field


class ComplaintCreateRequest(BaseModel):
    """General complaints (no verification_token, no account_id) remain
    unprotected per spec. If the complaint concerns account-specific data,
    a verification_token must be supplied instead of a raw account_id - the
    resolved token identity always wins over customer_id/account_id in the
    request body, which exist below only for the account-less general case.
    """

    verification_token: str | None = Field(default=None)
    customer_id: int | None = Field(default=None, gt=0)
    account_id: int | None = Field(default=None, gt=0)
    complaint_category: str = Field(..., min_length=1, max_length=100)
    complaint_description: str = Field(..., min_length=1, max_length=1000)
    branch_or_channel: str | None = Field(default=None, max_length=150)


class ComplaintResponse(BaseModel):
    complaint_id: int
    complaint_reference: str
    complaint_status: str
