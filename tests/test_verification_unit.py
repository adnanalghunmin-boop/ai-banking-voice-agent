import contextlib
from decimal import Decimal
from unittest.mock import MagicMock

import oracledb
import pytest

from app.models.verification import VerificationRequest
from app.services import verification as verification_module
from app.utils.exceptions import DatabaseUnavailableError

CUSTOMER = {"customer_id": 1, "national_id": "9876543210"}
ACCOUNT = {"account_id": 1, "customer_id": 1, "account_number": "1002003001"}
OTHER_CUSTOMER_ACCOUNT = {
    "account_id": 2,
    "customer_id": 2,
    "account_number": "1002003002",
}
TRANSACTION = {
    "transaction_id": 1,
    "amount": Decimal("32.5"),
    "merchant_or_type": "Carrefour",
    "transaction_type": "CARD_PURCHASE",
}

# Mirrors the real MERCHANT_ALIASES seed data.
SEED_ALIASES = [
    ("Carrefour", "CARREFOUR"),
    ("carrefour", "CARREFOUR"),
    ("كارفور", "CARREFOUR"),
]


@pytest.fixture(autouse=True)
def patch_connection(monkeypatch):
    monkeypatch.setattr(
        verification_module,
        "get_connection",
        lambda: contextlib.nullcontext(MagicMock()),
    )


def make_request(**overrides):
    data = dict(
        national_id="9876543210",
        account_number="1002003001",
        last_transaction_amount=Decimal("32.5"),
        last_transaction_merchant_or_type="Carrefour",
    )
    data.update(overrides)
    return VerificationRequest(**data)


def _patch_repo(
    monkeypatch,
    customer=CUSTOMER,
    account=ACCOUNT,
    transaction=TRANSACTION,
    aliases=None,
):
    monkeypatch.setattr(
        verification_module.repository,
        "get_customer_by_national_id",
        lambda conn, nid: customer,
    )
    monkeypatch.setattr(
        verification_module.repository,
        "get_account_by_number",
        lambda conn, num: account,
    )
    monkeypatch.setattr(
        verification_module.repository,
        "get_latest_completed_transaction",
        lambda conn, aid: transaction,
    )
    monkeypatch.setattr(
        verification_module.repository,
        "get_active_merchant_aliases",
        lambda conn: aliases if aliases is not None else [],
    )


def test_successful_verification(monkeypatch):
    _patch_repo(monkeypatch)

    result = verification_module.verify_customer(make_request())

    assert result.verified is True
    assert result.customer_id == 1
    assert result.account_id == 1
    assert result.reason is None


def test_wrong_national_id(monkeypatch):
    _patch_repo(monkeypatch, customer=None)

    result = verification_module.verify_customer(
        make_request(national_id="0000000000")
    )

    assert result.verified is False
    assert result.customer_id is None
    assert result.account_id is None
    assert result.reason == "verification_failed"


def test_wrong_account_number(monkeypatch):
    _patch_repo(monkeypatch, account=None)

    result = verification_module.verify_customer(
        make_request(account_number="0000000000")
    )

    assert result.verified is False
    assert result.reason == "verification_failed"


def test_account_belongs_to_another_customer(monkeypatch):
    _patch_repo(monkeypatch, account=OTHER_CUSTOMER_ACCOUNT)

    result = verification_module.verify_customer(make_request())

    assert result.verified is False
    assert result.reason == "verification_failed"


def test_wrong_transaction_amount(monkeypatch):
    _patch_repo(monkeypatch)

    result = verification_module.verify_customer(
        make_request(last_transaction_amount=Decimal("99.99"))
    )

    assert result.verified is False
    assert result.reason == "verification_failed"


def test_wrong_merchant_or_type(monkeypatch):
    _patch_repo(monkeypatch)

    result = verification_module.verify_customer(
        make_request(last_transaction_merchant_or_type="Amazon")
    )

    assert result.verified is False
    assert result.reason == "verification_failed"


def test_case_insensitive_merchant_match(monkeypatch):
    _patch_repo(monkeypatch)

    result = verification_module.verify_customer(
        make_request(last_transaction_merchant_or_type="  CARREFOUR  ")
    )

    assert result.verified is True


def test_transaction_type_match_accepted(monkeypatch):
    _patch_repo(monkeypatch)

    result = verification_module.verify_customer(
        make_request(last_transaction_merchant_or_type="card_purchase")
    )

    assert result.verified is True


def test_no_completed_transactions(monkeypatch):
    _patch_repo(monkeypatch, transaction=None)

    result = verification_module.verify_customer(make_request())

    assert result.verified is False
    assert result.reason == "verification_failed"


def test_merchant_alias_exact_match(monkeypatch):
    _patch_repo(monkeypatch, aliases=SEED_ALIASES)

    result = verification_module.verify_customer(
        make_request(last_transaction_merchant_or_type="Carrefour")
    )

    assert result.verified is True


def test_merchant_alias_lowercase_match(monkeypatch):
    _patch_repo(monkeypatch, aliases=SEED_ALIASES)

    result = verification_module.verify_customer(
        make_request(last_transaction_merchant_or_type="carrefour")
    )

    assert result.verified is True


def test_merchant_alias_arabic_match(monkeypatch):
    # Customer says the merchant's Arabic name; Oracle stores "Carrefour".
    # Only resolvable via the alias table, not plain normalization.
    _patch_repo(monkeypatch, aliases=SEED_ALIASES)

    result = verification_module.verify_customer(
        make_request(last_transaction_merchant_or_type="كارفور")
    )

    assert result.verified is True
    assert result.customer_id == 1
    assert result.account_id == 1


def test_unrelated_arabic_merchant_fails(monkeypatch):
    # "دانوب" (Danube, a different retailer) has no alias to CARREFOUR and
    # doesn't match the stored value under plain normalization either.
    _patch_repo(monkeypatch, aliases=SEED_ALIASES)

    result = verification_module.verify_customer(
        make_request(last_transaction_merchant_or_type="دانوب")
    )

    assert result.verified is False
    assert result.reason == "verification_failed"


def test_amount_mismatch_still_fails_with_aliases_present(monkeypatch):
    _patch_repo(monkeypatch, aliases=SEED_ALIASES)

    result = verification_module.verify_customer(
        make_request(
            last_transaction_amount=Decimal("99.99"),
            last_transaction_merchant_or_type="كارفور",
        )
    )

    assert result.verified is False
    assert result.reason == "verification_failed"


def test_account_mismatch_still_fails_with_aliases_present(monkeypatch):
    _patch_repo(monkeypatch, account=OTHER_CUSTOMER_ACCOUNT, aliases=SEED_ALIASES)

    result = verification_module.verify_customer(
        make_request(last_transaction_merchant_or_type="كارفور")
    )

    assert result.verified is False
    assert result.reason == "verification_failed"


def test_transaction_type_match_still_works_with_aliases_present(monkeypatch):
    _patch_repo(monkeypatch, aliases=SEED_ALIASES)

    result = verification_module.verify_customer(
        make_request(last_transaction_merchant_or_type="card_purchase")
    )

    assert result.verified is True


def test_database_error_raises_safe_exception(monkeypatch):
    def raise_error(conn, nid):
        raise oracledb.Error("simulated failure")

    monkeypatch.setattr(
        verification_module.repository, "get_customer_by_national_id", raise_error
    )

    with pytest.raises(DatabaseUnavailableError):
        verification_module.verify_customer(make_request())
