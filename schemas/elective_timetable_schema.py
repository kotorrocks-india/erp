# ============================================================================
# ELECTIVE TIMETABLE SCHEMA (Slide 24)
# ============================================================================
# Complete schema for elective/CP timetable with:
# - Topic modules with date ranges
# - Separate elective timetable grid
# - All-day block support
# - Module-specific faculty assignment
# - Date range overlap detection
# - Live capacity tracking
# ============================================================================

from __future__ import annotations
from sqlalchemy import text as sa_text
from sqlalchemy.engine import Engine
from core.schema_registry import register
import logging

log = logging.getLogger(__name__)

def _exec(conn, sql):
    """Execute SQL statement"""
    conn.execute(sa_text(sql))


# ============================================================================
# 1. ELECTIVE TOPIC MODULES (With Date Ranges)
# ============================================================================

@register
def install_elective_topic_modules(engine: Engine):
    """
    Topic modules with date ranges for conflict detection
    
    Example:
        Topic: "Machine Learning Applications"
          Module 1: "Supervised Learning" (Oct 1-31, Dr. Smith)
          Module 2: "Unsupervised Learning" (Nov 1-30, Dr. Jones)
          Module 3: "Deep Learning" (Dec 1-31, Dr. Brown)
    """
    with engine.begin() as conn:
        
        _exec(conn, """
            CREATE TABLE IF NOT EXISTS elective_topic_modules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                
                -- Link to topic
                topic_id INTEGER NOT NULL,
                topic_code_ay TEXT NOT NULL,
                
                -- Module identity
                module_number INTEGER NOT NULL,
                module_code TEXT NOT NULL,  -- e.g., "ML-M1", "ML-M2"
                module_name TEXT NOT NULL,
                module_description TEXT,
                
                -- Date ranges (CRITICAL for conflict detection)
                start_date DATE NOT NULL,
                end_date DATE NOT NULL,
                week_start INTEGER,  -- Week 1-16
                week_end INTEGER,
                
                -- Faculty (can differ from topic owner)
                faculty_in_charge TEXT,
                faculty_list TEXT,  -- JSON array of emails
                is_faculty_override BOOLEAN DEFAULT 0,
                
                -- Content
                learning_outcomes TEXT,  -- JSON array: ["LO1: ...", "LO2: ..."]
                topics_covered TEXT,  -- JSON array
                reference_materials TEXT,  -- JSON array
                assessment_methods TEXT,  -- JSON array
                
                -- Hours allocation
                lecture_hours INTEGER DEFAULT 0,
                practical_hours INTEGER DEFAULT 0,
                tutorial_hours INTEGER DEFAULT 0,
                self_study_hours INTEGER DEFAULT 0,
                
                -- Sequence
                sequence INTEGER DEFAULT 0,
                
                -- Status
                status TEXT DEFAULT 'draft',  -- draft, published, archived
                
                -- Metadata
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                created_by TEXT,
                updated_by TEXT,
                
                -- Constraints
                FOREIGN KEY (topic_id) REFERENCES elective_topics(id) ON DELETE CASCADE,
                UNIQUE(topic_id, module_number),
                UNIQUE(topic_code_ay, module_code),
                
                CHECK(module_number > 0),
                CHECK(start_date <= end_date),
                CHECK(week_start IS NULL OR week_start > 0),
                CHECK(week_end IS NULL OR week_end >= week_start),
                CHECK(status IN ('draft', 'published', 'archived'))
            )
        """)
        
        # Indexes
        _exec(conn, """
            CREATE INDEX IF NOT EXISTS idx_modules_topic 
            ON elective_topic_modules(topic_id)
        """)
        
        _exec(conn, """
            CREATE INDEX IF NOT EXISTS idx_modules_dates 
            ON elective_topic_modules(start_date, end_date)
        """)
        
        _exec(conn, """
            CREATE INDEX IF NOT EXISTS idx_modules_faculty 
            ON elective_topic_modules(faculty_in_charge)
        """)
        
        _exec(conn, """
            CREATE INDEX IF NOT EXISTS idx_modules_status 
            ON elective_topic_modules(status)
        """)
        
        log.info("✅ Installed elective_topic_modules table")


# ============================================================================
# 2. ELECTIVE TIMETABLE SLOTS (Separate from Regular TT)
# ============================================================================

