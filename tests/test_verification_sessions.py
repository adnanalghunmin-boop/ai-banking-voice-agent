import re
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.db import repository
from app.services import verification_sessions
from app.utils.exceptions import InvalidSessionError


def _future(minutes: int = 10) -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=minutes)


def _past(minutes: int = 1) -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=minutes)


def test_create_session_generates_unpredictable_tokens(monkeypatch):
    monkeypatch.setattr(
        repository, "create_verification_session", MagicMock(return_value=1)
    )

    token1 = verification_sessions.create_session(MagicMock(), customer_id=1, account_id=1)
    token2 = verification_sessions.create_session(MagicMock(), customer_id=1, account_id=1)

    assert token1 != token2
    assert len(token1) >= 32
    assert re.fullmatch(r"[A-Za-z0-9_-]+", token1)


def test_create_session_only_persists_hash_not_raw_token(monkeypatch):
    captured = {}

    def fake_create(conn, token_hash, customer_id, account_id, expires_at):
        captured["token_hash"] = token_hash
        captured["customer_id"] = customer_id
        captured["account_id"] = account_id
        captured["expires_at"] = expires_at
        return 1

    monkeypatch.setattr(repository, "create_verification_session", fake_create)

    raw_token = verification_sessions.create_session(MagicMock(), customer_id=1, account_id=1)

    assert captured["token_hash"] != raw_token
    assert len(captured["token_hash"]) == 64  # sha256 hex digest length
    assert captured["customer_id"] == 1
    assert captured["account_id"] == 1
    assert captured["expires_at"] > datetime.now(timezone.utc).replace(tzinfo=None)


def test_resolve_session_returns_correct_identity(monkeypatch):
    session = {
        "session_id": 1,
        "customer_id": 1,
        "account_id": 1,
        "expires_at": _future(),
        "active": True,
    }
    monkeypatch.setattr(
        repository, "get_verification_session_by_token_hash", lambda conn, h: session
    )

    ident = verification_sessions.resolve_session(MagicMock(), "some-token")

    assert ident == {"customer_id": 1, "account_id": 1}


def test_resolve_session_missing_token_rejected():
    with pytest.raises(InvalidSessionError):
        verification_sessions.resolve_session(MagicMock(), None)
    with pytest.raises(InvalidSessionError):
        verification_sessions.resolve_session(MagicMock(), "")


def test_resolve_session_unknown_token_rejected(monkeypatch):
    monkeypatch.setattr(
        repository, "get_verification_session_by_token_hash", lambda conn, h: None
    )

    with pytest.raises(InvalidSessionError):
        verification_sessions.resolve_session(MagicMock(), "unknown-token")


def test_resolve_session_expired_token_rejected(monkeypatch):
    session = {
        "session_id": 1,
        "customer_id": 1,
        "account_id": 1,
        "expires_at": _past(),
        "active": True,
    }
    monkeypatch.setattr(
        repository, "get_verification_session_by_token_hash", lambda conn, h: session
    )

    with pytest.raises(InvalidSessionError):
        verification_sessions.resolve_session(MagicMock(), "expired-token")


def test_resolve_session_inactive_token_rejected(monkeypatch):
    session = {
        "session_id": 1,
        "customer_id": 1,
        "account_id": 1,
        "expires_at": _future(),
        "active": False,
    }
    monkeypatch.setattr(
        repository, "get_verification_session_by_token_hash", lambda conn, h: session
    )

    with pytest.raises(InvalidSessionError):
        verification_sessions.resolve_session(MagicMock(), "inactive-token")


def test_invalid_session_error_message_is_generic():
    assert InvalidSessionError().message == "Invalid or expired verification session"
