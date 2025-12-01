# ============================================================================
# CROSS-TT CONFLICT DETECTION (Slide 23 vs Slide 24)
# ============================================================================
# Comprehensive conflict detection between:
# - Regular Weekly TT (Slide 23) - timetable_slots
# - Elective/CP TT (Slide 24) - elective_timetable_slots
#
# Detects:
# 1. Faculty teaching both TTs simultaneously
# 2. Students having overlapping classes
# 3. Room double-booking
# 4. Date range overlaps
# 5. All-day block conflicts
# ============================================================================

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, date
from sqlalchemy import text
from sqlalchemy.engine import Engine
import json


# ============================================================================
# 1. FACULTY CONFLICTS (Cross-TT)
# ============================================================================

def detect_faculty_cross_tt_conflicts(
    ay_label: str,
    term: int,
    degree_code: str,
    year: int,
    division_code: Optional[str] = None,
    engine: Engine = None
) -> List[Dict[str, Any]]:
    """
    Detect faculty teaching in BOTH regular TT and elective TT at same time
    
    Critical: Checks date range overlap for elective TT modules
    
    Example Conflict:
        Regular TT: Dr. Smith teaches TOS1 on Monday P1 (Sep 1 - Dec 15)
        Elective TT: Dr. Smith teaches ML on Monday P1 (Oct 1 - Nov 15)
        Result: CONFLICT (date ranges overlap)
    
    Returns:
        List of conflict dictionaries
    """
    
    conflicts = []
    
    with engine.connect() as conn:
        
        # Query: Faculty in both TTs at same day/period with date overlap
        result = conn.execute(text("""
            WITH regular_slots AS (
                SELECT 
                    r.id as regular_slot_id,
                    r.faculty_in_charge,
                    r.day_of_week,
                    r.period_id,
                    r.subject_code,
                    r.subject_name,
                    r.division_code,
                    r.bridge_length,
                    r.room_code,
                    -- Regular TT runs for entire term (approximate)
                    -- TODO: Add actual term dates from semesters table
                    date('now', 'start of month', '-2 months') as term_start,
                    date('now', 'start of month', '+2 months') as term_end
                FROM timetable_slots r
                WHERE r.ay_label = :ay
                  AND r.term = :term
                  AND r.degree_code = :degree
                  AND r.year = :year
                  AND (:div IS NULL OR r.division_code = :div)
                  AND r.status = 'published'
                  AND r.faculty_in_charge IS NOT NULL
            ),
            elective_slots AS (
                SELECT 
                    e.id as elective_slot_id,
                    e.faculty_in_charge,
                    e.day_of_week,
                    e.period_id,
                    e.topic_code_ay,
                    e.topic_name,
                    e.division_code,
                    e.bridge_length,
                    e.is_all_day_block,
                    e.room_code,
                    COALESCE(e.start_date, m.start_date) as start_date,
                    COALESCE(e.end_date, m.end_date) as end_date
                FROM elective_timetable_slots e
                LEFT JOIN elective_topic_modules m ON m.id = e.module_id
                WHERE e.ay_label = :ay
                  AND e.term = :term
                  AND e.degree_code = :degree
                  AND e.year = :year
                  AND (:div IS NULL OR e.division_code = :div OR e.division_code = 'ALL')
                  AND e.status = 'published'
                  AND e.faculty_in_charge IS NOT NULL
            )
            
            SELECT 
                r.regular_slot_id,
                r.faculty_in_charge,
                r.day_of_week,
                r.period_id,
                r.subject_code as regular_subject,
                r.subject_name as regular_subject_name,
                r.division_code as regular_division,
                r.bridge_length as regular_bridge_len,
                r.room_code as regular_room,
                r.term_start,
                r.term_end,
                e.elective_slot_id,
                e.topic_code_ay as elective_topic,
                e.topic_name as elective_topic_name,
                e.division_code as elective_division,
                e.bridge_length as elective_bridge_len,
                e.is_all_day_block,
                e.room_code as elective_room,
                e.start_date as elective_start,
                e.end_date as elective_end
                
            FROM regular_slots r
            INNER JOIN elective_slots e 
                ON e.faculty_in_charge = r.faculty_in_charge
                AND e.day_of_week = r.day_of_week
                
            WHERE 
                -- Period overlap (handle bridges and all-day blocks)
                (
                    -- Case 1: Elective all-day block conflicts with any regular slot
                    e.is_all_day_block = 1
                    OR
                    -- Case 2: Period range overlap
                    (
                        r.period_id BETWEEN e.period_id AND (e.period_id + e.bridge_length - 1)
                        OR
                        e.period_id BETWEEN r.period_id AND (r.period_id + r.bridge_length - 1)
                    )
                )
                -- Date range overlap (CRITICAL)
                AND (
                    -- Elective has date range that overlaps with term
                    e.start_date IS NOT NULL 
                    AND e.end_date IS NOT NULL
                    AND NOT (e.end_date < r.term_start OR e.start_date > r.term_end)
                )
                
        """), {
            'ay': ay_label,
            'term': term,
            'degree': degree_code,
            'year': year,
            'div': division_code
        })
        
        for row in result.fetchall():
            row_dict = dict(row._mapping)
            
            # Format conflict message
            conflict_type = 'cross_tt_all_day' if row_dict['is_all_day_block'] else 'cross_tt_faculty'
            
            regular_info = f"{row_dict['regular_subject']} (Div {row_dict['regular_division']})"
            elective_info = f"{row_dict['elective_topic_name']} (Div {row_dict['elective_division']})"
            
            date_range = f"{row_dict['elective_start']} to {row_dict['elective_end']}"
            
            conflicts.append({
                'conflict_type': conflict_type,
                'severity': 'error',
                'faculty_email': row_dict['faculty_in_charge'],
                'faculty_name': row_dict['faculty_in_charge'].split('@')[0].replace('.', ' ').title(),
                'day_of_week': row_dict['day_of_week'],
                'period_id': row_dict['period_id'],
                
                # Regular TT details
                'regular_slot_id': row_dict['regular_slot_id'],
                'regular_subject': regular_info,
                'regular_room': row_dict['regular_room'],
                
                # Elective TT details
                'elective_slot_id': row_dict['elective_slot_id'],
                'elective_topic': elective_info,
                'elective_room': row_dict['elective_room'],
                'elective_dates': date_range,
                'is_all_day': row_dict['is_all_day_block'],
                
                'message': (
                    f"❌ Faculty {row_dict['faculty_in_charge'].split('@')[0]} has conflicting schedules:\n"
                    f"  • Regular TT: {regular_info} on {row_dict['day_of_week']} P{row_dict['period_id']}\n"
                    f"  • Elective TT: {elective_info} on {row_dict['day_of_week']} "
                    f"{'(All-day)' if row_dict['is_all_day_block'] else 'P' + str(row_dict['period_id'])}\n"
                    f"  • Overlap during: {date_range}"
                ),
                
                'details': {
                    'regular_tt': {
                        'slot_id': row_dict['regular_slot_id'],
                        'subject': row_dict['regular_subject'],
                        'division': row_dict['regular_division'],
                        'room': row_dict['regular_room']
                    },
                    'elective_tt': {
                        'slot_id': row_dict['elective_slot_id'],
                        'topic': row_dict['elective_topic'],
                        'division': row_dict['elective_division'],
                        'room': row_dict['elective_room'],
                        'dates': date_range,
                        'all_day': bool(row_dict['is_all_day_block'])
                    }
                }
            })
    
    return conflicts