@register
def install_elective_timetable_slots(engine: Engine):
    """
    Separate timetable grid for electives/CP (Slide 24)
    Distinct from regular weekly TT (Slide 23)
    
    Features:
    - All-day block support
    - Module-specific scheduling
    - Date range tracking
    - Cross-division support
    """
    with engine.begin() as conn:
        
        _exec(conn, """
            CREATE TABLE IF NOT EXISTS elective_timetable_slots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                
                -- Academic Context
                ay_label TEXT NOT NULL,
                degree_code TEXT NOT NULL,
                program_code TEXT,
                branch_code TEXT,
                year INTEGER NOT NULL,
                term INTEGER NOT NULL,
                division_code TEXT,  -- Can be "ALL" for combined class
                
                -- Subject & Topic
                subject_code TEXT NOT NULL,
                subject_name TEXT,
                topic_id INTEGER NOT NULL,
                topic_code_ay TEXT NOT NULL,
                topic_name TEXT,
                
                -- Module (Optional - if module-based)
                module_id INTEGER,
                module_code TEXT,
                module_name TEXT,
                
                -- Time Slot
                day_of_week TEXT NOT NULL,  -- Mon, Tue, Wed, Thu, Fri, Sat
                period_id INTEGER NOT NULL,
                
                -- All-Day Block Support (CRITICAL)
                is_all_day_block BOOLEAN DEFAULT 0,
                all_day_note TEXT,  -- "Breaks provided by faculty"
                
                -- Bridging (same as regular TT)
                bridge_group_id TEXT,
                bridge_position INTEGER DEFAULT 1,
                bridge_length INTEGER DEFAULT 1,
                
                -- Faculty Assignment
                faculty_in_charge TEXT,
                faculty_list TEXT,  -- JSON array
                is_in_charge_override BOOLEAN DEFAULT 0,
                
                -- Resources
                room_code TEXT,
                room_type TEXT,
                
                -- Date Range (CRITICAL for module overlap detection)
                start_date DATE,
                end_date DATE,
                applies_to_weeks TEXT,  -- JSON array: [1,2,3,4] or null=all weeks
                
                -- Capacity Tracking
                topic_capacity INTEGER,  -- Denormalized from topic
                current_enrollment INTEGER DEFAULT 0,  -- Live count
                
                -- Status
                status TEXT DEFAULT 'draft',  -- draft, published, locked, deleted
                is_locked BOOLEAN DEFAULT 0,
                
                -- Notes
                notes TEXT,
                
                -- Metadata
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                created_by TEXT,
                updated_by TEXT,
                
                -- Constraints
                FOREIGN KEY (topic_id) REFERENCES elective_topics(id),
                FOREIGN KEY (module_id) REFERENCES elective_topic_modules(id),
                
                CHECK(status IN ('draft', 'published', 'locked', 'deleted')),
                CHECK(is_all_day_block IN (0, 1)),
                CHECK(bridge_position > 0),
                CHECK(bridge_length > 0),
                CHECK(current_enrollment >= 0),
                CHECK(start_date IS NULL OR end_date IS NULL OR start_date <= end_date)
            )
        """)
        
        # Indexes for performance
        _exec(conn, """
            CREATE INDEX IF NOT EXISTS idx_elec_tt_context 
            ON elective_timetable_slots(ay_label, degree_code, year, term, division_code)
        """)
        
        _exec(conn, """
            CREATE INDEX IF NOT EXISTS idx_elec_tt_timeslot 
            ON elective_timetable_slots(day_of_week, period_id)
        """)
        
        _exec(conn, """
            CREATE INDEX IF NOT EXISTS idx_elec_tt_faculty 
            ON elective_timetable_slots(faculty_in_charge)
        """)
        
        _exec(conn, """
            CREATE INDEX IF NOT EXISTS idx_elec_tt_topic 
            ON elective_timetable_slots(topic_id)
        """)
        
        _exec(conn, """
            CREATE INDEX IF NOT EXISTS idx_elec_tt_module 
            ON elective_timetable_slots(module_id)
        """)
        
        _exec(conn, """
            CREATE INDEX IF NOT EXISTS idx_elec_tt_dates 
            ON elective_timetable_slots(start_date, end_date)
        """)
        
        _exec(conn, """
            CREATE INDEX IF NOT EXISTS idx_elec_tt_status 
            ON elective_timetable_slots(status)
        """)
        
        _exec(conn, """
            CREATE INDEX IF NOT EXISTS idx_elec_tt_all_day 
            ON elective_timetable_slots(is_all_day_block)
        """)
        
        log.info("✅ Installed elective_timetable_slots table")


