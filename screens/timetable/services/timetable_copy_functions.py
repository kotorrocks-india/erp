# ============================================================================
# TIMETABLE COPY/CLONE FUNCTIONALITY
# ============================================================================
# Comprehensive copying across:
# - Divisions (A → B, or All divisions combined)
# - Degree cohorts (BARCH → MARCH)
# - Programs/Branches
# - Previous AY/Terms
# ============================================================================

from sqlalchemy import text
from sqlalchemy.engine import Engine
from typing import Dict, List, Optional
from datetime import datetime
import json


# ============================================================================
# COPY BETWEEN DIVISIONS (Same Degree/AY/Term)
# ============================================================================

def copy_timetable_to_division(
    engine: Engine,
    source_context: Dict,
    target_division: str,
    copy_faculty: bool = True,
    copy_rooms: bool = False,
    created_by: str = 'system'
) -> Dict:
    """
    Copy timetable from one division to another
    
    Use Cases:
    - Division A → Division B (separate classes)
    - Division A → "ALL" (combined class - all divisions together)
    
    Args:
        source_context: Source context with division_code
        target_division: Target division code (or "ALL" for combined)
        copy_faculty: Copy faculty assignments
        copy_rooms: Copy room assignments (usually False - different rooms)
        
    Returns:
        {'success': True, 'slots_copied': 45, 'bridges_copied': 3}
    """
    
    with engine.begin() as conn:
        # Check if target already has slots
        existing = conn.execute(text("""
            SELECT COUNT(*) as count
            FROM timetable_slots
            WHERE ay_label = :ay
              AND degree_code = :deg
              AND term = :term
              AND year = :year
              AND division_code = :target_div
        """), {
            'ay': source_context['ay_label'],
            'deg': source_context['degree_code'],
            'term': source_context['term'],
            'year': source_context['year'],
            'target_div': target_division
        }).fetchone()
        
        if existing[0] > 0:
            return {
                'success': False,
                'error': f'Target division {target_division} already has {existing[0]} slots. Delete first or use replace mode.'
            }
        
        # Get source slots
        source_slots = conn.execute(text("""
            SELECT *
            FROM timetable_slots
            WHERE ay_label = :ay
              AND degree_code = :deg
              AND term = :term
              AND year = :year
              AND division_code = :source_div
              AND status != 'deleted'
        """), {
            'ay': source_context['ay_label'],
            'deg': source_context['degree_code'],
            'term': source_context['term'],
            'year': source_context['year'],
            'source_div': source_context['division_code']
        }).fetchall()
        
        if not source_slots:
            return {
                'success': False,
                'error': 'Source division has no slots to copy'
            }
        
        # Track bridges to maintain group IDs
        bridge_map = {}  # old_bridge_id → new_bridge_id
        slots_copied = 0
        bridges_copied = 0
        
        # Copy each slot
        for slot in source_slots:
            # Handle bridge group ID
            new_bridge_id = None
            if slot['bridge_group_id']:
                if slot['bridge_group_id'] not in bridge_map:
                    # First slot of a new bridge
                    import uuid
                    new_bridge_id = f"bridge-{uuid.uuid4().hex[:8]}"
                    bridge_map[slot['bridge_group_id']] = new_bridge_id
                    bridges_copied += 1
                else:
                    new_bridge_id = bridge_map[slot['bridge_group_id']]
            
            # Insert copied slot
            conn.execute(text("""
                INSERT INTO timetable_slots (
                    ay_label, degree_code, program_code, branch_code,
                    year, term, division_code,
                    offering_id, subject_code, subject_type,
                    day_of_week, period_id,
                    bridge_group_id, bridge_position, bridge_length,
                    faculty_in_charge, faculty_list, is_in_charge_override,
                    room_code, room_type,
                    status, notes, created_by, created_at
                ) VALUES (
                    :ay, :deg, :prog, :branch,
                    :year, :term, :target_div,
                    :offering, :subject, :type,
                    :day, :period,
                    :bridge_id, :bridge_pos, :bridge_len,
                    :faculty, :faculty_list, :faculty_override,
                    :room, :room_type,
                    'draft', :notes, :created_by, CURRENT_TIMESTAMP
                )
            """), {
                'ay': source_context['ay_label'],
                'deg': source_context['degree_code'],
                'prog': slot['program_code'],
                'branch': slot['branch_code'],
                'year': source_context['year'],
                'term': source_context['term'],
                'target_div': target_division,
                'offering': slot['offering_id'],
                'subject': slot['subject_code'],
                'type': slot['subject_type'],
                'day': slot['day_of_week'],
                'period': slot['period_id'],
                'bridge_id': new_bridge_id,
                'bridge_pos': slot['bridge_position'],
                'bridge_len': slot['bridge_length'],
                'faculty': slot['faculty_in_charge'] if copy_faculty else None,
                'faculty_list': slot['faculty_list'] if copy_faculty else None,
                'faculty_override': slot['is_in_charge_override'] if copy_faculty else 0,
                'room': slot['room_code'] if copy_rooms else None,
                'room_type': slot['room_type'] if copy_rooms else None,
                'notes': f"Copied from Division {source_context['division_code']}",
                'created_by': created_by
            })
            
            slots_copied += 1
        
        return {
            'success': True,
            'slots_copied': slots_copied,
            'bridges_copied': bridges_copied,
            'source_division': source_context['division_code'],
            'target_division': target_division
        }


