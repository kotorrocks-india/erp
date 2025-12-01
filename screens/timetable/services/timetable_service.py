"""
Timetable Service - CRUD Operations for Timetable Slots
Handles creation, reading, updating, and deletion of timetable slots
"""

from typing import List, Optional, Dict, Any, Tuple
import json
import uuid
from datetime import datetime
from connection import get_engine


class TimetableSlot:
    """Lightweight slot representation for service layer"""
    def __init__(self, row_dict: Dict[str, Any]):
        self.id = row_dict.get('id')
        self.ay_label = row_dict['ay_label']
        self.degree_code = row_dict['degree_code']
        self.program_code = row_dict.get('program_code')
        self.branch_code = row_dict.get('branch_code')
        self.year = row_dict['year']
        self.term = row_dict['term']
        self.division_code = row_dict['division_code']
        self.offering_id = row_dict['offering_id']
        self.subject_code = row_dict['subject_code']
        self.subject_type = row_dict['subject_type']
        self.day_of_week = row_dict['day_of_week']
        self.period_id = row_dict['period_id']
        self.bridge_group_id = row_dict.get('bridge_group_id')
        self.bridge_position = row_dict.get('bridge_position', 1)
        self.bridge_length = row_dict.get('bridge_length', 1)
        self.faculty_in_charge = row_dict.get('faculty_in_charge')
        self.faculty_list = self._parse_json(row_dict.get('faculty_list'))
        self.is_in_charge_override = bool(row_dict.get('is_in_charge_override', 0))
        self.room_code = row_dict.get('room_code')
        self.room_type = row_dict.get('room_type')
        self.status = row_dict.get('status', 'draft')
        self.is_locked = bool(row_dict.get('is_locked', 0))
        self.notes = row_dict.get('notes')
        self.created_at = row_dict.get('created_at')
        self.updated_at = row_dict.get('updated_at')
        self.created_by = row_dict.get('created_by')
        self.updated_by = row_dict.get('updated_by')
    
    @staticmethod
    def _parse_json(value):
        """Parse JSON string to list"""
        if not value:
            return []
        try:
            return json.loads(value) if isinstance(value, str) else value
        except (json.JSONDecodeError, TypeError):
            return []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'ay_label': self.ay_label,
            'degree_code': self.degree_code,
            'program_code': self.program_code,
            'branch_code': self.branch_code,
            'year': self.year,
            'term': self.term,
            'division_code': self.division_code,
            'offering_id': self.offering_id,
            'subject_code': self.subject_code,
            'subject_type': self.subject_type,
            'day_of_week': self.day_of_week,
            'period_id': self.period_id,
            'bridge_group_id': self.bridge_group_id,
            'bridge_position': self.bridge_position,
            'bridge_length': self.bridge_length,
            'faculty_in_charge': self.faculty_in_charge,
            'faculty_list': self.faculty_list,
            'is_in_charge_override': self.is_in_charge_override,
            'room_code': self.room_code,
            'room_type': self.room_type,
            'status': self.status,
            'is_locked': self.is_locked,
            'notes': self.notes
        }


# ============================================================================
# CREATE OPERATIONS
# ============================================================================

def create_slot(
    ay_label: str,
    degree_code: str,
    year: int,
    term: int,
    division_code: str,
    offering_id: int,
    subject_code: str,
    subject_type: str,
    day_of_week: str,
    period_id: int,
    program_code: Optional[str] = None,
    branch_code: Optional[str] = None,
    faculty_in_charge: Optional[str] = None,
    faculty_list: Optional[List[str]] = None,
    room_code: Optional[str] = None,
    room_type: Optional[str] = None,
    notes: Optional[str] = None,
    created_by: Optional[str] = None
) -> Optional[TimetableSlot]:
    """
    Create a single timetable slot
    
    Args:
        All required timetable slot fields
        
    Returns:
        Created TimetableSlot or None if failed
    """
    engine = get_engine()
    
    try:
        with engine.begin() as conn:
            # Prepare faculty list as JSON
            faculty_json = json.dumps(faculty_list) if faculty_list else None
            
            result = conn.execute("""
                INSERT INTO timetable_slots (
                    ay_label, degree_code, program_code, branch_code,
                    year, term, division_code, offering_id,
                    subject_code, subject_type, day_of_week, period_id,
                    bridge_position, bridge_length,
                    faculty_in_charge, faculty_list,
                    room_code, room_type, notes,
                    status, created_by, created_at, updated_at
                ) VALUES (
                    ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?,
                    ?, ?,
                    ?, ?, ?,
                    'draft', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
            """, (
                ay_label, degree_code, program_code, branch_code,
                year, term, division_code, offering_id,
                subject_code, subject_type, day_of_week, period_id,
                1, 1,  # Default bridge position and length
                faculty_in_charge, faculty_json,
                room_code, room_type, notes,
                created_by
            ))
            
            slot_id = result.lastrowid
            return get_slot(slot_id)
            
    except Exception as e:
        print(f"Error creating slot: {e}")
        return None


