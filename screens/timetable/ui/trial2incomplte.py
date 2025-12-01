# ============================================================================
# COMPLETE TIMETABLE GRID - Fixed Semester Progression & Merged Cells
# ============================================================================
# Location: screens/timetable/ui/timetable_grid_complete.py
#
# Features:
# - Proper semester progression per AY + Term
# - Unified merged cell display (no "merged" text)
# - Integration with services (conflict detection, distribution tracking, etc.)
# - Year-semester labels follow degree structure
# - All functionality preserved
# ============================================================================

import streamlit as st
import pandas as pd
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.engine import Engine
from sqlalchemy import text
import json
import uuid
from datetime import datetime
import sys
import os

# Add services to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

# Import services
try:
    from services import (
        CONFLICT_DETECTION_AVAILABLE,
        detect_faculty_conflicts,
        detect_student_conflicts,
        detect_distribution_violations,
        DISTRIBUTION_TRACKING_AVAILABLE,
        get_distribution_status,
        validate_distribution_before_create,
        FACULTY_SCHEDULING_AVAILABLE,
        get_available_faculty,
        CROSS_TT_DETECTION_AVAILABLE,
        detect_all_cross_tt_conflicts
    )
except ImportError as e:
    print(f"⚠️ Services import failed: {e}")
    CONFLICT_DETECTION_AVAILABLE = False
    DISTRIBUTION_TRACKING_AVAILABLE = False
    FACULTY_SCHEDULING_AVAILABLE = False
    CROSS_TT_DETECTION_AVAILABLE = False
    
    def detect_faculty_conflicts(*args, **kwargs): return []
    def detect_student_conflicts(*args, **kwargs): return []
    def detect_distribution_violations(*args, **kwargs): return []
    def get_distribution_status(*args, **kwargs): return None
    def validate_distribution_before_create(*args, **kwargs): return True, ""
    def get_available_faculty(*args, **kwargs): return []
    def detect_all_cross_tt_conflicts(*args, **kwargs): return {'faculty_conflicts': [], 'student_conflicts': [], 'room_conflicts': [], 'total_errors': 0, 'total_warnings': 0, 'has_blocking_conflicts': False}


# ============================================================================
# COLOR SCHEMES
# ============================================================================

YEAR_COLORS = {
    1: '#F4CCCC',  # Light red/pink
    2: '#FCE5CD',  # Light orange/tan
    3: '#FFF2CC',  # Light yellow
    4: '#D9EAD3',  # Light green
    5: '#D0E0E3',  # Light blue
}

HEADER_COLORS = {
    'day': '#93C47D',
    'period': '#B7B7B7',
    'time': '#D9D9D9',
    'year_label': '#E6B8AF',
}

SUBJECT_TYPE_COLORS = {
    'Theory': '#E3F2FD',
    'Practical': '#FFF3E0',
    'Studio': '#F3E5F5',
    'Elective': '#E8F5E9',
    'Core': '#FFF9C4',
    'Lab': '#FFE0B2',
}


# ============================================================================
# VERSIONING FUNCTIONS
# ============================================================================

def generate_version_code(prefix: str, version_number: int) -> str:
    """Generate version code: TT-R0, TT-R1, etc."""
    return f"{prefix}-R{version_number}"


def get_next_version_number(engine: Engine, context: dict) -> int:
    """Get next version number for context"""
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT COALESCE(MAX(version_number), -1) + 1
            FROM timetable_versions
            WHERE ay_label = :ay
              AND degree_code = :deg
              AND term = :term
              AND COALESCE(division_code, '') = COALESCE(:div, '')
        """), {
            'ay': context['ay_label'],
            'deg': context['degree_code'],
            'term': context['term'],
            'div': context.get('division_code')
        }).fetchone()
        
        return result[0] if result else 0


def create_version(
    engine: Engine,
    context: dict,
    version_name: str,
    template_id: int = None,
    created_by: str = 'user'
) -> int:
    """Create new draft version"""
    version_number = get_next_version_number(engine, context)
    
    prefix = context.get('degree_code', 'TT')
    if context.get('division_code'):
        prefix = f"{prefix}-{context['division_code']}"
    
    version_code = generate_version_code(prefix, version_number)
    
    with engine.begin() as conn:
        result = conn.execute(text("""
            INSERT INTO timetable_versions (
                version_code, version_name, version_number,
                ay_label, degree_code, program_code, branch_code, term, division_code,
                template_id, status, created_by
            ) VALUES (
                :code, :name, :ver_num,
                :ay, :deg, :prog, :branch, :term, :div,
                :template, 'draft', :created_by
            )
        """), {
            'code': version_code,
            'name': version_name,
            'ver_num': version_number,
            'ay': context['ay_label'],
            'deg': context['degree_code'],
            'prog': context.get('program_code'),
            'branch': context.get('branch_code'),
            'term': context['term'],
            'div': context.get('division_code'),
            'template': template_id,
            'created_by': created_by
        })
        
        return result.lastrowid


def publish_version(engine: Engine, version_id: int, published_by: str = 'user') -> bool:
    """Publish a draft version"""
    with engine.begin() as conn:
        version = conn.execute(text("""
            SELECT version_code, status, ay_label, degree_code, term, division_code
            FROM timetable_versions WHERE id = :vid
        """), {'vid': version_id}).fetchone()
        
        if not version or version[1] != 'draft':
            return False
        
        # Archive current published
        conn.execute(text("""
            UPDATE timetable_versions
            SET status = 'archived', is_current_published = 0,
                archived_at = CURRENT_TIMESTAMP, archived_by = :by,
                archived_reason = 'Replaced by new version'
            WHERE ay_label = :ay AND degree_code = :deg AND term = :term
              AND COALESCE(division_code, '') = COALESCE(:div, '')
              AND status = 'published' AND is_current_published = 1
        """), {
            'by': published_by,
            'ay': version[2],
            'deg': version[3],
            'term': version[4],
            'div': version[5]
        })
        
        # Publish this version
        conn.execute(text("""
            UPDATE timetable_versions
            SET status = 'published', is_current_published = 1,
                published_at = CURRENT_TIMESTAMP, published_by = :by
            WHERE id = :vid
        """), {'vid': version_id, 'by': published_by})
        
        return True


# ============================================================================
# SEMESTER CALCULATION FUNCTIONS (Fixed for per-term display)
# ============================================================================

def get_term_dates(engine: Engine, ay_code: str, degree_code: str, 
                  batch_code: str = None, year_of_study: int = None) -> Optional[Dict]:
    """Get term dates for a specific AY/term/degree/batch/year combination."""
    with engine.connect() as conn:
        query = """
            SELECT term_number, term_label, start_date, end_date
            FROM batch_term_dates
            WHERE ay_code = :ay AND degree_code = :deg
        """
        params = {'ay': ay_code, 'deg': degree_code}
        
        if batch_code:
            query += " AND batch_code = :batch"
            params['batch'] = batch_code
        
        if year_of_study:
            query += " AND year_of_study = :year"
            params['year'] = year_of_study
        
        result = conn.execute(text(query), params).fetchone()
        
        if result:
            return {
                'term_number': result[0],
                'term_label': result[1],
                'start_date': result[2],
                'end_date': result[3]
            }
    
    return None


def get_semester_config(engine: Engine, degree_code: str) -> Optional[Dict]:
    """Fetch semester configuration for a degree."""
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT binding_mode, label_mode
            FROM semester_binding
            WHERE degree_code = :deg
        """), {'deg': degree_code}).fetchone()
        
        if result:
            return {
                'binding_mode': result[0],
                'label_mode': result[1]
            }
        return None


