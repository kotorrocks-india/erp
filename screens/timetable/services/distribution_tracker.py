"""
Distribution Tracker - Monitor and validate subject distribution usage
Tracks planned vs actual period allocation
"""

from typing import List, Dict, Any, Optional, Tuple
from connection import get_engine


# ============================================================================
# DISTRIBUTION STATUS
# ============================================================================

def get_distribution_status(
    offering_id: int,
    division_code: Optional[str]  # Changed to Optional
) -> Optional[Dict[str, Any]]:
    """
    Get distribution status for a specific subject/division
    
    Returns:
        Status dictionary with planned, actual, and remaining periods
    """
    engine = get_engine()
    
    try:
        with engine.connect() as conn:
            # Handle NULL division logic (Fix for 'nan' string in DB)
            if division_code is not None and str(division_code).lower() not in ('none', 'nan', ''):
                div_clause = "AND division_code = ?"
                params = [offering_id, division_code]
            else:
                div_clause = "AND (division_code IS NULL OR division_code = 'nan' OR division_code = '')"
                params = [offering_id]

            # Get planned periods from weekly_subject_distribution
            # Use weekly_frequency as fallback if day-wise counts are 0
            query = f"""
                SELECT 
                    offering_id,
                    ay_label,
                    degree_code,
                    term,
                    division_code,
                    subject_code,
                    CASE 
                        WHEN (mon_periods + tue_periods + wed_periods + thu_periods + fri_periods + sat_periods) > 0 
                        THEN (mon_periods + tue_periods + wed_periods + thu_periods + fri_periods + sat_periods)
                        ELSE COALESCE(weekly_frequency, 0) 
                    END as planned_total_periods
                FROM weekly_subject_distribution
                WHERE offering_id = ? {div_clause}
            """
            
            wsd_row = conn.execute(query, params).fetchone()
            if not wsd_row:
                return None
            
            wsd_dict = dict(wsd_row._mapping)
            
            # Get actual allocation from timetable_slots
            # Handle NULL division logic for slots table too
            if division_code is not None and str(division_code).lower() not in ('none', 'nan', ''):
                ts_div_clause = "AND division_code = ?"
                ts_params = [offering_id, division_code]
            else:
                ts_div_clause = "AND (division_code IS NULL OR division_code = 'nan' OR division_code = '')"
                ts_params = [offering_id]

            ts_query = f"""
                SELECT 
                    COUNT(*) as scheduled_period_slots,
                    COUNT(DISTINCT 
                        CASE WHEN bridge_position = 1 OR bridge_position IS NULL 
                        THEN id END
                    ) as scheduled_instances
                FROM timetable_slots
                WHERE offering_id = ? 
                  {ts_div_clause}
                  AND status != 'deleted'
            """
            
            ts_row = conn.execute(ts_query, ts_params).fetchone()
            ts_dict = dict(ts_row._mapping) if ts_row else {}
            
            # Calculate status
            planned = wsd_dict['planned_total_periods']
            actual = ts_dict.get('scheduled_period_slots', 0)
            
            if actual > planned:
                status = 'over_allocated'
            elif actual < planned:
                status = 'under_allocated'
            else:
                status = 'balanced'
            
            return {
                'offering_id': offering_id,
                'ay_label': wsd_dict['ay_label'],
                'degree_code': wsd_dict['degree_code'],
                'term': wsd_dict['term'],
                'division_code': division_code,
                'subject_code': wsd_dict['subject_code'],
                'planned_total_periods': planned,
                'scheduled_period_slots': actual,
                'scheduled_instances': ts_dict.get('scheduled_instances', 0),
                'remaining_periods': planned - actual,
                'allocation_status': status
            }
            
    except Exception as e:
        print(f"Error getting distribution status: {e}")
        return None


