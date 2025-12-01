"""
Faculty Scheduler - Faculty assignment, availability checking, and load management
"""

from typing import List, Dict, Any, Optional, Tuple
import json
from connection import get_engine


# ============================================================================
# FACULTY AVAILABILITY
# ============================================================================

def get_available_faculty(
    degree_code: str,
    program_code: Optional[str] = None,
    branch_code: Optional[str] = None,
    ay_label: Optional[str] = None,
    term: Optional[int] = None,
    day_of_week: Optional[str] = None,
    period_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Get faculty available for a given context and time
    
    Args:
        degree_code: Degree code (required)
        program_code: Program code (optional filter)
        branch_code: Branch code (optional filter)
        ay_label, term: If provided, check availability at specific time
        day_of_week, period_id: Specific time slot to check
        
    Returns:
        List of available faculty with their profiles and affiliations
    """
    engine = get_engine()
    
    try:
        with engine.connect() as conn:
            # Base query: Get affiliated faculty
            query = """
                SELECT 
                    fp.email,
                    fp.name,
                    fp.employee_id,
                    fp.phone,
                    fp.highest_qualification,
                    fp.specialization,
                    fp.status,
                    fa.degree_code,
                    fa.program_code,
                    fa.branch_code,
                    fa.designation,
                    fa.type as affiliation_type,
                    fa.active as affiliation_active
                FROM faculty_profiles fp
                JOIN faculty_affiliations fa ON fp.email = fa.email
                WHERE fp.status = 'active'
                  AND fa.active = 1
                  AND fa.degree_code = ?
            """
            
            params = [degree_code]
            
            if program_code:
                query += " AND (fa.program_code IS NULL OR fa.program_code = ?)"
                params.append(program_code)
            
            if branch_code:
                query += " AND (fa.branch_code IS NULL OR fa.branch_code = ?)"
                params.append(branch_code)
            
            query += " ORDER BY fa.type, fp.name"
            
            result = conn.execute(query, params)
            faculty_list = [dict(row._mapping) for row in result.fetchall()]
            
            # If time slot specified, filter by availability
            if ay_label and term and day_of_week and period_id:
                available_faculty = []
                for faculty in faculty_list:
                    if check_faculty_availability(
                        faculty['email'], ay_label, term, day_of_week, period_id
                    ):
                        available_faculty.append(faculty)
                return available_faculty
            
            return faculty_list
            
    except Exception as e:
        print(f"Error getting available faculty: {e}")
        return []


def check_faculty_availability(
    faculty_email: str,
    ay_label: str,
    term: int,
    day_of_week: str,
    period_id: int
) -> bool:
    """
    Check if faculty is available at a specific time
    
    Returns:
        True if available (not teaching another class)
    """
    engine = get_engine()
    
    try:
        with engine.connect() as conn:
            result = conn.execute("""
                SELECT COUNT(*) as clash_count
                FROM timetable_slots
                WHERE faculty_in_charge = ?
                  AND ay_label = ?
                  AND term = ?
                  AND day_of_week = ?
                  AND period_id = ?
                  AND status != 'deleted'
            """, (faculty_email, ay_label, term, day_of_week, period_id))
            
            row = result.fetchone()
            return row[0] == 0 if row else True
            
    except Exception as e:
        print(f"Error checking faculty availability: {e}")
        return False


def get_faculty_schedule(
    faculty_email: str,
    ay_label: str,
    term: int,
    degree_code: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Get complete schedule for a faculty member
    
    Returns:
        List of all slots where faculty is teaching
    """
    engine = get_engine()
    
    try:
        with engine.connect() as conn:
            query = """
                SELECT 
                    ts.*,
                    so.subject_name
                FROM timetable_slots ts
                LEFT JOIN subject_offerings so ON ts.offering_id = so.id
                WHERE ts.faculty_in_charge = ?
                  AND ts.ay_label = ?
                  AND ts.term = ?
                  AND ts.status != 'deleted'
            """
            
            params = [faculty_email, ay_label, term]
            
            if degree_code:
                query += " AND ts.degree_code = ?"
                params.append(degree_code)
            
            query += " ORDER BY ts.day_of_week, ts.period_id"
            
            result = conn.execute(query, params)
            return [dict(row._mapping) for row in result.fetchall()]
            
    except Exception as e:
        print(f"Error getting faculty schedule: {e}")
        return []


# ============================================================================
# FACULTY ASSIGNMENT
# ============================================================================

def assign_faculty_to_slot(
    slot_id: int,
    faculty_in_charge: str,
    other_faculty: Optional[List[str]] = None,
    is_override: bool = False,
    updated_by: Optional[str] = None
) -> bool:
    """
    Assign faculty to a timetable slot
    
    Args:
        slot_id: Slot ID
        faculty_in_charge: Email of subject in-charge
        other_faculty: List of additional faculty emails
        is_override: Mark as manual override
        updated_by: Who is assigning
        
    Returns:
        True if successful
    """
    engine = get_engine()
    
    try:
        with engine.begin() as conn:
            # Prepare faculty list
            faculty_json = json.dumps(other_faculty) if other_faculty else None
            
            conn.execute("""
                UPDATE timetable_slots
                SET faculty_in_charge = ?,
                    faculty_list = ?,
                    is_in_charge_override = ?,
                    updated_by = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (faculty_in_charge, faculty_json, 1 if is_override else 0, 
                  updated_by, slot_id))
            
            return True
            
    except Exception as e:
        print(f"Error assigning faculty: {e}")
        return False


def bulk_assign_faculty(
    slot_ids: List[int],
    faculty_email: str,
    as_in_charge: bool = True,
    updated_by: Optional[str] = None
) -> int:
    """
    Assign same faculty to multiple slots
    
    Returns:
        Number of slots updated
    """
    engine = get_engine()
    updated_count = 0
    
    try:
        with engine.begin() as conn:
            for slot_id in slot_ids:
                if as_in_charge:
                    conn.execute("""
                        UPDATE timetable_slots
                        SET faculty_in_charge = ?,
                            updated_by = ?,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (faculty_email, updated_by, slot_id))
                else:
                    # Add to faculty_list
                    # First, get current list
                    result = conn.execute(
                        "SELECT faculty_list FROM timetable_slots WHERE id = ?",
                        (slot_id,)
                    )
                    row = result.fetchone()
                    
                    if row:
                        current_list = json.loads(row[0]) if row[0] else []
                        if faculty_email not in current_list:
                            current_list.append(faculty_email)
                            
                            conn.execute("""
                                UPDATE timetable_slots
                                SET faculty_list = ?,
                                    updated_by = ?,
                                    updated_at = CURRENT_TIMESTAMP
                                WHERE id = ?
                            """, (json.dumps(current_list), updated_by, slot_id))
                
                updated_count += 1
        
        return updated_count
        
    except Exception as e:
        print(f"Error bulk assigning faculty: {e}")
        return updated_count


# ============================================================================
# FACULTY LOAD CALCULATION
# ============================================================================

def calculate_faculty_load(
    faculty_email: str,
    ay_label: str,
    term: int,
    degree_code: str
) -> Dict[str, Any]:
    """
    Calculate teaching load for a faculty member
    
    Returns:
        Dictionary with load metrics
    """
    engine = get_engine()
    
    try:
        with engine.connect() as conn:
            # Get all slots
            result = conn.execute("""
                SELECT 
                    ts.*,
                    so.subject_name
                FROM timetable_slots ts
                LEFT JOIN subject_offerings so ON ts.offering_id = so.id
                WHERE ts.faculty_in_charge = ?
                  AND ts.ay_label = ?
                  AND ts.term = ?
                  AND ts.degree_code = ?
                  AND ts.status != 'deleted'
            """, (faculty_email, ay_label, term, degree_code))
            
            slots = [dict(row._mapping) for row in result.fetchall()]
            
            # Calculate metrics
            total_periods = len(slots)
            unique_subjects = len(set(s['subject_code'] for s in slots))
            in_charge_count = len(set(s['subject_code'] for s in slots))
            
            # Group by subject
            subjects_breakdown = {}
            for slot in slots:
                subject = slot['subject_code']
                if subject not in subjects_breakdown:
                    subjects_breakdown[subject] = {
                        'subject_name': slot.get('subject_name', subject),
                        'periods': 0,
                        'divisions': set(),
                        'role': 'in_charge'
                    }
                subjects_breakdown[subject]['periods'] += 1
                subjects_breakdown[subject]['divisions'].add(slot['division_code'])
            
            # Convert sets to lists for JSON
            for subject in subjects_breakdown:
                subjects_breakdown[subject]['divisions'] = list(
                    subjects_breakdown[subject]['divisions']
                )
            
            # Group by day
            daily_schedule = {}
            for slot in slots:
                day = slot['day_of_week']
                if day not in daily_schedule:
                    daily_schedule[day] = []
                
                daily_schedule[day].append({
                    'period': slot['period_id'],
                    'subject': slot['subject_code'],
                    'division': slot['division_code'],
                    'room': slot.get('room_code')
                })
            
            # Sort each day by period
            for day in daily_schedule:
                daily_schedule[day].sort(key=lambda x: x['period'])
            
            return {
                'faculty_email': faculty_email,
                'ay_label': ay_label,
                'term': term,
                'degree_code': degree_code,
                'total_periods': total_periods,
                'total_hours': total_periods * 0.83,  # Assuming 50 min periods
                'total_subjects': unique_subjects,
                'in_charge_count': in_charge_count,
                'subjects_breakdown': subjects_breakdown,
                'daily_schedule': daily_schedule
            }
            
    except Exception as e:
        print(f"Error calculating faculty load: {e}")
        return {}


def save_faculty_load(load_data: Dict[str, Any]) -> bool:
    """Save calculated load to cache table"""
    engine = get_engine()
    
    try:
        with engine.begin() as conn:
            # Delete existing record
            conn.execute("""
                DELETE FROM faculty_teaching_load
                WHERE faculty_email = ?
                  AND ay_label = ?
                  AND term = ?
                  AND degree_code = ?
            """, (
                load_data['faculty_email'],
                load_data['ay_label'],
                load_data['term'],
                load_data['degree_code']
            ))
            
            # Insert new record
            conn.execute("""
                INSERT INTO faculty_teaching_load (
                    faculty_email, ay_label, term, degree_code,
                    total_periods, total_hours, total_subjects, in_charge_count,
                    subjects_breakdown, daily_schedule,
                    last_calculated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                load_data['faculty_email'],
                load_data['ay_label'],
                load_data['term'],
                load_data['degree_code'],
                load_data['total_periods'],
                load_data['total_hours'],
                load_data['total_subjects'],
                load_data['in_charge_count'],
                json.dumps(load_data['subjects_breakdown']),
                json.dumps(load_data['daily_schedule'])
            ))
            
            return True
            
    except Exception as e:
        print(f"Error saving faculty load: {e}")
        return False


def recalculate_all_loads(
    ay_label: str,
    term: int,
    degree_code: str
) -> int:
    """
    Recalculate loads for all faculty in a degree/term
    
    Returns:
        Number of faculty updated
    """
    engine = get_engine()
    count = 0
    
    try:
        with engine.connect() as conn:
            # Get all faculty teaching in this context
            result = conn.execute("""
                SELECT DISTINCT faculty_in_charge
                FROM timetable_slots
                WHERE ay_label = ?
                  AND term = ?
                  AND degree_code = ?
                  AND faculty_in_charge IS NOT NULL
                  AND status != 'deleted'
            """, (ay_label, term, degree_code))
            
            faculty_list = [row[0] for row in result.fetchall()]
            
            for faculty_email in faculty_list:
                load_data = calculate_faculty_load(
                    faculty_email, ay_label, term, degree_code
                )
                if load_data and save_faculty_load(load_data):
                    count += 1
        
        return count
        
    except Exception as e:
        print(f"Error recalculating loads: {e}")
        return count


def get_faculty_load(
    faculty_email: str,
    ay_label: str,
    term: int,
    degree_code: str,
    recalculate: bool = False
) -> Dict[str, Any]:
    """
    Get faculty load (from cache or recalculate)
    """
    engine = get_engine()
    
    if not recalculate:
        # Try to get from cache
        try:
            with engine.connect() as conn:
                result = conn.execute("""
                    SELECT * FROM faculty_teaching_load
                    WHERE faculty_email = ?
                      AND ay_label = ?
                      AND term = ?
                      AND degree_code = ?
                """, (faculty_email, ay_label, term, degree_code))
                
                row = result.fetchone()
                if row:
                    row_dict = dict(row._mapping)
                    # Parse JSON fields
                    row_dict['subjects_breakdown'] = json.loads(
                        row_dict['subjects_breakdown']
                    ) if row_dict.get('subjects_breakdown') else {}
                    row_dict['daily_schedule'] = json.loads(
                        row_dict['daily_schedule']
                    ) if row_dict.get('daily_schedule') else {}
                    return row_dict
        except Exception:
            pass
    
    # Recalculate
    load_data = calculate_faculty_load(faculty_email, ay_label, term, degree_code)
    if load_data:
        save_faculty_load(load_data)
    return load_data


def get_overloaded_faculty(
    ay_label: str,
    term: int,
    degree_code: str,
    max_periods: int = 30
) -> List[Dict[str, Any]]:
    """
    Get faculty exceeding max teaching periods
    """
    engine = get_engine()
    
    try:
        with engine.connect() as conn:
            result = conn.execute("""
                SELECT * FROM faculty_teaching_load
                WHERE ay_label = ?
                  AND term = ?
                  AND degree_code = ?
                  AND total_periods > ?
                ORDER BY total_periods DESC
            """, (ay_label, term, degree_code, max_periods))
            
            return [dict(row._mapping) for row in result.fetchall()]
            
    except Exception as e:
        print(f"Error getting overloaded faculty: {e}")
        return []


# ============================================================================
# FACULTY SUGGESTIONS
# ============================================================================

def suggest_faculty_for_subject(
    offering_id: int,
    degree_code: str,
    ay_label: str,
    term: int,
    max_load: int = 25
) -> List[Dict[str, Any]]:
    """
    Suggest faculty for a subject based on:
    - Affiliation
    - Current load
    - Specialization match (if available)
    
    Returns:
        List of suggested faculty sorted by suitability
    """
    engine = get_engine()
    
    try:
        with engine.connect() as conn:
            # Get subject details
            result = conn.execute("""
                SELECT subject_code, subject_name 
                FROM subject_offerings 
                WHERE id = ?
            """, (offering_id,))
            
            subject_row = result.fetchone()
            if not subject_row:
                return []
            
            subject_code = subject_row[0]
            
            # Get affiliated faculty with their current loads
            query = """
                SELECT 
                    fp.email,
                    fp.name,
                    fp.employee_id,
                    fp.specialization,
                    fa.type as affiliation_type,
                    fa.designation,
                    COALESCE(ftl.total_periods, 0) as current_load
                FROM faculty_profiles fp
                JOIN faculty_affiliations fa ON fp.email = fa.email
                LEFT JOIN faculty_teaching_load ftl 
                    ON fp.email = ftl.faculty_email
                    AND ftl.ay_label = ?
                    AND ftl.term = ?
                    AND ftl.degree_code = ?
                WHERE fp.status = 'active'
                  AND fa.active = 1
                  AND fa.degree_code = ?
                  AND COALESCE(ftl.total_periods, 0) < ?
                ORDER BY 
                    fa.type DESC,  -- Core first
                    current_load ASC,  -- Less loaded first
                    fp.name
            """
            
            result = conn.execute(query, (
                ay_label, term, degree_code,
                degree_code, max_load
            ))
            
            return [dict(row._mapping) for row in result.fetchall()]
            
    except Exception as e:
        print(f"Error suggesting faculty: {e}")
        return []


def get_least_loaded_faculty(
    ay_label: str,
    term: int,
    degree_code: str,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """Get faculty with least teaching load"""
    engine = get_engine()
    
    try:
        with engine.connect() as conn:
            result = conn.execute("""
                SELECT 
                    fp.email,
                    fp.name,
                    fp.employee_id,
                    fa.type as affiliation_type,
                    COALESCE(ftl.total_periods, 0) as current_load
                FROM faculty_profiles fp
                JOIN faculty_affiliations fa ON fp.email = fa.email
                LEFT JOIN faculty_teaching_load ftl 
                    ON fp.email = ftl.faculty_email
                    AND ftl.ay_label = ?
                    AND ftl.term = ?
                    AND ftl.degree_code = ?
                WHERE fp.status = 'active'
                  AND fa.active = 1
                  AND fa.degree_code = ?
                ORDER BY current_load ASC, fp.name
                LIMIT ?
            """, (ay_label, term, degree_code, degree_code, limit))
            
            return [dict(row._mapping) for row in result.fetchall()]
            
    except Exception as e:
        print(f"Error getting least loaded faculty: {e}")
        return []
