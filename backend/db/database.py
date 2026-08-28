import sqlite3
import os
import json
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "recovery_os.db")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _migrate(conn):
    """
    Apply any missing column migrations to an existing database.
    SQLite does not support ADD COLUMN IF NOT EXISTS, so we probe first.
    """
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
    conn = get_connection()
    cursor = conn.cursor()

    # Read and apply schema (idempotent via CREATE TABLE IF NOT EXISTS)
    with open(SCHEMA_PATH, "r") as f:
        schema_sql = f.read()
    cursor.executescript(schema_sql)
    conn.commit()

    # Apply live column migrations for existing DB files
    _migrate(conn)
    conn.close()

def dict_from_row(row):
    if row is None:
        return None
    return dict(row)

init_db()