def get_semester_structure(engine: Engine, degree_code: str, 
                          program_id: int = None, branch_id: int = None) -> Optional[Dict]:
    """Fetch semester structure (years, terms_per_year)."""
    with engine.connect() as conn:
        config = get_semester_config(engine, degree_code)
        
        if not config:
            return None
        
        binding_mode = config['binding_mode']
        
        # Try branch level first
        if binding_mode == 'branch' and branch_id:
            result = conn.execute(text("""
                SELECT years, terms_per_year, active
                FROM branch_semester_struct
                WHERE branch_id = :bid AND active = 1
            """), {'bid': branch_id}).fetchone()
            
            if result:
                return {
                    'years': result[0],
                    'terms_per_year': result[1],
                    'binding_mode': 'branch',
                    'active': result[2]
                }
        
        # Try program level
        if binding_mode in ('branch', 'program') and program_id:
            result = conn.execute(text("""
                SELECT years, terms_per_year, active
                FROM program_semester_struct
                WHERE program_id = :pid AND active = 1
            """), {'pid': program_id}).fetchone()
            
            if result:
                return {
                    'years': result[0],
                    'terms_per_year': result[1],
                    'binding_mode': 'program',
                    'active': result[2]
                }
        
        # Fall back to degree level
        result = conn.execute(text("""
            SELECT years, terms_per_year, active
            FROM degree_semester_struct
            WHERE degree_code = :deg AND active = 1
        """), {'deg': degree_code}).fetchone()
        
        if result:
            return {
                'years': result[0],
                'terms_per_year': result[1],
                'binding_mode': 'degree',
                'active': result[2]
            }
    
    return None


def get_semester_for_year_and_term(engine: Engine, degree_code: str, 
                                   year_of_study: int, term_number: int,
                                   program_id: int = None, branch_id: int = None) -> str:
    """
    Calculate which semester a year_of_study falls into for a given term.
    
    Example with 2 terms/year:
    - Year 1, Term 1 → Sem I
    - Year 1, Term 2 → Sem II
    - Year 2, Term 1 → Sem III
    - Year 2, Term 2 → Sem IV
    """
    sem_struct = get_semester_structure(engine, degree_code, program_id, branch_id)
    
    if not sem_struct:
        # Fallback: assume 2 terms/year
        semester_number = (year_of_study - 1) * 2 + term_number
        return _get_ordinal_label(semester_number)
    
    terms_per_year = sem_struct['terms_per_year']
    semester_number = (year_of_study - 1) * terms_per_year + term_number
    
    return _get_ordinal_label(semester_number)


def _get_ordinal_label(n: int) -> str:
    """Convert number to ordinal Roman numeral."""
    ordinals = {
        1: 'I', 2: 'II', 3: 'III', 4: 'IV', 5: 'V',
        6: 'VI', 7: 'VII', 8: 'VIII', 9: 'IX', 10: 'X',
        11: 'XI', 12: 'XII', 13: 'XIII', 14: 'XIV', 15: 'XV'
    }
    return ordinals.get(n, f'{n}')


