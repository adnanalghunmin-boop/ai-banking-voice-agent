from enum import Enum

from pydantic import Field

from app.models.common import TokenContext


class CustomerDetailField(str, Enum):
    MOBILE_NUMBER = "MOBILE_NUMBER"
    EMAIL = "EMAIL"
    ADDRESS = "ADDRESS"
    EMPLOYMENT_DETAILS = "EMPLOYMENT_DETAILS"


class CustomerDetailChangeRequest(TokenContext):
    field: CustomerDetailField
    requested_value: str = Field(..., min_length=1, max_length=300)
    confirmed: bool
