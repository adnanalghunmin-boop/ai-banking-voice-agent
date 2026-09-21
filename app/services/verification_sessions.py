"""Opaque, short-lived verification tokens.

A successful POST /api/v1/verification/verify issues one of these tokens.
It represents a single verified phone-call context (one customer_id/account_id
pairing) for up to 30 minutes. Every account-scoped action from then on
authenticates with this token instead of asserting customer_id/account_id
directly - see app/models/common.py:TokenContext and app/services/identity.py.

Only a SHA-256 hash of the token is ever persisted (VERIFICATION_SESSIONS.
token_hash) - the raw token is returned to the caller exactly once, at
issuance, and is never stored or logged anywhere.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import oracledb

from app.db import repository
from app.utils.exceptions import InvalidSessionError

TOKEN_ENTROPY_BYTES = 32  # secrets.token_urlsafe(32) -> 256 bits of entropy
SESSION_LIFETIME = timedelta(minutes=30)


def _utcnow() -> datetime:
    # Naive UTC, to match the naive TIMESTAMP(6) columns Oracle returns/accepts.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def create_session(conn: oracledb.Connection, customer_id: int, account_id: int) -> str:
    """Issue a new token for a just-verified customer/account pair and
    persist only its hash. Returns the raw token - the only time it exists
    outside the caller's memory."""
    raw_token = secrets.token_urlsafe(TOKEN_ENTROPY_BYTES)
    token_hash = _hash_token(raw_token)
    expires_at = _utcnow() + SESSION_LIFETIME
    repository.create_verification_session(
        conn, token_hash, customer_id, account_id, expires_at
    )
    return raw_token


def resolve_session(conn: oracledb.Connection, raw_token: str | None) -> dict[str, int]:
    """Resolve an opaque token to its verified {customer_id, account_id}.

    Raises InvalidSessionError - with the exact same generic message - for
    every failure case: missing token, unknown token, expired token, or a
    token that was deactivated. Callers can never learn which one it was.
    """
    if not raw_token:
        raise InvalidSessionError()

    token_hash = _hash_token(raw_token)
    session = repository.get_verification_session_by_token_hash(conn, token_hash)
    if session is None:
        raise InvalidSessionError()
    if not session["active"]:
        raise InvalidSessionError()
    if session["expires_at"] <= _utcnow():
        raise InvalidSessionError()

    return {"customer_id": session["customer_id"], "account_id": session["account_id"]}
