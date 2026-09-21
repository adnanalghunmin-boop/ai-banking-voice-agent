from enum import Enum

from pydantic import BaseModel, Field


class DocumentType(str, Enum):
    ACCOUNT_STATEMENT = "ACCOUNT_STATEMENT"
    IBAN_CERTIFICATE = "IBAN_CERTIFICATE"
    BANK_CERTIFICATE = "BANK_CERTIFICATE"
    LOAN_STATEMENT = "LOAN_STATEMENT"


class DocumentRequestCreateRequest(BaseModel):
    """A document request not tied to any account (e.g. a general bank
    certificate) may supply customer_id directly. A request involving an
    account is protected: it must supply verification_token instead of a
    raw account_id, and the resolved token identity always wins over any
    customer_id/account_id also present in the body.
    """

    verification_token: str | None = Field(default=None)
    customer_id: int | None = Field(default=None, gt=0)
    account_id: int | None = Field(default=None, gt=0)
    document_type: DocumentType
    delivery_method: str | None = Field(default=None, max_length=50)


class DocumentRequestResponse(BaseModel):
    document_request_id: int
    request_status: str
