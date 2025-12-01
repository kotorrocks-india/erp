"""
Services Package - Timetable Management Services
Complete initialization with all service modules
"""

# ============================================================================
# CORE SERVICES
# ============================================================================

from .faculty_service import FacultyService
from .operations_service import OperationsService
from .timetable_service import TimetableSlot

# ============================================================================
# CONFLICT DETECTION
# ============================================================================

try:
    from .conflict_detector import (
        Conflict,
        detect_faculty_conflicts,
        detect_student_conflicts,
        detect_distribution_violations,
        detect_room_conflicts,
        detect_all_conflicts,
        check_slot_conflicts,
        log_conflict,
        resolve_conflict,
        clear_conflicts,
        get_unresolved_conflicts,
        get_conflict_summary
    )
    CONFLICT_DETECTION_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Conflict detection unavailable: {e}")
    CONFLICT_DETECTION_AVAILABLE = False
    # Define dummy functions to prevent import errors
    Conflict = None
    def detect_faculty_conflicts(*args, **kwargs): return []
    def detect_student_conflicts(*args, **kwargs): return []
    def detect_distribution_violations(*args, **kwargs): return []
    def detect_room_conflicts(*args, **kwargs): return []
    def detect_all_conflicts(*args, **kwargs): return []
    def check_slot_conflicts(*args, **kwargs): return []
    def log_conflict(*args, **kwargs): return None
    def resolve_conflict(*args, **kwargs): return False
    def clear_conflicts(*args, **kwargs): return False
    def get_unresolved_conflicts(*args, **kwargs): return []
    def get_conflict_summary(*args, **kwargs): return {}


# ============================================================================
# CROSS-TT CONFLICT DETECTION
# ============================================================================

try:
    from .cross_tt_conflict_detector import (
        detect_faculty_cross_tt_conflicts,
        detect_student_cross_tt_conflicts,
        detect_room_cross_tt_conflicts,
        detect_all_cross_tt_conflicts,
        validate_elective_slot_creation,
        get_alternative_slots_avoiding_conflicts,
        export_cross_tt_conflicts_to_dict
    )
    CROSS_TT_DETECTION_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Cross-TT conflict detection unavailable: {e}")
    CROSS_TT_DETECTION_AVAILABLE = False
    # Define dummy functions
    def detect_faculty_cross_tt_conflicts(*args, **kwargs): return []
    def detect_student_cross_tt_conflicts(*args, **kwargs): return []
    def detect_room_cross_tt_conflicts(*args, **kwargs): return []
    def detect_all_cross_tt_conflicts(*args, **kwargs): return {'faculty_conflicts': [], 'student_conflicts': [], 'room_conflicts': [], 'total_errors': 0, 'total_warnings': 0, 'has_blocking_conflicts': False}
    def validate_elective_slot_creation(*args, **kwargs): return True, None
    def get_alternative_slots_avoiding_conflicts(*args, **kwargs): return []
    def export_cross_tt_conflicts_to_dict(*args, **kwargs): return {}


# ============================================================================
# DISTRIBUTION TRACKING
# ============================================================================

try:
    from .distribution_tracker import (
        get_distribution_status,
        get_all_distribution_status,
        get_incomplete_distributions,
        get_over_allocated_distributions,
        can_allocate_more,
        get_remaining_instances,
        validate_distribution_before_create,
        get_subjects_needing_allocation,
        get_distribution_summary,
        get_distribution_by_division,
        get_subject_distribution_details,
        get_completion_progress
    )
    DISTRIBUTION_TRACKING_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Distribution tracking unavailable: {e}")
    DISTRIBUTION_TRACKING_AVAILABLE = False
    # Define dummy functions
    def get_distribution_status(*args, **kwargs): return None
    def get_all_distribution_status(*args, **kwargs): return []
    def get_incomplete_distributions(*args, **kwargs): return []
    def get_over_allocated_distributions(*args, **kwargs): return []
    def can_allocate_more(*args, **kwargs): return True, 0
    def get_remaining_instances(*args, **kwargs): return 0
    def validate_distribution_before_create(*args, **kwargs): return True, ""
    def get_subjects_needing_allocation(*args, **kwargs): return []
    def get_distribution_summary(*args, **kwargs): return {}
    def get_distribution_by_division(*args, **kwargs): return {}
    def get_subject_distribution_details(*args, **kwargs): return {}
    def get_completion_progress(*args, **kwargs): return {}


# ============================================================================
# FACULTY SCHEDULING
# ============================================================================