def get_years_for_current_term(engine: Engine, ctx: Dict) -> List[int]:
    """Get which years have active students in the current term."""
    ay_code = ctx['ay_label']
    degree_code = ctx['degree_code']
    term_number = ctx['term']
    
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT DISTINCT year_of_study
            FROM batch_term_dates
            WHERE ay_code = :ay AND degree_code = :deg AND term_number = :term
            ORDER BY year_of_study
        """), {
            'ay': ay_code,
            'deg': degree_code,
            'term': term_number
        })
        
        years = [r[0] for r in result]
    
    if years:
        return years
    
    # Fallback: get from semester structure
    sem_struct = get_semester_structure(engine, degree_code, 
                                       ctx.get('program_id'), ctx.get('branch_id'))
    if sem_struct:
        return list(range(1, sem_struct['years'] + 1))
    
    # Default fallback
    return [1, 2, 3, 4]


def get_year_sem_tuples_for_term(engine: Engine, ctx: Dict) -> List[Tuple[int, int, str]]:
    """
    Get (year_of_study, term_number, semester_label) tuples for the current term only.
    
    Returns only entries for ctx['term'], with correct semester labels.
    """
    degree_code = ctx['degree_code']
    term_number = ctx['term']
    program_id = ctx.get('program_id')
    branch_id = ctx.get('branch_id')
    
    years = get_years_for_current_term(engine, ctx)
    
    year_sem_tuples = []
    
    for year in years:
        sem_label = get_semester_for_year_and_term(
            engine, degree_code, year, term_number, program_id, branch_id
        )
        year_sem_tuples.append((year, term_number, sem_label))
    
    return year_sem_tuples

# ============================================================================
# CONFLICT DETECTION & VALIDATION (Integrated with Services)
# ============================================================================

def validate_assignment(
    engine: Engine,
    context: Dict,
    year: int,
    division: str,
    day_of_week: int,
    period_id: int,
    offering_id: int,
    subject_code: str,
    faculty_email: Optional[str] = None,
    bridge_length: int = 1
) -> Tuple[bool, Optional[str]]:
    """Validate if an assignment can be created without conflicts"""
    
    with engine.connect() as conn:
        
        # 1. FACULTY CONFLICT CHECK
        if faculty_email:
            for i in range(bridge_length):
                check_period = period_id + i
                
                result = conn.execute(text("""
                    SELECT 
                        s.id, s.subject_code, s.degree_code, s.division_code,
                        s.year, o.subject_name
                    FROM timetable_slots s
                    LEFT JOIN subject_offerings o ON o.id = s.offering_id
                    WHERE s.ay_label = :ay AND s.term = :term
                      AND s.day_of_week = :day AND s.period_id = :period
                      AND (s.faculty_in_charge = :faculty 
                           OR s.faculty_list LIKE :faculty_pattern)
                      AND s.status != 'deleted'
                """), {
                    'ay': context['ay_label'], 'term': context['term'],
                    'day': day_of_week, 'period': check_period,
                    'faculty': faculty_email,
                    'faculty_pattern': f'%{faculty_email}%'
                }).fetchall()
                
                if result:
                    conflict = result[0]
                    return False, (
                        f"❌ Faculty Conflict: {faculty_email.split('@')[0]} is already teaching "
                        f"{conflict[5] or conflict[1]} for {conflict[2]} Year {conflict[4]} "
                        f"Division {conflict[3]} at this time"
                    )
        
        # 2. DISTRIBUTION VIOLATION CHECK (if service available)
        if DISTRIBUTION_TRACKING_AVAILABLE and offering_id and division:
            is_valid, error_msg = validate_distribution_before_create(
                offering_id, division, bridge_length
            )
            if not is_valid:
                return False, error_msg
        
        # 3. DIVISION/SUBJECT CONFLICT CHECK
        for i in range(bridge_length):
            check_period = period_id + i
            
            result = conn.execute(text("""
                SELECT id, subject_code
                FROM timetable_slots
                WHERE ay_label = :ay AND degree_code = :deg
                  AND term = :term AND year = :year
                  AND division_code = :div
                  AND day_of_week = :day AND period_id = :period
                  AND status != 'deleted'
            """), {
                'ay': context['ay_label'], 'deg': context['degree_code'],
                'term': context['term'], 'year': year, 'div': division,
                'day': day_of_week, 'period': check_period
            }).fetchone()
            
            if result:
                return False, (
                    f"❌ Slot Conflict: This division already has {result[1]} "
                    f"scheduled at this time"
                )
    
    return True, None


def get_conflicts_for_cell(
    engine: Engine,
    context: Dict,
    year: int,
    division: str,
    day_of_week: int,
    period_id: int
) -> List[Dict]:
    """Get all conflicts for a specific cell"""
    conflicts = []
    
    if not CONFLICT_DETECTION_AVAILABLE:
        return conflicts
    
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT s.*, o.subject_name
            FROM timetable_slots s
            LEFT JOIN subject_offerings o ON o.id = s.offering_id
            WHERE s.ay_label = :ay AND s.degree_code = :deg
              AND s.term = :term AND s.year = :year
              AND s.division_code = :div
              AND s.day_of_week = :day AND s.period_id = :period
              AND s.status != 'deleted'
        """), {
            'ay': context['ay_label'], 'deg': context['degree_code'],
            'term': context['term'], 'year': year, 'div': division,
            'day': day_of_week, 'period': period_id
        }).fetchone()
        
        if not result:
            return conflicts
        
        slot = dict(result._mapping)
        
        # Check faculty conflicts using service
        if slot.get('faculty_in_charge'):
            faculty_conflicts = detect_faculty_conflicts(
                context['ay_label'], context['term'], context['degree_code']
            )
            
            for conflict in faculty_conflicts:
                if str(slot['id']) in str(conflict.get('slot_ids', [])):
                    conflicts.append({
                        'type': 'faculty',
                        'severity': 'error',
                        'message': conflict.get('message', 'Faculty conflict detected')
                    })
        
        # Check distribution violations using service
        if DISTRIBUTION_TRACKING_AVAILABLE and slot.get('offering_id'):
            dist_status = get_distribution_status(
                slot['offering_id'], slot.get('division_code')
            )
            
            if dist_status and dist_status['allocation_status'] == 'over_allocated':
                conflicts.append({
                    'type': 'distribution',
                    'severity': 'error',
                    'message': f"Over-allocated: {dist_status['scheduled_period_slots']}/{dist_status['planned_total_periods']} periods used"
                })
    
    return conflicts


# ============================================================================
# DATABASE FUNCTIONS
# ============================================================================

