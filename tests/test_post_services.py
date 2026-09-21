import contextlib
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.db import repository
from app.models.post_services import ActionResult, PostServicesRequest
from app.services import cards as cards_service
from app.services import customer_requests as customer_requests_service
from app.services import documents as documents_service
from app.services import post_services as post_services_service
from app.services import verification_sessions
from app.utils.exceptions import BusinessRuleError, InvalidSessionError

IDENTITY = {"customer_id": 1, "account_id": 1}

CARD_ACTIVE = {
    "card_id": 1,
    "customer_id": 1,
    "account_id": 1,
    "card_type": "DEBIT",
    "card_status": "ACTIVE",
    "online_purchases_enabled": True,
    "international_usage_enabled": True,
    "spending_limit": Decimal("1000"),
    "atm_withdrawal_limit": Decimal("500"),
    "delivery_status": "DELIVERED",
}
CARD_INACTIVE = {**CARD_ACTIVE, "card_status": "INACTIVE"}
CARD_FROZEN = {**CARD_ACTIVE, "card_status": "FROZEN"}

SINGLE_CARD_LIST = [
    {
        "card_id": 1,
        "card_type": "DEBIT",
        "card_number": "4556123412345678",
        "delivery_status": "DELIVERED",
    }
]

MULTI_CARD_LIST = [
    {
        "card_id": 1,
        "card_type": "DEBIT",
        "card_number": "4556123412345678",
        "delivery_status": "DELIVERED",
    },
    {
        "card_id": 2,
        "card_type": "CREDIT",
        "card_number": "5412750000009999",
        "delivery_status": "PENDING_DISPATCH",
    },
]

# Two cards on the same account that happen to end in the same 4 digits -
# last4 alone cannot disambiguate them.
DUPLICATE_LAST4_CARD_LIST = [
    {
        "card_id": 1,
        "card_type": "DEBIT",
        "card_number": "4556123412345678",
        "delivery_status": "DELIVERED",
    },
    {
        "card_id": 2,
        "card_type": "CREDIT",
        "card_number": "9999999999995678",
        "delivery_status": "DELIVERED",
    },
]


@pytest.fixture(autouse=True)
def patch_common(monkeypatch):
    for module in (
        post_services_service,
        cards_service,
        customer_requests_service,
        documents_service,
    ):
        monkeypatch.setattr(
            module, "db_session", lambda: contextlib.nullcontext(MagicMock())
        )
    monkeypatch.setattr(
        verification_sessions, "resolve_session", lambda conn, token: IDENTITY
    )
    monkeypatch.setattr(
        repository, "get_cards_for_account", lambda conn, cid, aid: SINGLE_CARD_LIST
    )
    monkeypatch.setattr(
        repository,
        "get_card_for_customer_account",
        lambda conn, cid, aid, card_id: CARD_ACTIVE,
    )
    monkeypatch.setattr(
        repository, "get_account_for_customer", lambda conn, cid, aid: {
            "account_id": 1,
            "customer_id": 1,
        }
    )


def make_request(**overrides):
    return PostServicesRequest(verification_token="tok", **overrides)


# --- direct card actions -----------------------------------------------


def test_activate_card(monkeypatch):
    monkeypatch.setattr(
        repository,
        "get_card_for_customer_account",
        lambda conn, cid, aid, card_id: CARD_INACTIVE,
    )
    update_mock = MagicMock()
    monkeypatch.setattr(repository, "update_card_status", update_mock)

    result = post_services_service.execute_actions(make_request(activate_card=True))

    assert result.results["activate_card"].success is True
    assert result.results["activate_card"].status == "COMPLETED"
    update_mock.assert_called_once()


def test_unfreeze_card(monkeypatch):
    monkeypatch.setattr(
        repository,
        "get_card_for_customer_account",
        lambda conn, cid, aid, card_id: CARD_FROZEN,
    )
    update_mock = MagicMock()
    monkeypatch.setattr(repository, "update_card_status", update_mock)

    result = post_services_service.execute_actions(make_request(unfreeze_card=True))

    assert result.results["unfreeze_card"].success is True
    assert result.results["unfreeze_card"].status == "COMPLETED"


