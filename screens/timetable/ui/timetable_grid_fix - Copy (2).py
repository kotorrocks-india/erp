# ============================================================================
# MERGED TIMETABLE GRID - Interactive UI + Full Features
# ============================================================================
# Combines:
# - Interactive Streamlit UI from timetable_grid_fix.py
# - Versioning system from timetable_excel_complete.py
# - Conflict detection from timetable_excel_complete.py
# - All bridging operations from both files
# ============================================================================

import streamlit as st
import pandas as pd
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.engine import Engine
from sqlalchemy import text
import json
import uuid
from datetime import datetime

# Import conflict detector if available
try:
    from conflict_detector import (
        detect_faculty_conflicts,
        detect_student_conflicts,
        detect_distribution_violations,
        detect_room_conflicts
    )
    CONFLICT_DETECTION_AVAILABLE = True
except ImportError:
    CONFLICT_DETECTION_AVAILABLE = False


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
# VERSIONING FUNCTIONS (from complete)
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
# CONFLICT DETECTION (from complete)
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
        
        # 2. DISTRIBUTION VIOLATION CHECK
        result = conn.execute(text("""
            SELECT 
                d.mon_periods + d.tue_periods + d.wed_periods + 
                d.thu_periods + d.fri_periods + d.sat_periods as planned_total,
                COALESCE(
                    (SELECT COUNT(*) 
                     FROM timetable_slots ts
                     WHERE ts.offering_id = :offering_id
                       AND ts.division_code = :div
                       AND ts.year = :year
                       AND ts.term = :term
                       AND ts.ay_label = :ay
                       AND ts.status != 'deleted'),
                    0
                ) as already_scheduled
            FROM weekly_subject_distribution d
            WHERE d.offering_id = :offering_id
              AND d.division_code = :div
              AND d.year = :year
              AND d.term = :term
              AND d.ay_label = :ay
        """), {
            'offering_id': offering_id, 'div': division,
            'year': year, 'term': context['term'],
            'ay': context['ay_label']
        }).fetchone()
        
        if result:
            planned_total = result[0]
            already_scheduled = result[1]
            
            if already_scheduled + bridge_length > planned_total:
                return False, (
                    f"❌ Distribution Violation: {subject_code} has only "
                    f"{planned_total - already_scheduled} period(s) remaining "
                    f"(trying to add {bridge_length})"
                )
        
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
        
        # Check faculty conflicts
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
        
        # Check distribution violations
        dist_conflicts = detect_distribution_violations(
            context['ay_label'], context['degree_code'], context['term']
        )
        
        for conflict in dist_conflicts:
            if (conflict.get('subject_code') == slot['subject_code'] and 
                conflict.get('division_code') == slot['division_code']):
                conflicts.append({
                    'type': 'distribution',
                    'severity': conflict.get('severity', 'warning'),
                    'message': conflict.get('message', 'Distribution violation')
                })
    
    return conflicts


# ============================================================================
# DATABASE FUNCTIONS (from fix with schema checks)
# ============================================================================

def ensure_tables(engine: Engine):
    """Ensure required tables exist"""
    with engine.begin() as conn:
        # Check if table exists
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
        
        # Check and create timetable_versions if missing
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
    
    # Validate assignment
    is_valid, error_msg = validate_assignment(
        engine, ctx, year, div, day, period,
        offering_id, subj, faculty_email, 1
    )
    
    if not is_valid:
        raise ValueError(error_msg)
    
    with engine.begin() as conn:
        # Delete existing
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
        
        # Insert new
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


# ============================================================================
# BRIDGING FUNCTIONS (merged from both)
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