# ============================================================================
# COPY TO ALL DIVISIONS (Combined Class)
# ============================================================================

def create_combined_class_timetable(
    engine: Engine,
    source_context: Dict,
    target_divisions: List[str],
    created_by: str = 'system'
) -> Dict:
    """
    Create combined class timetable for all divisions
    
    Use Case: When all divisions attend same class together
    
    Example:
        Division A has slots created
        Copy to ALL divisions → Creates division_code = "ALL"
        All students attend together
    
    Args:
        source_context: Source division context
        target_divisions: List of division codes to combine (e.g., ['A', 'B', 'C'])
        
    Returns:
        {'success': True, 'combined_division': 'ALL', 'slots_copied': 45}
    """
    
    # Create "ALL" division timetable
    combined_context = source_context.copy()
    combined_context['division_code'] = 'ALL'
    
    result = copy_timetable_to_division(
        engine,
        source_context,
        target_division='ALL',
        copy_faculty=True,
        copy_rooms=True,
        created_by=created_by
    )
    
    if result['success']:
        result['combined_division'] = 'ALL'
        result['divisions_included'] = target_divisions
        result['note'] = 'Combined class - all divisions attend together'
    
    return result


# ============================================================================
# COPY BETWEEN DEGREE COHORTS
# ============================================================================

