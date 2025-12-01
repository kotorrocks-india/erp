"""
Conflict Detector - Comprehensive conflict detection for timetable slots
Detects faculty, student, room, distribution, and bridge conflicts
"""

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import json
from connection import get_engine


class Conflict:
    """Represents a timetable conflict"""
    def __init__(self, row_dict: Dict[str, Any]):
        self.id = row_dict.get('id')
        self.ay_label = row_dict['ay_label']
        self.degree_code = row_dict['degree_code']
        self.term = row_dict['term']
        self.conflict_type = row_dict['conflict_type']
        self.severity = row_dict['severity']
        self.slot_ids = self._parse_json(row_dict.get('slot_ids', '[]'))
        self.message = row_dict['message']
        self.faculty_emails = self._parse_json(row_dict.get('faculty_emails'))
        self.division_codes = self._parse_json(row_dict.get('division_codes'))
        self.details = self._parse_json(row_dict.get('details'))
        self.is_resolved = bool(row_dict.get('is_resolved', 0))
        self.can_auto_resolve = bool(row_dict.get('can_auto_resolve', 0))
        self.created_at = row_dict.get('created_at')
    
    @staticmethod
    def _parse_json(value):
        if not value:
            return None
        try:
            return json.loads(value) if isinstance(value, str) else value
        except (json.JSONDecodeError, TypeError):
            return None


# ============================================================================
# FACULTY CONFLICT DETECTION (Institution-wide)
# ============================================================================

