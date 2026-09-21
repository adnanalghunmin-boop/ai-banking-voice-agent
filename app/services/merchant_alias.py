"""Deterministic merchant/type alias resolution for verification.

The LLM must never decide whether two merchant names are "the same" (e.g.
a customer speaking a merchant's Arabic name against a database record
stored in Latin script). Instead, the small MERCHANT_ALIASES table maps
known alternate spellings - different scripts, casing, punctuation - to one
canonical value, and resolution here is a plain dictionary lookup after the
same deterministic normalization used everywhere else in verification.
Nothing here is fuzzy, ML-based, or LLM-driven.
"""

import oracledb

from app.db import repository


def _normalize(value: str) -> str:
    # str.lower() is a no-op on Arabic (no letter case), so this is safe to
    # apply unconditionally rather than needing to detect the script first.
    return " ".join(value.strip().lower().split())


def build_alias_map(conn: oracledb.Connection) -> dict[str, str]:
    """Load active aliases once per verification attempt, keyed by their
    normalized spelling, so every string compared during that attempt is
    resolved against one consistent snapshot."""
    return {
        _normalize(alias_value): canonical_value.strip().upper()
        for alias_value, canonical_value in repository.get_active_merchant_aliases(
            conn
        )
    }


def resolve(value: str, alias_map: dict[str, str]) -> str:
    """Resolve a merchant/type string to its canonical form via alias_map.

    Falls back to the normalized raw value itself when no alias exists, so
    merchants/types with no configured alias keep matching exactly as they
    did before this mechanism existed (case-insensitive, whitespace-
    normalized string equality).
    """
    normalized = _normalize(value)
    return alias_map.get(normalized, normalized)