try:
    from .faculty_scheduler import (
        get_available_faculty,
        check_faculty_availability,
        get_faculty_schedule,
        assign_faculty_to_slot,
        bulk_assign_faculty,
        calculate_faculty_load,
        save_faculty_load,
        recalculate_all_loads,
        get_faculty_load,
        get_overloaded_faculty,
        suggest_faculty_for_subject,
        get_least_loaded_faculty
    )
    FACULTY_SCHEDULING_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Faculty scheduling unavailable: {e}")
    FACULTY_SCHEDULING_AVAILABLE = False
    # Define dummy functions
    def get_available_faculty(*args, **kwargs): return []
    def check_faculty_availability(*args, **kwargs): return True
    def get_faculty_schedule(*args, **kwargs): return []
    def assign_faculty_to_slot(*args, **kwargs): return False
    def bulk_assign_faculty(*args, **kwargs): return 0
    def calculate_faculty_load(*args, **kwargs): return {}
    def save_faculty_load(*args, **kwargs): return False
    def recalculate_all_loads(*args, **kwargs): return 0
    def get_faculty_load(*args, **kwargs): return {}
    def get_overloaded_faculty(*args, **kwargs): return []
    def suggest_faculty_for_subject(*args, **kwargs): return []
    def get_least_loaded_faculty(*args, **kwargs): return []


# ============================================================================
# TIMETABLE COPY/CLONE FUNCTIONS
# ============================================================================

try:
    from .timetable_copy_functions import (
        copy_timetable_to_division,
        create_combined_class_timetable,
        copy_timetable_to_degree_cohort,
        copy_timetable_from_previous_term,
        copy_timetable_to_all_divisions,
        preview_timetable_copy
    )
    TIMETABLE_COPY_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Timetable copy functions unavailable: {e}")
    TIMETABLE_COPY_AVAILABLE = False
    # Define dummy functions
    def copy_timetable_to_division(*args, **kwargs): return {'success': False, 'error': 'Copy functions unavailable'}
    def create_combined_class_timetable(*args, **kwargs): return {'success': False, 'error': 'Copy functions unavailable'}
    def copy_timetable_to_degree_cohort(*args, **kwargs): return {'success': False, 'error': 'Copy functions unavailable'}
    def copy_timetable_from_previous_term(*args, **kwargs): return {'success': False, 'error': 'Copy functions unavailable'}
    def copy_timetable_to_all_divisions(*args, **kwargs): return {'success': False, 'error': 'Copy functions unavailable'}
    def preview_timetable_copy(*args, **kwargs): return {}


# ============================================================================
# EXCEL EXPORT
# ============================================================================

try:
    from .excel_export_with_faculty_colors import (
        TimetableExcelExporter,
        export_timetable_to_excel,
        FACULTY_COLORS,
        BACKGROUND_COLORS
    )
    EXCEL_EXPORT_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Excel export unavailable: {e}")
    EXCEL_EXPORT_AVAILABLE = False
    TimetableExcelExporter = None
    def export_timetable_to_excel(*args, **kwargs): return None
    FACULTY_COLORS = {}
    BACKGROUND_COLORS = {}


# ============================================================================
# TIMETABLE SERVICE OPERATIONS
# ============================================================================

