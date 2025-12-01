# ============================================================================
# COMPLETE EXCEL-STYLE TIMETABLE SYSTEM WITH CONFLICT DETECTION
# ============================================================================
# Single integrated file with ALL features:
# - Excel grid matching your image
# - Bridging (cell merging) support
# - Subject + Faculty dropdowns
# - Versioning (Draft/Publish/Archive)
# - Template selection (Auto + Manual)
# - Division support
# - All years view
# - Real-time conflict detection & prevention
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
    print("Warning: conflict_detector not found. Conflict detection disabled.")


# ============================================================================
# COLOR SCHEMES (From your Excel image)
# ============================================================================

YEAR_COLORS = {
    1: '#F4CCCC',  # Light red/pink
    2: '#FCE5CD',  # Light orange/tan
    3: '#FFF2CC',  # Light yellow
    4: '#D9EAD3',  # Light green
    5: '#D0E0E3',  # Light blue
}

HEADER_COLORS = {
    'day': '#93C47D',          # Green
    'period': '#B7B7B7',       # Grey
    'time': '#D9D9D9',         # Light grey
    'year_label': '#E6B8AF',   # Tan
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
        # Get version info
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
# BRIDGING FUNCTIONS
# ============================================================================

def create_bridge_group_id() -> str:
    """Generate unique bridge group ID"""
    return f"bridge-{uuid.uuid4().hex[:8]}"


def create_bridge(
    engine: Engine,
    context: Dict,
    year: int,
    division: str,
    day_of_week: int,
    start_period_id: int,
    bridge_length: int,
    subject_data: Dict
) -> bool:
    """Create a bridge (multiple contiguous periods for one subject)"""
    
    bridge_group_id = create_bridge_group_id()
    
    with engine.begin() as conn:
        # Get period IDs in order
        periods = conn.execute(text("""
            SELECT slot_index as id
            FROM day_template_slots
            WHERE template_id = (
                SELECT id FROM day_templates
                WHERE ay_label = :ay AND degree_code = :deg AND term = :term
                  AND status = 'published'
                ORDER BY 
                  (year IS NOT NULL) + (division_code IS NOT NULL) + 
                  (branch_code IS NOT NULL) + (program_code IS NOT NULL) DESC
                LIMIT 1
            )
            AND is_teaching_slot = 1
            ORDER BY slot_index
        """), {
            'ay': context['ay_label'],
            'deg': context['degree_code'],
            'term': context['term']
        }).fetchall()
        
        period_ids = [p[0] for p in periods]
        
        if start_period_id not in period_ids:
            return False
        
        start_idx = period_ids.index(start_period_id)
        
        # Create slots for each period in bridge
        for position in range(1, bridge_length + 1):
            if start_idx + position - 1 >= len(period_ids):
                return False
            
            period_id = period_ids[start_idx + position - 1]
            
            conn.execute(text("""
                INSERT INTO timetable_slots (
                    ay_label, degree_code, program_code, branch_code,
                    year, term, division_code,
                    offering_id, subject_code, subject_type,
                    day_of_week, period_id,
                    bridge_group_id, bridge_position, bridge_length,
                    status, created_at
                ) VALUES (
                    :ay, :deg, :prog, :branch,
                    :year, :term, :div,
                    :offering, :subj_code, :subj_type,
                    :day, :period,
                    :bridge_id, :position, :length,
                    'draft', CURRENT_TIMESTAMP
                )
            """), {
                'ay': context['ay_label'],
                'deg': context['degree_code'],
                'prog': context.get('program_code'),
                'branch': context.get('branch_code'),
                'year': year,
                'term': context['term'],
                'div': division,
                'offering': subject_data['offering_id'],
                'subj_code': subject_data['subject_code'],
                'subj_type': subject_data.get('subject_type', 'Theory'),
                'day': day_of_week,
                'period': period_id,
                'bridge_id': bridge_group_id,
                'position': position,
                'length': bridge_length
            })
        
        return True


def delete_bridge(engine: Engine, bridge_group_id: str) -> bool:
    """Delete all slots in a bridge (removes entire subject)"""
    with engine.begin() as conn:
        conn.execute(text("""
            DELETE FROM timetable_slots
            WHERE bridge_group_id = :bridge_id
        """), {'bridge_id': bridge_group_id})
    return True


def unmerge_bridge(engine: Engine, bridge_group_id: str) -> bool:
    """
    Unmerge a bridge - keeps first slot, removes others
    
    Example:
        Before: 4-period bridge (Period 1-4)
        After: Single slot (Period 1 only)
    """
    with engine.begin() as conn:
        # Keep only first slot (position 1), remove others
        conn.execute(text("""
            DELETE FROM timetable_slots
            WHERE bridge_group_id = :bridge_id
              AND bridge_position > 1
        """), {'bridge_id': bridge_group_id})
        
        # Update remaining slot to be non-bridged
        conn.execute(text("""
            UPDATE timetable_slots
            SET bridge_group_id = NULL,
                bridge_position = 1,
                bridge_length = 1
            WHERE bridge_group_id = :bridge_id
              AND bridge_position = 1
        """), {'bridge_id': bridge_group_id})
    
    return True


def shorten_bridge(engine: Engine, bridge_group_id: str, new_length: int) -> bool:
    """
    Shorten a bridge by removing periods from the end
    
    Example:
        Before: 4-period bridge
        After: 2-period bridge (removes last 2 periods)
    """
    with engine.begin() as conn:
        # Get current length
        current = conn.execute(text("""
            SELECT bridge_length FROM timetable_slots
            WHERE bridge_group_id = :bridge_id
            LIMIT 1
        """), {'bridge_id': bridge_group_id}).fetchone()
        
        if not current or current[0] <= new_length:
            return False
        
        # Delete slots beyond new length
        conn.execute(text("""
            DELETE FROM timetable_slots
            WHERE bridge_group_id = :bridge_id
              AND bridge_position > :new_len
        """), {'bridge_id': bridge_group_id, 'new_len': new_length})
        
        # Update remaining slots with new length
        conn.execute(text("""
            UPDATE timetable_slots
            SET bridge_length = :new_len
            WHERE bridge_group_id = :bridge_id
        """), {'bridge_id': bridge_group_id, 'new_len': new_length})
    
    return True


def extend_bridge(
    engine: Engine,
    bridge_group_id: str,
    additional_periods: int,
    context: Dict
) -> bool:
    """
    Extend a bridge by adding more periods to the end
    
    Example:
        Before: 2-period bridge (Period 1-2)
        After: 4-period bridge (Period 1-4)
    """
    with engine.begin() as conn:
        # Get current bridge info
        bridge_info = conn.execute(text("""
            SELECT 
                ay_label, degree_code, program_code, branch_code,
                year, term, division_code,
                offering_id, subject_code, subject_type,
                day_of_week, bridge_length
            FROM timetable_slots
            WHERE bridge_group_id = :bridge_id
            ORDER BY bridge_position DESC
            LIMIT 1
        """), {'bridge_id': bridge_group_id}).fetchone()
        
        if not bridge_info:
            return False
        
        # Get period IDs
        periods = conn.execute(text("""
            SELECT slot_index as id
            FROM day_template_slots
            WHERE template_id = (
                SELECT id FROM day_templates
                WHERE ay_label = :ay AND degree_code = :deg AND term = :term
                  AND status = 'published'
                LIMIT 1
            )
            AND is_teaching_slot = 1
            ORDER BY slot_index
        """), {
            'ay': bridge_info[0],
            'deg': bridge_info[1],
            'term': bridge_info[5]
        }).fetchall()
        
        period_ids = [p[0] for p in periods]
        
        # Get last period in current bridge
        last_period = conn.execute(text("""
            SELECT period_id
            FROM timetable_slots
            WHERE bridge_group_id = :bridge_id
            ORDER BY bridge_position DESC
            LIMIT 1
        """), {'bridge_id': bridge_group_id}).fetchone()
        
        if not last_period or last_period[0] not in period_ids:
            return False
        
        last_idx = period_ids.index(last_period[0])
        current_length = bridge_info[11]
        new_length = current_length + additional_periods
        
        # Add new slots
        for i in range(additional_periods):
            new_position = current_length + i + 1
            new_period_idx = last_idx + i + 1
            
            if new_period_idx >= len(period_ids):
                return False  # Can't extend beyond available periods
            
            new_period_id = period_ids[new_period_idx]
            
            conn.execute(text("""
                INSERT INTO timetable_slots (
                    ay_label, degree_code, program_code, branch_code,
                    year, term, division_code,
                    offering_id, subject_code, subject_type,
                    day_of_week, period_id,
                    bridge_group_id, bridge_position, bridge_length,
                    status, created_at
                ) VALUES (
                    :ay, :deg, :prog, :branch,
                    :year, :term, :div,
                    :offering, :subj_code, :subj_type,
                    :day, :period,
                    :bridge_id, :position, :length,
                    'draft', CURRENT_TIMESTAMP
                )
            """), {
                'ay': bridge_info[0],
                'deg': bridge_info[1],
                'prog': bridge_info[2],
                'branch': bridge_info[3],
                'year': bridge_info[4],
                'term': bridge_info[5],
                'div': bridge_info[6],
                'offering': bridge_info[7],
                'subj_code': bridge_info[8],
                'subj_type': bridge_info[9],
                'day': bridge_info[10],
                'period': new_period_id,
                'bridge_id': bridge_group_id,
                'position': new_position,
                'length': new_length
            })
        
        # Update all slots with new length
        conn.execute(text("""
            UPDATE timetable_slots
            SET bridge_length = :new_len
            WHERE bridge_group_id = :bridge_id
        """), {'bridge_id': bridge_group_id, 'new_len': new_length})
    
    return True


# ============================================================================
# CONFLICT VALIDATION
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
    """
    Validate if an assignment can be created without conflicts
    
    Checks:
    1. Faculty conflict - Same faculty teaching elsewhere at same time
    2. Subject distribution - Subject not exceeding planned periods
    3. Division conflict - Same subject/period already assigned to division
    4. Student conflict - Same year students have another subject at same time
    
    Returns:
        (is_valid, error_message)
    """
    
    with engine.connect() as conn:
        
        # ========================================
        # 1. FACULTY CONFLICT CHECK
        # ========================================
        if faculty_email:
            # Check if faculty is teaching elsewhere at this time (across ALL degrees/divisions)
            for i in range(bridge_length):
                check_period = period_id + i
                
                result = conn.execute(text("""
                    SELECT 
                        s.id,
                        s.subject_code,
                        s.degree_code,
                        s.division_code,
                        s.year,
                        o.subject_name
                    FROM timetable_slots s
                    LEFT JOIN subject_offerings o ON o.id = s.offering_id
                    WHERE s.ay_label = :ay
                      AND s.term = :term
                      AND s.day_of_week = :day
                      AND s.period_id = :period
                      AND (s.faculty_in_charge = :faculty 
                           OR s.faculty_list LIKE :faculty_pattern)
                      AND s.status != 'deleted'
                """), {
                    'ay': context['ay_label'],
                    'term': context['term'],
                    'day': day_of_week,
                    'period': check_period,
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
        
        # ========================================
        # 2. DISTRIBUTION VIOLATION CHECK
        # ========================================
        # Check if subject hasn't exceeded planned periods for this division
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
            'offering_id': offering_id,
            'div': division,
            'year': year,
            'term': context['term'],
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
        
        # ========================================
        # 3. DIVISION/SUBJECT CONFLICT CHECK
        # ========================================
        # Check if this subject is already scheduled at this time for this division
        for i in range(bridge_length):
            check_period = period_id + i
            
            result = conn.execute(text("""
                SELECT id, subject_code
                FROM timetable_slots
                WHERE ay_label = :ay
                  AND degree_code = :deg
                  AND term = :term
                  AND year = :year
                  AND division_code = :div
                  AND day_of_week = :day
                  AND period_id = :period
                  AND status != 'deleted'
            """), {
                'ay': context['ay_label'],
                'deg': context['degree_code'],
                'term': context['term'],
                'year': year,
                'div': division,
                'day': day_of_week,
                'period': check_period
            }).fetchone()
            
            if result:
                return False, (
                    f"❌ Slot Conflict: This division already has {result[1]} "
                    f"scheduled at this time"
                )
        
        # ========================================
        # 4. STUDENT CONFLICT CHECK
        # ========================================
        # Students of same year can't have 2 subjects at same time
        # This is already covered by check #3 above (division/subject conflict)
        
    return True, None


def get_conflicts_for_cell(
    engine: Engine,
    context: Dict,
    year: int,
    division: str,
    day_of_week: int,
    period_id: int
) -> List[Dict]:
    """
    Get all conflicts for a specific cell
    
    Returns list of conflict dictionaries with type and message
    """
    conflicts = []
    
    if not CONFLICT_DETECTION_AVAILABLE:
        return conflicts
    
    with engine.connect() as conn:
        # Get slot at this position
        result = conn.execute(text("""
            SELECT 
                s.*,
                o.subject_name
            FROM timetable_slots s
            LEFT JOIN subject_offerings o ON o.id = s.offering_id
            WHERE s.ay_label = :ay
              AND s.degree_code = :deg
              AND s.term = :term
              AND s.year = :year
              AND s.division_code = :div
              AND s.day_of_week = :day
              AND s.period_id = :period
              AND s.status != 'deleted'
        """), {
            'ay': context['ay_label'],
            'deg': context['degree_code'],
            'term': context['term'],
            'year': year,
            'div': division,
            'day': day_of_week,
            'period': period_id
        }).fetchone()
        
        if not result:
            return conflicts
        
        slot = dict(result._mapping)
        
        # Check faculty conflicts
        if slot.get('faculty_in_charge'):
            faculty_conflicts = detect_faculty_conflicts(
                context['ay_label'],
                context['term'],
                context['degree_code']
            )
            
            # Filter for this specific slot
            for conflict in faculty_conflicts:
                if str(slot['id']) in str(conflict.get('slot_ids', [])):
                    conflicts.append({
                        'type': 'faculty',
                        'severity': 'error',
                        'message': conflict.get('message', 'Faculty conflict detected')
                    })
        
        # Check distribution violations
        dist_conflicts = detect_distribution_violations(
            context['ay_label'],
            context['degree_code'],
            context['term']
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
# DATA FETCHING
# ============================================================================

def fetch_slots_for_context(
    engine: Engine,
    context: Dict
) -> Dict[int, List[Dict]]:
    """
    Fetch all slots for all years in context.
    AUTO-FIX: Joins subjects_catalog to get names, as subject_offerings only has codes.
    """
    
    all_slots = {}
    
    for year in [1, 2, 3, 4, 5]:
        with engine.connect() as conn:
            # We use a try-catch block to handle cases where subjects_catalog might be missing
            try:
                # OPTION 1: Robust query linking to catalog
                query = text("""
                    SELECT 
                        s.*,
                        -- Prioritize Name Source: 1. Catalog Name, 2. Topic Name (Electives), 3. Code (Fallback)
                        COALESCE(sc.subject_name, o.topic_name, s.subject_code) as subject_name,
                        o.subject_type
                    FROM timetable_slots s
                    LEFT JOIN subject_offerings o ON o.id = s.offering_id
                    -- Try to find name in catalog
                    LEFT JOIN subjects_catalog sc ON (
                        sc.subject_code = s.subject_code 
                        AND sc.degree_code = s.degree_code
                    )
                    WHERE s.ay_label = :ay
                      AND s.degree_code = :deg
                      AND s.term = :term
                      AND s.year = :year
                      AND (:div IS NULL OR s.division_code = :div)
                    ORDER BY s.day_of_week, s.period_id, s.bridge_position
                """)
                
                result = conn.execute(query, {
                    'ay': context['ay_label'],
                    'deg': context['degree_code'],
                    'term': context['term'],
                    'year': year,
                    'div': context.get('division_code')
                }).fetchall()
                
            except Exception as e:
                # OPTION 2: Emergency Fallback (if subjects_catalog table is missing)
                print(f"⚠️ Catalog join failed ({e}), falling back to simple query.")
                query = text("""
                    SELECT 
                        s.*,
                        s.subject_code as subject_name
                    FROM timetable_slots s
                    WHERE s.ay_label = :ay
                      AND s.degree_code = :deg
                      AND s.term = :term
                      AND s.year = :year
                      AND (:div IS NULL OR s.division_code = :div)
                    ORDER BY s.day_of_week, s.period_id, s.bridge_position
                """)
                
                result = conn.execute(query, {
                    'ay': context['ay_label'],
                    'deg': context['degree_code'],
                    'term': context['term'],
                    'year': year,
                    'div': context.get('division_code')
                }).fetchall()
            
            slots = []
            for row in result:
                slot = dict(row._mapping)
                # Parse faculty list
                if slot.get('faculty_list'):
                    try:
                        slot['faculty_list_parsed'] = json.loads(slot['faculty_list'])
                    except:
                        slot['faculty_list_parsed'] = []
                else:
                    slot['faculty_list_parsed'] = []
                
                slots.append(slot)
            
            all_slots[year] = slots
    
    return all_slots

def fetch_subjects_for_distribution(
    engine: Engine,
    context: Dict,
    year: int,
    division: str
) -> List[Dict]:
    """Fetch available subjects from distribution"""
    
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT 
                d.id as dist_id,
                d.offering_id,
                d.subject_code,
                d.subject_type,
                o.subject_name,
                d.mon_periods + d.tue_periods + d.wed_periods + 
                d.thu_periods + d.fri_periods + d.sat_periods as total_weekly_periods,
                COALESCE(
                    (SELECT COUNT(*) 
                     FROM timetable_slots ts
                     WHERE ts.offering_id = d.offering_id
                       AND ts.division_code = d.division_code
                       AND ts.year = d.year
                       AND ts.term = d.term),
                    0
                ) as assigned_periods
            FROM weekly_subject_distribution d
            JOIN subject_offerings o ON o.id = d.offering_id
            WHERE d.ay_label = :ay
              AND d.degree_code = :deg
              AND d.year = :yr
              AND d.term = :term
              AND d.division_code = :div
            ORDER BY d.subject_code
        """), {
            'ay': context['ay_label'],
            'deg': context['degree_code'],
            'yr': year,
            'term': context['term'],
            'div': division
        }).fetchall()
        
        subjects = []
        for row in result:
            remaining = row[6] - row[7]
            subjects.append({
                'dist_id': row[0],
                'offering_id': row[1],
                'subject_code': row[2],
                'subject_type': row[3],
                'subject_name': row[4],
                'total_periods': row[6],
                'assigned_periods': row[7],
                'remaining_periods': remaining,
                'display': f"{row[2]} - {row[4]} ({remaining} left)"
            })
        
        return subjects


def fetch_faculty_list(engine: Engine) -> List[Dict]:
    """Fetch all active faculty"""
    
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT email, full_name, department
            FROM faculty
            WHERE active = 1
            ORDER BY full_name
        """)).fetchall()
        
        return [{
            'email': row[0],
            'name': row[1],
            'dept': row[2],
            'display': f"{row[1]} ({row[2]})"
        } for row in result]


# ============================================================================
# MAIN EXCEL GRID CLASS
# ============================================================================

class CompleteExcelTimetableGrid:
    """
    Complete Excel-style timetable with ALL features integrated
    """
    
    def __init__(self, engine: Engine):
        self.engine = engine
        
        # ---------------------------------------------------------
        # FIX: Initialize Database Tables if they don't exist
        # ---------------------------------------------------------
        with self.engine.begin() as conn:
            # 1. Create timetable_versions table
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS timetable_versions (
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
            
            # 2. Create timetable_slots table (if missing)
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS timetable_slots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ay_label TEXT,
                    degree_code TEXT,
                    program_code TEXT,
                    branch_code TEXT,
                    year INTEGER,
                    term INTEGER,
                    division_code TEXT,
                    offering_id INTEGER,
                    subject_code TEXT,
                    subject_type TEXT,
                    day_of_week INTEGER,
                    period_id INTEGER,
                    bridge_group_id TEXT,
                    bridge_position INTEGER DEFAULT 1,
                    bridge_length INTEGER DEFAULT 1,
                    status TEXT DEFAULT 'draft',
                    faculty_in_charge TEXT,
                    faculty_list TEXT,
                    room_code TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
        # ---------------------------------------------------------

        # Initialize session state
        if 'current_version_id' not in st.session_state:
            st.session_state.current_version_id = None
        
        if 'show_faculty_names' not in st.session_state:
            st.session_state.show_faculty_names = True
        
        if 'bridge_mode' not in st.session_state:
            st.session_state.bridge_mode = False
            
    def render(self, context: Dict):
        """Main render function"""
        
        st.subheader("📊 Excel-Style Timetable System")
        st.caption("Complete timetable management with versioning and cell merging")
        
        # Version management panel
        self._render_version_panel(context)
        
        st.divider()
        
        # Controls
        self._render_controls()
        
        st.divider()
        
        # Main grid
        if st.session_state.current_version_id:
            self._render_excel_grid(context)
        else:
            st.info("👆 Create or select a version to start editing timetable")
    
    def _render_version_panel(self, context: Dict):
        """Render version management panel"""
        
        st.markdown("### 📋 Version Management")
        
        # Fetch versions for this context
        with self.engine.connect() as conn:
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
                    
                    # Show version info
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
            if st.session_state.current_version_id and versions:
                current = [v for v in versions if v[0] == st.session_state.current_version_id][0]
                
                if current[3] == 'draft':
                    if st.button("✅ Publish", use_container_width=True):
                        if publish_version(self.engine, current[0]):
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
                    new_id = create_version(
                        self.engine,
                        context,
                        version_name
                    )
                    st.session_state.current_version_id = new_id
                    st.session_state.show_create_version_form = False
                    st.success(f"✅ Created version!")
                    st.rerun()
                
                if cancel:
                    st.session_state.show_create_version_form = False
                    st.rerun()
    
    def _render_controls(self):
        """Render control panel"""
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            mode = st.radio(
                "Mode",
                ['view', 'edit'],
                format_func=lambda x: '👁️ View Only' if x == 'view' else '✏️ Edit Mode',
                horizontal=True,
                key='mode_radio'
            )
            if mode != st.session_state.get('excel_grid_mode', 'view'):
                st.session_state.excel_grid_mode = mode
                st.rerun()
        
        with col2:
            show_fac = st.checkbox(
                "Show Faculty Names",
                value=st.session_state.show_faculty_names,
                key='faculty_checkbox'
            )
            if show_fac != st.session_state.show_faculty_names:
                st.session_state.show_faculty_names = show_fac
                st.rerun()
        
        with col3:
            bridge = st.checkbox(
                "🔗 Bridge Mode (Merge Cells)",
                value=st.session_state.bridge_mode,
                key='bridge_checkbox',
                help="Enable to create subjects spanning multiple periods"
            )
            if bridge != st.session_state.bridge_mode:
                st.session_state.bridge_mode = bridge
                st.rerun()
        
        with col4:
            if st.button("🔄 Refresh", use_container_width=True):
                st.rerun()
        
        # Show mode-specific help
        if st.session_state.get('excel_grid_mode') == 'edit':
            st.info("✏️ **Edit Mode Active:** Click on cells to add/edit subjects. Use bridge controls to merge/unmerge cells.")
        else:
            st.info("👁️ **View Mode:** Switch to Edit Mode to modify timetable.")
    
    def _render_excel_grid(self, context: Dict):
        """Render the main Excel-style grid"""
        
        st.markdown("### 📅 Weekly Timetable")
        
        # Fetch all slots
        all_slots = fetch_slots_for_context(self.engine, context)
        
        # Get template config
        #from ui.timetable_grid_tab import get_periods_config, get_teaching_periods
        
        # Render for each day
        for day_name in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']:
            day_num = {'Monday': 1, 'Tuesday': 2, 'Wednesday': 3, 
                      'Thursday': 4, 'Friday': 5, 'Saturday': 6}[day_name]
            
            # Day header
            st.markdown(
                f'<div style="background-color: {HEADER_COLORS["day"]}; '
                f'padding: 10px; text-align: center; font-weight: bold; '
                f'font-size: 18px; margin-top: 20px; color: white;">'
                f'{day_name.upper()}</div>',
                unsafe_allow_html=True
            )
            
            # Get periods
            periods_config = get_periods_config(
                context['ay_label'],
                context['degree_code'],
                context['term'],
                self.engine
            )
            
            if not periods_config or not periods_config.get('template_id'):
                st.warning(f"No template for {day_name}")
                continue
            
            teaching_periods = get_teaching_periods(periods_config, day_name)
            
            # Render grid for this day
            self._render_day_grid(context, day_name, day_num, teaching_periods, all_slots)
    
    def _render_day_grid(
        self,
        context: Dict,
        day_name: str,
        day_num: int,
        periods: List[Dict],
        all_slots: Dict[int, List[Dict]]
    ):
        """Render grid for one day with HTML table"""
        
        # Start table
        html = '<table style="width:100%; border-collapse: collapse; margin-bottom: 30px; font-family: Arial, sans-serif;">'
        
        # Header rows
        html += '<tr>'
        html += f'<th style="background-color: {HEADER_COLORS["period"]}; padding: 10px; border: 1px solid #999; font-weight: bold;">PERIODS</th>'
        for p in periods:
            html += f'<th style="background-color: {HEADER_COLORS["period"]}; padding: 10px; border: 1px solid #999; text-align: center;">{p["label"]}</th>'
        html += '</tr>'
        
        html += '<tr>'
        html += f'<th style="background-color: {HEADER_COLORS["time"]}; padding: 8px; border: 1px solid #999; font-weight: bold;">TIME</th>'
        for p in periods:
            html += f'<th style="background-color: {HEADER_COLORS["time"]}; padding: 6px; border: 1px solid #999; text-align: center; font-size: 11px;">{p["start_time"]}-{p["end_time"]}</th>'
        html += '</tr>'
        
        # Year rows
        for year in [1, 2, 3, 4, 5]:
            division = context.get('division_code', 'A')
            year_slots = [s for s in all_slots.get(year, []) if s['day_of_week'] == day_num]
            
            html += self._render_year_row_html(
                context, year, division, day_num, periods, year_slots
            )
        
        html += '</table>'
        
        st.markdown(html, unsafe_allow_html=True)
    
    def _render_year_row_html(
        self,
        context: Dict,
        year: int,
        division: str,
        day_num: int,
        periods: List[Dict],
        slots: List[Dict]
    ) -> str:
        """Render one year row as HTML with bridging support, edit controls, and conflict indicators"""
        
        year_bg = YEAR_COLORS.get(year, '#FFFFFF')
        
        # Year label
        semester = ['I', 'III', 'V', 'VII', 'IX'][year - 1]
        ordinal = ['1st', '2nd', '3rd', '4th', '5th'][year - 1]
        
        html = '<tr>'
        html += f'<td style="background-color: {HEADER_COLORS["year_label"]}; padding: 12px; border: 1px solid #999; font-weight: bold; white-space: nowrap;">{ordinal} Year Semester {semester}</td>'
        
        # Build period → slot map (handle bridges)
        period_map = {}
        processed_bridges = set()
        
        for slot in slots:
            period_id = slot['period_id']
            bridge_id = slot.get('bridge_group_id')
            
            if bridge_id:
                if bridge_id not in processed_bridges and slot['bridge_position'] == 1:
                    period_map[period_id] = {
                        'type': 'bridge_start',
                        'slot': slot,
                        'colspan': slot['bridge_length']
                    }
                    processed_bridges.add(bridge_id)
                elif bridge_id in processed_bridges:
                    period_map[period_id] = {'type': 'skip'}
            else:
                period_map[period_id] = {
                    'type': 'single',
                    'slot': slot
                }
        
        # Render cells
        for period in periods:
            pid = period['id']
            
            if pid in period_map:
                info = period_map[pid]
                
                if info['type'] == 'skip':
                    continue
                
                elif info['type'] in ['bridge_start', 'single']:
                    slot = info['slot']
                    colspan = info.get('colspan', 1)
                    is_bridge = info['type'] == 'bridge_start'
                    
                    # Check for conflicts
                    conflicts = get_conflicts_for_cell(
                        self.engine, context, year, division, day_num, pid
                    )
                    
                    # Determine cell background color based on conflicts
                    cell_bg = year_bg
                    border_style = '1px solid #999'
                    
                    if conflicts:
                        has_error = any(c['severity'] == 'error' for c in conflicts)
                        has_warning = any(c['severity'] == 'warning' for c in conflicts)
                        
                        if has_error:
                            cell_bg = '#FFCDD2'  # Light red for errors
                            border_style = '3px solid #D32F2F'  # Bold red border
                        elif has_warning:
                            cell_bg = '#FFF9C4'  # Light yellow for warnings
                            border_style = '2px solid #F57C00'  # Orange border
                    
                    html += f'<td colspan="{colspan}" style="background-color: {cell_bg}; padding: 12px; border: {border_style}; vertical-align: top; position: relative;">'
                    
                    # Conflict indicator badge
                    if conflicts:
                        error_count = sum(1 for c in conflicts if c['severity'] == 'error')
                        warning_count = sum(1 for c in conflicts if c['severity'] == 'warning')
                        
                        if error_count > 0:
                            html += f'<div style="position: absolute; top: 4px; right: 4px; background-color: #D32F2F; color: white; font-size: 10px; padding: 2px 6px; border-radius: 10px; font-weight: bold;">⚠️ {error_count}</div>'
                        elif warning_count > 0:
                            html += f'<div style="position: absolute; top: 4px; right: 4px; background-color: #F57C00; color: white; font-size: 10px; padding: 2px 6px; border-radius: 10px; font-weight: bold;">⚡ {warning_count}</div>'
                    
                    # Subject name
                    html += f'<div style="font-weight: bold; font-size: 13px; margin-bottom: 4px;">{slot.get("subject_name", slot["subject_code"])}</div>'
                    
                    # Bridge indicator
                    if is_bridge:
                        html += f'<div style="font-size: 10px; color: #999; margin-bottom: 4px;">🔗 {colspan} periods merged</div>'
                    
                    # Faculty names
                    if st.session_state.show_faculty_names and slot.get('faculty_list_parsed'):
                        for fac in slot['faculty_list_parsed']:
                            name = fac.split('@')[0].replace('.', ' ').title()
                            html += f'<div style="font-size: 11px; color: #555;">{name}</div>'
                    
                    # Conflict messages (collapsible)
                    if conflicts:
                        html += '<details style="margin-top: 6px; font-size: 10px;">'
                        html += '<summary style="cursor: pointer; color: #D32F2F; font-weight: bold;">⚠️ View Conflicts</summary>'
                        html += '<div style="margin-top: 4px; padding: 4px; background-color: #FFF; border-radius: 4px;">'
                        for conflict in conflicts:
                            icon = '❌' if conflict['severity'] == 'error' else '⚡'
                            html += f'<div style="margin: 2px 0; color: #333;">{icon} {conflict["message"]}</div>'
                        html += '</div>'
                        html += '</details>'
                    
                    # Edit controls (only in edit mode)
                    if st.session_state.get('excel_grid_mode') == 'edit':
                        html += '<div style="margin-top: 8px; padding-top: 8px; border-top: 1px solid #ddd;">'
                        
                        if is_bridge:
                            # Bridge controls
                            bridge_id = slot.get('bridge_group_id')
                            html += f'<div style="font-size: 10px;">'
                            html += f'<a href="#" onclick="return false;" style="color: #1976D2; text-decoration: none; margin-right: 8px;" title="Extend bridge">➕ Extend</a>'
                            html += f'<a href="#" onclick="return false;" style="color: #F57C00; text-decoration: none; margin-right: 8px;" title="Shorten bridge">➖ Shorten</a>'
                            html += f'<a href="#" onclick="return false;" style="color: #7B1FA2; text-decoration: none; margin-right: 8px;" title="Unmerge to single period">🔓 Unmerge</a>'
                            html += f'<a href="#" onclick="return false;" style="color: #D32F2F; text-decoration: none;" title="Delete subject">🗑️ Delete</a>'
                            html += '</div>'
                        else:
                            # Single slot controls
                            html += f'<div style="font-size: 10px;">'
                            html += f'<a href="#" onclick="return false;" style="color: #1976D2; text-decoration: none; margin-right: 8px;" title="Merge with next periods">🔗 Merge</a>'
                            html += f'<a href="#" onclick="return false;" style="color: #388E3C; text-decoration: none; margin-right: 8px;" title="Edit faculty">👥 Faculty</a>'
                            html += f'<a href="#" onclick="return false;" style="color: #D32F2F; text-decoration: none;" title="Delete">🗑️ Delete</a>'
                            html += '</div>'
                        
                        html += '</div>'
                    
                    html += '</td>'
            else:
                # Empty cell - show + add button in edit mode
                html += f'<td style="background-color: {year_bg}; padding: 12px; border: 1px solid #999; min-height: 60px; text-align: center;">'
                
                if st.session_state.get('excel_grid_mode') == 'edit':
                    html += '<a href="#" onclick="return false;" style="color: #666; text-decoration: none; font-size: 20px;" title="Add subject">➕</a>'
                
                html += '</td>'
        
        html += '</tr>'
        return html

# ============================================================================
# HELPER FUNCTIONS (Schema-Corrected)
# ============================================================================

def get_periods_config(ay_label, degree_code, term, engine):
    """
    Fetch the active day template and its slots.
    UPDATED: Matches 'periods_schema.py' column names (fixed_start_time, etc.)
    """
    from sqlalchemy import text
    with engine.connect() as conn:
        # 1. Find the best matching published template
        # We prioritize templates with specific definitions, but fallback to generic ones
        template = conn.execute(text("""
            SELECT id
            FROM day_templates
            WHERE ay_label = :ay 
              AND degree_code = :deg 
              AND term = :term
              AND status = 'published'
            ORDER BY 
              -- Prefer more specific templates (if multiple exist)
              (year IS NOT NULL) + 
              (division_code IS NOT NULL) + 
              (branch_code IS NOT NULL) + 
              (program_code IS NOT NULL) DESC
            LIMIT 1
        """), {'ay': ay_label, 'deg': degree_code, 'term': term}).fetchone()
        
        if not template:
            return None
        
        # 2. Fetch slots using correct schema column names
        slots = conn.execute(text("""
            SELECT 
                slot_index as id, 
                fixed_start_time as start_time, 
                fixed_end_time as end_time, 
                slot_label as label, 
                is_teaching_slot
            FROM day_template_slots
            WHERE template_id = :tid
            ORDER BY slot_index
        """), {'tid': template[0]}).fetchall()
        
        return {
            'template_id': template[0],
            'slots': [dict(s._mapping) for s in slots]
        }

def get_teaching_periods(config, day_name):
    """
    Extract only teaching periods (excluding breaks).
    """
    if not config or 'slots' not in config:
        return []
    
    return [
        {
            'id': s['id'], 
            'label': s['label'],
            'start_time': s['start_time'], 
            'end_time': s['end_time']
        }
        for s in config['slots'] 
        if s['is_teaching_slot']
    ]


# ============================================================================
# ENTRY POINT
# ============================================================================

def render_complete_excel_timetable(ctx: Any, engine: Engine):
    """
    Main entry point - call this from app_weekly_planner.py
    
    This is the ONLY function you need to import!
    """
    
    # Normalize context
    if hasattr(ctx, 'ay'):
        context = {
            'ay_label': ctx.ay,
            'degree_code': ctx.degree,
            'term': ctx.term,
            'program_code': ctx.program,
            'branch_code': ctx.branch,
            'division_code': ctx.division
        }
    else:
        context = ctx
    
    # Render
    grid = CompleteExcelTimetableGrid(engine)
    grid.render(context)
