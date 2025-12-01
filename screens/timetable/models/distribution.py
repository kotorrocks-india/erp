"""
Subject Distribution Model - weekly_subject_distribution table
"""

from dataclasses import dataclass
from typing import Optional, List
from datetime import date
import json


@dataclass
class SubjectDistribution:
    """Represents a row in weekly_subject_distribution"""
    id: Optional[int]
    offering_id: int
    subject_code: str
    subject_name: str
    subject_type: str
    
    # Hierarchy context
    ay_label: str
    degree_code: str
    program_code: Optional[str]
    branch_code: Optional[str]
    year: int
    term: int
    division_code: Optional[str]
    
    # Credits
    student_credits: float
    teaching_credits: float
    credit_allocation_method: str
    
    # Faculty assignment
    faculty_emails: List[str]  # First = In-Charge
    
    # Slot model
    slot_model: str  # 'period_count_per_day' or 'explicit_slots'
    
    # Period counts per day (for period_count model)
    mon_periods: int
    tue_periods: int
    wed_periods: int
    thu_periods: int
    fri_periods: int
    sat_periods: int
    
    # Explicit slots per day (for explicit_slots model) - JSON strings
    mon_slots: Optional[str]
    tue_slots: Optional[str]
    wed_slots: Optional[str]
    thu_slots: Optional[str]
    fri_slots: Optional[str]
    sat_slots: Optional[str]
    
    # Flags
    is_all_day_elective_block: bool
    extended_afternoon_days: Optional[str]  # CSV: "Mon,Wed"
    
    # Date ranges (for partial-term modules)
    module_start_date: Optional[date]
    module_end_date: Optional[date]
    week_start: int
    week_end: int
    
    # Resources
    room_code: Optional[str]
    
    @property
    def in_charge_email(self) -> Optional[str]:
        """Get subject in-charge email (first faculty)"""
        return self.faculty_emails[0] if self.faculty_emails else None
    
    @property
    def other_faculty_emails(self) -> List[str]:
        """Get other faculty emails (not in-charge)"""
        return self.faculty_emails[1:] if len(self.faculty_emails) > 1 else []
    
    @property
    def total_periods_per_week(self) -> int:
        """Calculate total periods per week"""
        return (
            self.mon_periods + self.tue_periods + self.wed_periods +
            self.thu_periods + self.fri_periods + self.sat_periods
        )
    
    @property
    def extended_days_list(self) -> List[str]:
        """Get list of extended afternoon days"""
        if not self.extended_afternoon_days:
            return []
        return [day.strip() for day in self.extended_afternoon_days.split(',') if day.strip()]
    
    @property
    def has_module_dates(self) -> bool:
        """Check if module has specific date range"""
        return self.module_start_date is not None and self.module_end_date is not None
    
    def get_explicit_slots_for_day(self, day: str) -> List[int]:
        """Get explicit slot list for a day"""
        slot_attr = f"{day.lower()}_slots"
        slot_json = getattr(self, slot_attr, None)
        if not slot_json:
            return []
        try:
            return json.loads(slot_json)
        except:
            return []
    
    def to_dict(self) -> dict:
        """Convert to dictionary for database operations"""
        return {
            'id': self.id,
            'offering_id': self.offering_id,
            'subject_code': self.subject_code,
            'ay_label': self.ay_label,
            'degree_code': self.degree_code,
            'program_code': self.program_code,
            'branch_code': self.branch_code,
            'year': self.year,
            'term': self.term,
            'division_code': self.division_code,
            'subject_type': self.subject_type,
            'student_credits': self.student_credits,
            'teaching_credits': self.teaching_credits,
            'mon_periods': self.mon_periods,
            'tue_periods': self.tue_periods,
            'wed_periods': self.wed_periods,
            'thu_periods': self.thu_periods,
            'fri_periods': self.fri_periods,
            'sat_periods': self.sat_periods,
            'is_all_day_elective_block': 1 if self.is_all_day_elective_block else 0,
            'extended_afternoon_days': self.extended_afternoon_days,
            'module_start_date': self.module_start_date,
            'module_end_date': self.module_end_date,
            'week_start': self.week_start,
            'week_end': self.week_end,
            'room_code': self.room_code,
        }
