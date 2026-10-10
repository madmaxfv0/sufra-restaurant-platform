"""A cross-process write lock for the one decision that must not race.

Two guests can click the same last free table in the same second, from two
different applications running as two different processes. An in-process
lock cannot help; a green button in the browser is not protection either.
SQLite's own BEGIN IMMEDIATE takes the database writer lock before we read,
so the conflict check and the insert that trusts it cannot interleave with
anybody else's.

PostgreSQL deployments do not need this: their default isolation plus the
uniqueness checks in the same transaction already serialise the write, so
the caller falls back to the ORM session there.
"""
from __future__ import annotations

import contextlib
import sqlite3

from .database import DB_PATH, IS_SQLITE


@contextlib.contextmanager
def immediate():
    """Yield a raw sqlite3 connection holding the writer lock, or None."""
    if not IS_SQLITE:
        yield None
        return
    con = sqlite3.connect(str(DB_PATH), timeout=30.0, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=15000")
    con.execute("BEGIN IMMEDIATE")
    try:
        yield con
        con.execute("COMMIT")
    except Exception:
        try:
            con.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        con.close()


SQL_TS = "%Y-%m-%d %H:%M:%S.%f"


def ts(dt) -> str:
    return dt.strftime(SQL_TS)


def parse_ts(value):
    from datetime import datetime
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip().replace("T", " ")
    for fmt in (SQL_TS, "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None