def get_years_in_distribution(engine: Engine, ctx: Dict) -> List[int]:
    """Get years that have subjects in distribution"""
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT DISTINCT year
            FROM weekly_subject_distribution
            WHERE ay_label = :ay AND degree_code = :deg AND term = :term
            ORDER BY year
        """), {'ay': ctx['ay_label'], 'deg': ctx['degree_code'], 'term': ctx['term']})
        return [r[0] for r in result]


# ============================================================================
# VERSION PANEL UI (from complete)
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
# INTERACTIVE CELL RENDERER (from fix, enhanced with conflicts)
# ============================================================================

def render_cell(engine: Engine, ctx: Dict, year: int, div: str, day: int, day_name: str,
                period: Dict, periods_list: List[Dict], edit_mode: bool, show_fac: bool, 
                bridge_mode: bool, ver: int = None):
    """Render a single timetable cell with conflict indicators"""
    
    pid = period['id']
    key = f"c_{day}_{pid}_{year}_{div or 'X'}"
    year_bg = YEAR_COLORS.get(year, '#FFF')
    
    existing = get_slot(engine, ctx, year, div, day, pid, ver)
    
    # Check for conflicts
    conflicts = get_conflicts_for_cell(engine, ctx, year, div, day, pid) if existing else []
    has_error = any(c['severity'] == 'error' for c in conflicts)
    has_warning = any(c['severity'] == 'warning' for c in conflicts)
    
    # Adjust styling based on conflicts
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
    
    if is_bridge_continuation:
        st.markdown(
            f"""<div style="background: linear-gradient(135deg, {year_bg} 0%, #ddd 100%); 
                padding: 6px; border-radius: 4px; min-height: 50px; 
                border: 1px dashed #999; text-align: center; opacity: 0.6;">
                <span style="font-size: 10px; color: #666;">⬅️ merged</span>
            </div>""",
            unsafe_allow_html=True
        )
        return
    
    if existing and not is_bridge_continuation:
        subj = existing.get('subject_name') or existing.get('subject_code', 'Unknown')
        fac = existing.get('faculty_name', '')
        
        if is_bridge_start:
            border_style = "2px solid #1976D2"
            merge_indicator = f'<div style="font-size:9px; color:#1976D2; margin-top:4px;">🔗 {bridge_length} periods</div>'
        else:
            merge_indicator = ""
        
        # Conflict badge
        conflict_badge = ""
        if conflicts:
            error_count = sum(1 for c in conflicts if c['severity'] == 'error')
            warning_count = sum(1 for c in conflicts if c['severity'] == 'warning')
            
            if error_count > 0:
                conflict_badge = f'<div style="position: absolute; top: 2px; right: 2px; background: #D32F2F; color: white; font-size: 9px; padding: 2px 5px; border-radius: 8px; font-weight: bold;">⚠️ {error_count}</div>'
            elif warning_count > 0:
                conflict_badge = f'<div style="position: absolute; top: 2px; right: 2px; background: #F57C00; color: white; font-size: 9px; padding: 2px 5px; border-radius: 8px; font-weight: bold;">⚡ {warning_count}</div>'
        
        st.markdown(
            f"""<div style="background: {year_bg}; padding: 6px; border-radius: 4px; 
                min-height: 50px; font-size: 11px; border: {border_style}; position: relative;">
                {conflict_badge}
                <strong>{subj}</strong>
                {'<br><span style="color:#666">' + fac + '</span>' if show_fac and fac else ''}
                {merge_indicator}
            </div>""",
            unsafe_allow_html=True
        )
        
        # Show conflicts
        if conflicts:
            with st.expander(f"⚠️ {len(conflicts)} Conflict(s)", expanded=False):
                for conf in conflicts:
                    icon = '❌' if conf['severity'] == 'error' else '⚡'
                    st.caption(f"{icon} {conf['message']}")
        
        if edit_mode:
            if is_bridge_start:
                c1, c2, c3 = st.columns(3)
                if c1.button("➕", key=f"ext_{key}", help="Extend bridge"):
                    extend_bridge(engine, bridge_id)
                    st.rerun()
                if c2.button("➖", key=f"shr_{key}", help="Shrink bridge"):
                    shrink_bridge(engine, bridge_id)
                    st.rerun()
                if c3.button("🔓", key=f"unm_{key}", help="Unmerge"):
                    unmerge_bridge(engine, bridge_id)
                    st.rerun()
                
                c4, c5 = st.columns(2)
                if c4.button("✏️", key=f"e_{key}", help="Edit"):
                    st.session_state[f"edit_{key}"] = True
                    st.rerun()
                if c5.button("🗑️", key=f"d_{key}", help="Delete"):
                    delete_bridge(engine, bridge_id)
                    st.rerun()
            else:
                c1, c2 = st.columns(2)
                if c1.button("✏️", key=f"e_{key}", help="Edit", use_container_width=True):
                    st.session_state[f"edit_{key}"] = True
                    st.rerun()
                if c2.button("🗑️", key=f"d_{key}", help="Delete", use_container_width=True):
                    delete_slot(engine, ctx, year, div, day, pid, ver)
                    st.rerun()
    else:
        st.markdown(
            f"""<div style="background: {year_bg}; padding: 6px; border-radius: 4px; 
                min-height: 50px; border: 1px solid #ccc; text-align: center;">
            </div>""",
            unsafe_allow_html=True
        )
        
        if edit_mode:
            if st.button("➕", key=f"a_{key}", help="Add Subject", use_container_width=True):
                st.session_state[f"edit_{key}"] = True
                st.session_state[f"bridge_mode_{key}"] = bridge_mode
                st.rerun()
    
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


# ============================================================================
# MAIN RENDERER
# ============================================================================

def render_complete_excel_timetable(context: Dict, engine: Engine):
    """Main entry point - renders the interactive timetable grid with full features"""
    
    ensure_tables(engine)
    
    # Initialize state
    if 'current_version_id' not in st.session_state:
        st.session_state.current_version_id = None
    if 'tt_edit_mode' not in st.session_state:
        st.session_state.tt_edit_mode = False
    if 'tt_show_faculty' not in st.session_state:
        st.session_state.tt_show_faculty = True
    
    st.subheader("📊 Excel-Style Timetable System")
    st.caption("Complete timetable management with versioning, conflict detection, and cell merging")
    
    # Version management panel
    render_version_panel(engine, context)
    
    st.divider()
    
    # Only show timetable if version is selected
    if not st.session_state.current_version_id:
        st.info("👆 Create or select a version to start editing timetable")
        return
    
    ver = st.session_state.current_version_id
    
    # Controls
    st.markdown("### 📅 Weekly Timetable")
    
    col1, col2, col3, col4 = st.columns([1.5, 1.5, 1.5, 1])
    
    with col1:
        mode = st.radio("Mode", ["👁️ View Only", "✏️ Edit Mode"], 
                       index=1 if st.session_state.tt_edit_mode else 0,
                       horizontal=True, key="tt_mode_radio")
        st.session_state.tt_edit_mode = (mode == "✏️ Edit Mode")
    
    with col2:
        st.session_state.tt_show_faculty = st.checkbox(
            "Show Faculty Names", 
            value=st.session_state.tt_show_faculty,
            key="tt_show_fac_check"
        )
    
    with col3:
        bridge_mode = st.checkbox("🔗 Bridge Mode (Merge Cells)", key="tt_bridge_check",
                                 help="Enable to merge periods")
    
    with col4:
        if st.button("🔄 Refresh", use_container_width=True):
            st.rerun()
    
    if st.session_state.tt_edit_mode:
        if CONFLICT_DETECTION_AVAILABLE:
            st.info("✏️ **Edit Mode Active:** Click ➕ to add subjects. Conflicts are automatically detected and highlighted.")
        else:
            st.warning("✏️ **Edit Mode Active:** Click ➕ to add subjects. ⚠️ Conflict detection unavailable.")
    
    # Get periods
    periods = get_template_periods(engine, context['ay_label'], context['degree_code'], context['term'])
    
    if not periods:
        st.error("❌ No published template found. Please publish a timegrid template first.")
        st.stop()
    
    # Get years and divisions
    years = get_years_in_distribution(engine, context) or [1, 2, 3, 4]
    divisions = get_divisions(engine, context) or [None]
    
    # Days
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    day_map = {d: i + 1 for i, d in enumerate(days)}
    
    # Render each day
    for day_name in days:
        day_num = day_map[day_name]
        
        st.markdown(
            f'<div style="background: {HEADER_COLORS["day"]}; padding: 10px; '
            f'text-align: center; font-weight: bold; font-size: 16px; '
            f'color: white; margin-top: 15px; border-radius: 4px;">'
            f'{day_name.upper()}</div>',
            unsafe_allow_html=True
        )
        
        # Period headers
        cols = st.columns([1.5] + [1] * len(periods))
        cols[0].markdown("**PERIODS**")
        for i, p in enumerate(periods):
            cols[i + 1].markdown(f"**{p['label']}**")
        
        # Time row
        time_cols = st.columns([1.5] + [1] * len(periods))
        time_cols[0].markdown("*TIME*")
        for i, p in enumerate(periods):
            t = f"{p.get('start_time', '')} - {p.get('end_time', '')}"
            time_cols[i + 1].caption(t)
        
        # Year rows
        for yr in years:
            for div in divisions:
                sem = ['I', 'III', 'V', 'VII', 'IX'][yr - 1] if yr <= 5 else str(yr * 2 - 1)
                ord_name = ['1st', '2nd', '3rd', '4th', '5th'][yr - 1] if yr <= 5 else f'{yr}th'
                div_lbl = f" ({div})" if div else ""
                
                row_cols = st.columns([1.5] + [1] * len(periods))
                
                row_cols[0].markdown(
                    f'<div style="background: {YEAR_COLORS.get(yr, "#FFF")}; '
                    f'padding: 8px; font-weight: bold; border-radius: 4px; '
                    f'border: 1px solid #ccc; font-size: 12px;">'
                    f'{ord_name} Year Semester {sem}{div_lbl}</div>',
                    unsafe_allow_html=True
                )
                
                for i, period in enumerate(periods):
                    with row_cols[i + 1]:
                        render_cell(
                            engine, context, yr, div, day_num, day_name,
                            period, periods, st.session_state.tt_edit_mode,
                            st.session_state.tt_show_faculty, bridge_mode, ver
                        )
        
        st.markdown("---")
    
    # Stats
    with st.expander("📊 Timetable Statistics"):
        with engine.connect() as conn:
            stats = conn.execute(text("""
                SELECT 
                    COUNT(*) as total_slots,
                    COUNT(DISTINCT subject_code) as subjects,
                    COUNT(DISTINCT faculty_in_charge) as faculty
                FROM timetable_slots
                WHERE ay_label = :ay AND degree_code = :deg AND term = :term
                  AND status = 'active'
            """), {
                'ay': context['ay_label'],
                'deg': context['degree_code'],
                'term': context['term']
            }).fetchone()
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Slots", stats[0] if stats else 0)
            c2.metric("Subjects", stats[1] if stats else 0)
            c3.metric("Faculty", stats[2] if stats else 0)


if __name__ == "__main__":
    st.error("Import this module from app_weekly_planner.py")