def detect_faculty_conflicts(
    ay_label: str,
    term: int,
    degree_code: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Detect faculty teaching multiple classes at same time
    
    Args:
        ay_label: Academic year
        term: Term number
        degree_code: Optional filter by degree (default: institution-wide)
        
    Returns:
        List of conflict dictionaries
    """
    engine = get_engine()
    conflicts = []
    
    try:
        with engine.connect() as conn:
            # Query for faculty double-booking
            query = """
                SELECT 
                    faculty_in_charge,
                    day_of_week,
                    period_id,
                    COUNT(*) as clash_count,
                    GROUP_CONCAT(id) as slot_ids_str,
                    GROUP_CONCAT(subject_code) as subjects,
                    GROUP_CONCAT(division_code) as divisions,
                    GROUP_CONCAT(degree_code) as degrees
                FROM timetable_slots
                WHERE ay_label = ? 
                  AND term = ? 
                  AND faculty_in_charge IS NOT NULL
                  AND status != 'deleted'
            """
            
            params = [ay_label, term]
            
            if degree_code:
                query += " AND degree_code = ?"
                params.append(degree_code)
            
            query += """
                GROUP BY faculty_in_charge, day_of_week, period_id
                HAVING clash_count > 1
            """
            
            result = conn.execute(query, params)
            
            for row in result.fetchall():
                row_dict = dict(row._mapping)
                
                conflicts.append({
                    'conflict_type': 'faculty',
                    'severity': 'error',
                    'faculty_email': row_dict['faculty_in_charge'],
                    'day_of_week': row_dict['day_of_week'],
                    'period_id': row_dict['period_id'],
                    'slot_ids': [int(x) for x in row_dict['slot_ids_str'].split(',')],
                    'subjects': row_dict['subjects'].split(','),
                    'divisions': row_dict['divisions'].split(','),
                    'degrees': row_dict['degrees'].split(','),
                    'message': f"Faculty {row_dict['faculty_in_charge']} teaching {row_dict['clash_count']} classes at {row_dict['day_of_week']} Period {row_dict['period_id']}",
                    'details': {
                        'faculty': row_dict['faculty_in_charge'],
                        'time': f"{row_dict['day_of_week']} P{row_dict['period_id']}",
                        'clash_count': row_dict['clash_count']
                    }
                })
    
    except Exception as e:
        print(f"Error detecting faculty conflicts: {e}")
    
    return conflicts


# ============================================================================
# STUDENT CONFLICT DETECTION (Per Division)
# ============================================================================

def detect_student_conflicts(
    ay_label: str,
    degree_code: str,
    term: int,
    division_code: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Detect students (division) having multiple subjects at same time
    
    Args:
        ay_label: Academic year
        degree_code: Degree code
        term: Term number
        division_code: Optional specific division
        
    Returns:
        List of conflict dictionaries
    """
    engine = get_engine()
    conflicts = []
    
    try:
        with engine.connect() as conn:
            query = """
                SELECT 
                    division_code,
                    day_of_week,
                    period_id,
                    year,
                    COUNT(*) as clash_count,
                    GROUP_CONCAT(id) as slot_ids_str,
                    GROUP_CONCAT(subject_code) as subjects
                FROM timetable_slots
                WHERE ay_label = ? 
                  AND degree_code = ?
                  AND term = ?
                  AND status != 'deleted'
            """
            
            params = [ay_label, degree_code, term]
            
            if division_code:
                query += " AND division_code = ?"
                params.append(division_code)
            
            query += """
                GROUP BY division_code, day_of_week, period_id, year
                HAVING clash_count > 1
            """
            
            result = conn.execute(query, params)
            
            for row in result.fetchall():
                row_dict = dict(row._mapping)
                
                conflicts.append({
                    'conflict_type': 'student',
                    'severity': 'error',
                    'division_code': row_dict['division_code'],
                    'year': row_dict['year'],
                    'day_of_week': row_dict['day_of_week'],
                    'period_id': row_dict['period_id'],
                    'slot_ids': [int(x) for x in row_dict['slot_ids_str'].split(',')],
                    'subjects': row_dict['subjects'].split(','),
                    'message': f"Division {row_dict['division_code']} has {row_dict['clash_count']} subjects at {row_dict['day_of_week']} Period {row_dict['period_id']}",
                    'details': {
                        'division': row_dict['division_code'],
                        'year': row_dict['year'],
                        'time': f"{row_dict['day_of_week']} P{row_dict['period_id']}",
                        'clash_count': row_dict['clash_count']
                    }
                })
    
    except Exception as e:
        print(f"Error detecting student conflicts: {e}")
    
    return conflicts


# ============================================================================
# DISTRIBUTION VIOLATION DETECTION
# ============================================================================

def detect_distribution_violations(
    ay_label: str,
    degree_code: str,
    term: int
) -> List[Dict[str, Any]]:
    """
    Detect subjects over-allocated or under-allocated compared to distribution
    
    Uses v_distribution_tracking view if available, otherwise raw query
    """
    engine = get_engine()
    conflicts = []
    
    try:
        with engine.connect() as conn:
            # Try using view first
            try:
                result = conn.execute("""
                    SELECT * FROM v_distribution_tracking
                    WHERE ay_label = ? 
                      AND degree_code = ?
                      AND term = ?
                      AND allocation_status IN ('over_allocated', 'under_allocated')
                """, (ay_label, degree_code, term))
                
                for row in result.fetchall():
                    row_dict = dict(row._mapping)
                    
                    severity = 'error' if row_dict['allocation_status'] == 'over_allocated' else 'warning'
                    
                    conflicts.append({
                        'conflict_type': 'distribution',
                        'severity': severity,
                        'offering_id': row_dict['offering_id'],
                        'subject_code': row_dict['subject_code'],
                        'division_code': row_dict['division_code'],
                        'planned': row_dict['planned_total_periods'],
                        'actual': row_dict['scheduled_period_slots'],
                        'status': row_dict['allocation_status'],
                        'message': f"{row_dict['subject_code']} ({row_dict['division_code']}): Planned {row_dict['planned_total_periods']} periods, Scheduled {row_dict['scheduled_period_slots']}",
                        'details': {
                            'subject': row_dict['subject_code'],
                            'division': row_dict['division_code'],
                            'planned': row_dict['planned_total_periods'],
                            'actual': row_dict['scheduled_period_slots'],
                            'difference': row_dict['scheduled_period_slots'] - row_dict['planned_total_periods']
                        }
                    })
                    
            except Exception:
                # Fallback: Manual query if view doesn't exist
                result = conn.execute("""
                    SELECT 
                        ts.offering_id,
                        ts.subject_code,
                        ts.division_code,
                        wsd.mon_periods + wsd.tue_periods + wsd.wed_periods + 
                        wsd.thu_periods + wsd.fri_periods + wsd.sat_periods as planned,
                        COUNT(*) as actual
                    FROM timetable_slots ts
                    JOIN weekly_subject_distribution wsd 
                        ON ts.offering_id = wsd.offering_id 
                        AND ts.division_code = wsd.division_code
                    WHERE ts.ay_label = ? 
                      AND ts.degree_code = ?
                      AND ts.term = ?
                      AND ts.status != 'deleted'
                    GROUP BY ts.offering_id, ts.subject_code, ts.division_code
                    HAVING actual != planned
                """, (ay_label, degree_code, term))
                
                for row in result.fetchall():
                    row_dict = dict(row._mapping)
                    actual = row_dict['actual']
                    planned = row_dict['planned']
                    
                    severity = 'error' if actual > planned else 'warning'
                    status = 'over_allocated' if actual > planned else 'under_allocated'
                    
                    conflicts.append({
                        'conflict_type': 'distribution',
                        'severity': severity,
                        'offering_id': row_dict['offering_id'],
                        'subject_code': row_dict['subject_code'],
                        'division_code': row_dict['division_code'],
                        'planned': planned,
                        'actual': actual,
                        'status': status,
                        'message': f"{row_dict['subject_code']} ({row_dict['division_code']}): Planned {planned} periods, Scheduled {actual}",
                        'details': {
                            'subject': row_dict['subject_code'],
                            'division': row_dict['division_code'],
                            'planned': planned,
                            'actual': actual,
                            'difference': actual - planned
                        }
                    })
    
    except Exception as e:
        print(f"Error detecting distribution violations: {e}")
    
    return conflicts


# ============================================================================
# ROOM CONFLICT DETECTION
# ============================================================================

def detect_room_conflicts(
    ay_label: str,
    term: int,
    degree_code: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Detect rooms double-booked at same time
    """
    engine = get_engine()
    conflicts = []
    
    try:
        with engine.connect() as conn:
            query = """
                SELECT 
                    room_code,
                    day_of_week,
                    period_id,
                    COUNT(*) as clash_count,
                    GROUP_CONCAT(id) as slot_ids_str,
                    GROUP_CONCAT(subject_code) as subjects,
                    GROUP_CONCAT(division_code) as divisions
                FROM timetable_slots
                WHERE ay_label = ? 
                  AND term = ?
                  AND room_code IS NOT NULL
                  AND status != 'deleted'
            """
            
            params = [ay_label, term]
            
            if degree_code:
                query += " AND degree_code = ?"
                params.append(degree_code)
            
            query += """
                GROUP BY room_code, day_of_week, period_id
                HAVING clash_count > 1
            """
            
            result = conn.execute(query, params)
            
            for row in result.fetchall():
                row_dict = dict(row._mapping)
                
                conflicts.append({
                    'conflict_type': 'room',
                    'severity': 'warning',  # Room conflicts are warnings, not errors
                    'room_code': row_dict['room_code'],
                    'day_of_week': row_dict['day_of_week'],
                    'period_id': row_dict['period_id'],
                    'slot_ids': [int(x) for x in row_dict['slot_ids_str'].split(',')],
                    'subjects': row_dict['subjects'].split(','),
                    'divisions': row_dict['divisions'].split(','),
                    'message': f"Room {row_dict['room_code']} booked by {row_dict['clash_count']} classes at {row_dict['day_of_week']} Period {row_dict['period_id']}",
                    'details': {
                        'room': row_dict['room_code'],
                        'time': f"{row_dict['day_of_week']} P{row_dict['period_id']}",
                        'clash_count': row_dict['clash_count']
                    }
                })
    
    except Exception as e:
        print(f"Error detecting room conflicts: {e}")
    
    return conflicts


# ============================================================================
# COMPREHENSIVE CONFLICT DETECTION
# ============================================================================

def detect_all_conflicts(
    ay_label: str,
    degree_code: str,
    term: int,
    log_to_db: bool = True
) -> List[Dict[str, Any]]:
    """
    Run all conflict detection checks
    
    Args:
        ay_label: Academic year
        degree_code: Degree code
        term: Term number
        log_to_db: If True, save conflicts to database
        
    Returns:
        List of all detected conflicts
    """
    all_conflicts = []
    
    # 1. Faculty conflicts (institution-wide)
    all_conflicts.extend(detect_faculty_conflicts(ay_label, term))
    
    # 2. Student conflicts (degree-specific)
    all_conflicts.extend(detect_student_conflicts(ay_label, degree_code, term))
    
    # 3. Distribution violations
    all_conflicts.extend(detect_distribution_violations(ay_label, degree_code, term))
    
    # 4. Room conflicts
    all_conflicts.extend(detect_room_conflicts(ay_label, term, degree_code))
    
    # Log to database if requested
    if log_to_db:
        clear_conflicts(ay_label, degree_code, term)
        for conflict in all_conflicts:
            log_conflict(
                ay_label=ay_label,
                degree_code=degree_code,
                term=term,
                conflict_type=conflict['conflict_type'],
                severity=conflict['severity'],
                slot_ids=conflict.get('slot_ids', []),
                message=conflict['message'],
                details=conflict.get('details')
            )
    
    return all_conflicts


def check_slot_conflicts(
    ay_label: str,
    degree_code: str,
    term: int,
    year: int,
    division_code: str,
    day_of_week: str,
    period_id: int,
    offering_id: int,
    faculty_in_charge: Optional[str] = None,
    room_code: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Check for potential conflicts before creating a slot
    
    Returns:
        List of potential conflicts
    """
    conflicts = []
    engine = get_engine()
    
    try:
        with engine.connect() as conn:
            # 1. Check student conflict (same division, same time)
            result = conn.execute("""
                SELECT id, subject_code FROM timetable_slots
                WHERE ay_label = ? AND degree_code = ? AND term = ?
                  AND division_code = ? AND year = ?
                  AND day_of_week = ? AND period_id = ?
                  AND status != 'deleted'
            """, (ay_label, degree_code, term, division_code, year, day_of_week, period_id))
            
            existing = result.fetchone()
            if existing:
                conflicts.append({
                    'conflict_type': 'student',
                    'severity': 'error',
                    'message': f"Division {division_code} already has {existing[1]} at this time",
                    'slot_ids': [existing[0]]
                })
            
            # 2. Check faculty conflict
            if faculty_in_charge:
                result = conn.execute("""
                    SELECT id, subject_code, division_code FROM timetable_slots
                    WHERE ay_label = ? AND term = ?
                      AND faculty_in_charge = ?
                      AND day_of_week = ? AND period_id = ?
                      AND status != 'deleted'
                """, (ay_label, term, faculty_in_charge, day_of_week, period_id))
                
                existing = result.fetchone()
                if existing:
                    conflicts.append({
                        'conflict_type': 'faculty',
                        'severity': 'error',
                        'message': f"Faculty already teaching {existing[1]} (Div {existing[2]}) at this time",
                        'slot_ids': [existing[0]]
                    })
            
            # 3. Check room conflict
            if room_code:
                result = conn.execute("""
                    SELECT id, subject_code, division_code FROM timetable_slots
                    WHERE ay_label = ? AND term = ?
                      AND room_code = ?
                      AND day_of_week = ? AND period_id = ?
                      AND status != 'deleted'
                """, (ay_label, term, room_code, day_of_week, period_id))
                
                existing = result.fetchone()
                if existing:
                    conflicts.append({
                        'conflict_type': 'room',
                        'severity': 'warning',
                        'message': f"Room already booked for {existing[1]} (Div {existing[2]})",
                        'slot_ids': [existing[0]]
                    })
            
            # 4. Check distribution
            result = conn.execute("""
                SELECT 
                    COUNT(*) as allocated,
                    wsd.mon_periods + wsd.tue_periods + wsd.wed_periods + 
                    wsd.thu_periods + wsd.fri_periods + wsd.sat_periods as planned
                FROM timetable_slots ts
                JOIN weekly_subject_distribution wsd 
                    ON ts.offering_id = wsd.offering_id 
                    AND ts.division_code = wsd.division_code
                WHERE ts.offering_id = ?
                  AND ts.division_code = ?
                  AND ts.status != 'deleted'
            """, (offering_id, division_code))
            
            row = result.fetchone()
            if row and row[0] >= row[1]:
                conflicts.append({
                    'conflict_type': 'distribution',
                    'severity': 'error',
                    'message': f"Subject already fully allocated ({row[0]}/{row[1]} periods used)"
                })
    
    except Exception as e:
        print(f"Error checking slot conflicts: {e}")
    
    return conflicts


# ============================================================================
# CONFLICT LOGGING & MANAGEMENT
# ============================================================================

def log_conflict(
    ay_label: str,
    degree_code: str,
    term: int,
    conflict_type: str,
    severity: str,
    slot_ids: List[int],
    message: str,
    details: Optional[Dict[str, Any]] = None,
    faculty_emails: Optional[List[str]] = None,
    division_codes: Optional[List[str]] = None
) -> Optional[int]:
    """Log a conflict to database"""
    engine = get_engine()
    
    try:
        with engine.begin() as conn:
            result = conn.execute("""
                INSERT INTO timetable_conflicts (
                    ay_label, degree_code, term,
                    conflict_type, severity,
                    slot_ids, message, details,
                    faculty_emails, division_codes,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                ay_label, degree_code, term,
                conflict_type, severity,
                json.dumps(slot_ids), message, json.dumps(details) if details else None,
                json.dumps(faculty_emails) if faculty_emails else None,
                json.dumps(division_codes) if division_codes else None
            ))
            
            return result.lastrowid
            
    except Exception as e:
        print(f"Error logging conflict: {e}")
        return None


def resolve_conflict(
    conflict_id: int,
    resolved_by: str,
    notes: Optional[str] = None
) -> bool:
    """Mark a conflict as resolved"""
    engine = get_engine()
    
    try:
        with engine.begin() as conn:
            conn.execute("""
                UPDATE timetable_conflicts
                SET is_resolved = 1,
                    resolved_at = CURRENT_TIMESTAMP,
                    resolved_by = ?,
                    resolution_notes = ?
                WHERE id = ?
            """, (resolved_by, notes, conflict_id))
            
            return True
            
    except Exception as e:
        print(f"Error resolving conflict: {e}")
        return False


def clear_conflicts(
    ay_label: str,
    degree_code: str,
    term: int,
    resolved_only: bool = False
) -> bool:
    """Clear conflicts for a context"""
    engine = get_engine()
    
    try:
        with engine.begin() as conn:
            query = """
                DELETE FROM timetable_conflicts
                WHERE ay_label = ? AND degree_code = ? AND term = ?
            """
            params = [ay_label, degree_code, term]
            
            if resolved_only:
                query += " AND is_resolved = 1"
            
            conn.execute(query, params)
            return True
            
    except Exception as e:
        print(f"Error clearing conflicts: {e}")
        return False


def get_unresolved_conflicts(
    ay_label: str,
    degree_code: str,
    term: int
) -> List[Conflict]:
    """Get all unresolved conflicts"""
    engine = get_engine()
    
    try:
        with engine.connect() as conn:
            result = conn.execute("""
                SELECT * FROM timetable_conflicts
                WHERE ay_label = ? AND degree_code = ? AND term = ?
                  AND is_resolved = 0
                ORDER BY severity DESC, created_at DESC
            """, (ay_label, degree_code, term))
            
            return [Conflict(dict(row._mapping)) for row in result.fetchall()]
            
    except Exception as e:
        print(f"Error getting unresolved conflicts: {e}")
        return []


def get_conflict_summary(
    ay_label: str,
    degree_code: str,
    term: int
) -> Dict[str, Any]:
    """Get summary of conflicts"""
    engine = get_engine()
    
    try:
        with engine.connect() as conn:
            result = conn.execute("""
                SELECT 
                    conflict_type,
                    severity,
                    COUNT(*) as count,
                    SUM(CASE WHEN is_resolved = 1 THEN 1 ELSE 0 END) as resolved
                FROM timetable_conflicts
                WHERE ay_label = ? AND degree_code = ? AND term = ?
                GROUP BY conflict_type, severity
            """, (ay_label, degree_code, term))
            
            summary = {}
            for row in result.fetchall():
                row_dict = dict(row._mapping)
                key = f"{row_dict['conflict_type']}_{row_dict['severity']}"
                summary[key] = {
                    'type': row_dict['conflict_type'],
                    'severity': row_dict['severity'],
                    'total': row_dict['count'],
                    'resolved': row_dict['resolved'],
                    'pending': row_dict['count'] - row_dict['resolved']
                }
            
            return summary
            
    except Exception as e:
        print(f"Error getting conflict summary: {e}")
        return {}