# ============================================================================
# 2. STUDENT CONFLICTS (Cross-TT)
# ============================================================================

def detect_student_cross_tt_conflicts(
    ay_label: str,
    term: int,
    degree_code: str,
    year: int,
    division_code: str,
    engine: Engine
) -> List[Dict[str, Any]]:
    """
    Detect students having overlapping classes in both TTs
    
    Example:
        Division A students have TOS1 on Monday P1 (regular TT)
        Same students selected ML elective on Monday P1 (elective TT)
        Result: CONFLICT
    
    Returns:
        List of conflict dictionaries
    """
    
    conflicts = []
    
    with engine.connect() as conn:
        
        # Find overlapping slots for same division/students
        result = conn.execute(text("""
            WITH regular_slots AS (
                SELECT 
                    r.id,
                    r.day_of_week,
                    r.period_id,
                    r.subject_code,
                    r.division_code,
                    r.bridge_length
                FROM timetable_slots r
                WHERE r.ay_label = :ay
                  AND r.term = :term
                  AND r.degree_code = :degree
                  AND r.year = :year
                  AND r.division_code = :div
                  AND r.status = 'published'
            ),
            elective_slots AS (
                SELECT 
                    e.id,
                    e.day_of_week,
                    e.period_id,
                    e.topic_name,
                    e.division_code,
                    e.bridge_length,
                    e.is_all_day_block,
                    e.topic_id,
                    COALESCE(e.start_date, m.start_date) as start_date,
                    COALESCE(e.end_date, m.end_date) as end_date
                FROM elective_timetable_slots e
                LEFT JOIN elective_topic_modules m ON m.id = e.module_id
                WHERE e.ay_label = :ay
                  AND e.term = :term
                  AND e.degree_code = :degree
                  AND e.year = :year
                  AND (e.division_code = :div OR e.division_code = 'ALL')
                  AND e.status = 'published'
            )
            
            SELECT 
                r.id as regular_slot_id,
                r.subject_code,
                r.day_of_week,
                r.period_id,
                r.bridge_length as regular_bridge,
                e.id as elective_slot_id,
                e.topic_name,
                e.bridge_length as elective_bridge,
                e.is_all_day_block,
                e.start_date,
                e.end_date,
                -- Count students affected
                (SELECT COUNT(DISTINCT student_roll_no)
                 FROM elective_student_selections
                 WHERE topic_id = e.topic_id
                   AND status = 'confirmed'
                   AND division_code = :div
                ) as students_affected
                
            FROM regular_slots r
            INNER JOIN elective_slots e 
                ON e.day_of_week = r.day_of_week
            
            WHERE 
                -- Period overlap
                (
                    e.is_all_day_block = 1
                    OR
                    (
                        r.period_id BETWEEN e.period_id AND (e.period_id + e.bridge_length - 1)
                        OR
                        e.period_id BETWEEN r.period_id AND (r.period_id + r.bridge_length - 1)
                    )
                )
                -- Check if any students selected this elective
                AND EXISTS (
                    SELECT 1 FROM elective_student_selections
                    WHERE topic_id = e.topic_id
                      AND status = 'confirmed'
                      AND division_code = :div
                )
        """), {
            'ay': ay_label,
            'term': term,
            'degree': degree_code,
            'year': year,
            'div': division_code
        })
        
        for row in result.fetchall():
            row_dict = dict(row._mapping)
            
            conflicts.append({
                'conflict_type': 'student_cross_tt',
                'severity': 'error',
                'division': division_code,
                'day_of_week': row_dict['day_of_week'],
                'period_id': row_dict['period_id'],
                'students_affected': row_dict['students_affected'],
                
                'regular_slot_id': row_dict['regular_slot_id'],
                'regular_subject': row_dict['subject_code'],
                
                'elective_slot_id': row_dict['elective_slot_id'],
                'elective_topic': row_dict['topic_name'],
                
                'message': (
                    f"❌ Students in Division {division_code} have overlapping classes:\n"
                    f"  • Regular TT: {row_dict['subject_code']} on {row_dict['day_of_week']} P{row_dict['period_id']}\n"
                    f"  • Elective TT: {row_dict['topic_name']} on {row_dict['day_of_week']} "
                    f"{'(All-day)' if row_dict['is_all_day_block'] else 'P' + str(row_dict['period_id'])}\n"
                    f"  • Students affected: {row_dict['students_affected']}"
                )
            })
    
    return conflicts