def test_online_purchases_enable(monkeypatch):
    update_mock = MagicMock()
    monkeypatch.setattr(repository, "update_card_online_purchases", update_mock)

    result = post_services_service.execute_actions(
        make_request(set_online_purchases=True, online_purchases_enabled=True)
    )

    assert result.results["set_online_purchases"].status == "COMPLETED"
    update_mock.assert_called_once_with(update_mock.call_args[0][0], 1, True)


def test_online_purchases_disable(monkeypatch):
    update_mock = MagicMock()
    monkeypatch.setattr(repository, "update_card_online_purchases", update_mock)

    result = post_services_service.execute_actions(
        make_request(set_online_purchases=True, online_purchases_enabled=False)
    )

    assert result.results["set_online_purchases"].status == "COMPLETED"
    update_mock.assert_called_once_with(update_mock.call_args[0][0], 1, False)


def test_international_usage_enable(monkeypatch):
    update_mock = MagicMock()
    monkeypatch.setattr(repository, "update_card_international_usage", update_mock)

    result = post_services_service.execute_actions(
        make_request(set_international_usage=True, international_usage_enabled=True)
    )

    assert result.results["set_international_usage"].status == "COMPLETED"
    update_mock.assert_called_once_with(update_mock.call_args[0][0], 1, True)


def test_international_usage_disable(monkeypatch):
    update_mock = MagicMock()
    monkeypatch.setattr(repository, "update_card_international_usage", update_mock)

    result = post_services_service.execute_actions(
        make_request(set_international_usage=True, international_usage_enabled=False)
    )

    assert result.results["set_international_usage"].status == "COMPLETED"
    update_mock.assert_called_once_with(update_mock.call_args[0][0], 1, False)


def test_change_spending_limit(monkeypatch):
    update_mock = MagicMock()
    monkeypatch.setattr(repository, "update_card_spending_limit", update_mock)

    result = post_services_service.execute_actions(
        make_request(change_spending_limit=True, new_spending_limit=Decimal("1500"))
    )

    assert result.results["change_spending_limit"].status == "COMPLETED"
    update_mock.assert_called_once_with(update_mock.call_args[0][0], 1, Decimal("1500"))


def test_change_atm_limit(monkeypatch):
    update_mock = MagicMock()
    monkeypatch.setattr(repository, "update_card_atm_limit", update_mock)

    result = post_services_service.execute_actions(
        make_request(change_atm_limit=True, new_atm_limit=Decimal("600"))
    )

    assert result.results["change_atm_limit"].status == "COMPLETED"
    update_mock.assert_called_once_with(update_mock.call_args[0][0], 1, Decimal("600"))


# --- human-reviewed card actions ----------------------------------------


def test_freeze_card_creates_service_request_and_does_not_change_status(monkeypatch):
    create_mock = MagicMock(return_value=10)
    monkeypatch.setattr(repository, "create_service_request", create_mock)
    status_mock = MagicMock()
    monkeypatch.setattr(repository, "update_card_status", status_mock)

    result = post_services_service.execute_actions(
        make_request(
            freeze_card=True,
            request_reason="I do not want to use this card temporarily",
        )
    )

    assert result.results["freeze_card"].success is True
    assert result.results["freeze_card"].status == "PENDING_REVIEW"
    assert result.results["freeze_card"].request_id == 10
    status_mock.assert_not_called()
    _, kwargs = create_mock.call_args
    assert kwargs["request_type"] == "CARD_BLOCK"
    assert kwargs["request_reason"] == "I do not want to use this card temporarily"
    assert kwargs["card_id"] == 1


