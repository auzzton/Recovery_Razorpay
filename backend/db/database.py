"""
database.py — Dual-Mode Database Adapter
=========================================
Supports two backends transparently:

  PostgreSQL (production / demo)
  ──────────────────────────────
  Set DATABASE_URL to a valid connection string, e.g.:
    postgresql://user:password@host:5432/recovery_os
  The adapter uses psycopg2 and executes schema.sql verbatim —
  SERIAL PRIMARY KEY, partial WHERE indexes, REFERENCES — all work natively.

  SQLite (local development / CI without Postgres)
  ─────────────────────────────────────────────────
  Leave DATABASE_URL unset.
  The adapter rewrites schema.sql at load time:
    SERIAL PRIMARY KEY  →  INTEGER PRIMARY KEY
    WHERE is_terminal … →  (partial index clause stripped, unsupported in SQLite)
  This keeps a single schema.sql as the canonical PostgreSQL definition.

Usage
─────
  from backend.db.database import get_connection, dict_from_row, init_db, DB_BACKEND, PLACEHOLDER

  DB_BACKEND  →  "postgresql" | "sqlite"
"""

import os
import json
import logging
import re
import sqlite3
from datetime import datetime

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────
DATABASE_URL = os.environ.get("DATABASE_URL")  # e.g. postgresql://user:pw@host/db
DB_PATH      = os.path.join(os.path.dirname(__file__), "recovery_os.db")
SCHEMA_PATH  = os.path.join(os.path.dirname(__file__), "schema.sql")

DB_BACKEND  = "postgresql" if DATABASE_URL else "sqlite"
PLACEHOLDER = "%s"         if DB_BACKEND == "postgresql" else "?"
logger.info("[DB] Backend: %s  |  SQL placeholder: %s", DB_BACKEND, PLACEHOLDER)


# ── Connection factory ─────────────────────────────────────────────────────────

def get_connection():
    """
    Return a live database connection.

    PostgreSQL: psycopg2 connection with RealDictCursor so rows behave like
                dicts — identical to the sqlite3.Row interface used by SQLite.
    SQLite:     sqlite3 connection with Row factory.
    """
    if DB_BACKEND == "postgresql":
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = False
        # Use RealDictCursor so rows support column-name access like sqlite3.Row
        conn._cursor_factory = psycopg2.extras.RealDictCursor
        return conn
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn


def _cursor(conn):
    """Return a cursor appropriate for the current backend."""
    if DB_BACKEND == "postgresql":
        import psycopg2.extras
        return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    return conn.cursor()


# ── Schema initialisation ──────────────────────────────────────────────────────

def _sqlite_compat_schema(sql: str) -> str:
    """
    Rewrite PostgreSQL-only DDL so SQLite can execute it.
    Only applied when DB_BACKEND == 'sqlite'.
    Changes made:
      • SERIAL PRIMARY KEY  →  INTEGER PRIMARY KEY
      • Partial index WHERE clause  →  removed (SQLite supports partial indexes
        but not with boolean column expressions using FALSE keyword in all versions)
    """
    # SERIAL → INTEGER (SQLite uses INTEGER PRIMARY KEY for autoincrement)
    sql = re.sub(r'\bSERIAL\b', 'INTEGER', sql, flags=re.IGNORECASE)
    # Strip partial index WHERE clause (simplest safe approach)
    sql = re.sub(
        r'(CREATE\s+UNIQUE\s+INDEX\b.*?)\s+WHERE\s+[^\n;]+',
        r'\1',
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return sql


def _migrate_sqlite(conn):
    """
    Apply any missing column migrations to an *existing* SQLite file.
    SQLite does not support ADD COLUMN IF NOT EXISTS, so we probe first.
    No-op on PostgreSQL (migrations handled by schema execution or Alembic).
    """
    if DB_BACKEND != "sqlite":
        return
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(at_risk_events)")
    existing_cols = {row["name"] for row in cursor.fetchall()}
    migrations = [
        ("razorpay_payment_id", "ALTER TABLE at_risk_events ADD COLUMN razorpay_payment_id VARCHAR(64)"),
        ("payment_captured",    "ALTER TABLE at_risk_events ADD COLUMN payment_captured BOOLEAN DEFAULT FALSE"),
    ]
    for col_name, sql in migrations:
        if col_name not in existing_cols:
            cursor.execute(sql)
    conn.commit()


def init_db():
    """
    Initialise the database schema idempotently.

    PostgreSQL: executes schema.sql verbatim using psycopg2.
    SQLite:     rewrites SERIAL → INTEGER, strips partial-index WHERE clauses,
                then feeds the patched SQL to sqlite3.executescript().
    """
    with open(SCHEMA_PATH, "r") as f:
        raw_schema = f.read()

    conn = get_connection()
    try:
        if DB_BACKEND == "postgresql":
            cur = _cursor(conn)
            # Split on semicolons and execute each statement individually
            for stmt in raw_schema.split(";"):
                stmt = stmt.strip()
                if stmt:
                    try:
                        cur.execute(stmt)
                    except Exception as exc:  # noqa: BLE001
                        # IF NOT EXISTS guarantees idempotency; log & continue
                        logger.debug("[DB] Schema stmt skipped (%s): %.80s", exc, stmt)
                        conn.rollback()
            conn.commit()
            logger.info("[DB] PostgreSQL schema initialised from schema.sql (verbatim).")
        else:
            sqlite_schema = _sqlite_compat_schema(raw_schema)
            cur = conn.cursor()
            cur.executescript(sqlite_schema)
            conn.commit()
            _migrate_sqlite(conn)
            logger.info("[DB] SQLite schema initialised (SERIAL rewritten to INTEGER).")
    finally:
        conn.close()


# ── Row serialisation ──────────────────────────────────────────────────────────

def dict_from_row(row):
    """Convert a database row to a plain dict regardless of backend."""
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    return dict(row)


# ── Auto-init on import ────────────────────────────────────────────────────────
init_db()