# ============================================================================
# 3. ROOM CONFLICTS (Cross-TT)
# ============================================================================

def detect_room_cross_tt_conflicts(
    ay_label: str,
    term: int,
    degree_code: str,
    engine: Engine
) -> List[Dict[str, Any]]:
    """
    Detect rooms double-booked across both TTs
    
    Example:
        Regular TT: Lab 101 on Monday P1 (TOS1 practicals)
        Elective TT: Lab 101 on Monday P1 (ML hands-on)
        Result: CONFLICT
    """
    
    conflicts = []
    
    with engine.connect() as conn:
        
        result = conn.execute(text("""
            WITH regular_slots AS (
                SELECT 
                    r.id,
                    r.room_code,
                    r.day_of_week,
                    r.period_id,
                    r.subject_code,
                    r.year,
                    r.division_code,
                    r.bridge_length
                FROM timetable_slots r
                WHERE r.ay_label = :ay
                  AND r.term = :term
                  AND r.degree_code = :degree
                  AND r.status = 'published'
                  AND r.room_code IS NOT NULL
            ),
            elective_slots AS (
                SELECT 
                    e.id,
                    e.room_code,
                    e.day_of_week,
                    e.period_id,
                    e.topic_name,
                    e.year,
                    e.division_code,
                    e.bridge_length,
                    e.is_all_day_block,
                    COALESCE(e.start_date, m.start_date) as start_date,
                    COALESCE(e.end_date, m.end_date) as end_date
                FROM elective_timetable_slots e
                LEFT JOIN elective_topic_modules m ON m.id = e.module_id
                WHERE e.ay_label = :ay
                  AND e.term = :term
                  AND e.degree_code = :degree
                  AND e.status = 'published'
                  AND e.room_code IS NOT NULL
            )
            
            SELECT 
                r.room_code,
                r.day_of_week,
                r.period_id,
                r.id as regular_slot_id,
                r.subject_code,
                r.year as regular_year,
                r.division_code as regular_division,
                e.id as elective_slot_id,
                e.topic_name,
                e.year as elective_year,
                e.division_code as elective_division,
                e.is_all_day_block,
                e.start_date,
                e.end_date
                
            FROM regular_slots r
            INNER JOIN elective_slots e 
                ON e.room_code = r.room_code
                AND e.day_of_week = r.day_of_week
            
            WHERE 
                -- Period overlap
                (
                    e.is_all_day_block = 1
                    OR
                    (
                        r.period_id BETWEEN e.period_id AND (e.period_id + e.bridge_length - 1)
                        OR
                        e.period_id BETWEEN r.period_id AND (r.period_id + r.bridge_length - 1)
                    )
                )
                -- Date overlap (if elective has date range)
                AND (
                    e.start_date IS NULL 
                    OR e.end_date IS NULL
                    OR 1=1  -- TODO: Add proper date range check with term dates
                )
        """), {
            'ay': ay_label,
            'term': term,
            'degree': degree_code
        })
        
        for row in result.fetchall():
            row_dict = dict(row._mapping)
            
            conflicts.append({
                'conflict_type': 'room_cross_tt',
                'severity': 'warning',  # Usually not critical
                'room_code': row_dict['room_code'],
                'day_of_week': row_dict['day_of_week'],
                'period_id': row_dict['period_id'],
                
                'regular_slot_id': row_dict['regular_slot_id'],
                'regular_subject': row_dict['subject_code'],
                'regular_year': row_dict['regular_year'],
                'regular_division': row_dict['regular_division'],
                
                'elective_slot_id': row_dict['elective_slot_id'],
                'elective_topic': row_dict['topic_name'],
                'elective_year': row_dict['elective_year'],
                'elective_division': row_dict['elective_division'],
                
                'message': (
                    f"⚠️ Room {row_dict['room_code']} double-booked:\n"
                    f"  • Regular TT: {row_dict['subject_code']} (Y{row_dict['regular_year']} Div {row_dict['regular_division']})\n"
                    f"  • Elective TT: {row_dict['topic_name']} (Y{row_dict['elective_year']} Div {row_dict['elective_division']})\n"
                    f"  • Time: {row_dict['day_of_week']} P{row_dict['period_id']}"
                )
            })
    
    return conflicts