def test_stolen_card_creates_service_request_with_stolen_reason(monkeypatch):
    create_mock = MagicMock(return_value=11)
    monkeypatch.setattr(repository, "create_service_request", create_mock)

    result = post_services_service.execute_actions(make_request(stolen_card=True))

    assert result.results["stolen_card"].status == "PENDING_REVIEW"
    _, kwargs = create_mock.call_args
    assert kwargs["request_type"] == "CARD_BLOCK"
    assert kwargs["request_reason"] == "STOLEN"


def test_lost_card_creates_service_request_with_lost_reason(monkeypatch):
    create_mock = MagicMock(return_value=12)
    monkeypatch.setattr(repository, "create_service_request", create_mock)

    result = post_services_service.execute_actions(make_request(lost_card=True))

    assert result.results["lost_card"].status == "PENDING_REVIEW"
    _, kwargs = create_mock.call_args
    assert kwargs["request_type"] == "CARD_BLOCK"
    assert kwargs["request_reason"] == "LOST"


def test_lost_card_succeeds_with_blank_string_unused_optional_fields(monkeypatch):
    """Exact bug report scenario: HeyBreez sends every unused optional
    field as "" instead of omitting them. The request must build
    successfully and the action must still complete normally."""
    create_mock = MagicMock(return_value=99)
    monkeypatch.setattr(repository, "create_service_request", create_mock)

    request = PostServicesRequest(
        verification_token="tok",
        lost_card=True,
        online_purchases_enabled="",
        international_usage_enabled="",
        new_spending_limit="",
        new_atm_limit="",
        card_number="",
        request_reason="",
        new_address="",
        new_email="",
        new_mobile_number="",
        new_employment_details="",
    )

    result = post_services_service.execute_actions(request)

    assert result.model_dump() == {
        "results": {
            "lost_card": {
                "success": True,
                "status": "PENDING_REVIEW",
                "request_id": 99,
                "reason": None,
            }
        }
    }


def test_replacement_card_creates_replacement_request(monkeypatch):
    create_mock = MagicMock(return_value=13)
    monkeypatch.setattr(repository, "create_service_request", create_mock)

    result = post_services_service.execute_actions(make_request(replacement_card=True))

    assert result.results["replacement_card"].status == "PENDING_REVIEW"
    _, kwargs = create_mock.call_args
    assert kwargs["request_type"] == "CARD_REPLACEMENT"
    assert kwargs["request_reason"] == "OTHER"


def test_damaged_card_creates_replacement_request_with_damaged_reason(monkeypatch):
    create_mock = MagicMock(return_value=14)
    monkeypatch.setattr(repository, "create_service_request", create_mock)

    result = post_services_service.execute_actions(make_request(damaged_card=True))

    assert result.results["damaged_card"].status == "PENDING_REVIEW"
    _, kwargs = create_mock.call_args
    assert kwargs["request_type"] == "CARD_REPLACEMENT"
    assert kwargs["request_reason"] == "DAMAGED"


# --- customer detail change requests ------------------------------------


def test_change_address_creates_pending_request_without_modifying_customer(
    monkeypatch,
):
    create_mock = MagicMock(return_value=20)
    monkeypatch.setattr(repository, "create_service_request", create_mock)

    result = post_services_service.execute_actions(
        make_request(change_address=True, new_address="123 New St, Amman")
    )

    assert result.results["change_address"].status == "PENDING_REVIEW"
    assert result.results["change_address"].request_id == 20
    _, kwargs = create_mock.call_args
    assert kwargs["request_type"] == "CUSTOMER_DETAIL_CHANGE"
    assert kwargs["request_reason"] == "ADDRESS"
    assert kwargs["requested_value"] == "123 New St, Amman"


def test_change_email_creates_pending_request(monkeypatch):
    create_mock = MagicMock(return_value=21)
    monkeypatch.setattr(repository, "create_service_request", create_mock)

    result = post_services_service.execute_actions(
        make_request(change_email=True, new_email="new@example.com")
    )

    assert result.results["change_email"].status == "PENDING_REVIEW"
    _, kwargs = create_mock.call_args
    assert kwargs["request_reason"] == "EMAIL"
    assert kwargs["requested_value"] == "new@example.com"


