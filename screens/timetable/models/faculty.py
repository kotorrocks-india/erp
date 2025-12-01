"""
Faculty Models - Based on faculty_profiles and faculty_affiliations schemas
"""

from dataclasses import dataclass
from typing import Optional
from datetime import datetime


@dataclass
class FacultyProfile:
    """Faculty profile from faculty_profiles table"""
    id: Optional[int]
    email: str
    name: str
    phone: Optional[str]
    employee_id: Optional[str]
    date_of_joining: Optional[str]
    highest_qualification: Optional[str]
    specialization: Optional[str]
    status: str  # 'active', 'inactive', etc.
    username: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    
    @property
    def is_active(self) -> bool:
        """Check if faculty is active"""
        return self.status == 'active'
    
    @property
    def initials(self) -> str:
        """Get initials from name"""
        parts = self.name.split()
        if len(parts) >= 2:
            return f"{parts[0][0]}{parts[-1][0]}"
        elif len(parts) == 1:
            return parts[0][:2]
        return "??"
    
    @property
    def display_name(self) -> str:
        """Get display name with employee ID if available"""
        if self.employee_id:
            return f"{self.name} ({self.employee_id})"
        return self.name


@dataclass
class FacultyAffiliation:
    """Faculty affiliation from faculty_affiliations table"""
    id: Optional[int]
    email: str
    degree_code: str
    program_code: Optional[str]
    branch_code: Optional[str]
    group_code: Optional[str]
    designation: str
    type: str  # 'core' or 'visiting'
    allowed_credit_override: bool
    active: bool
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    
    @property
    def is_core(self) -> bool:
        """Check if this is a core affiliation"""
        return self.type.lower() == 'core'
    
    @property
    def is_visiting(self) -> bool:
        """Check if this is a visiting affiliation"""
        return self.type.lower() == 'visiting'
    
    @property
    def type_label(self) -> str:
        """Get human-readable type label"""
        return "Core" if self.is_core else "Visiting"
    
    def matches_context(self, degree: str, program: Optional[str] = None, 
                       branch: Optional[str] = None) -> bool:
        """Check if this affiliation matches the given context"""
        if self.degree_code.lower() != degree.lower():
            return False
        
        # If affiliation has program specified, it must match
        if self.program_code and program:
            if self.program_code.lower() != program.lower():
                return False
        
        # If affiliation has branch specified, it must match
        if self.branch_code and branch:
            if self.branch_code.lower() != branch.lower():
                return False
        
        return True


@dataclass
class FacultyWithAffiliation:
    """Combined faculty profile with affiliation for a specific context"""
    profile: FacultyProfile
    affiliation: FacultyAffiliation
    
    @property
    def email(self) -> str:
        return self.profile.email
    
    @property
    def name(self) -> str:
        return self.profile.name
    
    @property
    def type(self) -> str:
        return self.affiliation.type
    
    @property
    def is_core(self) -> bool:
        return self.affiliation.is_core
    
    @property
    def is_visiting(self) -> bool:
        return self.affiliation.is_visiting
    
    @property
    def is_active(self) -> bool:
        return self.profile.is_active and self.affiliation.active
    
    @property
    def display_name(self) -> str:
        """Display name with type indicator"""
        type_suffix = " (V)" if self.is_visiting else ""
        return f"{self.profile.name}{type_suffix}"
    
    @property
    def initials(self) -> str:
        return self.profile.initials