# ============================================================================
# 4. COMPREHENSIVE CROSS-TT CONFLICT CHECK
# ============================================================================

def detect_all_cross_tt_conflicts(
    ay_label: str,
    term: int,
    degree_code: str,
    year: Optional[int] = None,
    division_code: Optional[str] = None,
    engine: Engine = None
) -> Dict[str, Any]:
    """
    Run ALL cross-TT conflict checks
    
    Returns:
        {
            'faculty_conflicts': [...],
            'student_conflicts': [...],
            'room_conflicts': [...],
            'total_errors': 15,
            'total_warnings': 3,
            'has_blocking_conflicts': True
        }
    """
    
    all_conflicts = {
        'faculty_conflicts': [],
        'student_conflicts': [],
        'room_conflicts': [],
        'total_errors': 0,
        'total_warnings': 0,
        'has_blocking_conflicts': False
    }
    
    # Faculty conflicts (CRITICAL)
    faculty_conflicts = detect_faculty_cross_tt_conflicts(
        ay_label, term, degree_code, year or 1, division_code, engine
    )
    all_conflicts['faculty_conflicts'] = faculty_conflicts
    all_conflicts['total_errors'] += len([c for c in faculty_conflicts if c['severity'] == 'error'])
    
    # Student conflicts (CRITICAL) - check per division
    if division_code:
        student_conflicts = detect_student_cross_tt_conflicts(
            ay_label, term, degree_code, year or 1, division_code, engine
        )
        all_conflicts['student_conflicts'] = student_conflicts
        all_conflicts['total_errors'] += len([c for c in student_conflicts if c['severity'] == 'error'])
    
    # Room conflicts (WARNING)
    room_conflicts = detect_room_cross_tt_conflicts(
        ay_label, term, degree_code, engine
    )
    all_conflicts['room_conflicts'] = room_conflicts
    all_conflicts['total_warnings'] += len([c for c in room_conflicts if c['severity'] == 'warning'])
    
    # Check if any blocking conflicts
    all_conflicts['has_blocking_conflicts'] = all_conflicts['total_errors'] > 0
    
    return all_conflicts