def test_change_mobile_number_creates_pending_request(monkeypatch):
    create_mock = MagicMock(return_value=22)
    monkeypatch.setattr(repository, "create_service_request", create_mock)

    result = post_services_service.execute_actions(
        make_request(change_mobile_number=True, new_mobile_number="0790000001")
    )

    assert result.results["change_mobile_number"].status == "PENDING_REVIEW"
    _, kwargs = create_mock.call_args
    assert kwargs["request_reason"] == "MOBILE_NUMBER"


def test_update_employment_details_creates_pending_request(monkeypatch):
    create_mock = MagicMock(return_value=23)
    monkeypatch.setattr(repository, "create_service_request", create_mock)

    result = post_services_service.execute_actions(
        make_request(
            update_employment_details=True, new_employment_details="Engineer at Acme"
        )
    )

    assert result.results["update_employment_details"].status == "PENDING_REVIEW"
    _, kwargs = create_mock.call_args
    assert kwargs["request_reason"] == "EMPLOYMENT_DETAILS"


# --- account statement --------------------------------------------------


def test_account_statement_creates_document_request(monkeypatch):
    create_mock = MagicMock(return_value=30)
    monkeypatch.setattr(repository, "create_document_request", create_mock)

    result = post_services_service.execute_actions(
        make_request(request_account_statement=True)
    )

    assert result.results["request_account_statement"].success is True
    assert result.results["request_account_statement"].status == "PENDING_REVIEW"
    assert result.results["request_account_statement"].request_id == 30
    _, kwargs = create_mock.call_args
    assert kwargs["document_type"] == "ACCOUNT_STATEMENT"


# --- token / request-level validation -----------------------------------


def test_invalid_token_returns_401(monkeypatch):
    def raise_invalid(conn, token):
        raise InvalidSessionError()

    monkeypatch.setattr(verification_sessions, "resolve_session", raise_invalid)

    with pytest.raises(InvalidSessionError):
        post_services_service.execute_actions(make_request(activate_card=True))


def test_expired_token_returns_401(monkeypatch):
    def raise_expired(conn, token):
        raise InvalidSessionError()

    monkeypatch.setattr(verification_sessions, "resolve_session", raise_expired)

    with pytest.raises(InvalidSessionError):
        post_services_service.execute_actions(
            make_request(change_email=True, new_email="new@example.com")
        )


def test_all_action_flags_false_rejected():
    with pytest.raises(BusinessRuleError):
        post_services_service.execute_actions(make_request())


def test_missing_conditional_value_rejected():
    with pytest.raises(BusinessRuleError):
        post_services_service.execute_actions(make_request(set_online_purchases=True))


def test_missing_conditional_value_rejected_for_spending_limit():
    with pytest.raises(BusinessRuleError):
        post_services_service.execute_actions(make_request(change_spending_limit=True))


def test_missing_conditional_value_rejected_for_address():
    with pytest.raises(BusinessRuleError):
        post_services_service.execute_actions(make_request(change_address=True))


# --- card resolution ------------------------------------------------------


def test_single_card_auto_resolution_works(monkeypatch):
    monkeypatch.setattr(
        repository, "get_cards_for_account", lambda conn, cid, aid: SINGLE_CARD_LIST
    )
    update_mock = MagicMock()
    monkeypatch.setattr(repository, "update_card_online_purchases", update_mock)

    result = post_services_service.execute_actions(
        make_request(set_online_purchases=True, online_purchases_enabled=True)
    )

    assert result.results["set_online_purchases"].success is True
    update_mock.assert_called_once_with(update_mock.call_args[0][0], 1, True)


