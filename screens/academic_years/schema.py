# screens/academic_years/schema.py
from __future__ import annotations
from sqlalchemy import text as sa_text
from sqlalchemy.engine import Engine
import json, datetime

def _exec(conn, sql: str, params: dict | None = None):
    conn.execute(sa_text(sql), params or {})

def install_academic_years(engine: Engine):
    with engine.begin() as conn:
        _exec(conn, """
        CREATE TABLE IF NOT EXISTS academic_years(
          ay_code   TEXT PRIMARY KEY COLLATE NOCASE,
          start_date TEXT NOT NULL,
          end_date   TEXT NOT NULL,
          status     TEXT NOT NULL DEFAULT 'planned' CHECK(status IN ('planned','open','closed')),
          created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
          updated_at DATETIME
        );""")
        _exec(conn, "CREATE UNIQUE INDEX IF NOT EXISTS uq_ay_code ON academic_years(ay_code)")
        _exec(conn, "CREATE INDEX IF NOT EXISTS ix_ay_status ON academic_years(status)")
        _exec(conn, "CREATE INDEX IF NOT EXISTS ix_ay_start_date ON academic_years(start_date)")

def install_ay_audit(engine: Engine):
    with engine.begin() as conn:
        _exec(conn, """
        CREATE TABLE IF NOT EXISTS academic_years_audit(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          ay_code TEXT NOT NULL,
          action  TEXT NOT NULL,
          note    TEXT,
          changed_fields TEXT,
          actor   TEXT,
          at DATETIME DEFAULT CURRENT_TIMESTAMP
        );""")
        _exec(conn, "CREATE INDEX IF NOT EXISTS ix_ay_audit_code ON academic_years_audit(ay_code)")
        _exec(conn, "CREATE INDEX IF NOT EXISTS ix_ay_audit_at ON academic_years_audit(at)")

def install_app_settings(engine: Engine):
    with engine.begin() as conn:
        _exec(conn, """
        CREATE TABLE IF NOT EXISTS app_settings(
          key TEXT PRIMARY KEY,
          value TEXT
        );""")

def install_batch_term_dates(engine: Engine):
    """
    Direct term dates for each batch/year/term.
    """
    with engine.begin() as conn:
        _exec(conn, """
        CREATE TABLE IF NOT EXISTS batch_term_dates(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          degree_code TEXT NOT NULL COLLATE NOCASE,
          batch_code TEXT NOT NULL COLLATE NOCASE,
          ay_code TEXT NOT NULL COLLATE NOCASE,
          year_of_study INTEGER NOT NULL,
          term_number INTEGER NOT NULL,
          term_label TEXT NOT NULL,
          start_date TEXT NOT NULL,
          end_date TEXT NOT NULL,
          created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
          updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(degree_code, batch_code, ay_code, year_of_study, term_number)
        );""")
        _exec(conn, """
        CREATE INDEX IF NOT EXISTS ix_batch_term_dates_lookup 
        ON batch_term_dates(degree_code, batch_code, ay_code)
        """)
        _exec(conn, """
        CREATE INDEX IF NOT EXISTS ix_batch_term_dates_year 
        ON batch_term_dates(degree_code, batch_code, ay_code, year_of_study)
        """)

def install_batch_term_dates_audit(engine: Engine):
    """Audit trail for term date changes."""
    with engine.begin() as conn:
        _exec(conn, """
        CREATE TABLE IF NOT EXISTS batch_term_dates_audit(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          batch_term_id INTEGER NOT NULL,
          action TEXT NOT NULL,
          actor TEXT,
          note TEXT,
          changed_fields TEXT,
          at DATETIME DEFAULT CURRENT_TIMESTAMP
        );""")
        _exec(conn, "CREATE INDEX IF NOT EXISTS ix_batch_term_audit_id ON batch_term_dates_audit(batch_term_id)")
        _exec(conn, "CREATE INDEX IF NOT EXISTS ix_batch_term_audit_at ON batch_term_dates_audit(at)")

def install_all(engine: Engine):
    """Install all academic year tables."""
    install_academic_years(engine)
    install_ay_audit(engine)
    install_app_settings(engine)
    install_batch_term_dates(engine)
    install_batch_term_dates_audit(engine)