def create_bridge(
    ay_label: str,
    degree_code: str,
    year: int,
    term: int,
    division_code: str,
    offering_id: int,
    subject_code: str,
    subject_type: str,
    day_of_week: str,
    start_period_id: int,
    bridge_length: int,
    consecutive_period_ids: List[int],
    program_code: Optional[str] = None,
    branch_code: Optional[str] = None,
    faculty_in_charge: Optional[str] = None,
    faculty_list: Optional[List[str]] = None,
    room_code: Optional[str] = None,
    room_type: Optional[str] = None,
    notes: Optional[str] = None,
    created_by: Optional[str] = None
) -> List[TimetableSlot]:
    """
    Create a bridged slot allocation (multiple consecutive periods)
    
    Args:
        consecutive_period_ids: List of period IDs in order (must be consecutive)
        bridge_length: Number of periods to bridge
        
    Returns:
        List of created TimetableSlot objects
    """
    engine = get_engine()
    
    if len(consecutive_period_ids) != bridge_length:
        raise ValueError(f"Period IDs count ({len(consecutive_period_ids)}) must match bridge_length ({bridge_length})")
    
    # Generate unique bridge group ID
    bridge_group_id = str(uuid.uuid4())
    
    try:
        with engine.begin() as conn:
            faculty_json = json.dumps(faculty_list) if faculty_list else None
            
            slot_ids = []
            
            for position, period_id in enumerate(consecutive_period_ids, start=1):
                result = conn.execute("""
                    INSERT INTO timetable_slots (
                        ay_label, degree_code, program_code, branch_code,
                        year, term, division_code, offering_id,
                        subject_code, subject_type, day_of_week, period_id,
                        bridge_group_id, bridge_position, bridge_length,
                        faculty_in_charge, faculty_list,
                        room_code, room_type, notes,
                        status, created_by, created_at, updated_at
                    ) VALUES (
                        ?, ?, ?, ?,
                        ?, ?, ?, ?,
                        ?, ?, ?, ?,
                        ?, ?, ?,
                        ?, ?,
                        ?, ?, ?,
                        'draft', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                """, (
                    ay_label, degree_code, program_code, branch_code,
                    year, term, division_code, offering_id,
                    subject_code, subject_type, day_of_week, period_id,
                    bridge_group_id, position, bridge_length,
                    faculty_in_charge, faculty_json,
                    room_code, room_type, notes,
                    created_by
                ))
                
                slot_ids.append(result.lastrowid)
            
            # Return all created slots
            return [get_slot(sid) for sid in slot_ids]
            
    except Exception as e:
        print(f"Error creating bridge: {e}")
        return []


# ============================================================================
# READ OPERATIONS
# ============================================================================

def get_slot(slot_id: int) -> Optional[TimetableSlot]:
    """Get slot by ID"""
    engine = get_engine()
    
    try:
        with engine.connect() as conn:
            result = conn.execute("""
                SELECT * FROM timetable_slots WHERE id = ?
            """, (slot_id,))
            
            row = result.fetchone()
            if row:
                return TimetableSlot(dict(row._mapping))
            return None
            
    except Exception as e:
        print(f"Error getting slot: {e}")
        return None


def get_slots_for_context(
    ay_label: str,
    degree_code: str,
    term: int,
    division_code: str,
    year: Optional[int] = None
) -> List[TimetableSlot]:
    """Get all slots for a specific context"""
    engine = get_engine()
    
    try:
        with engine.connect() as conn:
            if year is not None:
                result = conn.execute("""
                    SELECT * FROM timetable_slots
                    WHERE ay_label = ? 
                      AND degree_code = ? 
                      AND term = ?
                      AND year = ?
                      AND division_code = ?
                      AND status != 'deleted'
                    ORDER BY day_of_week, period_id
                """, (ay_label, degree_code, term, year, division_code))
            else:
                result = conn.execute("""
                    SELECT * FROM timetable_slots
                    WHERE ay_label = ? 
                      AND degree_code = ? 
                      AND term = ?
                      AND division_code = ?
                      AND status != 'deleted'
                    ORDER BY year, day_of_week, period_id
                """, (ay_label, degree_code, term, division_code))
            
            return [TimetableSlot(dict(row._mapping)) for row in result.fetchall()]
            
    except Exception as e:
        print(f"Error getting slots: {e}")
        return []