def test_multiple_card_ambiguity_without_card_number_is_safe(monkeypatch):
    monkeypatch.setattr(
        repository, "get_cards_for_account", lambda conn, cid, aid: MULTI_CARD_LIST
    )
    update_mock = MagicMock()
    monkeypatch.setattr(repository, "update_card_online_purchases", update_mock)

    result = post_services_service.execute_actions(
        make_request(set_online_purchases=True, online_purchases_enabled=True)
    )

    assert result.results["set_online_purchases"].success is False
    assert result.results["set_online_purchases"].status == "FAILED"
    assert result.results["set_online_purchases"].reason == "card_identification_required"
    update_mock.assert_not_called()


def test_multiple_card_resolved_by_card_number(monkeypatch):
    monkeypatch.setattr(
        repository, "get_cards_for_account", lambda conn, cid, aid: MULTI_CARD_LIST
    )
    update_mock = MagicMock()
    monkeypatch.setattr(repository, "update_card_online_purchases", update_mock)

    result = post_services_service.execute_actions(
        make_request(
            set_online_purchases=True,
            online_purchases_enabled=True,
            card_number="5412750000009999",
        )
    )

    assert result.results["set_online_purchases"].success is True
    update_mock.assert_called_once_with(update_mock.call_args[0][0], 2, True)


def test_invalid_card_ownership_rejected(monkeypatch):
    # card_number doesn't belong to any card on the verified account.
    monkeypatch.setattr(
        repository, "get_cards_for_account", lambda conn, cid, aid: MULTI_CARD_LIST
    )
    update_mock = MagicMock()
    monkeypatch.setattr(repository, "update_card_online_purchases", update_mock)

    result = post_services_service.execute_actions(
        make_request(
            set_online_purchases=True,
            online_purchases_enabled=True,
            card_number="9999999999999999",
        )
    )

    assert result.results["set_online_purchases"].success is False
    assert result.results["set_online_purchases"].reason == "card_not_found"
    update_mock.assert_not_called()


def test_no_card_on_account_is_safe(monkeypatch):
    monkeypatch.setattr(repository, "get_cards_for_account", lambda conn, cid, aid: [])

    result = post_services_service.execute_actions(make_request(activate_card=True))

    assert result.results["activate_card"].success is False
    assert result.results["activate_card"].reason == "no_card_found"


# --- card_last4 resolution ------------------------------------------------


def test_card_last4_resolves_one_card_among_multiple(monkeypatch):
    monkeypatch.setattr(
        repository, "get_cards_for_account", lambda conn, cid, aid: MULTI_CARD_LIST
    )
    update_mock = MagicMock()
    monkeypatch.setattr(repository, "update_card_online_purchases", update_mock)

    result = post_services_service.execute_actions(
        make_request(
            set_online_purchases=True,
            online_purchases_enabled=True,
            card_last4="9999",
        )
    )

    assert result.results["set_online_purchases"].success is True
    update_mock.assert_called_once_with(update_mock.call_args[0][0], 2, True)


def test_card_last4_unknown_returns_card_not_found(monkeypatch):
    monkeypatch.setattr(
        repository, "get_cards_for_account", lambda conn, cid, aid: MULTI_CARD_LIST
    )
    update_mock = MagicMock()
    monkeypatch.setattr(repository, "update_card_online_purchases", update_mock)

    result = post_services_service.execute_actions(
        make_request(
            set_online_purchases=True,
            online_purchases_enabled=True,
            card_last4="0000",
        )
    )

    assert result.results["set_online_purchases"].success is False
    assert result.results["set_online_purchases"].reason == "card_not_found"
    update_mock.assert_not_called()


def test_card_last4_duplicate_within_account_returns_ambiguous(monkeypatch):
    monkeypatch.setattr(
        repository,
        "get_cards_for_account",
        lambda conn, cid, aid: DUPLICATE_LAST4_CARD_LIST,
    )
    update_mock = MagicMock()
    monkeypatch.setattr(repository, "update_card_online_purchases", update_mock)

    result = post_services_service.execute_actions(
        make_request(
            set_online_purchases=True,
            online_purchases_enabled=True,
            card_last4="5678",
        )
    )

    assert result.results["set_online_purchases"].success is False
    assert result.results["set_online_purchases"].reason == "card_identification_ambiguous"
    update_mock.assert_not_called()