def copy_timetable_to_degree_cohort(
    engine: Engine,
    source_context: Dict,
    target_context: Dict,
    copy_mode: str = 'structure_only',
    created_by: str = 'system'
) -> Dict:
    """
    Copy timetable between degree cohorts
    
    Use Cases:
    - BARCH Year 1 → MARCH Year 1 (different degree)
    - BARCH Program A → BARCH Program B (different program)
    - BARCH Branch Civil → BARCH Branch Arch (different branch)
    
    Args:
        source_context: Source degree/program/branch/division
        target_context: Target degree/program/branch/division
        copy_mode:
            - 'structure_only': Copy time slots, subject types (no faculty/rooms)
            - 'full_copy': Copy everything including faculty and rooms
            - 'template_copy': Copy as template (change subject offerings to match target)
            
    Returns:
        {'success': True, 'slots_copied': 45, 'mode': 'structure_only'}
    """
    
    with engine.begin() as conn:
        # Validate target context
        target_existing = conn.execute(text("""
            SELECT COUNT(*) as count
            FROM timetable_slots
            WHERE ay_label = :ay
              AND degree_code = :deg
              AND (:prog IS NULL OR program_code = :prog)
              AND (:branch IS NULL OR branch_code = :branch)
              AND year = :year
              AND term = :term
              AND division_code = :div
        """), {
            'ay': target_context['ay_label'],
            'deg': target_context['degree_code'],
            'prog': target_context.get('program_code'),
            'branch': target_context.get('branch_code'),
            'year': target_context['year'],
            'term': target_context['term'],
            'div': target_context['division_code']
        }).fetchone()
        
        if target_existing[0] > 0:
            return {
                'success': False,
                'error': f'Target cohort already has {target_existing[0]} slots'
            }
        
        # Get source slots
        source_slots = conn.execute(text("""
            SELECT *
            FROM timetable_slots
            WHERE ay_label = :ay
              AND degree_code = :deg
              AND (:prog IS NULL OR program_code = :prog)
              AND (:branch IS NULL OR branch_code = :branch)
              AND year = :year
              AND term = :term
              AND division_code = :div
              AND status != 'deleted'
        """), {
            'ay': source_context['ay_label'],
            'deg': source_context['degree_code'],
            'prog': source_context.get('program_code'),
            'branch': source_context.get('branch_code'),
            'year': source_context['year'],
            'term': source_context['term'],
            'div': source_context['division_code']
        }).fetchall()
        
        if not source_slots:
            return {
                'success': False,
                'error': 'Source cohort has no slots to copy'
            }
        
        # Bridge mapping
        bridge_map = {}
        slots_copied = 0
        
        # Copy slots
        for slot in source_slots:
            # Handle bridges
            new_bridge_id = None
            if slot['bridge_group_id']:
                if slot['bridge_group_id'] not in bridge_map:
                    import uuid
                    new_bridge_id = f"bridge-{uuid.uuid4().hex[:8]}"
                    bridge_map[slot['bridge_group_id']] = new_bridge_id
                else:
                    new_bridge_id = bridge_map[slot['bridge_group_id']]
            
            # Determine what to copy based on mode
            if copy_mode == 'structure_only':
                faculty_in_charge = None
                faculty_list = None
                room_code = None
                room_type = None
            elif copy_mode == 'full_copy':
                faculty_in_charge = slot['faculty_in_charge']
                faculty_list = slot['faculty_list']
                room_code = slot['room_code']
                room_type = slot['room_type']
            elif copy_mode == 'template_copy':
                # For template: try to match subject in target degree
                # (Would need subject mapping logic here)
                faculty_in_charge = None
                faculty_list = None
                room_code = None
                room_type = None
            
            # Insert
            conn.execute(text("""
                INSERT INTO timetable_slots (
                    ay_label, degree_code, program_code, branch_code,
                    year, term, division_code,
                    offering_id, subject_code, subject_type,
                    day_of_week, period_id,
                    bridge_group_id, bridge_position, bridge_length,
                    faculty_in_charge, faculty_list,
                    room_code, room_type,
                    status, notes, created_by, created_at
                ) VALUES (
                    :ay, :deg, :prog, :branch,
                    :year, :term, :div,
                    :offering, :subject, :type,
                    :day, :period,
                    :bridge_id, :bridge_pos, :bridge_len,
                    :faculty, :faculty_list,
                    :room, :room_type,
                    'draft', :notes, :created_by, CURRENT_TIMESTAMP
                )
            """), {
                'ay': target_context['ay_label'],
                'deg': target_context['degree_code'],
                'prog': target_context.get('program_code'),
                'branch': target_context.get('branch_code'),
                'year': target_context['year'],
                'term': target_context['term'],
                'div': target_context['division_code'],
                'offering': slot['offering_id'],
                'subject': slot['subject_code'],
                'type': slot['subject_type'],
                'day': slot['day_of_week'],
                'period': slot['period_id'],
                'bridge_id': new_bridge_id,
                'bridge_pos': slot['bridge_position'],
                'bridge_len': slot['bridge_length'],
                'faculty': faculty_in_charge,
                'faculty_list': faculty_list,
                'room': room_code,
                'room_type': room_type,
                'notes': f"Copied from {source_context['degree_code']} (mode: {copy_mode})",
                'created_by': created_by
            })
            
            slots_copied += 1
        
        return {
            'success': True,
            'slots_copied': slots_copied,
            'bridges_copied': len(bridge_map),
            'mode': copy_mode,
            'source': f"{source_context['degree_code']} Year {source_context['year']} Div {source_context['division_code']}",
            'target': f"{target_context['degree_code']} Year {target_context['year']} Div {target_context['division_code']}"
        }


# ============================================================================
# COPY FROM PREVIOUS AY/TERM
# ============================================================================