# ============================================================================
# 3. ELECTIVE TIMETABLE CONFLICTS (Separate Conflict Log)
# ============================================================================

@register
def install_elective_timetable_conflicts(engine: Engine):
    """
    Conflict tracking for elective timetable
    Includes cross-reference with regular TT (Slide 23)
    """
    with engine.begin() as conn:
        
        _exec(conn, """
            CREATE TABLE IF NOT EXISTS elective_timetable_conflicts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                
                -- Context
                ay_label TEXT NOT NULL,
                degree_code TEXT NOT NULL,
                term INTEGER NOT NULL,
                
                -- Conflict Type
                conflict_type TEXT NOT NULL,
                -- 'faculty_overlap', 'date_range_overlap', 'capacity_exceeded',
                -- 'cross_tt_conflict' (Slide 23 vs 24), 'module_overlap',
                -- 'room_double_book', 'all_day_conflict'
                
                severity TEXT NOT NULL,  -- error, warning, info
                
                -- Involved Entities
                slot_ids TEXT,  -- JSON array of elective_timetable_slots IDs
                regular_tt_slot_ids TEXT,  -- JSON array if cross-TT conflict
                topic_ids TEXT,  -- JSON array
                module_ids TEXT,  -- JSON array
                faculty_emails TEXT,  -- JSON array
                division_codes TEXT,  -- JSON array
                
                -- Description
                message TEXT NOT NULL,
                details TEXT,  -- JSON with full conflict details
                
                -- Date Range
                conflict_start_date DATE,
                conflict_end_date DATE,
                
                -- Resolution
                is_resolved BOOLEAN DEFAULT 0,
                resolved_at DATETIME,
                resolved_by TEXT,
                resolution_note TEXT,
                
                can_auto_resolve BOOLEAN DEFAULT 0,
                requires_override BOOLEAN DEFAULT 0,
                override_reason TEXT,
                
                -- Metadata
                detected_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                created_by TEXT,
                
                CHECK(conflict_type IN (
                    'faculty_overlap', 'date_range_overlap', 'capacity_exceeded',
                    'cross_tt_conflict', 'module_overlap', 'room_double_book',
                    'all_day_conflict', 'student_overlap'
                )),
                CHECK(severity IN ('error', 'warning', 'info'))
            )
        """)
        
        _exec(conn, """
            CREATE INDEX IF NOT EXISTS idx_elec_conflicts_context 
            ON elective_timetable_conflicts(ay_label, degree_code, term)
        """)
        
        _exec(conn, """
            CREATE INDEX IF NOT EXISTS idx_elec_conflicts_type 
            ON elective_timetable_conflicts(conflict_type)
        """)
        
        _exec(conn, """
            CREATE INDEX IF NOT EXISTS idx_elec_conflicts_resolved 
            ON elective_timetable_conflicts(is_resolved)
        """)
        
        _exec(conn, """
            CREATE INDEX IF NOT EXISTS idx_elec_conflicts_dates 
            ON elective_timetable_conflicts(conflict_start_date, conflict_end_date)
        """)
        
        log.info("✅ Installed elective_timetable_conflicts table")


# ============================================================================
# 4. VIEWS - Combined Elective Schedule
# ============================================================================

