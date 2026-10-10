"""SUFRA database engine.

Local development defaults to SQLite with WAL/busy timeout. Production can set
DATABASE_URL to PostgreSQL without changing application code. PostgreSQL uses
connection pooling + pre-ping for peak-demand resilience.
"""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import event, inspect, text
from sqlmodel import Session, SQLModel, create_engine

# NOVA_DB_PATH moves the SQLite file off the code directory: a hosted deploy
# keeps it on a persistent volume, where a redeploy cannot replace it.
DB_PATH = Path(os.getenv("NOVA_DB_PATH", "").strip()
               or Path(__file__).resolve().parent.parent / "nova.db")
_env_url = os.getenv("DATABASE_URL", "").strip()
if _env_url.startswith("postgres://"):
    _env_url = "postgresql+psycopg://" + _env_url[len("postgres://"):]
elif _env_url.startswith("postgresql://") and "+" not in _env_url.split("://", 1)[0]:
    _env_url = "postgresql+psycopg://" + _env_url[len("postgresql://"):]
DB_URL = _env_url or f"sqlite:///{DB_PATH}"
IS_SQLITE = DB_URL.startswith("sqlite")

kwargs = {"echo": False, "pool_pre_ping": True}
if IS_SQLITE:
    kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
else:
    kwargs.update({
        "pool_size": int(os.getenv("DB_POOL_SIZE", "10")),
        "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "20")),
        "pool_recycle": int(os.getenv("DB_POOL_RECYCLE", "1800")),
        "pool_timeout": int(os.getenv("DB_POOL_TIMEOUT", "30")),
    })
engine = create_engine(DB_URL, **kwargs)

if IS_SQLITE:
    @event.listens_for(engine, "connect")
    def _sqlite_reliability(dbapi_connection, _):
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA busy_timeout=10000")
        cur.close()


def create_db() -> None:
    SQLModel.metadata.create_all(engine)
    # Existing databases need the additive translation field before any router
    # loads Ingredient (create_all alone does not add columns to old tables).
    with engine.begin() as conn:
        schema = inspect(conn)
        if schema.has_table("ingredient") and "name_ru" not in {c["name"] for c in schema.get_columns("ingredient")}:
            conn.execute(text("ALTER TABLE ingredient ADD COLUMN name_ru TEXT NOT NULL DEFAULT ''"))


def get_session() -> Session:
    return Session(engine)
