# schemas/holidays_schema.py
"""
Holidays & Academic Calendar Schema (Slide 26).
Manages institution-wide and scoped holidays (Degree/Program/Branch).
Includes support for 'Working Saturday' overrides.
"""

from __future__ import annotations
from sqlalchemy import text as sa_text
from sqlalchemy.engine import Engine
from core.schema_registry import register
import logging

logger = logging.getLogger(__name__)

def _exec(conn, sql: str, params: dict = None):
    return conn.execute(sa_text(sql), params or {})

# ===========================================================================
# HOLIDAYS TABLE
# ===========================================================================

def install_holidays_table(engine: Engine):
    """
    Creates the main holidays table with scope hierarchy support.
    """
    with engine.begin() as conn:
        _exec(conn, """
        CREATE TABLE IF NOT EXISTS holidays (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            
            -- Core details
            date DATE NOT NULL,
            title TEXT NOT NULL,
            
            -- Scope Hierarchy (Enum emulation)
            scope_level TEXT NOT NULL DEFAULT 'institution' 
                CHECK (scope_level IN ('institution', 'degree', 'program', 'branch')),
            
            -- Scope Links (Nullable based on scope_level)
            degree_code TEXT,
            program_code TEXT,
            branch_code TEXT,
            
            -- Optional link to specific Academic Year
            ay_code TEXT,
            
            -- Special Flags
            is_working_saturday INTEGER NOT NULL DEFAULT 0, -- 0=False, 1=True
            
            -- Metadata
            notes TEXT,
            source TEXT DEFAULT 'ui' CHECK (source IN ('ui', 'import', 'api')),
            
            -- Audit fields
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            created_by TEXT,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_by TEXT,
            
            -- Foreign Keys
            FOREIGN KEY (degree_code) REFERENCES degrees(code) ON DELETE CASCADE,
            FOREIGN KEY (program_code) REFERENCES programs(program_code) ON DELETE CASCADE,
            FOREIGN KEY (branch_code) REFERENCES branches(branch_code) ON DELETE CASCADE,
            FOREIGN KEY (ay_code) REFERENCES academic_years(ay_code) ON DELETE SET NULL,
            
            -- Data Integrity Constraints
            -- 1. Uniqueness: A specific scope cannot have two entries for the same date
            UNIQUE(date, scope_level, degree_code, program_code, branch_code),
            
            -- 2. Scope Integrity (If Branch, need Program/Degree; If Program, need Degree)
            -- Note: SQLite checking of other columns in CHECK is valid
            CHECK (
                (scope_level = 'institution' AND degree_code IS NULL) OR
                (scope_level = 'degree' AND degree_code IS NOT NULL AND program_code IS NULL) OR
                (scope_level = 'program' AND degree_code IS NOT NULL AND program_code IS NOT NULL AND branch_code IS NULL) OR
                (scope_level = 'branch' AND degree_code IS NOT NULL AND program_code IS NOT NULL AND branch_code IS NOT NULL)
            )
        )
        """)
        
        # Indexes for performance (Calendar lookups are date-heavy)
        _exec(conn, "CREATE INDEX IF NOT EXISTS ix_holidays_date ON holidays(date)")
        _exec(conn, "CREATE INDEX IF NOT EXISTS ix_holidays_scope ON holidays(scope_level, degree_code, branch_code)")
        _exec(conn, "CREATE INDEX IF NOT EXISTS ix_holidays_ay ON holidays(ay_code)")

        logger.info("✓ Installed holidays table")

# ===========================================================================
# AUDIT TABLE
# ===========================================================================

def install_holidays_audit(engine: Engine):
    """
    Audit trail for holiday changes (required for step-up auth & rollback).
    """
    with engine.begin() as conn:
        _exec(conn, """
        CREATE TABLE IF NOT EXISTS holidays_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            holiday_id INTEGER NOT NULL,
            
            -- Snapshot of state
            date DATE,
            title TEXT,
            scope_tuple TEXT, -- "institution" or "branch:B-ARCH|..."
            
            -- Action
            action TEXT NOT NULL, -- create, update, delete, bulk_import
            changed_fields TEXT,  -- JSON blob
            
            -- Actor
            actor TEXT,
            actor_role TEXT,
            
            -- Context
            reason TEXT,
            step_up_performed INTEGER DEFAULT 0,
            source TEXT,
            
            occurred_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        _exec(conn, "CREATE INDEX IF NOT EXISTS ix_holidays_audit_id ON holidays_audit(holiday_id)")
        _exec(conn, "CREATE INDEX IF NOT EXISTS ix_holidays_audit_date ON holidays_audit(occurred_at)")

        logger.info("✓ Installed holidays_audit table")

# ===========================================================================
# TRIGGERS
# ===========================================================================

def install_holidays_triggers(engine: Engine):
    with engine.begin() as conn:
        # Auto-update updated_at
        _exec(conn, """
        CREATE TRIGGER IF NOT EXISTS trg_holidays_updated_at
        AFTER UPDATE ON holidays
        BEGIN
            UPDATE holidays 
            SET updated_at = CURRENT_TIMESTAMP 
            WHERE id = NEW.id;
        END;
        """)
        
        logger.info("✓ Installed holidays triggers")

# ===========================================================================
# REGISTRY ENTRY POINT
# ===========================================================================

@register("holidays")
def install_holidays_schema(engine: Engine):
    """
    Install Holidays & Academic Calendar schema.
    """
    logger.info("Installing Holidays schema...")
    try:
        install_holidays_table(engine)
        install_holidays_audit(engine)
        install_holidays_triggers(engine)
        return True
    except Exception as e:
        logger.error(f"❌ Holidays schema installation failed: {e}", exc_info=True)
        return False
