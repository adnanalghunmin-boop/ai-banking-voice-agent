import oracledb
import pytest

from app.db import connection
from app.utils.exceptions import DatabaseUnavailableError


class _RaisingConnection:
    def __enter__(self):
        raise oracledb.Error("simulated connection failure")

    def __exit__(self, exc_type, exc, tb):
        return False


def test_db_session_wraps_oracle_errors_safely(monkeypatch):
    monkeypatch.setattr(connection, "get_connection", lambda: _RaisingConnection())

    with pytest.raises(DatabaseUnavailableError):
        with connection.db_session():
            pass