def get_all_distribution_status(
    ay_label: str,
    degree_code: str,
    term: int,
    division_code: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Get distribution status for all subjects in a context
    """
    engine = get_engine()
    
    try:
        with engine.connect() as conn:
            # Get all offerings from weekly_subject_distribution
            # Handle NULL division logic
            if division_code is not None and str(division_code).lower() not in ('none', 'nan', ''):
                div_clause = "AND division_code = ?"
                params = [ay_label, degree_code, term, division_code]
            else:
                div_clause = "AND (division_code IS NULL OR division_code = 'nan' OR division_code = '')"
                params = [ay_label, degree_code, term]
            
            query = f"""
                SELECT offering_id, division_code
                FROM weekly_subject_distribution
                WHERE ay_label = ? AND degree_code = ? AND term = ?
                {div_clause}
            """
            
            result = conn.execute(query, params)
            offerings = result.fetchall()
            
            # Get status for each
            statuses = []
            for row in offerings:
                status = get_distribution_status(row[0], row[1])
                if status:
                    statuses.append(status)
            
            return statuses
            
    except Exception as e:
        print(f"Error getting all distribution status: {e}")
        return []


def get_incomplete_distributions(
    ay_label: str,
    degree_code: str,
    term: int
) -> List[Dict[str, Any]]:
    """
    Get subjects that are under-allocated (not fully scheduled)
    """
    all_statuses = get_all_distribution_status(ay_label, degree_code, term)
    return [s for s in all_statuses if s['allocation_status'] == 'under_allocated']


def get_over_allocated_distributions(
    ay_label: str,
    degree_code: str,
    term: int
) -> List[Dict[str, Any]]:
    """
    Get subjects that are over-allocated (scheduled too many times)
    """
    all_statuses = get_all_distribution_status(ay_label, degree_code, term)
    return [s for s in all_statuses if s['allocation_status'] == 'over_allocated']


# ============================================================================
# ALLOCATION VALIDATION
# ============================================================================

def can_allocate_more(
    offering_id: int,
    division_code: Optional[str] # Changed to Optional
) -> Tuple[bool, int]:
    """
    Check if more periods can be allocated for a subject
    
    Returns:
        (can_allocate, remaining_periods)
    """
    status = get_distribution_status(offering_id, division_code)
    
    if not status:
        return False, 0
    
    remaining = status['remaining_periods']
    return remaining > 0, remaining


def get_remaining_instances(
    offering_id: int,
    division_code: Optional[str] # Changed to Optional
) -> int:
    """
    Get number of remaining instances (teaching occurrences) to schedule
    
    Note: This is different from remaining periods.
    If a subject needs 5 periods and 2 are scheduled, remaining is 3 periods.
    But those 3 periods might be 1 triple-period instance, or 3 single-period instances.
    """
    status = get_distribution_status(offering_id, division_code)
    
    if not status:
        return 0
    
    return max(0, status['remaining_periods'])


def validate_distribution_before_create(
    offering_id: int,
    division_code: Optional[str], # Changed to Optional
    periods_to_add: int = 1
) -> Tuple[bool, str]:
    """
    Validate if adding N periods would violate distribution
    
    Args:
        offering_id: Subject offering ID
        division_code: Division code
        periods_to_add: Number of periods to add (default 1, or bridge length)
        
    Returns:
        (is_valid, error_message)
    """
    status = get_distribution_status(offering_id, division_code)
    
    if not status:
        return False, "Distribution plan not found for this subject/division"
    
    remaining = status['remaining_periods']
    
    if periods_to_add > remaining:
        return False, f"Cannot add {periods_to_add} periods. Only {remaining} periods remaining."
    
    return True, ""


# ============================================================================
# SUBJECTS NEEDING ALLOCATION
# ============================================================================

def get_subjects_needing_allocation(
    ay_label: str,
    degree_code: str,
    term: int,
    division_code: Optional[str],  # Changed from str to Optional[str] to reflect reality
    min_remaining: int = 1
) -> List[Dict[str, Any]]:
    """
    Get subjects that still need periods allocated.
    Handles both specific divisions and NULL divisions correctly.
    """
    engine = get_engine()
    
    try:
        with engine.connect() as conn:
            # 1. Prepare dynamic SQL parts based on whether division is None
            if division_code is not None and str(division_code).lower() not in ('none', 'nan', ''):
                div_filter = "AND wsd.division_code = ?"
                ts_div_filter = "AND ts.division_code = wsd.division_code"
                params = [ay_label, degree_code, term, division_code, min_remaining]
            else:
                div_filter = "AND (wsd.division_code IS NULL OR wsd.division_code = 'nan' OR wsd.division_code = '')"
                # Standard SQL equality fails with NULL, so we explicitly check for NULL in subquery
                ts_div_filter = "AND (ts.division_code IS NULL OR ts.division_code = 'nan' OR ts.division_code = '')"
                params = [ay_label, degree_code, term, min_remaining]

            # 2. Construct the query
            # We use CASE logic to use weekly_frequency if day-wise periods sum to 0
            query = f"""
                SELECT 
                    wsd.offering_id,
                    wsd.subject_code,
                    so.subject_name,
                    so.subject_type,
                    CASE 
                        WHEN (wsd.mon_periods + wsd.tue_periods + wsd.wed_periods + 
                              wsd.thu_periods + wsd.fri_periods + wsd.sat_periods) > 0 
                        THEN (wsd.mon_periods + wsd.tue_periods + wsd.wed_periods + 
                              wsd.thu_periods + wsd.fri_periods + wsd.sat_periods)
                        ELSE COALESCE(wsd.weekly_frequency, 0)
                    END as planned_periods,
                    COALESCE(
                        (SELECT COUNT(*) 
                         FROM timetable_slots ts 
                         WHERE ts.offering_id = wsd.offering_id 
                           {ts_div_filter}
                           AND ts.status != 'deleted'),
                        0
                    ) as allocated_periods
                FROM weekly_subject_distribution wsd
                LEFT JOIN subject_offerings so ON wsd.offering_id = so.id
                WHERE wsd.ay_label = ?
                  AND wsd.degree_code = ?
                  AND wsd.term = ?
                  {div_filter}
                HAVING (planned_periods - allocated_periods) >= ?
                ORDER BY wsd.subject_code
            """
            
            # 3. Execute
            result = conn.execute(query, params)
            
            # 4. Process results
            subjects = []
            for row in result.fetchall():
                row_dict = dict(row._mapping)
                remaining = row_dict['planned_periods'] - row_dict['allocated_periods']
                
                subjects.append({
                    'offering_id': row_dict['offering_id'],
                    'subject_code': row_dict['subject_code'],
                    'subject_name': row_dict['subject_name'],
                    'subject_type': row_dict['subject_type'],
                    'planned_periods': row_dict['planned_periods'],
                    'allocated_periods': row_dict['allocated_periods'],
                    'remaining_periods': remaining,
                    'progress_percent': (
                        row_dict['allocated_periods'] / row_dict['planned_periods'] * 100
                        if row_dict['planned_periods'] > 0 else 0
                    )
                })
            
            return subjects
            
    except Exception as e:
        print(f"Error getting subjects needing allocation: {e}")
        return []
    
# ============================================================================
# DISTRIBUTION SUMMARY & REPORTING
# ============================================================================

def get_distribution_summary(
    ay_label: str,
    degree_code: str,
    term: int
) -> Dict[str, Any]:
    """
    Get overall distribution summary for a timetable
    
    Returns:
        Summary statistics
    """
    all_statuses = get_all_distribution_status(ay_label, degree_code, term)
    
    if not all_statuses:
        return {
            'total_subjects': 0,
            'balanced': 0,
            'under_allocated': 0,
            'over_allocated': 0,
            'total_planned_periods': 0,
            'total_allocated_periods': 0,
            'completion_percent': 0
        }
    
    total_subjects = len(all_statuses)
    balanced = sum(1 for s in all_statuses if s['allocation_status'] == 'balanced')
    under = sum(1 for s in all_statuses if s['allocation_status'] == 'under_allocated')
    over = sum(1 for s in all_statuses if s['allocation_status'] == 'over_allocated')
    
    total_planned = sum(s['planned_total_periods'] for s in all_statuses)
    total_allocated = sum(s['scheduled_period_slots'] for s in all_statuses)
    
    completion_percent = (
        (total_allocated / total_planned * 100) if total_planned > 0 else 0
    )
    
    return {
        'total_subjects': total_subjects,
        'balanced': balanced,
        'under_allocated': under,
        'over_allocated': over,
        'total_planned_periods': total_planned,
        'total_allocated_periods': total_allocated,
        'remaining_periods': total_planned - total_allocated,
        'completion_percent': round(completion_percent, 1),
        'is_complete': balanced == total_subjects
    }


def get_distribution_by_division(
    ay_label: str,
    degree_code: str,
    term: int,
    year: int
) -> Dict[str, Dict[str, Any]]:
    """
    Get distribution summary grouped by division
    
    Returns:
        Dictionary keyed by division_code with summary for each
    """
    engine = get_engine()
    
    try:
        with engine.connect() as conn:
            # Get all divisions for this year
            result = conn.execute("""
                SELECT DISTINCT division_code
                FROM weekly_subject_distribution
                WHERE ay_label = ? 
                  AND degree_code = ?
                  AND term = ?
                  AND year = ?
                ORDER BY division_code
            """, (ay_label, degree_code, term, year))
            
            divisions = [row[0] for row in result.fetchall()]
            
            summary_by_division = {}
            
            for division in divisions:
                statuses = get_all_distribution_status(
                    ay_label, degree_code, term, division
                )
                
                summary_by_division[division] = {
                    'total_subjects': len(statuses),
                    'balanced': sum(
                        1 for s in statuses if s['allocation_status'] == 'balanced'
                    ),
                    'under_allocated': sum(
                        1 for s in statuses if s['allocation_status'] == 'under_allocated'
                    ),
                    'over_allocated': sum(
                        1 for s in statuses if s['allocation_status'] == 'over_allocated'
                    ),
                    'total_planned': sum(s['planned_total_periods'] for s in statuses),
                    'total_allocated': sum(s['scheduled_period_slots'] for s in statuses),
                }
                
                # Calculate completion
                if summary_by_division[division]['total_planned'] > 0:
                    summary_by_division[division]['completion_percent'] = round(
                        summary_by_division[division]['total_allocated'] / 
                        summary_by_division[division]['total_planned'] * 100,
                        1
                    )
                else:
                    summary_by_division[division]['completion_percent'] = 0
            
            return summary_by_division
            
    except Exception as e:
        print(f"Error getting distribution by division: {e}")
        return {}


def get_subject_distribution_details(
    offering_id: int,
    division_code: Optional[str] # Changed to Optional
) -> Dict[str, Any]:
    """
    Get detailed distribution information for a subject
    
    Includes:
    - Planned distribution (day-wise breakdown)
    - Actual allocation (all slots)
    - Remaining periods
    - Suggestions
    """
    engine = get_engine()
    
    try:
        with engine.connect() as conn:
            # Get planned distribution
            if division_code is not None and str(division_code).lower() not in ('none', 'nan', ''):
                div_clause = "AND wsd.division_code = ?"
                params = [offering_id, division_code]
            else:
                div_clause = "AND (wsd.division_code IS NULL OR wsd.division_code = 'nan' OR wsd.division_code = '')"
                params = [offering_id]

            query = f"""
                SELECT 
                    wsd.*,
                    so.subject_name,
                    so.subject_type
                FROM weekly_subject_distribution wsd
                LEFT JOIN subject_offerings so ON wsd.offering_id = so.id
                WHERE wsd.offering_id = ? {div_clause}
            """

            result = conn.execute(query, params)
            wsd_row = result.fetchone()
            if not wsd_row:
                return {}
            
            wsd_dict = dict(wsd_row._mapping)
            
            # Get actual slots
            if division_code is not None and str(division_code).lower() not in ('none', 'nan', ''):
                ts_div_clause = "AND division_code = ?"
                ts_params = [offering_id, division_code]
            else:
                ts_div_clause = "AND (division_code IS NULL OR division_code = 'nan' OR division_code = '')"
                ts_params = [offering_id]

            ts_query = f"""
                SELECT *
                FROM timetable_slots
                WHERE offering_id = ? 
                  {ts_div_clause}
                  AND status != 'deleted'
                ORDER BY day_of_week, period_id
            """

            result = conn.execute(ts_query, ts_params)
            
            slots = [dict(row._mapping) for row in result.fetchall()]
            
            # Group slots by day
            slots_by_day = {}
            for slot in slots:
                day = slot['day_of_week']
                if day not in slots_by_day:
                    slots_by_day[day] = []
                slots_by_day[day].append(slot)
            
            # Calculate day-wise allocation
            day_map = {
                'Mon': wsd_dict['mon_periods'],
                'Tue': wsd_dict['tue_periods'],
                'Wed': wsd_dict['wed_periods'],
                'Thu': wsd_dict['thu_periods'],
                'Fri': wsd_dict['fri_periods'],
                'Sat': wsd_dict['sat_periods']
            }
            
            day_wise_status = {}
            for day, planned in day_map.items():
                allocated = len(slots_by_day.get(day, []))
                day_wise_status[day] = {
                    'planned': planned,
                    'allocated': allocated,
                    'remaining': planned - allocated,
                    'slots': slots_by_day.get(day, [])
                }
            
            # Overall status
            total_planned = sum(day_map.values())
            # Fallback to weekly_frequency if day-wise is 0
            if total_planned == 0:
                total_planned = wsd_dict.get('weekly_frequency', 0)

            total_allocated = len(slots)
            
            return {
                'offering_id': offering_id,
                'division_code': division_code,
                'subject_code': wsd_dict['subject_code'],
                'subject_name': wsd_dict.get('subject_name'),
                'subject_type': wsd_dict.get('subject_type'),
                'total_planned': total_planned,
                'total_allocated': total_allocated,
                'remaining': total_planned - total_allocated,
                'day_wise_planned': day_map,
                'day_wise_status': day_wise_status,
                'all_slots': slots
            }
            
    except Exception as e:
        print(f"Error getting subject distribution details: {e}")
        return {}


def get_completion_progress(
    ay_label: str,
    degree_code: str,
    term: int,
    year: int
) -> Dict[str, Any]:
    """
    Get overall completion progress for a year's timetable
    
    Returns progress across all divisions
    """
    divisions_summary = get_distribution_by_division(
        ay_label, degree_code, term, year
    )
    
    if not divisions_summary:
        return {
            'total_divisions': 0,
            'overall_completion': 0,
            'divisions': {}
        }
    
    total_planned = sum(d['total_planned'] for d in divisions_summary.values())
    total_allocated = sum(d['total_allocated'] for d in divisions_summary.values())
    
    overall_completion = (
        (total_allocated / total_planned * 100) if total_planned > 0 else 0
    )
    
    return {
        'total_divisions': len(divisions_summary),
        'total_planned_periods': total_planned,
        'total_allocated_periods': total_allocated,
        'overall_completion': round(overall_completion, 1),
        'divisions': divisions_summary
    }