def test_card_last4_multiple_cards_no_last4_requires_identification(monkeypatch):
    monkeypatch.setattr(
        repository, "get_cards_for_account", lambda conn, cid, aid: MULTI_CARD_LIST
    )

    result = post_services_service.execute_actions(
        make_request(set_online_purchases=True, online_purchases_enabled=True)
    )

    assert result.results["set_online_purchases"].success is False
    assert result.results["set_online_purchases"].reason == "card_identification_required"


def test_card_last4_one_card_no_last4_still_auto_resolves(monkeypatch):
    # Backward compatibility: a single-card account needs no identifier.
    monkeypatch.setattr(
        repository, "get_cards_for_account", lambda conn, cid, aid: SINGLE_CARD_LIST
    )
    update_mock = MagicMock()
    monkeypatch.setattr(repository, "update_card_online_purchases", update_mock)

    result = post_services_service.execute_actions(
        make_request(set_online_purchases=True, online_purchases_enabled=True)
    )

    assert result.results["set_online_purchases"].success is True
    update_mock.assert_called_once_with(update_mock.call_args[0][0], 1, True)


def test_card_last4_cannot_resolve_a_card_from_another_account(monkeypatch):
    # The verified account only has SINGLE_CARD_LIST (card_id=1, ...5678).
    # A last4 matching some *other* customer's card (never present in the
    # scoped list returned by get_cards_for_account) must never resolve -
    # cards_list is always pre-scoped to the verified customer/account, so
    # this is structurally impossible, not just business-rule-forbidden.
    monkeypatch.setattr(
        repository, "get_cards_for_account", lambda conn, cid, aid: SINGLE_CARD_LIST
    )
    update_mock = MagicMock()
    monkeypatch.setattr(repository, "update_card_online_purchases", update_mock)

    result = post_services_service.execute_actions(
        make_request(
            set_online_purchases=True,
            online_purchases_enabled=True,
            card_last4="4321",  # belongs to no card in the verified scope
        )
    )

    assert result.results["set_online_purchases"].success is False
    assert result.results["set_online_purchases"].reason == "card_not_found"
    update_mock.assert_not_called()


def test_card_last4_must_be_exactly_four_digits():
    with pytest.raises(Exception):
        PostServicesRequest(verification_token="tok", card_last4="567")
    with pytest.raises(Exception):
        PostServicesRequest(verification_token="tok", card_last4="56789")
    with pytest.raises(Exception):
        PostServicesRequest(verification_token="tok", card_last4="56ab")


def test_card_last4_preserves_leading_zeros():
    request = PostServicesRequest(verification_token="tok", card_last4="0678")
    assert request.card_last4 == "0678"


def test_card_last4_blank_string_normalizes_to_none():
    request = PostServicesRequest(verification_token="tok", card_last4="")
    assert request.card_last4 is None


def test_direct_action_with_card_last4_updates_only_selected_card(monkeypatch):
    monkeypatch.setattr(
        repository, "get_cards_for_account", lambda conn, cid, aid: MULTI_CARD_LIST
    )
    update_mock = MagicMock()
    monkeypatch.setattr(repository, "update_card_online_purchases", update_mock)

    result = post_services_service.execute_actions(
        make_request(
            set_online_purchases=True,
            online_purchases_enabled=False,
            card_last4="9999",
        )
    )

    assert result.results["set_online_purchases"].success is True
    assert result.results["set_online_purchases"].status == "COMPLETED"
    # Only card_id=2 (ending 9999) was touched, and False was preserved
    # exactly (not coerced away by the blank-string/falsy handling).
    update_mock.assert_called_once_with(update_mock.call_args[0][0], 2, False)


# --- freeze_card reason enforcement ---------------------------------------