def get_slots_for_year(
    ay_label: str,
    degree_code: str,
    term: int,
    year: int
) -> List[TimetableSlot]:
    """Get all slots for a degree year (all divisions)"""
    engine = get_engine()
    
    try:
        with engine.connect() as conn:
            result = conn.execute("""
                SELECT * FROM timetable_slots
                WHERE ay_label = ? 
                  AND degree_code = ? 
                  AND term = ?
                  AND year = ?
                  AND status != 'deleted'
                ORDER BY division_code, day_of_week, period_id
            """, (ay_label, degree_code, term, year))
            
            return [TimetableSlot(dict(row._mapping)) for row in result.fetchall()]
            
    except Exception as e:
        print(f"Error getting slots for year: {e}")
        return []


def get_bridge_slots(bridge_group_id: str) -> List[TimetableSlot]:
    """Get all slots in a bridge group"""
    engine = get_engine()
    
    try:
        with engine.connect() as conn:
            result = conn.execute("""
                SELECT * FROM timetable_slots
                WHERE bridge_group_id = ?
                ORDER BY bridge_position
            """, (bridge_group_id,))
            
            return [TimetableSlot(dict(row._mapping)) for row in result.fetchall()]
            
    except Exception as e:
        print(f"Error getting bridge slots: {e}")
        return []


def get_slot_at_time(
    ay_label: str,
    degree_code: str,
    term: int,
    division_code: str,
    day_of_week: str,
    period_id: int
) -> Optional[TimetableSlot]:
    """Check if a slot exists at specific time"""
    engine = get_engine()
    
    try:
        with engine.connect() as conn:
            result = conn.execute("""
                SELECT * FROM timetable_slots
                WHERE ay_label = ?
                  AND degree_code = ?
                  AND term = ?
                  AND division_code = ?
                  AND day_of_week = ?
                  AND period_id = ?
                  AND status != 'deleted'
                LIMIT 1
            """, (ay_label, degree_code, term, division_code, day_of_week, period_id))
            
            row = result.fetchone()
            if row:
                return TimetableSlot(dict(row._mapping))
            return None
            
    except Exception as e:
        print(f"Error checking slot at time: {e}")
        return None


# ============================================================================
# UPDATE OPERATIONS
# ============================================================================

def update_slot(
    slot_id: int,
    updates: Dict[str, Any],
    updated_by: Optional[str] = None
) -> Optional[TimetableSlot]:
    """
    Update a slot with provided fields
    
    Args:
        slot_id: ID of slot to update
        updates: Dictionary of fields to update
        updated_by: Who is updating
        
    Returns:
        Updated TimetableSlot or None
    """
    engine = get_engine()
    
    if not updates:
        return get_slot(slot_id)
    
    # Build SET clause dynamically
    set_clauses = []
    values = []
    
    for key, value in updates.items():
        if key in ['faculty_list'] and isinstance(value, list):
            value = json.dumps(value)
        set_clauses.append(f"{key} = ?")
        values.append(value)
    
    # Add updated_at and updated_by
    set_clauses.append("updated_at = CURRENT_TIMESTAMP")
    if updated_by:
        set_clauses.append("updated_by = ?")
        values.append(updated_by)
    
    values.append(slot_id)
    
    try:
        with engine.begin() as conn:
            conn.execute(f"""
                UPDATE timetable_slots
                SET {', '.join(set_clauses)}
                WHERE id = ?
            """, values)
            
            return get_slot(slot_id)
            
    except Exception as e:
        print(f"Error updating slot: {e}")
        return None


def update_slot_faculty(
    slot_id: int,
    faculty_in_charge: Optional[str] = None,
    faculty_list: Optional[List[str]] = None,
    is_override: bool = False,
    updated_by: Optional[str] = None
) -> Optional[TimetableSlot]:
    """Update faculty assignment for a slot"""
    updates = {}
    
    if faculty_in_charge is not None:
        updates['faculty_in_charge'] = faculty_in_charge
        updates['is_in_charge_override'] = 1 if is_override else 0
    
    if faculty_list is not None:
        updates['faculty_list'] = faculty_list
    
    return update_slot(slot_id, updates, updated_by)


def lock_slot(slot_id: int, updated_by: Optional[str] = None) -> bool:
    """Lock a slot to prevent modifications"""
    result = update_slot(slot_id, {'is_locked': 1}, updated_by)
    return result is not None


def unlock_slot(slot_id: int, updated_by: Optional[str] = None) -> bool:
    """Unlock a slot to allow modifications"""
    result = update_slot(slot_id, {'is_locked': 0}, updated_by)
    return result is not None


