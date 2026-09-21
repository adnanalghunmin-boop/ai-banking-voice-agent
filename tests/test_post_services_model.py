from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.models.post_services import PostServicesRequest


def test_empty_string_boolean_optional_fields_become_none():
    request = PostServicesRequest(
        verification_token="tok",
        online_purchases_enabled="",
        international_usage_enabled="",
    )

    assert request.online_purchases_enabled is None
    assert request.international_usage_enabled is None


def test_empty_string_decimal_optional_fields_become_none():
    request = PostServicesRequest(
        verification_token="tok",
        new_spending_limit="",
        new_atm_limit="",
    )

    assert request.new_spending_limit is None
    assert request.new_atm_limit is None


def test_empty_string_string_optional_fields_become_none():
    request = PostServicesRequest(
        verification_token="tok",
        card_number="",
        request_reason="",
        new_address="",
        new_email="",
        new_mobile_number="",
        new_employment_details="",
    )

    assert request.card_number is None
    assert request.request_reason is None
    assert request.new_address is None
    assert request.new_email is None
    assert request.new_mobile_number is None
    assert request.new_employment_details is None


def test_false_boolean_values_are_preserved_not_converted():
    request = PostServicesRequest(
        verification_token="tok",
        online_purchases_enabled=False,
        international_usage_enabled=False,
    )

    assert request.online_purchases_enabled is False
    assert request.international_usage_enabled is False


def test_zero_decimal_values_are_preserved_not_converted():
    request = PostServicesRequest(
        verification_token="tok",
        new_spending_limit=0,
        new_atm_limit=Decimal("0"),
    )

    assert request.new_spending_limit == Decimal("0")
    assert request.new_atm_limit == Decimal("0")


def test_valid_non_empty_values_are_unaffected():
    request = PostServicesRequest(
        verification_token="tok",
        online_purchases_enabled=True,
        new_spending_limit=Decimal("1500"),
        new_email="new@example.com",
        card_number="4556123412345678",
    )

    assert request.online_purchases_enabled is True
    assert request.new_spending_limit == Decimal("1500")
    assert request.new_email == "new@example.com"
    assert request.card_number == "4556123412345678"


def test_action_flags_are_unaffected_by_the_blank_string_validator():
    # Action flags are plain bool = False, not Optional, and were never
    # part of this validator's field list - confirm they still behave
    # exactly as before (rejecting non-boolean input normally).
    request = PostServicesRequest(verification_token="tok", lost_card=True)
    assert request.lost_card is True
    assert request.freeze_card is False


def test_verification_token_handling_is_unaffected():
    # verification_token is not in the blank-string field list; an empty
    # string there must still pass through as-is (resolve_session treats
    # it as falsy/invalid at the service layer, not at the model layer).
    request = PostServicesRequest(verification_token="")
    assert request.verification_token == ""


# --- card_last4 normalization ---------------------------------------------
# HeyBreez configures card_last4 as Text but sometimes serializes it as a
# JSON number; it must be normalized to a string before the 4-digit check.


def _last4(value):
    return PostServicesRequest(verification_token="tok", card_last4=value).card_last4


def test_card_last4_string_is_accepted_unchanged():
    assert _last4("5454") == "5454"


def test_card_last4_integer_is_normalized_to_string():
    assert _last4(5454) == "5454"


def test_card_last4_integer_like_float_is_normalized_to_string():
    assert _last4(5454.0) == "5454"


def test_card_last4_none_stays_none():
    assert _last4(None) is None


def test_card_last4_omitted_defaults_to_none():
    assert PostServicesRequest(verification_token="tok").card_last4 is None


def test_card_last4_empty_string_becomes_none():
    assert _last4("") is None


def test_card_last4_leading_zero_string_is_preserved():
    assert _last4("0123") == "0123"


def test_card_last4_numeric_value_never_gets_leading_zeros_reconstructed():
    # 123 arrives when a client drops the leading zero of "0123". We must
    # not guess it back - it fails the 4-digit check instead.
    with pytest.raises(ValidationError):
        _last4(123)
    with pytest.raises(ValidationError):
        _last4(123.0)


@pytest.mark.parametrize("value", ["567", "56789", 567, 56789, 56789.0, 0, -1234])
def test_card_last4_invalid_length_or_sign_is_rejected(value):
    with pytest.raises(ValidationError):
        _last4(value)


@pytest.mark.parametrize("value", ["56ab", "abcd", "12 4", "-123", "12.4", " 123"])
def test_card_last4_non_digit_string_is_rejected(value):
    with pytest.raises(ValidationError):
        _last4(value)


@pytest.mark.parametrize("value", [5454.5, 5454.1, -5454.5, float("nan"), float("inf")])
def test_card_last4_non_integer_float_is_rejected(value):
    with pytest.raises(ValidationError):
        _last4(value)


@pytest.mark.parametrize("value", [True, False, [], {}, ["5454"]])
def test_card_last4_other_types_are_rejected(value):
    with pytest.raises(ValidationError):
        _last4(value)