def ensure_tables(engine: Engine):
    """Ensure required tables exist"""
    with engine.begin() as conn:
        table_exists = conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='timetable_slots'"
        )).fetchone()
        
        if not table_exists:
            conn.execute(text("""
                CREATE TABLE timetable_slots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ay_label TEXT NOT NULL,
                    degree_code TEXT NOT NULL,
                    program_code TEXT,
                    branch_code TEXT,
                    year INTEGER NOT NULL,
                    term INTEGER NOT NULL,
                    division_code TEXT,
                    offering_id INTEGER,
                    subject_code TEXT,
                    subject_type TEXT,
                    day_of_week INTEGER NOT NULL,
                    period_id INTEGER NOT NULL,
                    bridge_group_id TEXT,
                    bridge_position INTEGER DEFAULT 1,
                    bridge_length INTEGER DEFAULT 1,
                    status TEXT DEFAULT 'active',
                    faculty_in_charge TEXT,
                    faculty_list TEXT,
                    room_code TEXT,
                    version_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
        
        versions_exists = conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='timetable_versions'"
        )).fetchone()
        
        if not versions_exists:
            conn.execute(text("""
                CREATE TABLE timetable_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    version_code TEXT NOT NULL,
                    version_name TEXT,
                    version_number INTEGER,
                    ay_label TEXT,
                    degree_code TEXT,
                    program_code TEXT,
                    branch_code TEXT,
                    term INTEGER,
                    division_code TEXT,
                    template_id INTEGER,
                    status TEXT DEFAULT 'draft',
                    is_current_published BOOLEAN DEFAULT 0,
                    created_by TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    published_by TEXT,
                    published_at TIMESTAMP,
                    archived_by TEXT,
                    archived_at TIMESTAMP,
                    archived_reason TEXT
                )
            """))


def get_template_periods(engine: Engine, ay: str, degree: str, term: int) -> List[Dict]:
    """Get periods from published template"""
    with engine.connect() as conn:
        template = conn.execute(text("""
            SELECT id FROM day_templates
            WHERE ay_label = :ay AND degree_code = :deg AND term = :term
            AND status = 'published'
            ORDER BY (year IS NOT NULL) + (division_code IS NOT NULL) DESC
            LIMIT 1
        """), {'ay': ay, 'deg': degree, 'term': term}).fetchone()
        
        if not template:
            return []
        
        slots = conn.execute(text("""
            SELECT slot_index as id, slot_label as label,
                   fixed_start_time as start_time, fixed_end_time as end_time,
                   is_teaching_slot, duration_min
            FROM day_template_slots
            WHERE template_id = :tid AND is_teaching_slot = 1
            ORDER BY slot_index
        """), {'tid': template[0]}).fetchall()
        
        return [dict(s._mapping) for s in slots]


def get_distribution_subjects(engine: Engine, ay: str, degree: str, year: int, term: int, div: str = None) -> List[Dict]:
    """Get subjects from weekly distribution"""
    with engine.connect() as conn:
        query = """
            SELECT DISTINCT
                wsd.subject_code,
                COALESCE(sc.subject_name, wsd.subject_code) as subject_name,
                wsd.subject_type,
                wsd.division_code,
                wsd.offering_id,
                wsd.subject_code || ' - ' || COALESCE(sc.subject_name, wsd.subject_code) as display_name
            FROM weekly_subject_distribution wsd
            LEFT JOIN subjects_catalog sc ON wsd.subject_code = sc.subject_code
            WHERE wsd.ay_label = :ay
              AND wsd.degree_code = :deg
              AND wsd.year = :year
              AND wsd.term = :term
        """
        params = {'ay': ay, 'deg': degree, 'year': year, 'term': term}
        
        if div:
            query += " AND (wsd.division_code = :div OR wsd.division_code IS NULL)"
            params['div'] = div
        
        query += " ORDER BY wsd.subject_code"
        
        result = conn.execute(text(query), params)
        return [dict(r._mapping) for r in result]


def get_faculty_list(engine: Engine, degree: str) -> List[Dict]:
    """Get faculty for a degree"""
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT DISTINCT
                fp.id as faculty_id,
                fp.email,
                fp.name as faculty_name,
                fa.designation
            FROM faculty_profiles fp
            JOIN faculty_affiliations fa ON fp.email = fa.email
            WHERE fa.degree_code = :deg AND fa.active = 1
            ORDER BY fp.name
        """), {'deg': degree})
        return [dict(r._mapping) for r in result]


def get_slot(engine: Engine, ctx: Dict, year: int, div: str, day: int, period: int, ver: int = None) -> Optional[Dict]:
    """Get existing slot assignment"""
    with engine.connect() as conn:
        params = {
            'ay': ctx['ay_label'], 'deg': ctx['degree_code'],
            'year': year, 'term': ctx['term'], 'div': div,
            'day': day, 'per': period
        }
        
        query = """
            SELECT ts.*, sc.subject_name, fp.name as faculty_name
            FROM timetable_slots ts
            LEFT JOIN subjects_catalog sc ON ts.subject_code = sc.subject_code
            LEFT JOIN faculty_profiles fp ON ts.faculty_in_charge = fp.email
            WHERE ts.ay_label = :ay AND ts.degree_code = :deg
              AND ts.year = :year AND ts.term = :term
              AND COALESCE(ts.division_code, '') = COALESCE(:div, '')
              AND ts.day_of_week = :day AND ts.period_id = :per
              AND ts.status = 'active'
        """
        
        if ver:
            query += " AND ts.version_id = :ver"
            params['ver'] = ver
        
        result = conn.execute(text(query), params).fetchone()
        return dict(result._mapping) if result else None


def save_slot(engine: Engine, ctx: Dict, year: int, div: str, day: int, period: int,
              subj: str, stype: str, offering_id: int = None, faculty_email: str = None, ver: int = None):
    """Save a slot assignment with conflict validation"""
    ensure_tables(engine)
    
    is_valid, error_msg = validate_assignment(
        engine, ctx, year, div, day, period,
        offering_id, subj, faculty_email, 1
    )
    
    if not is_valid:
        raise ValueError(error_msg)
    
    with engine.begin() as conn:
        params = {
            'ay': ctx['ay_label'], 'deg': ctx['degree_code'],
            'year': year, 'term': ctx['term'], 'div': div,
            'day': day, 'per': period
        }
        
        delete_query = """
            DELETE FROM timetable_slots
            WHERE ay_label = :ay AND degree_code = :deg
              AND year = :year AND term = :term
              AND COALESCE(division_code, '') = COALESCE(:div, '')
              AND day_of_week = :day AND period_id = :per
        """
        
        if ver:
            delete_query += " AND COALESCE(version_id, 0) = COALESCE(:ver, 0)"
            params['ver'] = ver
        
        conn.execute(text(delete_query), params)
        
        conn.execute(text("""
            INSERT INTO timetable_slots (
                ay_label, degree_code, year, term, division_code,
                day_of_week, period_id, subject_code, subject_type,
                offering_id, faculty_in_charge, faculty_list, version_id, status
            ) VALUES (
                :ay, :deg, :year, :term, :div,
                :day, :per, :subj, :stype,
                :offering, :fac, :fac, :ver, 'active'
            )
        """), {
            'ay': ctx['ay_label'], 'deg': ctx['degree_code'],
            'year': year, 'term': ctx['term'], 'div': div,
            'day': day, 'per': period, 'subj': subj, 'stype': stype,
            'offering': offering_id, 'fac': faculty_email, 'ver': ver
        })


