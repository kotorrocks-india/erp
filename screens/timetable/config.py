"""
Configuration Constants for Weekly Planner & Timetable
"""

# Days of the week
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
DAY_INDICES = {day: idx for idx, day in enumerate(DAYS, start=1)}

# Period configuration
MAX_PERIODS_BASELINE = 8
MAX_PERIODS_EXTENDED = 16

# Week range
DEFAULT_WEEK_START = 1
DEFAULT_WEEK_END = 20

# Color scheme from Slide 23 YAML
COLORS = {
    "in_charge": "#2F80ED",      # Blue - Subject In-Charge
    "regular": "#000000",         # Black - Regular Faculty
    "visiting": "#FF6AA2",        # Pink - Visiting Faculty
    "extended": "#FFF9C4",        # Light yellow - Extended afternoon
    "all_day": "#E3F2FD",        # Light blue - All-day elective
    "archived": "#9E9E9E",        # Grey - Archived timetables
    "published": "#4CAF50",       # Green - Published timetables
}

# Slot model options
class SlotModel:
    PERIOD_COUNT = "period_count_per_day"
    EXPLICIT_SLOTS = "explicit_slots"

# Subject types
class SubjectType:
    CORE = "Core"
    ELECTIVE = "Elective"
    COLLEGE_PROJECT = "College Project"

# Credit allocation methods
class CreditAllocation:
    EQUAL_PER_FACULTY = "equal_per_faculty"
    SPLIT_BY_COUNT = "split_by_faculty_count"

# Faculty affiliation types (from your schema)
class FacultyType:
    CORE = "core"
    VISITING = "visiting"

# Timetable status
class TimetableStatus:
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"

# Faculty configuration
class FacultyConfig:
    # Minimum faculty per subject
    MIN_FACULTY_PER_SUBJECT = 1
    
    # Maximum faculty per subject (configurable)
    MAX_FACULTY_PER_SUBJECT = 10
    
    # In-charge rules
    ALLOW_VISITING_IN_CHARGE = False  # Global toggle
    REQUIRE_CORE_IN_CHARGE = True     # Inverse of above
    
    # Faculty selection
    SHOW_INACTIVE_FACULTY = False

# Validation configuration
class ValidationConfig:
    ENABLE_CONFLICT_CHECKING = True
    ENABLE_DATE_OVERLAP_CHECK = True
    ENABLE_ROOM_CONFLICT_CHECK = False  # Rooms feature optional
    WARN_ON_CROSS_DIVISION_CONFLICT = True

# Export configuration
class ExportConfig:
    PDF_PAGE_SIZE = "A3"
    PDF_ORIENTATION = "landscape"
    EXCEL_SHEET_PER_DIVISION = True
    INCLUDE_LEGEND = True
    DESIGNER_NAME = "LPEP System"  # For footer

# Audit configuration
class AuditConfig:
    KEEP_LAST_REVISIONS = 50
    LOG_ALL_MUTATIONS = True
    CAPTURE_ACTOR_DETAILS = True

# UI Configuration
class UIConfig:
    SHOW_LEGEND = True
    SHOW_QUICK_JUMPS = True
    ENABLE_DRAG_DROP = False  # Future feature
    SHOW_TOOLTIPS = True
    DEFAULT_TAB = 0  # 0=Distribution, 1=Timetable, 2=Operations, 3=Audit

# Database configuration
class DatabaseConfig:
    # Timeout for long operations (seconds)
    QUERY_TIMEOUT = 30
    
    # Connection pool settings (if using pooling)
    POOL_SIZE = 10
    MAX_OVERFLOW = 20

# Feature flags
class FeatureFlags:
    ENABLE_EXPLICIT_SLOTS = False  # Not yet implemented
    ENABLE_ROOM_MANAGEMENT = False  # Optional feature
    ENABLE_NOTIFICATIONS = False   # Email/SMS notifications
    ENABLE_PERMISSIONS = False     # Role-based access control
    ENABLE_APPROVALS = False       # Publish approval workflow
    ENABLE_REVISIONING = False     # R{n} versioning
    ENABLE_IMPORT_CSV = True       # CSV import
    ENABLE_EXPORT_PDF = False      # PDF export (needs implementation)
    ENABLE_EXPORT_EXCEL = False    # Excel export (needs implementation)

# Messages
class Messages:
    NO_SUBJECTS = "⚠️ No subject offerings found. Please configure Subject Offerings (Slide 19) first."
    NO_FACULTY = "⚠️ No faculty found. Please configure Faculty Profiles (Slide 10) first."
    SAVE_SUCCESS = "✅ Saved successfully!"
    DELETE_SUCCESS = "✅ Deleted successfully!"
    PUBLISH_SUCCESS = "✅ Published successfully!"
    ARCHIVE_SUCCESS = "✅ Archived successfully!"
    VALIDATION_ERROR = "❌ Validation errors found. Please fix before saving."
    CONFLICT_WARNING = "⚠️ Faculty conflicts detected. Review warnings below."
    NO_CHANGES = "ℹ️ No changes detected."

# Help text
class HelpText:
    EXTENDED_AFTERNOON = "Mark days where periods exceed baseline (8). These will show with * marker."
    ALL_DAY_ELECTIVE = "Full-day workshop with breaks provided by faculty as required."
    MODULE_DATES = "Optional: Specify if this subject runs for only part of the term."
    VISITING_IN_CHARGE = "By default, only Core faculty can be Subject In-Charge. Toggle to allow Visiting faculty."
    FACULTY_CONFLICTS = "System checks if selected faculty are already teaching at this time in other divisions."
