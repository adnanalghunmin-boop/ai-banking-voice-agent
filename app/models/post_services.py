import re
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, field_validator

from app.models.common import TokenContext

_CARD_LAST4_PATTERN = re.compile(r"\d{4}")

# Optional fields only - never includes an action flag (bool = False, not
# Optional) or verification_token (handled separately by TokenContext).
_BLANK_STRING_TO_NONE_FIELDS = (
    "card_number",
    "card_last4",
    "request_reason",
    "online_purchases_enabled",
    "international_usage_enabled",
    "new_spending_limit",
    "new_atm_limit",
    "new_address",
    "new_email",
    "new_mobile_number",
    "new_employment_details",
)


class PostServicesRequest(TokenContext):
    # Human-reviewed card actions
    freeze_card: bool = False
    stolen_card: bool = False
    lost_card: bool = False
    replacement_card: bool = False
    damaged_card: bool = False

    # Direct card actions
    activate_card: bool = False
    unfreeze_card: bool = False
    set_online_purchases: bool = False
    set_international_usage: bool = False
    change_spending_limit: bool = False
    change_atm_limit: bool = False

    # Document request
    request_account_statement: bool = False

    # Human-reviewed customer detail changes
    change_address: bool = False
    change_email: bool = False
    change_mobile_number: bool = False
    update_employment_details: bool = False

    # Card resolution / optional context. card_last4 is the preferred
    # identifier (never requires or exposes a full card number);
    # card_number is kept only for backward compatibility.
    card_number: str | None = None
    card_last4: str | None = None
    request_reason: str | None = None

    # Conditional values required by specific actions
    online_purchases_enabled: bool | None = None
    international_usage_enabled: bool | None = None
    new_spending_limit: Decimal | None = None
    new_atm_limit: Decimal | None = None

    new_address: str | None = None
    new_email: str | None = None
    new_mobile_number: str | None = None
    new_employment_details: str | None = None

    @field_validator(*_BLANK_STRING_TO_NONE_FIELDS, mode="before")
    @classmethod
    def _blank_string_to_none(cls, value: Any) -> Any:
        """HeyBreez sends unused optional fields as "" rather than
        omitting them or sending null. Treat "" as "not provided" for
        every optional field here - but leave real values (False, 0,
        Decimal("0"), non-empty strings) untouched, so this only ever
        widens what's accepted, never changes what a real value means."""
        if value == "":
            return None
        return value

    @field_validator("card_last4", mode="before")
    @classmethod
    def _coerce_numeric_card_last4(cls, value: Any) -> Any:
        """card_last4 is configured as Text in HeyBreez, but some requests
        still serialize it as a JSON number (5454 / 5454.0). Convert those
        to a string so the normal 4-digit check below still applies.

        Only converts - never pads. A numeric 123 becomes "123" and then
        fails the 4-digit check rather than being guessed into "0123".
        None, "" and other strings pass through untouched (the blank-string
        validator handles ""), as do bools, which are ints in Python but
        are never a valid card_last4 and must keep failing str validation.
        """
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return str(value)
        if isinstance(value, float):
            if not value.is_integer():
                raise ValueError("card_last4 must be exactly 4 digits")
            return str(int(value))
        return value

    @field_validator("card_last4", mode="after")
    @classmethod
    def _validate_card_last4_format(cls, value: str | None) -> str | None:
        """Exactly 4 numeric digits when provided. Kept as a plain str
        throughout (never cast to int) so a value like "0678" preserves
        its leading zero."""
        if value is not None and not _CARD_LAST4_PATTERN.fullmatch(value):
            raise ValueError("card_last4 must be exactly 4 digits")
        return value


class ActionResult(BaseModel):
    success: bool
    # "COMPLETED" (direct action applied), "PENDING_REVIEW" (a
    # SERVICE_REQUESTS/DOCUMENT_REQUESTS row was created for human
    # follow-up), or "FAILED" (see `reason` for a safe, machine-readable
    # code - never a raw exception or SQL error).
    status: str
    request_id: int | None = None
    reason: str | None = None


class PostServicesResponse(BaseModel):
    results: dict[str, ActionResult]
