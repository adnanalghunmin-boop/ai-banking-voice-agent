import logging

from fastapi import APIRouter

from app.db.connection import get_connection
from app.utils.exceptions import DatabaseUnavailableError

import oracledb

logger = logging.getLogger(__name__)

router = APIRouter()
database_router = APIRouter(prefix="/api/v1/database", tags=["database"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@database_router.get("/health")
def database_health() -> dict[str, str]:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM dual")
                cur.fetchone()
        return {"status": "ok"}
    except oracledb.Error:
        logger.exception("Database health check failed")
        raise DatabaseUnavailableError() from None
