# screens/rubrics/rubrics_schema.py
"""
Rubrics Schema (Definitions Only).
Designed to support Academic Year (AY) rollover and Degree/Program scoping.

1. rubric_criteria_catalog: Timeless definitions (Global or Degree-specific).
2. rubric_configs: AY-specific settings linked to Subject Offerings.
"""

from __future__ import annotations
from sqlalchemy import text as sa_text
from sqlalchemy.engine import Engine
import logging

# Schema Registry Registration
try:
    from core.schema_registry import register
except ImportError:
    def register(func):
        return func

logger = logging.getLogger(__name__)


def _exec(conn, sql: str, params: dict = None):
    """Execute SQL with parameters."""
    return conn.execute(sa_text(sql), params or {})

def _has_column(conn, table: str, col: str) -> bool:
    """Helper to check if a column exists."""
    cursor = conn.execute(sa_text(f"PRAGMA table_info({table})"))
    return any(row[1] == col for row in cursor.fetchall())


@register
def install_rubrics_schema(engine: Engine):
    """
    Install tables for Rubric Definitions.
    """
    logger.info("Installing Rubrics schema (Definitions Only)...")
    
    with engine.begin() as conn:
        
        # ========================================================
        # 1. GLOBAL CRITERIA CATALOG (Timeless)
        # ========================================================
        # These are the "Master Buckets" (e.g., Content, Expression).
        # They do NOT reset every year. They persist so you can analyze 
        # "Content" scores across 5 years of data.
        # They are scoped by Degree/Program/Branch to allow variations.
        _exec(conn, """
        CREATE TABLE IF NOT EXISTS rubric_criteria_catalog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            
            -- The unique identifier for the category
            key TEXT NOT NULL,       -- e.g., 'content_barch'
            label TEXT NOT NULL,     -- e.g., 'Content'
            description TEXT,
            
            -- Scope: Links to your degrees/programs schemas
            -- If NULL, it applies to the whole institution.
            degree_code TEXT,        -- REFERENCES degrees(code)
            program_code TEXT,       -- REFERENCES programs(program_code)
            branch_code TEXT,        -- REFERENCES branches(branch_code)
            
            active INTEGER NOT NULL DEFAULT 1,
            
            -- Audit
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME,
            
            -- Ensure we don't have duplicate keys within the same scope
            UNIQUE(key, degree_code, program_code, branch_code)
        )
        """)
        
        # ========================================================
        # 2. RUBRIC CONFIGURATIONS (AY-Specific)
        # ========================================================
        # This dictates IF rubrics are enabled for a specific subject in a specific AY.
        # Since 'offering_id' comes from 'subject_offerings' (which has 'ay_label'),
        # this table is inherently AY-based.
        #
        # TO COPY FROM AY to AY:
        # You simply read the row for the old offering_id and INSERT a new row
        # for the new offering_id.
        _exec(conn, """
        CREATE TABLE IF NOT EXISTS rubric_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            
            -- Links to a specific Subject Offering (which is tied to an AY)
            offering_id INTEGER NOT NULL,
            
            -- Policy Settings (To be copied forward)
            co_linking_enabled INTEGER NOT NULL DEFAULT 0,
            normalization_enabled INTEGER NOT NULL DEFAULT 1,
            visible_to_students INTEGER NOT NULL DEFAULT 1,
            
            -- Traceability for AY Copying
            copied_from_config_id INTEGER,  -- Links to previous year's config ID
            
            -- Status
            status TEXT NOT NULL DEFAULT 'draft',
            is_locked INTEGER NOT NULL DEFAULT 0,
            locked_reason TEXT,
            
            -- Audit
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            created_by TEXT,
            updated_at DATETIME,
            updated_by TEXT,
            
            UNIQUE(offering_id),
            FOREIGN KEY(offering_id) REFERENCES subject_offerings(id) ON DELETE CASCADE
        )
        """)
        
        # ========================================================
        # 3. AUDIT TRAIL
        # ========================================================
        _exec(conn, """
        CREATE TABLE IF NOT EXISTS rubrics_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            occurred_at_utc DATETIME DEFAULT CURRENT_TIMESTAMP,
            rubric_config_id INTEGER,
            offering_id INTEGER,
            scope TEXT,
            action TEXT NOT NULL,
            note TEXT,
            changed_fields TEXT,
            actor_id TEXT,
            actor_role TEXT,
            operation TEXT,
            reason TEXT,
            source TEXT
        )
        """)
        
        # ========================================================
        # 4. VERSIONING
        # ========================================================
        _exec(conn, """
        CREATE TABLE IF NOT EXISTS version_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            entity_type TEXT NOT NULL,
            entity_id INTEGER NOT NULL,
            snapshot_reason TEXT,
            actor TEXT,
            snapshot_data TEXT, -- JSON blob
            version_number INTEGER
        )
        """)
        
        # --- MIGRATION CHECKS (For existing databases) ---
        # Ensure columns exist if table was already created
        if not _has_column(conn, "rubric_criteria_catalog", "degree_code"):
            _exec(conn, "ALTER TABLE rubric_criteria_catalog ADD COLUMN degree_code TEXT")
            _exec(conn, "ALTER TABLE rubric_criteria_catalog ADD COLUMN program_code TEXT")
            _exec(conn, "ALTER TABLE rubric_criteria_catalog ADD COLUMN branch_code TEXT")
            logger.info("Migrated rubric_criteria_catalog: Added scope columns")
            
        if not _has_column(conn, "rubric_configs", "copied_from_config_id"):
            _exec(conn, "ALTER TABLE rubric_configs ADD COLUMN copied_from_config_id INTEGER")
            logger.info("Migrated rubric_configs: Added copy tracking column")

        logger.info("✓ Installed rubrics_schema (Definitions Only)")