def publish_slot(slot_id: int, updated_by: Optional[str] = None) -> bool:
    """Publish a slot (make it visible to students)"""
    result = update_slot(slot_id, {'status': 'published'}, updated_by)
    return result is not None


# ============================================================================
# DELETE OPERATIONS
# ============================================================================

def delete_slot(slot_id: int, hard_delete: bool = False) -> bool:
    """
    Delete a slot (soft delete by default)
    
    Args:
        slot_id: ID of slot to delete
        hard_delete: If True, permanently delete; if False, mark as deleted
        
    Returns:
        True if successful
    """
    engine = get_engine()
    
    try:
        with engine.begin() as conn:
            if hard_delete:
                conn.execute("DELETE FROM timetable_slots WHERE id = ?", (slot_id,))
            else:
                conn.execute("""
                    UPDATE timetable_slots 
                    SET status = 'deleted', updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (slot_id,))
            
            return True
            
    except Exception as e:
        print(f"Error deleting slot: {e}")
        return False


def delete_bridge(bridge_group_id: str, hard_delete: bool = False) -> bool:
    """Delete all slots in a bridge group"""
    engine = get_engine()
    
    try:
        with engine.begin() as conn:
            if hard_delete:
                conn.execute("""
                    DELETE FROM timetable_slots 
                    WHERE bridge_group_id = ?
                """, (bridge_group_id,))
            else:
                conn.execute("""
                    UPDATE timetable_slots 
                    SET status = 'deleted', updated_at = CURRENT_TIMESTAMP
                    WHERE bridge_group_id = ?
                """, (bridge_group_id,))
            
            return True
            
    except Exception as e:
        print(f"Error deleting bridge: {e}")
        return False


def clear_timetable(
    ay_label: str,
    degree_code: str,
    term: int,
    division_code: Optional[str] = None,
    year: Optional[int] = None
) -> bool:
    """Clear timetable for a context (soft delete all slots)"""
    engine = get_engine()
    
    try:
        with engine.begin() as conn:
            query = """
                UPDATE timetable_slots 
                SET status = 'deleted', updated_at = CURRENT_TIMESTAMP
                WHERE ay_label = ? AND degree_code = ? AND term = ?
            """
            params = [ay_label, degree_code, term]
            
            if year is not None:
                query += " AND year = ?"
                params.append(year)
            
            if division_code is not None:
                query += " AND division_code = ?"
                params.append(division_code)
            
            conn.execute(query, params)
            return True
            
    except Exception as e:
        print(f"Error clearing timetable: {e}")
        return False


# ============================================================================
# BULK OPERATIONS
# ============================================================================

def publish_timetable(
    ay_label: str,
    degree_code: str,
    term: int,
    division_code: Optional[str] = None,
    year: Optional[int] = None
) -> bool:
    """Publish all draft slots in a timetable"""
    engine = get_engine()
    
    try:
        with engine.begin() as conn:
            query = """
                UPDATE timetable_slots 
                SET status = 'published', updated_at = CURRENT_TIMESTAMP
                WHERE ay_label = ? AND degree_code = ? AND term = ?
                  AND status = 'draft'
            """
            params = [ay_label, degree_code, term]
            
            if year is not None:
                query += " AND year = ?"
                params.append(year)
            
            if division_code is not None:
                query += " AND division_code = ?"
                params.append(division_code)
            
            conn.execute(query, params)
            return True
            
    except Exception as e:
        print(f"Error publishing timetable: {e}")
        return False


def get_timetable_summary(
    ay_label: str,
    degree_code: str,
    term: int
) -> Dict[str, Any]:
    """Get summary statistics for a timetable"""
    engine = get_engine()
    
    try:
        with engine.connect() as conn:
            result = conn.execute("""
                SELECT 
                    COUNT(*) as total_slots,
                    COUNT(DISTINCT division_code) as divisions,
                    COUNT(DISTINCT year) as years,
                    COUNT(DISTINCT subject_code) as subjects,
                    COUNT(DISTINCT faculty_in_charge) as faculty_count,
                    SUM(CASE WHEN status = 'draft' THEN 1 ELSE 0 END) as draft_count,
                    SUM(CASE WHEN status = 'published' THEN 1 ELSE 0 END) as published_count,
                    SUM(CASE WHEN bridge_length > 1 AND bridge_position = 1 THEN 1 ELSE 0 END) as bridge_count
                FROM timetable_slots
                WHERE ay_label = ? AND degree_code = ? AND term = ?
                  AND status != 'deleted'
            """, (ay_label, degree_code, term))
            
            row = result.fetchone()
            if row:
                return dict(row._mapping)
            return {}
            
    except Exception as e:
        print(f"Error getting summary: {e}")
        return {}