def copy_timetable_from_previous_term(
    engine: Engine,
    source_ay: str,
    source_term: int,
    target_ay: str,
    target_term: int,
    degree_code: str,
    year: int,
    division_code: str,
    copy_mode: str = 'structure_only',
    created_by: str = 'system'
) -> Dict:
    """
    Copy timetable from previous academic year or term
    
    Use Cases:
    - AY 2024-25 Term 1 → AY 2025-26 Term 1 (yearly rollover)
    - AY 2025-26 Term 1 → AY 2025-26 Term 2 (term rollover)
    
    Args:
        source_ay: Source academic year
        source_term: Source term
        target_ay: Target academic year
        target_term: Target term
        degree_code: Degree code
        year: Year number
        division_code: Division code
        copy_mode: 'structure_only' or 'full_copy'
        
    Returns:
        {'success': True, 'slots_copied': 45}
    """
    
    source_context = {
        'ay_label': source_ay,
        'degree_code': degree_code,
        'term': source_term,
        'year': year,
        'division_code': division_code
    }
    
    target_context = {
        'ay_label': target_ay,
        'degree_code': degree_code,
        'term': target_term,
        'year': year,
        'division_code': division_code
    }
    
    result = copy_timetable_to_degree_cohort(
        engine,
        source_context,
        target_context,
        copy_mode=copy_mode,
        created_by=created_by
    )
    
    if result['success']:
        result['rollover_type'] = 'AY' if source_ay != target_ay else 'Term'
        result['source_period'] = f"{source_ay} Term {source_term}"
        result['target_period'] = f"{target_ay} Term {target_term}"
    
    return result


# ============================================================================
# BULK COPY OPERATIONS
# ============================================================================

def copy_timetable_to_all_divisions(
    engine: Engine,
    source_context: Dict,
    target_divisions: List[str],
    copy_faculty: bool = True,
    copy_rooms: bool = False,
    created_by: str = 'system'
) -> Dict:
    """
    Copy timetable from one division to multiple divisions
    
    Use Case: Division A is finalized, copy to B, C, D
    
    Returns:
        {
            'success': True,
            'total_copied': 135,
            'results': [
                {'division': 'B', 'slots_copied': 45},
                {'division': 'C', 'slots_copied': 45},
                {'division': 'D', 'slots_copied': 45}
            ]
        }
    """
    
    results = []
    total_copied = 0
    
    for target_div in target_divisions:
        if target_div == source_context['division_code']:
            continue  # Skip source division
        
        result = copy_timetable_to_division(
            engine,
            source_context,
            target_div,
            copy_faculty=copy_faculty,
            copy_rooms=copy_rooms,
            created_by=created_by
        )
        
        results.append({
            'division': target_div,
            'success': result['success'],
            'slots_copied': result.get('slots_copied', 0),
            'error': result.get('error')
        })
        
        if result['success']:
            total_copied += result['slots_copied']
    
    return {
        'success': all(r['success'] for r in results),
        'total_copied': total_copied,
        'results': results,
        'source_division': source_context['division_code']
    }


# ============================================================================
# VALIDATION & PREVIEW
# ============================================================================

def preview_timetable_copy(
    engine: Engine,
    source_context: Dict,
    target_context: Dict
) -> Dict:
    """
    Preview what would be copied without actually copying
    
    Returns:
        {
            'source_slots': 45,
            'source_subjects': ['TOS1', 'ADS2', ...],
            'source_bridges': 3,
            'target_existing': 0,
            'can_copy': True
        }
    """
    
    with engine.connect() as conn:
        # Source info
        source = conn.execute(text("""
            SELECT 
                COUNT(*) as total_slots,
                COUNT(DISTINCT subject_code) as unique_subjects,
                COUNT(DISTINCT bridge_group_id) as bridges,
                GROUP_CONCAT(DISTINCT subject_code) as subjects
            FROM timetable_slots
            WHERE ay_label = :ay
              AND degree_code = :deg
              AND term = :term
              AND year = :year
              AND division_code = :div
              AND status != 'deleted'
        """), {
            'ay': source_context['ay_label'],
            'deg': source_context['degree_code'],
            'term': source_context['term'],
            'year': source_context['year'],
            'div': source_context['division_code']
        }).fetchone()
        
        # Target info
        target = conn.execute(text("""
            SELECT COUNT(*) as existing
            FROM timetable_slots
            WHERE ay_label = :ay
              AND degree_code = :deg
              AND term = :term
              AND year = :year
              AND division_code = :div
        """), {
            'ay': target_context['ay_label'],
            'deg': target_context['degree_code'],
            'term': target_context['term'],
            'year': target_context['year'],
            'div': target_context['division_code']
        }).fetchone()
        
        return {
            'source_slots': source[0],
            'source_subjects': source[3].split(',') if source[3] else [],
            'source_bridges': source[2],
            'target_existing': target[0],
            'can_copy': target[0] == 0,
            'warning': f'Target has {target[0]} existing slots' if target[0] > 0 else None
        }