@register
def install_elective_timetable_views(engine: Engine):
    """Create helpful views for elective timetable"""
    with engine.begin() as conn:
        
        # View: Elective schedule with all details
        _exec(conn, """
            CREATE VIEW IF NOT EXISTS v_elective_schedule AS
            SELECT 
                -- Slot details
                ets.id as slot_id,
                ets.ay_label,
                ets.degree_code,
                ets.year,
                ets.term,
                ets.division_code,
                
                -- Subject & Topic
                ets.subject_code,
                ets.subject_name,
                ets.topic_id,
                ets.topic_code_ay,
                ets.topic_name,
                
                -- Module (if applicable)
                ets.module_id,
                ets.module_code,
                ets.module_name,
                m.start_date as module_start_date,
                m.end_date as module_end_date,
                
                -- Schedule
                ets.day_of_week,
                ets.period_id,
                ets.is_all_day_block,
                ets.bridge_length,
                
                -- Faculty
                ets.faculty_in_charge,
                ets.faculty_list,
                
                -- Capacity
                ets.topic_capacity,
                ets.current_enrollment,
                CASE 
                    WHEN ets.topic_capacity > 0 
                    THEN CAST(ets.current_enrollment AS REAL) / ets.topic_capacity * 100
                    ELSE 0
                END as enrollment_percentage,
                
                -- Room
                ets.room_code,
                ets.room_type,
                
                -- Date range
                ets.start_date as slot_start_date,
                ets.end_date as slot_end_date,
                
                -- Status
                ets.status,
                ets.is_locked
                
            FROM elective_timetable_slots ets
            LEFT JOIN elective_topic_modules m ON m.id = ets.module_id
            
            WHERE ets.status != 'deleted'
            
            ORDER BY 
                ets.ay_label,
                ets.degree_code,
                ets.year,
                ets.term,
                ets.division_code,
                CASE ets.day_of_week
                    WHEN 'Monday' THEN 1
                    WHEN 'Tuesday' THEN 2
                    WHEN 'Wednesday' THEN 3
                    WHEN 'Thursday' THEN 4
                    WHEN 'Friday' THEN 5
                    WHEN 'Saturday' THEN 6
                END,
                ets.period_id
        """)
        
        # View: Topic capacity summary
        _exec(conn, """
            CREATE VIEW IF NOT EXISTS v_elective_topic_capacity AS
            SELECT 
                et.id as topic_id,
                et.topic_code_ay,
                et.topic_name,
                et.capacity,
                
                -- Current selections
                COUNT(DISTINCT CASE WHEN ess.status = 'confirmed' THEN ess.student_roll_no END) as confirmed,
                COUNT(DISTINCT CASE WHEN ess.status = 'waitlisted' THEN ess.student_roll_no END) as waitlisted,
                
                -- Availability
                et.capacity - COUNT(DISTINCT CASE WHEN ess.status = 'confirmed' THEN ess.student_roll_no END) as available,
                
                -- Percentage
                CASE 
                    WHEN et.capacity > 0 
                    THEN CAST(COUNT(DISTINCT CASE WHEN ess.status = 'confirmed' THEN ess.student_roll_no END) AS REAL) / et.capacity * 100
                    ELSE 0
                END as fill_percentage,
                
                -- Status
                CASE
                    WHEN et.capacity = 0 THEN 'unlimited'
                    WHEN COUNT(DISTINCT CASE WHEN ess.status = 'confirmed' THEN ess.student_roll_no END) >= et.capacity THEN 'full'
                    WHEN COUNT(DISTINCT CASE WHEN ess.status = 'confirmed' THEN ess.student_roll_no END) >= et.capacity * 0.5 THEN 'filling'
                    ELSE 'low'
                END as capacity_status,
                
                et.ay_label,
                et.year,
                et.term
                
            FROM elective_topics et
            LEFT JOIN elective_student_selections ess 
                ON ess.topic_code_ay = et.topic_code_ay 
                AND ess.ay_label = et.ay_label
            
            WHERE et.status = 'published'
            
            GROUP BY et.id
        """)
        
        log.info("✅ Installed elective timetable views")


# ============================================================================
# MAIN INSTALLER
# ============================================================================

@register
def install_elective_timetable_schema(engine: Engine):
    """
    Install complete elective timetable schema
    
    Tables:
    1. elective_topic_modules - Module breakdown with date ranges
    2. elective_timetable_slots - Separate elective TT grid
    3. elective_timetable_conflicts - Conflict tracking
    
    Views:
    1. v_elective_schedule - Complete schedule view
    2. v_elective_topic_capacity - Live capacity tracking
    """
    
    log.info("Installing elective timetable schema...")
    
    install_elective_topic_modules(engine)
    install_elective_timetable_slots(engine)
    install_elective_timetable_conflicts(engine)
    install_elective_timetable_views(engine)
    
    log.info("✅ Elective timetable schema installation complete!")
