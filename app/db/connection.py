import logging
from contextlib import contextmanager
from typing import Iterator

import oracledb

from app.config import settings
from app.utils.exceptions import DatabaseUnavailableError

logger = logging.getLogger(__name__)

_pool: oracledb.ConnectionPool | None = None


def init_pool() -> None:
    """Create the Oracle connection pool. Safe to call multiple times."""
    global _pool
    if _pool is not None:
        return
    _pool = oracledb.create_pool(
        user=settings.db_user,
        password=settings.db_password,
        dsn=settings.db_dsn,
        min=1,
        max=5,
        increment=1,
    )
    logger.info("Oracle connection pool initialized (dsn=%s)", settings.db_dsn)


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close(force=True)
        _pool = None
        logger.info("Oracle connection pool closed")


@contextmanager
def get_connection() -> Iterator[oracledb.Connection]:
    """Borrow a connection from the pool, returning it when done."""
    if _pool is None:
        init_pool()
    assert _pool is not None
    conn = _pool.acquire()
    try:
        yield conn
    finally:
        _pool.release(conn)


@contextmanager
def db_session() -> Iterator[oracledb.Connection]:
    """Borrow a connection and convert any raw Oracle error into a safe,
    non-leaking DatabaseUnavailableError. Preferred over get_connection()
    directly for new service code so every caller doesn't repeat the same
    try/except oracledb.Error boilerplate.
    """
    try:
        with get_connection() as conn:
            yield conn
    except oracledb.Error:
        logger.exception("Database error")
        raise DatabaseUnavailableError() from None