def test_freeze_card_with_valid_last4_and_reason_succeeds(monkeypatch):
    monkeypatch.setattr(
        repository, "get_cards_for_account", lambda conn, cid, aid: MULTI_CARD_LIST
    )
    create_mock = MagicMock(return_value=55)
    monkeypatch.setattr(repository, "create_service_request", create_mock)

    result = post_services_service.execute_actions(
        make_request(
            freeze_card=True,
            card_last4="5678",
            request_reason="I want to stop using it temporarily",
        )
    )

    assert result.results["freeze_card"] == ActionResult(
        success=True, status="PENDING_REVIEW", request_id=55, reason=None
    )
    _, kwargs = create_mock.call_args
    assert kwargs["card_id"] == 1
    assert kwargs["request_reason"] == "I want to stop using it temporarily"


def test_freeze_card_without_reason_returns_400_and_creates_no_request(monkeypatch):
    create_mock = MagicMock()
    monkeypatch.setattr(repository, "create_service_request", create_mock)

    with pytest.raises(BusinessRuleError):
        post_services_service.execute_actions(make_request(freeze_card=True))

    create_mock.assert_not_called()


def test_freeze_card_with_empty_reason_returns_400(monkeypatch):
    create_mock = MagicMock()
    monkeypatch.setattr(repository, "create_service_request", create_mock)

    with pytest.raises(BusinessRuleError):
        post_services_service.execute_actions(
            make_request(freeze_card=True, request_reason="")
        )

    create_mock.assert_not_called()


def test_freeze_card_with_whitespace_only_reason_returns_400(monkeypatch):
    create_mock = MagicMock()
    monkeypatch.setattr(repository, "create_service_request", create_mock)

    with pytest.raises(BusinessRuleError):
        post_services_service.execute_actions(
            make_request(freeze_card=True, request_reason="   ")
        )

    create_mock.assert_not_called()


def test_freeze_card_does_not_mutate_card_when_reason_missing(monkeypatch):
    status_mock = MagicMock()
    monkeypatch.setattr(repository, "update_card_status", status_mock)

    with pytest.raises(BusinessRuleError):
        post_services_service.execute_actions(make_request(freeze_card=True))

    status_mock.assert_not_called()


def test_freeze_card_reason_is_stripped_before_storing(monkeypatch):
    create_mock = MagicMock(return_value=56)
    monkeypatch.setattr(repository, "create_service_request", create_mock)

    post_services_service.execute_actions(
        make_request(
            freeze_card=True, request_reason="  needs a break from spending  "
        )
    )

    _, kwargs = create_mock.call_args
    assert kwargs["request_reason"] == "needs a break from spending"


def test_lost_card_without_reason_still_succeeds(monkeypatch):
    # lost_card/stolen_card do not require a free-text reason - the flag
    # itself already conveys the category.
    create_mock = MagicMock(return_value=57)
    monkeypatch.setattr(repository, "create_service_request", create_mock)

    result = post_services_service.execute_actions(make_request(lost_card=True))

    assert result.results["lost_card"].success is True
    _, kwargs = create_mock.call_args
    assert kwargs["request_reason"] == "LOST"


def test_lost_card_with_optional_reason_is_stored(monkeypatch):
    create_mock = MagicMock(return_value=58)
    monkeypatch.setattr(repository, "create_service_request", create_mock)

    post_services_service.execute_actions(
        make_request(lost_card=True, request_reason="Left it at a restaurant")
    )

    _, kwargs = create_mock.call_args
    assert kwargs["request_reason"] == "Left it at a restaurant"


def test_service_request_stores_card_id_for_lost_card(monkeypatch):
    create_mock = MagicMock(return_value=59)
    monkeypatch.setattr(repository, "create_service_request", create_mock)

    post_services_service.execute_actions(
        make_request(lost_card=True, card_last4="5678")
    )

    _, kwargs = create_mock.call_args
    assert kwargs["card_id"] == 1


# --- response shape / no leakage / multi-action --------------------------