# ============================================================================
# 5. VALIDATION BEFORE CREATING ELECTIVE SLOT
# ============================================================================

def validate_elective_slot_creation(
    engine: Engine,
    context: Dict,
    topic_id: int,
    day_of_week: str,
    period_id: int,
    faculty_email: Optional[str] = None,
    room_code: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    is_all_day_block: bool = False
) -> Tuple[bool, Optional[str]]:
    """
    Validate if elective slot can be created without conflicting with regular TT
    
    Args:
        context: {'ay_label', 'degree_code', 'term', 'year', 'division_code'}
        topic_id: Elective topic ID
        day_of_week: Day name
        period_id: Period number
        faculty_email: Faculty email (optional)
        room_code: Room code (optional)
        start_date: Module start date (optional)
        end_date: Module end date (optional)
        is_all_day_block: All-day flag
        
    Returns:
        (is_valid, error_message)
    """
    
    with engine.connect() as conn:
        
        # ========================================
        # 1. FACULTY CONFLICT CHECK
        # ========================================
        if faculty_email:
            
            # Get term date range (approximate - should come from semesters table)
            term_start = conn.execute(text("""
                SELECT MIN(start_date) as start_date
                FROM semesters
                WHERE ay_label = :ay 
                  AND degree_code = :deg 
                  AND term = :term
            """), {
                'ay': context['ay_label'],
                'deg': context['degree_code'],
                'term': context['term']
            }).fetchone()
            
            if not term_start or not term_start[0]:
                # Fallback if no semester dates
                term_start_date = None
                term_end_date = None
            else:
                term_start_date = term_start[0]
                # Assume 4 months for term
                term_end_date = None  # TODO: Get from semesters table
            
            # Check regular TT conflicts
            regular_conflicts = conn.execute(text("""
                SELECT 
                    id, subject_code, division_code, room_code
                FROM timetable_slots
                WHERE ay_label = :ay
                  AND degree_code = :deg
                  AND term = :term
                  AND year = :year
                  AND day_of_week = :day
                  AND (
                      :is_all_day = 1  -- All-day conflicts with any period
                      OR
                      period_id = :period  -- Same period
                  )
                  AND (
                      faculty_in_charge = :faculty
                      OR faculty_list LIKE :faculty_pattern
                  )
                  AND status = 'published'
            """), {
                'ay': context['ay_label'],
                'deg': context['degree_code'],
                'term': context['term'],
                'year': context['year'],
                'day': day_of_week,
                'period': period_id,
                'faculty': faculty_email,
                'faculty_pattern': f'%{faculty_email}%',
                'is_all_day': 1 if is_all_day_block else 0
            }).fetchall()
            
            if regular_conflicts:
                conflict = regular_conflicts[0]
                return False, (
                    f"❌ Faculty Conflict: {faculty_email.split('@')[0]} is already teaching "
                    f"{conflict[1]} (Div {conflict[2]}) in Regular TT at this time"
                )
        
        # ========================================
        # 2. STUDENT CONFLICT CHECK
        # ========================================
        if context.get('division_code') and context['division_code'] != 'ALL':
            
            # Check if students have regular class at this time
            student_conflicts = conn.execute(text("""
                SELECT 
                    id, subject_code
                FROM timetable_slots
                WHERE ay_label = :ay
                  AND degree_code = :deg
                  AND term = :term
                  AND year = :year
                  AND division_code = :div
                  AND day_of_week = :day
                  AND (
                      :is_all_day = 1
                      OR period_id = :period
                  )
                  AND status = 'published'
            """), {
                'ay': context['ay_label'],
                'deg': context['degree_code'],
                'term': context['term'],
                'year': context['year'],
                'div': context['division_code'],
                'day': day_of_week,
                'period': period_id,
                'is_all_day': 1 if is_all_day_block else 0
            }).fetchall()
            
            if student_conflicts:
                conflict = student_conflicts[0]
                return False, (
                    f"❌ Student Conflict: Division {context['division_code']} students "
                    f"already have {conflict[1]} in Regular TT at this time"
                )
        
        # ========================================
        # 3. ROOM CONFLICT CHECK
        # ========================================
        if room_code:
            
            room_conflicts = conn.execute(text("""
                SELECT 
                    id, subject_code, division_code
                FROM timetable_slots
                WHERE ay_label = :ay
                  AND degree_code = :deg
                  AND term = :term
                  AND day_of_week = :day
                  AND (
                      :is_all_day = 1
                      OR period_id = :period
                  )
                  AND room_code = :room
                  AND status = 'published'
            """), {
                'ay': context['ay_label'],
                'deg': context['degree_code'],
                'term': context['term'],
                'day': day_of_week,
                'period': period_id,
                'room': room_code,
                'is_all_day': 1 if is_all_day_block else 0
            }).fetchall()
            
            if room_conflicts:
                conflict = room_conflicts[0]
                return False, (
                    f"⚠️ Room Conflict: {room_code} is already booked for "
                    f"{conflict[1]} (Div {conflict[2]}) in Regular TT at this time"
                )
    
    return True, None