try:
    from .timetable_service import (
        create_slot,
        create_bridge,
        get_slot,
        get_slots_for_context,
        get_slots_for_year,
        get_bridge_slots,
        get_slot_at_time,
        update_slot,
        update_slot_faculty,
        lock_slot,
        unlock_slot,
        publish_slot,
        delete_slot,
        delete_bridge,
        clear_timetable,
        publish_timetable,
        get_timetable_summary
    )
    TIMETABLE_SERVICE_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Timetable service operations unavailable: {e}")
    TIMETABLE_SERVICE_AVAILABLE = False
    # Define dummy functions
    def create_slot(*args, **kwargs): return None
    def create_bridge(*args, **kwargs): return []
    def get_slot(*args, **kwargs): return None
    def get_slots_for_context(*args, **kwargs): return []
    def get_slots_for_year(*args, **kwargs): return []
    def get_bridge_slots(*args, **kwargs): return []
    def get_slot_at_time(*args, **kwargs): return None
    def update_slot(*args, **kwargs): return None
    def update_slot_faculty(*args, **kwargs): return None
    def lock_slot(*args, **kwargs): return False
    def unlock_slot(*args, **kwargs): return False
    def publish_slot(*args, **kwargs): return False
    def delete_slot(*args, **kwargs): return False
    def delete_bridge(*args, **kwargs): return False
    def clear_timetable(*args, **kwargs): return False
    def publish_timetable(*args, **kwargs): return False
    def get_timetable_summary(*args, **kwargs): return {}


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    # Core services
    'FacultyService',
    'OperationsService',
    'TimetableSlot',
    
    # Conflict detection
    'CONFLICT_DETECTION_AVAILABLE',
    'Conflict',
    'detect_faculty_conflicts',
    'detect_student_conflicts',
    'detect_distribution_violations',
    'detect_room_conflicts',
    'detect_all_conflicts',
    'check_slot_conflicts',
    'log_conflict',
    'resolve_conflict',
    'clear_conflicts',
    'get_unresolved_conflicts',
    'get_conflict_summary',
    
    # Cross-TT conflict detection
    'CROSS_TT_DETECTION_AVAILABLE',
    'detect_faculty_cross_tt_conflicts',
    'detect_student_cross_tt_conflicts',
    'detect_room_cross_tt_conflicts',
    'detect_all_cross_tt_conflicts',
    'validate_elective_slot_creation',
    'get_alternative_slots_avoiding_conflicts',
    'export_cross_tt_conflicts_to_dict',
    
    # Distribution tracking
    'DISTRIBUTION_TRACKING_AVAILABLE',
    'get_distribution_status',
    'get_all_distribution_status',
    'get_incomplete_distributions',
    'get_over_allocated_distributions',
    'can_allocate_more',
    'get_remaining_instances',
    'validate_distribution_before_create',
    'get_subjects_needing_allocation',
    'get_distribution_summary',
    'get_distribution_by_division',
    'get_subject_distribution_details',
    'get_completion_progress',
    
    # Faculty scheduling
    'FACULTY_SCHEDULING_AVAILABLE',
    'get_available_faculty',
    'check_faculty_availability',
    'get_faculty_schedule',
    'assign_faculty_to_slot',
    'bulk_assign_faculty',
    'calculate_faculty_load',
    'save_faculty_load',
    'recalculate_all_loads',
    'get_faculty_load',
    'get_overloaded_faculty',
    'suggest_faculty_for_subject',
    'get_least_loaded_faculty',
    
    # Timetable copy functions
    'TIMETABLE_COPY_AVAILABLE',
    'copy_timetable_to_division',
    'create_combined_class_timetable',
    'copy_timetable_to_degree_cohort',
    'copy_timetable_from_previous_term',
    'copy_timetable_to_all_divisions',
    'preview_timetable_copy',
    
    # Excel export
    'EXCEL_EXPORT_AVAILABLE',
    'TimetableExcelExporter',
    'export_timetable_to_excel',
    'FACULTY_COLORS',
    'BACKGROUND_COLORS',
    
    # Timetable service operations
    'TIMETABLE_SERVICE_AVAILABLE',
    'create_slot',
    'create_bridge',
    'get_slot',
    'get_slots_for_context',
    'get_slots_for_year',
    'get_bridge_slots',
    'get_slot_at_time',
    'update_slot',
    'update_slot_faculty',
    'lock_slot',
    'unlock_slot',
    'publish_slot',
    'delete_slot',
    'delete_bridge',
    'clear_timetable',
    'publish_timetable',
    'get_timetable_summary',
]


# ============================================================================
# STATUS SUMMARY
# ============================================================================

def get_services_status():
    """Get availability status of all services"""
    return {
        'conflict_detection': CONFLICT_DETECTION_AVAILABLE,
        'cross_tt_detection': CROSS_TT_DETECTION_AVAILABLE,
        'distribution_tracking': DISTRIBUTION_TRACKING_AVAILABLE,
        'faculty_scheduling': FACULTY_SCHEDULING_AVAILABLE,
        'timetable_copy': TIMETABLE_COPY_AVAILABLE,
        'excel_export': EXCEL_EXPORT_AVAILABLE,
        'timetable_service': TIMETABLE_SERVICE_AVAILABLE,
    }


def print_services_status():
    """Print service availability status"""
    status = get_services_status()
    print("\n" + "="*60)
    print("TIMETABLE SERVICES STATUS")
    print("="*60)
    for service, available in status.items():
        icon = "✅" if available else "❌"
        print(f"{icon} {service.replace('_', ' ').title()}: {'Available' if available else 'Unavailable'}")
    print("="*60 + "\n")


# Print status on import
if __name__ != '__main__':
    # Only print in verbose mode or debug mode
    import os
    if os.environ.get('TIMETABLE_DEBUG') or os.environ.get('VERBOSE'):
        print_services_status()