def delete_slot(engine: Engine, ctx: Dict, year: int, div: str, day: int, period: int, ver: int = None):
    """Delete a slot assignment"""
    with engine.begin() as conn:
        params = {
            'ay': ctx['ay_label'], 'deg': ctx['degree_code'],
            'year': year, 'term': ctx['term'], 'div': div,
            'day': day, 'per': period
        }
        
        query = """
            DELETE FROM timetable_slots
            WHERE ay_label = :ay AND degree_code = :deg
              AND year = :year AND term = :term
              AND COALESCE(division_code, '') = COALESCE(:div, '')
              AND day_of_week = :day AND period_id = :per
        """
        
        if ver:
            query += " AND COALESCE(version_id, 0) = COALESCE(:ver, 0)"
            params['ver'] = ver
        
        conn.execute(text(query), params)


def get_divisions(engine: Engine, ctx: Dict) -> List[str]:
    """Get divisions for context"""
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT DISTINCT division_code
            FROM weekly_subject_distribution
            WHERE ay_label = :ay AND degree_code = :deg AND term = :term
              AND division_code IS NOT NULL AND division_code != ''
            ORDER BY division_code
        """), {'ay': ctx['ay_label'], 'deg': ctx['degree_code'], 'term': ctx['term']})
        return [r[0] for r in result]

# ============================================================================
# BRIDGING FUNCTIONS (Cell Merging)
# ============================================================================

def create_bridge(engine: Engine, ctx: Dict, year: int, div: str, day: int, 
                  start_period: int, bridge_length: int, subj: str, stype: str, 
                  offering_id: int = None, faculty_email: str = None, ver: int = None):
    """Create a bridged (merged) slot spanning multiple periods"""
    ensure_tables(engine)
    
    # Validate bridge assignment
    is_valid, error_msg = validate_assignment(
        engine, ctx, year, div, day, start_period,
        offering_id, subj, faculty_email, bridge_length
    )
    
    if not is_valid:
        raise ValueError(error_msg)
    
    bridge_id = str(uuid.uuid4())[:8]
    
    with engine.begin() as conn:
        # Delete any existing slots in the bridge range
        for i in range(bridge_length):
            period_id = start_period + i
            params = {
                'ay': ctx['ay_label'], 'deg': ctx['degree_code'],
                'year': year, 'term': ctx['term'], 'div': div,
                'day': day, 'per': period_id
            }
            conn.execute(text("""
                DELETE FROM timetable_slots
                WHERE ay_label = :ay AND degree_code = :deg
                  AND year = :year AND term = :term
                  AND COALESCE(division_code, '') = COALESCE(:div, '')
                  AND day_of_week = :day AND period_id = :per
            """), params)
        
        # Create bridge slots
        for i in range(bridge_length):
            period_id = start_period + i
            position = i + 1
            
            conn.execute(text("""
                INSERT INTO timetable_slots (
                    ay_label, degree_code, year, term, division_code,
                    day_of_week, period_id, subject_code, subject_type,
                    offering_id, faculty_in_charge, faculty_list, 
                    bridge_group_id, bridge_position, bridge_length,
                    version_id, status
                ) VALUES (
                    :ay, :deg, :year, :term, :div,
                    :day, :per, :subj, :stype,
                    :offering, :fac, :fac,
                    :bridge_id, :pos, :len,
                    :ver, 'active'
                )
            """), {
                'ay': ctx['ay_label'], 'deg': ctx['degree_code'],
                'year': year, 'term': ctx['term'], 'div': div,
                'day': day, 'per': period_id, 'subj': subj, 'stype': stype,
                'offering': offering_id, 'fac': faculty_email, 
                'bridge_id': bridge_id, 'pos': position, 'len': bridge_length, 'ver': ver
            })
    
    return bridge_id


def delete_bridge(engine: Engine, bridge_id: str):
    """Delete all slots in a bridge"""
    with engine.begin() as conn:
        conn.execute(text("""
            DELETE FROM timetable_slots WHERE bridge_group_id = :bid
        """), {'bid': bridge_id})


def extend_bridge(engine: Engine, bridge_id: str, additional_periods: int = 1):
    """Extend a bridge by adding more periods"""
    with engine.connect() as conn:
        bridge = conn.execute(text("""
            SELECT * FROM timetable_slots 
            WHERE bridge_group_id = :bid AND bridge_position = 1
        """), {'bid': bridge_id}).fetchone()
        
        if not bridge:
            return False
        
        bridge = dict(bridge._mapping)
        current_length = bridge['bridge_length']
        new_length = current_length + additional_periods
        last_period = bridge['period_id'] + current_length - 1
        
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE timetable_slots SET bridge_length = :len WHERE bridge_group_id = :bid
        """), {'len': new_length, 'bid': bridge_id})
        
        for i in range(additional_periods):
            period_id = last_period + i + 1
            position = current_length + i + 1
            
            conn.execute(text("""
                INSERT INTO timetable_slots (
                    ay_label, degree_code, year, term, division_code,
                    day_of_week, period_id, subject_code, subject_type,
                    offering_id, faculty_in_charge, faculty_list,
                    bridge_group_id, bridge_position, bridge_length, status
                ) VALUES (
                    :ay, :deg, :year, :term, :div,
                    :day, :per, :subj, :stype,
                    :offering, :fac, :fac,
                    :bid, :pos, :len, 'active'
                )
            """), {
                'ay': bridge['ay_label'], 'deg': bridge['degree_code'],
                'year': bridge['year'], 'term': bridge['term'], 
                'div': bridge.get('division_code'),
                'day': bridge['day_of_week'], 'per': period_id,
                'subj': bridge['subject_code'], 'stype': bridge.get('subject_type'),
                'offering': bridge.get('offering_id'),
                'fac': bridge.get('faculty_in_charge'), 'bid': bridge_id,
                'pos': position, 'len': new_length
            })
    
    return True


