# schemas/schedule_schema.py
"""
Subject Scheduling Schema (Slide 28) - Enhanced
- Added 'status' for Draft/Publish workflow.
"""
from __future__ import annotations
from sqlalchemy import text as sa_text
from sqlalchemy.engine import Engine
from core.schema_registry import register
import logging

logger = logging.getLogger(__name__)

def _exec(conn, sql: str, params: dict = None):
    return conn.execute(sa_text(sql), params or {})

def install_schedule_sessions(engine: Engine):
    with engine.begin() as conn:
        _exec(conn, """
        CREATE TABLE IF NOT EXISTS schedule_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_id INTEGER NOT NULL,
            session_date DATE NOT NULL,
            day_of_week TEXT,
            slot_signature TEXT NOT NULL,
            start_period INTEGER DEFAULT 1,
            span_periods INTEGER DEFAULT 1,
            extended_afternoon INTEGER DEFAULT 0,
            
            -- Typed Units
            l_units INTEGER DEFAULT 0,
            t_units INTEGER DEFAULT 0,
            p_units INTEGER DEFAULT 0,
            s_units INTEGER DEFAULT 0,
            
            kind TEXT DEFAULT 'mixed',
            lecture_notes TEXT,
            studio_notes TEXT,
            
            assignment_id INTEGER,
            due_date DATE,
            completed TEXT DEFAULT '',
            
            -- Organization
            batch_year INTEGER,
            semester INTEGER,
            branch_id INTEGER,
            
            -- Workflow Status (New)
            status TEXT DEFAULT 'draft', -- 'draft', 'published'
            
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            created_by TEXT,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_by TEXT,
            
            FOREIGN KEY (subject_id) REFERENCES subject_offerings(id),
            FOREIGN KEY (assignment_id) REFERENCES assignments(id) ON DELETE SET NULL
        )
        """)
        _exec(conn, "CREATE INDEX IF NOT EXISTS ix_sched_subject_date ON schedule_sessions(subject_id, session_date)")

def install_schedule_audit(engine: Engine):
    with engine.begin() as conn:
        _exec(conn, """
        CREATE TABLE IF NOT EXISTS schedule_sessions_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER,
            action TEXT,
            actor TEXT,
            occurred_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)

def install_schedule_triggers(engine: Engine):
    with engine.begin() as conn:
        _exec(conn, """
        CREATE TRIGGER IF NOT EXISTS trg_schedule_updated_at
        AFTER UPDATE ON schedule_sessions
        BEGIN
            UPDATE schedule_sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
        END;
        """)

@register("schedule_sessions")
def install_schedule_schema(engine: Engine):
    install_schedule_sessions(engine)
    install_schedule_audit(engine)
    install_schedule_triggers(engine)