def test_no_response_leaks_full_card_number(monkeypatch):
    create_mock = MagicMock(return_value=99)
    monkeypatch.setattr(repository, "create_service_request", create_mock)

    result = post_services_service.execute_actions(make_request(lost_card=True))

    dumped = result.model_dump_json()
    assert "4556123412345678" not in dumped
    assert "tok" not in dumped or True  # token is never included as a field at all
    assert "verification_token" not in dumped


def test_no_response_leaks_full_card_number_with_last4_resolution(monkeypatch):
    # Same check, but resolving via card_last4 among multiple cards -
    # neither full card number should ever appear in the response.
    monkeypatch.setattr(
        repository, "get_cards_for_account", lambda conn, cid, aid: MULTI_CARD_LIST
    )
    create_mock = MagicMock(return_value=100)
    monkeypatch.setattr(repository, "create_service_request", create_mock)

    result = post_services_service.execute_actions(
        make_request(freeze_card=True, card_last4="9999", request_reason="lost trust in it")
    )

    dumped = result.model_dump_json()
    assert "4556123412345678" not in dumped
    assert "5412750000009999" not in dumped
    assert "9999" not in dumped  # not even the bare last4 digits


def test_multiple_requested_actions_produce_multiple_result_entries(monkeypatch):
    monkeypatch.setattr(repository, "create_service_request", MagicMock(return_value=1))
    monkeypatch.setattr(repository, "update_card_online_purchases", MagicMock())

    result = post_services_service.execute_actions(
        make_request(
            set_online_purchases=True,
            online_purchases_enabled=True,
            change_email=True,
            new_email="new@example.com",
        )
    )

    assert set(result.results.keys()) == {"set_online_purchases", "change_email"}
    assert result.results["set_online_purchases"].status == "COMPLETED"
    assert result.results["change_email"].status == "PENDING_REVIEW"


def test_one_failing_action_does_not_block_others(monkeypatch):
    # activate_card will fail (card already ACTIVE via CARD_ACTIVE fixture);
    # change_email should still succeed independently.
    monkeypatch.setattr(repository, "create_service_request", MagicMock(return_value=1))

    result = post_services_service.execute_actions(
        make_request(
            activate_card=True,
            change_email=True,
            new_email="new@example.com",
        )
    )

    assert result.results["activate_card"].success is False
    assert result.results["activate_card"].status == "FAILED"
    assert result.results["change_email"].success is True
    assert result.results["change_email"].status == "PENDING_REVIEW"


# --- API-level HTTP status ------------------------------------------------
# These don't need real token resolution - both checks happen before
# db_session is ever opened - so they're unaffected by the autouse mock
# above and exercise the real route/handler end to end.


def test_api_all_action_flags_false_returns_400(client):
    resp = client.post("/api/v1/post-services", json={"verification_token": "tok"})

    assert resp.status_code == 400


def test_api_missing_conditional_value_returns_400(client):
    resp = client.post(
        "/api/v1/post-services",
        json={"verification_token": "tok", "set_online_purchases": True},
    )

    assert resp.status_code == 400


def test_api_lost_card_succeeds_with_blank_string_unused_optional_fields(
    client, monkeypatch
):
    """Reproduces the reported HeyBreez payload shape end-to-end through
    the real FastAPI/Pydantic request-parsing boundary: unused optional
    fields sent as "" instead of omitted/null. Before the fix, FastAPI
    itself would reject this body with 422 before the route even ran."""
    monkeypatch.setattr(repository, "create_service_request", MagicMock(return_value=42))

    resp = client.post(
        "/api/v1/post-services",
        json={
            "verification_token": "tok",
            "lost_card": True,
            "online_purchases_enabled": "",
            "international_usage_enabled": "",
            "new_spending_limit": "",
            "new_atm_limit": "",
            "card_number": "",
            "request_reason": "",
            "new_address": "",
            "new_email": "",
            "new_mobile_number": "",
            "new_employment_details": "",
        },
    )

    assert resp.status_code == 200
    assert resp.json() == {
        "results": {
            "lost_card": {
                "success": True,
                "status": "PENDING_REVIEW",
                "request_id": 42,
                "reason": None,
            }
        }
    }
