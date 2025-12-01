"""
Timetable Models - normalized_weekly_assignment and revisions
"""

from dataclasses import dataclass
from typing import Optional, List
from datetime import date, datetime
import json


@dataclass
class TimetableSlot:
    """Represents a slot in normalized_weekly_assignment table"""
    id: Optional[int]
    
    # Context
    ay_label: str
    degree_code: str
    program_code: Optional[str]
    branch_code: Optional[str]
    year: int
    term: int
    division_code: Optional[str]
    
    # Subject link
    offering_id: int
    subject_code: str
    subject_name: str
    subject_type: str
    
    # Time slot
    day_of_week: int  # 1=Mon, 6=Sat
    period_index: int  # 1-8 (or up to 16)
    
    # Faculty assignment
    faculty_emails: List[str]  # First = In-Charge
    is_override_in_charge: bool  # True if Visiting allowed as In-Charge
    
    # Resources
    room_code: Optional[str]
    
    # Flags
    is_all_day_block: bool
    
    # Date ranges (denormalized for fast queries)
    module_start_date: Optional[date]
    module_end_date: Optional[date]
    week_start: int
    week_end: int
    
    # Status
    status: str  # 'draft', 'published', 'archived'
    
    created_at: Optional[datetime]
    
    @property
    def in_charge_email(self) -> Optional[str]:
        """Get subject in-charge email"""
        return self.faculty_emails[0] if self.faculty_emails else None
    
    @property
    def other_faculty_emails(self) -> List[str]:
        """Get other faculty emails"""
        return self.faculty_emails[1:] if len(self.faculty_emails) > 1 else []
    
    @property
    def faculty_count(self) -> int:
        """Get count of assigned faculty"""
        return len(self.faculty_emails)
    
    @property
    def day_name(self) -> str:
        """Get day name from index"""
        days = ["", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
        return days[self.day_of_week] if 1 <= self.day_of_week <= 6 else "?"
    
    @property
    def has_module_dates(self) -> bool:
        """Check if slot has specific date range"""
        return self.module_start_date is not None and self.module_end_date is not None
    
    def to_dict(self) -> dict:
        """Convert to dictionary for database operations"""
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
            'period_index': self.period_index,
            'faculty_ids': json.dumps(self.faculty_emails),
            'is_override_in_charge': 1 if self.is_override_in_charge else 0,
            'room_code': self.room_code,
            'is_all_day_block': 1 if self.is_all_day_block else 0,
            'module_start_date': self.module_start_date,
            'module_end_date': self.module_end_date,
            'week_start': self.week_start,
            'week_end': self.week_end,
        }


@dataclass
class TimetableRevision:
    """Represents a timetable revision (for future revisioning feature)"""
    id: Optional[int]
    
    # Context
    ay_label: str
    degree_code: str
    year: int
    term: int
    division_code: Optional[str]
    
    # Revision info
    revision_number: int  # R1, R2, R3, etc.
    snapshot_json: str  # Full timetable snapshot
    diff_summary: Optional[str]  # What changed
    
    # Status
    is_finalized: bool
    is_published: bool
    
    # Audit
    created_by: str
    created_at: datetime
    
    # Approval (if required)
    approved_by: Optional[str]
    approved_at: Optional[datetime]
    approval_reason: Optional[str]
    
    @property
    def revision_label(self) -> str:
        """Get revision label (e.g., 'R3')"""
        return f"R{self.revision_number}"
    
    @property
    def is_approved(self) -> bool:
        """Check if revision is approved"""
        return self.approved_by is not None
    
    def get_snapshot(self) -> dict:
        """Parse snapshot JSON"""
        try:
            return json.loads(self.snapshot_json)
        except:
            return {}


@dataclass
class TimetableMetadata:
    """Metadata for a timetable (status, revision, etc.)"""
    
    # Context
    ay_label: str
    degree_code: str
    year: int
    term: int
    division_code: Optional[str]
    
    # Status
    status: str  # 'draft', 'published', 'archived'
    
    # Revision info
    current_revision: int
    total_revisions: int
    
    # Dates
    last_modified_at: datetime
    last_modified_by: str
    published_at: Optional[datetime]
    published_by: Optional[str]
    archived_at: Optional[datetime]
    archived_by: Optional[str]
    
    # Flags
    is_finalized: bool
    is_editable: bool  # Based on status and permissions
    
    @property
    def status_label(self) -> str:
        """Get human-readable status label"""
        labels = {
            'draft': '📝 Draft',
            'published': '✅ Published',
            'archived': '📦 Archived',
        }
        return labels.get(self.status, self.status)
    
    @property
    def revision_label(self) -> str:
        """Get current revision label"""
        return f"R{self.current_revision}"
