from __future__ import annotations
from sqlalchemy import text as sa_text
from sqlalchemy.engine import Engine
from core.schema_registry import register
import logging

log = logging.getLogger(__name__)

def _exec(conn, sql):
    conn.execute(sa_text(sql))

@register
def install_weekly_distribution_schema(engine: Engine):
    """
    Master Schema for Weekly Planning & Timetabling.
    Includes Distribution, Timetable Slots, and Audit Trails.
    """
    with engine.begin() as conn:
        
        # =================================================================
        # 1. WEEKLY DISTRIBUTION (The "Skeleton" Plan)
        # =================================================================
        # Updated to include frequency and term-date fields per migration script
        _exec(conn, """
            CREATE TABLE IF NOT EXISTS weekly_subject_distribution (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                offering_id INTEGER NOT NULL,
                
                -- Hierarchy Context
                ay_label TEXT NOT NULL,
                degree_code TEXT NOT NULL,
                program_code TEXT,
                branch_code TEXT,
                year INTEGER NOT NULL,
                term INTEGER NOT NULL,
                division_code TEXT COLLATE NOCASE,

                subject_code TEXT NOT NULL,
                subject_type TEXT NOT NULL,

                -- Split Credits
                student_credits REAL DEFAULT 0,
                teaching_credits REAL DEFAULT 0,

                -- Weekly "Shape"
                mon_periods INTEGER DEFAULT 0,
                tue_periods INTEGER DEFAULT 0,
                wed_periods INTEGER DEFAULT 0,
                thu_periods INTEGER DEFAULT 0,
                fri_periods INTEGER DEFAULT 0,
                sat_periods INTEGER DEFAULT 0,

                -- Module Configuration (Enhanced Fields)
                duration_type TEXT DEFAULT 'full_term', -- 'full_term' or 'module'
                weekly_frequency INTEGER DEFAULT 1,     -- For full_term subjects
                is_module_override INTEGER DEFAULT 0,   -- 1 if user overrode auto-detection

                -- Dates
                module_start_date DATE,
                module_end_date DATE,
                term_start_date DATE,                   -- Snapshots term context
                term_end_date DATE,
                week_start INTEGER DEFAULT 1,
                week_end INTEGER DEFAULT 20,

                -- Flags
                is_all_day_elective_block INTEGER DEFAULT 0,
                extended_afternoon_days TEXT,

                -- Resources
                room_code TEXT,
                
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (offering_id) REFERENCES subject_offerings(id)
            )
        """)

        # Unique Plan per Subject per Division
        _exec(conn, """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_wsd_offering_div
            ON weekly_subject_distribution (offering_id, division_code)
        """)

        # =================================================================
        # 2. AUDIT TRAIL
        # =================================================================
        _exec(conn, """
            CREATE TABLE IF NOT EXISTS weekly_subject_distribution_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                distribution_id INTEGER DEFAULT 0,
                offering_id INTEGER DEFAULT 0,
                ay_label TEXT,
                degree_code TEXT,
                division_code TEXT,
                change_reason TEXT,
                changed_by TEXT,
                changed_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        _exec(conn, """
            CREATE INDEX IF NOT EXISTS idx_wsd_audit_context 
            ON weekly_subject_distribution_audit(degree_code, division_code, ay_label)
        """)

        # =================================================================
        # 3. NORMALIZED ASSIGNMENT (The "Timetable Slots")
        # =================================================================
        _exec(conn, """
            CREATE TABLE IF NOT EXISTS normalized_weekly_assignment (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ay_label TEXT NOT NULL,
                degree_code TEXT NOT NULL,
                program_code TEXT,
                branch_code TEXT,
                year INTEGER NOT NULL,
                term INTEGER NOT NULL,
                division_code TEXT,
                offering_id INTEGER NOT NULL,
                subject_code TEXT NOT NULL,
                subject_type TEXT NOT NULL,
                day_of_week INTEGER NOT NULL,
                period_index INTEGER NOT NULL,
                faculty_ids TEXT,
                room_code TEXT,
                is_override_in_charge INTEGER DEFAULT 0,
                is_all_day_block INTEGER DEFAULT 0,
                module_start_date DATE,
                module_end_date DATE,
                week_start INTEGER,
                week_end INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (offering_id) REFERENCES subject_offerings(id)
            )
        """)
        
        _exec(conn, """
            CREATE INDEX IF NOT EXISTS idx_nwa_conflict_check
            ON normalized_weekly_assignment (ay_label, day_of_week, period_index)
        """)

        # =================================================================
        # 4. POSITIONAL ROLES VIEW
        # =================================================================
        _exec(conn, "DROP VIEW IF EXISTS v_subject_positional_roles")
        _exec(conn, """
            CREATE VIEW v_subject_positional_roles AS
            SELECT DISTINCT
                ay_label, degree_code, term, division_code, subject_code,
                json_extract(faculty_ids, '$[0]') as faculty_email,
                'Subject In-Charge' as role,
                is_override_in_charge as is_override
            FROM normalized_weekly_assignment
            WHERE faculty_ids IS NOT NULL
            UNION ALL
            SELECT DISTINCT
                n.ay_label, n.degree_code, n.term, n.division_code, n.subject_code,
                each.value as faculty_email,
                'Subject Faculty' as role,
                0 as is_override
            FROM normalized_weekly_assignment n, 
                 json_each(n.faculty_ids) each
            WHERE each.id > 0
        """)
        
        log.info("✅ Weekly Distribution & Timetable Schema Installed (Complete)")