# ============================================================================
# 6. CONFLICT RESOLUTION HELPERS
# ============================================================================

def get_alternative_slots_avoiding_conflicts(
    engine: Engine,
    context: Dict,
    faculty_email: str,
    day_of_week: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None
) -> List[Dict]:
    """
    Find alternative time slots that avoid conflicts
    
    Returns:
        List of available period IDs on the given day
    """
    
    with engine.connect() as conn:
        
        # Get all periods
        all_periods = conn.execute(text("""
            SELECT slot_index as period_id
            FROM day_template_slots
            WHERE template_id = (
                SELECT id FROM day_templates
                WHERE ay_label = :ay 
                  AND degree_code = :deg 
                  AND term = :term
                  AND status = 'published'
                LIMIT 1
            )
            AND is_teaching_slot = 1
            ORDER BY slot_index
        """), {
            'ay': context['ay_label'],
            'deg': context['degree_code'],
            'term': context['term']
        }).fetchall()
        
        available = []
        
        for period in all_periods:
            pid = period[0]
            
            # Check if this period is free
            is_valid, _ = validate_elective_slot_creation(
                engine,
                context,
                topic_id=0,  # Dummy
                day_of_week=day_of_week,
                period_id=pid,
                faculty_email=faculty_email,
                start_date=start_date,
                end_date=end_date
            )
            
            if is_valid:
                available.append({
                    'period_id': pid,
                    'day_of_week': day_of_week,
                    'label': f"{day_of_week} Period {pid}"
                })
        
        return available


# ============================================================================
# 7. EXPORT CONFLICT REPORT
# ============================================================================

def export_cross_tt_conflicts_to_dict(
    conflicts: Dict[str, Any]
) -> Dict:
    """
    Format conflicts for export/display
    
    Returns:
        {
            'summary': {...},
            'faculty_conflicts': [...],
            'student_conflicts': [...],
            'room_conflicts': [...]
        }
    """
    
    return {
        'summary': {
            'total_errors': conflicts['total_errors'],
            'total_warnings': conflicts['total_warnings'],
            'has_blocking_conflicts': conflicts['has_blocking_conflicts'],
            'faculty_conflict_count': len(conflicts['faculty_conflicts']),
            'student_conflict_count': len(conflicts['student_conflicts']),
            'room_conflict_count': len(conflicts['room_conflicts'])
        },
        'faculty_conflicts': [
            {
                'faculty': c['faculty_name'],
                'day': c['day_of_week'],
                'period': c['period_id'],
                'regular_subject': c['regular_subject'],
                'elective_topic': c['elective_topic'],
                'dates': c['elective_dates'],
                'severity': c['severity']
            }
            for c in conflicts['faculty_conflicts']
        ],
        'student_conflicts': [
            {
                'division': c['division'],
                'day': c['day_of_week'],
                'period': c['period_id'],
                'regular_subject': c['regular_subject'],
                'elective_topic': c['elective_topic'],
                'students_affected': c['students_affected'],
                'severity': c['severity']
            }
            for c in conflicts['student_conflicts']
        ],
        'room_conflicts': [
            {
                'room': c['room_code'],
                'day': c['day_of_week'],
                'period': c['period_id'],
                'regular_subject': c['regular_subject'],
                'elective_topic': c['elective_topic'],
                'severity': c['severity']
            }
            for c in conflicts['room_conflicts']
        ]
    }