def shrink_bridge(engine: Engine, bridge_id: str, remove_periods: int = 1):
    """Shrink a bridge by removing periods from the end"""
    with engine.connect() as conn:
        bridge = conn.execute(text("""
            SELECT bridge_length FROM timetable_slots 
            WHERE bridge_group_id = :bid AND bridge_position = 1
        """), {'bid': bridge_id}).fetchone()
        
        if not bridge or bridge[0] <= 1:
            return False
        
        current_length = bridge[0]
        new_length = max(1, current_length - remove_periods)
    
    with engine.begin() as conn:
        conn.execute(text("""
            DELETE FROM timetable_slots 
            WHERE bridge_group_id = :bid AND bridge_position > :len
        """), {'bid': bridge_id, 'len': new_length})
        
        if new_length == 1:
            conn.execute(text("""
                UPDATE timetable_slots 
                SET bridge_group_id = NULL, bridge_position = 1, bridge_length = 1
                WHERE bridge_group_id = :bid
            """), {'bid': bridge_id})
        else:
            conn.execute(text("""
                UPDATE timetable_slots SET bridge_length = :len WHERE bridge_group_id = :bid
            """), {'len': new_length, 'bid': bridge_id})
    
    return True


def unmerge_bridge(engine: Engine, bridge_id: str):
    """Convert bridge back to individual single-period slots"""
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE timetable_slots 
            SET bridge_group_id = NULL, bridge_position = 1, bridge_length = 1
            WHERE bridge_group_id = :bid
        """), {'bid': bridge_id})

# ============================================================================
# VERSION PANEL UI
# ============================================================================

def render_version_panel(engine: Engine, context: Dict):
    """Render version management panel"""
    
    st.markdown("### 📋 Version Management")
    
    with engine.connect() as conn:
        versions = conn.execute(text("""
            SELECT id, version_code, version_name, status, version_number,
                   created_at, published_at
            FROM timetable_versions
            WHERE ay_label = :ay
              AND degree_code = :deg
              AND term = :term
              AND (:div IS NULL OR division_code = :div OR division_code IS NULL)
            ORDER BY version_number DESC
        """), {
            'ay': context['ay_label'],
            'deg': context['degree_code'],
            'term': context['term'],
            'div': context.get('division_code')
        }).fetchall()
    
    col1, col2, col3 = st.columns([3, 2, 1])
    
    with col1:
        if versions:
            version_options = [
                f"{v[1]} - {v[2]} ({v[3].upper()})" 
                for v in versions
            ]
            
            selected_idx = st.selectbox(
                "Select Version",
                range(len(version_options)),
                format_func=lambda i: version_options[i],
                key='version_selector'
            )
            
            if selected_idx is not None:
                st.session_state.current_version_id = versions[selected_idx][0]
                
                current = versions[selected_idx]
                status_emoji = {
                    'draft': '📝',
                    'published': '✅',
                    'archived': '📦'
                }
                
                st.caption(f"{status_emoji.get(current[3], '📄')} Version: {current[1]} | "
                         f"Status: {current[3].upper()} | "
                         f"Created: {current[5]}")
        else:
            st.info("No versions exist. Create a new version to start.")
    
    with col2:
        if st.button("➕ Create New Version", use_container_width=True):
            st.session_state.show_create_version_form = True
            st.rerun()
    
    with col3:
        if st.session_state.get('current_version_id') and versions:
            current = [v for v in versions if v[0] == st.session_state.current_version_id][0]
            
            if current[3] == 'draft':
                if st.button("✅ Publish", use_container_width=True):
                    if publish_version(engine, current[0]):
                        st.success("Version published!")
                        st.rerun()
    
    # Create version form
    if st.session_state.get('show_create_version_form'):
        with st.form("create_version_form"):
            st.markdown("#### Create New Version")
            
            version_name = st.text_input("Version Name", value=f"Timetable Draft")
            
            col_a, col_b = st.columns(2)
            
            with col_a:
                submit = st.form_submit_button("Create", type="primary")
            
            with col_b:
                cancel = st.form_submit_button("Cancel")
            
            if submit and version_name:
                new_id = create_version(engine, context, version_name)
                st.session_state.current_version_id = new_id
                st.session_state.show_create_version_form = False
                st.success(f"✅ Created version!")
                st.rerun()
            
            if cancel:
                st.session_state.show_create_version_form = False
                st.rerun()


# ============================================================================
# CELL RENDERING - WITH UNIFIED MERGED CELL DISPLAY
# ============================================================================

def render_merged_cell_content(existing: Dict, show_fac: bool, bridge_length: int) -> str:
    """
    Render the content of a merged cell as a single unified display.
    No "merged" text - just clean subject/faculty info in one block.
    """
    subj = existing.get('subject_name') or existing.get('subject_code', 'Unknown')
    fac = existing.get('faculty_name', '')
    
    # Subject name - larger font
    content_html = f'<div style="font-size: 13px; font-weight: bold; margin-bottom: 6px; color: #1a1a1a;">{subj}</div>'
    
    # Faculty name if enabled
    if show_fac and fac:
        content_html += f'<div style="font-size: 11px; color: #555; margin-bottom: 4px;">{fac}</div>'
    
    # Subject type badge
    subject_type = existing.get('subject_type', '')
    if subject_type:
        type_color = SUBJECT_TYPE_COLORS.get(subject_type, '#E0E0E0')
        content_html += f'<div style="display: inline-block; font-size: 9px; color: #333; background: {type_color}; padding: 2px 8px; border-radius: 10px; margin-top: 2px;">{subject_type}</div>'
    
    # Period count for merged cells
    if bridge_length > 1:
        content_html += f'<div style="font-size: 9px; color: #1976D2; margin-top: 6px; font-weight: 600;">🔗 {bridge_length} periods</div>'
    
    return content_html


def render_cell(engine: Engine, ctx: Dict, year: int, div: str, day: int, day_name: str,
                period: Dict, periods_list: List[Dict], edit_mode: bool, show_fac: bool, 
                bridge_mode: bool, ver: int = None):
    """
    Render a single timetable cell with proper merged cell handling.
    Merged cells span multiple periods and display as one unified block.
    """
    
    pid = period['id']
    key = f"c_{day}_{pid}_{year}_{div or 'X'}"
    year_bg = YEAR_COLORS.get(year, '#FFF')
    
    existing = get_slot(engine, ctx, year, div, day, pid, ver)
    
    # Check for conflicts
    conflicts = get_conflicts_for_cell(engine, ctx, year, div, day, pid) if existing else []
    has_error = any(c['severity'] == 'error' for c in conflicts)
    has_warning = any(c['severity'] == 'warning' for c in conflicts)
    
    # Determine styling based on state
    if has_error:
        year_bg = '#FFCDD2'  # Light red
        border_style = '3px solid #D32F2F'
    elif has_warning:
        year_bg = '#FFF9C4'  # Light yellow
        border_style = '2px solid #F57C00'
    else:
        border_style = '1px solid #ccc'
    
    is_bridge_start = existing and existing.get('bridge_group_id') and existing.get('bridge_position') == 1
    is_bridge_continuation = existing and existing.get('bridge_group_id') and existing.get('bridge_position', 1) > 1
    bridge_length = existing.get('bridge_length', 1) if existing else 1
    bridge_id = existing.get('bridge_group_id') if existing else None
    
    # Skip rendering for continuation cells (they're part of merged cell above)
    if is_bridge_continuation:
        return
    
    # MERGED CELL - Render as single unified block (NO "merged" text)
    if existing and is_bridge_start and bridge_length > 1:
        # Calculate height based on number of merged periods (approximate)
        min_height = 60 + (bridge_length - 1) * 65
        
        # Build conflict badge if needed
        conflict_badge = ""
        if conflicts:
            error_count = sum(1 for c in conflicts if c['severity'] == 'error')
            warning_count = sum(1 for c in conflicts if c['severity'] == 'warning')
            
            if error_count > 0:
                conflict_badge = f'<div style="position: absolute; top: 4px; right: 4px; background: #D32F2F; color: white; font-size: 9px; padding: 3px 6px; border-radius: 8px; font-weight: bold; z-index: 10;">❌ {error_count}</div>'
            elif warning_count > 0:
                conflict_badge = f'<div style="position: absolute; top: 4px; right: 4px; background: #F57C00; color: white; font-size: 9px; padding: 3px 6px; border-radius: 8px; font-weight: bold; z-index: 10;">⚡ {warning_count}</div>'
        
        # Render the unified merged cell
        content = render_merged_cell_content(existing, show_fac, bridge_length)
        
        st.markdown(
            f"""<div style="background: {year_bg}; padding: 14px; border-radius: 6px; 
                min-height: {min_height}px; font-size: 11px; border: {border_style}; 
                position: relative; box-shadow: 0 2px 6px rgba(0,0,0,0.12); display: flex; 
                flex-direction: column; justify-content: center; align-items: center; 
                text-align: center; gap: 4px;">
                {conflict_badge}
                {content}
            </div>""",
            unsafe_allow_html=True
        )
        
        # Show conflicts in expander if any
        if conflicts:
            with st.expander(f"⚠️ {len(conflicts)} Conflict(s)", expanded=False):
                for conf in conflicts:
                    icon = '❌' if conf['severity'] == 'error' else '⚡'
                    st.caption(f"{icon} {conf['message']}")
        
        # Edit controls for merged cell
        if edit_mode:
            c1, c2, c3, c4, c5 = st.columns(5)
            
            if c1.button("➕", key=f"ext_{key}", help="Extend by 1 period", use_container_width=True):
                extend_bridge(engine, bridge_id)
                st.rerun()
            
            if c2.button("➖", key=f"shr_{key}", help="Shrink by 1 period", use_container_width=True):
                shrink_bridge(engine, bridge_id)
                st.rerun()
            
            if c3.button("🔀", key=f"unm_{key}", help="Unmerge to individual slots", use_container_width=True):
                unmerge_bridge(engine, bridge_id)
                st.rerun()
            
            if c4.button("✏️", key=f"e_{key}", help="Edit", use_container_width=True):
                st.session_state[f"edit_{key}"] = True
                st.rerun()
            
            if c5.button("🗑️", key=f"d_{key}", help="Delete entire merged slot", use_container_width=True):
                delete_bridge(engine, bridge_id)
                st.rerun()
    
    # SINGLE SLOT (not merged)
    elif existing and not is_bridge_continuation:
        # Build conflict badge
        conflict_badge = ""
        if conflicts:
            error_count = sum(1 for c in conflicts if c['severity'] == 'error')
            warning_count = sum(1 for c in conflicts if c['severity'] == 'warning')
            
            if error_count > 0:
                conflict_badge = f'<div style="position: absolute; top: 2px; right: 2px; background: #D32F2F; color: white; font-size: 9px; padding: 2px 5px; border-radius: 8px; font-weight: bold;">❌ {error_count}</div>'
            elif warning_count > 0:
                conflict_badge = f'<div style="position: absolute; top: 2px; right: 2px; background: #F57C00; color: white; font-size: 9px; padding: 2px 5px; border-radius: 8px; font-weight: bold;">⚡ {warning_count}</div>'
        
        content = render_merged_cell_content(existing, show_fac, 1)
        
        st.markdown(
            f"""<div style="background: {year_bg}; padding: 10px; border-radius: 4px; 
                min-height: 60px; font-size: 11px; border: {border_style}; 
                position: relative; display: flex; flex-direction: column; 
                justify-content: center; align-items: center; text-align: center;">
                {conflict_badge}
                {content}
            </div>""",
            unsafe_allow_html=True
        )
        
        # Show conflicts
        if conflicts:
            with st.expander(f"⚠️ {len(conflicts)} Conflict(s)", expanded=False):
                for conf in conflicts:
                    icon = '❌' if conf['severity'] == 'error' else '⚡'
                    st.caption(f"{icon} {conf['message']}")
        
        # Edit controls
        if edit_mode:
            c1, c2 = st.columns(2)
            if c1.button("✏️", key=f"e_{key}", help="Edit", use_container_width=True):
                st.session_state[f"edit_{key}"] = True
                st.rerun()
            if c2.button("🗑️", key=f"d_{key}", help="Delete", use_container_width=True):
                delete_slot(engine, ctx, year, div, day, pid, ver)
                st.rerun()
    
    # EMPTY CELL
    else:
        st.markdown(
            f"""<div style="background: {year_bg}; padding: 10px; border-radius: 4px; 
                min-height: 60px; border: 1px solid #ddd; text-align: center; 
                display: flex; align-items: center; justify-content: center; 
                color: #bbb; font-size: 24px; opacity: 0.5;">
                ∅
            </div>""",
            unsafe_allow_html=True
        )
        
        if edit_mode:
            if st.button("➕", key=f"a_{key}", help="Add Subject", use_container_width=True):
                st.session_state[f"edit_{key}"] = True
                st.session_state[f"bridge_mode_{key}"] = bridge_mode
                st.rerun()
    
    # Edit form if needed
    if edit_mode and st.session_state.get(f"edit_{key}"):
        with st.expander(f"📝 {day_name} P{pid} Y{year}", expanded=True):
            render_editor(engine, ctx, year, div, day, pid, periods_list, key, existing, 
                         st.session_state.get(f"bridge_mode_{key}", bridge_mode), ver)


def render_editor(engine: Engine, ctx: Dict, year: int, div: str, day: int, 
                  period: int, periods_list: List[Dict], key: str, existing: Optional[Dict], 
                  bridge_mode: bool, ver: int = None):
    """Render the editor form with conflict validation"""
    
    subjects = get_distribution_subjects(engine, ctx['ay_label'], ctx['degree_code'], year, ctx['term'], div)
    
    if not subjects:
        st.warning(f"No subjects in distribution for Year {year}")
        if st.button("Cancel", key=f"x1_{key}"):
            st.session_state[f"edit_{key}"] = False
            st.rerun()
        return
    
    subj_opts = ["-- Select Subject --"] + [s['display_name'] for s in subjects]
    
    curr_idx = 0
    if existing and existing.get('subject_code'):
        for i, s in enumerate(subjects):
            if s['subject_code'] == existing['subject_code']:
                curr_idx = i + 1
                break
    
    sel_subj = st.selectbox("Subject", subj_opts, index=curr_idx, key=f"subj_{key}")
    
    if sel_subj != "-- Select Subject --":
        subj_data = next((s for s in subjects if s['display_name'] == sel_subj), None)
        
        if subj_data:
            st.caption(f"Type: {subj_data.get('subject_type', 'N/A')}")
            
            # Show distribution status if available
            if DISTRIBUTION_TRACKING_AVAILABLE and subj_data.get('offering_id'):
                dist_status = get_distribution_status(subj_data['offering_id'], div)
                if dist_status:
                    remaining = dist_status['remaining_periods']
                    status_color = '#4CAF50' if remaining > 0 else '#F44336'
                    st.markdown(
                        f'<div style="background: {status_color}20; padding: 8px; border-radius: 4px; margin: 8px 0;">'
                        f'<strong>Distribution:</strong> {dist_status["scheduled_period_slots"]}/{dist_status["planned_total_periods"]} periods used '
                        f'({remaining} remaining)</div>',
                        unsafe_allow_html=True
                    )
            
            faculty = get_faculty_list(engine, ctx['degree_code'])
            
            if faculty:
                fac_opts = ["-- Select Faculty --"] + [f"{f['faculty_name']} ({f.get('designation', '')})" for f in faculty]
                
                fac_idx = 0
                if existing and existing.get('faculty_in_charge'):
                    for i, f in enumerate(faculty):
                        if f['email'] == existing['faculty_in_charge']:
                            fac_idx = i + 1
                            break
                
                sel_fac = st.selectbox("Faculty", fac_opts, index=fac_idx, key=f"fac_{key}")
                
                bridge_length = 1
                if bridge_mode:
                    st.markdown("---")
                    st.markdown("**🔗 Bridge (Merge Periods)**")
                    
                    current_period_idx = next((i for i, p in enumerate(periods_list) if p['id'] == period), 0)
                    max_bridge = len(periods_list) - current_period_idx
                    
                    if max_bridge > 1:
                        bridge_length = st.slider(
                            "Number of periods to merge",
                            min_value=1,
                            max_value=min(max_bridge, 6),
                            value=existing.get('bridge_length', 1) if existing else 1,
                            key=f"bridge_{key}"
                        )
                        
                        if bridge_length > 1:
                            merged_periods = [periods_list[current_period_idx + i]['label'] 
                                            for i in range(bridge_length) 
                                            if current_period_idx + i < len(periods_list)]
                            st.info(f"Will merge: {' + '.join(merged_periods)}")
                    else:
                        st.caption("This is the last period - cannot create bridge")
                
                c1, c2 = st.columns(2)
                
                if c1.button("💾 Save", key=f"sv_{key}", type="primary", use_container_width=True):
                    try:
                        fac_email = None
                        if sel_fac != "-- Select Faculty --":
                            fac_data = faculty[fac_opts.index(sel_fac) - 1]
                            fac_email = fac_data['email']
                        
                        if bridge_length > 1:
                            create_bridge(
                                engine, ctx, year, div, day, period, bridge_length,
                                subj_data['subject_code'], subj_data.get('subject_type'),
                                subj_data.get('offering_id'), fac_email, ver
                            )
                        else:
                            save_slot(engine, ctx, year, div, day, period,
                                     subj_data['subject_code'], subj_data.get('subject_type'),
                                     subj_data.get('offering_id'), fac_email, ver)
                        
                        st.session_state[f"edit_{key}"] = False
                        st.success("✅ Saved!")
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))
                
                if c2.button("Cancel", key=f"x2_{key}", use_container_width=True):
                    st.session_state[f"edit_{key}"] = False
                    st.rerun()
            else:
                st.info("No faculty found for this degree")
                if st.button("Cancel", key=f"x3_{key}"):
                    st.session_state[f"edit_{key}"] = False
                    st.rerun()
    else:
        if st.button("Cancel", key=f"x4_{key}"):
            st.session_state[f"edit_{key}"] = False
            st.rerun()
