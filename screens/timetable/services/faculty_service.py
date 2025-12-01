"""
Faculty Service - Manages faculty data using real schemas
"""

from typing import List, Optional
from sqlalchemy import text
from sqlalchemy.engine import Engine
import pandas as pd

from models.context import Context
from models.faculty import FacultyProfile, FacultyAffiliation, FacultyWithAffiliation
from config import FacultyConfig, FacultyType


class FacultyService:
    """Service for faculty-related operations"""
    
    def __init__(self, engine: Engine):
        self.engine = engine
    
    def get_faculty_for_context(self, ctx: Context, 
                               include_inactive: bool = False) -> List[FacultyWithAffiliation]:
        """
        Get all faculty affiliated with the given context (degree/program/branch).
        Combines faculty_profiles with faculty_affiliations.
        """
        with self.engine.connect() as conn:
            # Build query
            query = text("""
                SELECT 
                    -- Profile columns
                    fp.id as profile_id,
                    fp.email,
                    fp.name,
                    fp.phone,
                    fp.employee_id,
                    fp.date_of_joining,
                    fp.highest_qualification,
                    fp.specialization,
                    fp.status,
                    fp.username,
                    fp.created_at as profile_created_at,
                    fp.updated_at as profile_updated_at,
                    -- Affiliation columns
                    fa.id as affiliation_id,
                    fa.degree_code,
                    fa.program_code,
                    fa.branch_code,
                    fa.group_code,
                    fa.designation,
                    fa.type,
                    fa.allowed_credit_override,
                    fa.active as affiliation_active,
                    fa.created_at as affiliation_created_at,
                    fa.updated_at as affiliation_updated_at
                FROM faculty_profiles fp
                JOIN faculty_affiliations fa ON LOWER(fp.email) = LOWER(fa.email)
                WHERE fa.degree_code = :degree
                  AND (fa.program_code = :program OR fa.program_code IS NULL OR :program IS NULL)
                  AND (fa.branch_code = :branch OR fa.branch_code IS NULL OR :branch IS NULL)
                  AND fa.active = 1
                  AND (:include_inactive = 1 OR fp.status = 'active')
                ORDER BY fp.name
            """)
            
            result = conn.execute(query, {
                'degree': ctx.degree,
                'program': ctx.program,
                'branch': ctx.branch,
                'include_inactive': 1 if include_inactive else 0
            })
            
            faculty_list = []
            for row in result:
                # Build profile
                profile = FacultyProfile(
                    id=row.profile_id,
                    email=row.email,
                    name=row.name,
                    phone=row.phone,
                    employee_id=row.employee_id,
                    date_of_joining=row.date_of_joining,
                    highest_qualification=row.highest_qualification,
                    specialization=row.specialization,
                    status=row.status,
                    username=row.username,
                    created_at=row.profile_created_at,
                    updated_at=row.profile_updated_at
                )
                
                # Build affiliation
                affiliation = FacultyAffiliation(
                    id=row.affiliation_id,
                    email=row.email,
                    degree_code=row.degree_code,
                    program_code=row.program_code,
                    branch_code=row.branch_code,
                    group_code=row.group_code,
                    designation=row.designation,
                    type=row.type,
                    allowed_credit_override=bool(row.allowed_credit_override),
                    active=bool(row.affiliation_active),
                    created_at=row.affiliation_created_at,
                    updated_at=row.affiliation_updated_at
                )
                
                faculty_list.append(FacultyWithAffiliation(profile, affiliation))
            
            return faculty_list
    
    def get_core_faculty(self, ctx: Context) -> List[FacultyWithAffiliation]:
        """Get only core faculty for context"""
        all_faculty = self.get_faculty_for_context(ctx)
        return [f for f in all_faculty if f.is_core]
    
    def get_visiting_faculty(self, ctx: Context) -> List[FacultyWithAffiliation]:
        """Get only visiting faculty for context"""
        all_faculty = self.get_faculty_for_context(ctx)
        return [f for f in all_faculty if f.is_visiting]
    
    def get_faculty_by_email(self, email: str, ctx: Context) -> Optional[FacultyWithAffiliation]:
        """Get specific faculty by email for context"""
        all_faculty = self.get_faculty_for_context(ctx, include_inactive=True)
        for f in all_faculty:
            if f.email.lower() == email.lower():
                return f
        return None
    
    def get_faculty_by_emails(self, emails: List[str], ctx: Context) -> List[FacultyWithAffiliation]:
        """Get multiple faculty by emails"""
        all_faculty = self.get_faculty_for_context(ctx, include_inactive=True)
        email_set = {e.lower() for e in emails}
        return [f for f in all_faculty if f.email.lower() in email_set]
    
    def validate_in_charge(self, email: str, ctx: Context, 
                          allow_visiting: bool = False) -> tuple[bool, Optional[str]]:
        """
        Validate if faculty can be subject in-charge.
        
        Returns: (is_valid, error_message)
        """
        faculty = self.get_faculty_by_email(email, ctx)
        
        if not faculty:
            return False, f"Faculty {email} not found or not affiliated with {ctx.degree}"
        
        if not faculty.is_active:
            return False, f"{faculty.name} is not active"
        
        # Check if visiting and not allowed
        if faculty.is_visiting and not allow_visiting:
            return False, f"{faculty.name} is Visiting faculty. Toggle 'Allow Visiting In-Charge' to proceed."
        
        return True, None
    
    def validate_faculty_team(self, emails: List[str], ctx: Context,
                             allow_visiting_in_charge: bool = False) -> tuple[bool, List[str]]:
        """
        Validate entire faculty team.
        First faculty must be valid in-charge.
        
        Returns: (is_valid, error_messages)
        """
        errors = []
        
        if not emails:
            errors.append("At least one faculty member required")
            return False, errors
        
        # Check minimum
        if len(emails) < FacultyConfig.MIN_FACULTY_PER_SUBJECT:
            errors.append(f"Minimum {FacultyConfig.MIN_FACULTY_PER_SUBJECT} faculty required")
        
        # Check maximum
        if len(emails) > FacultyConfig.MAX_FACULTY_PER_SUBJECT:
            errors.append(f"Maximum {FacultyConfig.MAX_FACULTY_PER_SUBJECT} faculty allowed")
        
        # Validate in-charge (first faculty)
        in_charge_email = emails[0]
        is_valid, error_msg = self.validate_in_charge(
            in_charge_email, ctx, allow_visiting_in_charge
        )
        if not is_valid:
            errors.append(f"In-Charge: {error_msg}")
        
        # Validate all faculty exist and are active
        faculty_list = self.get_faculty_by_emails(emails, ctx)
        found_emails = {f.email.lower() for f in faculty_list}
        
        for email in emails:
            if email.lower() not in found_emails:
                errors.append(f"Faculty {email} not found or not affiliated")
            else:
                # Check if active
                faculty = next(f for f in faculty_list if f.email.lower() == email.lower())
                if not faculty.is_active:
                    errors.append(f"{faculty.name} is not active")
        
        # Check for duplicates
        if len(emails) != len(set(e.lower() for e in emails)):
            errors.append("Duplicate faculty in team")
        
        return len(errors) == 0, errors
    
    def get_available_faculty(self, ctx: Context, day: int, period: int,
                             module_start: Optional[str], module_end: Optional[str],
                             current_slot_id: Optional[int] = None) -> List[FacultyWithAffiliation]:
        """
        Get faculty available for a specific time slot (no conflicts).
        Checks against normalized_weekly_assignment for overlaps.
        """
        all_faculty = self.get_faculty_for_context(ctx)
        
        # Get conflicting faculty emails
        with self.engine.connect() as conn:
            query = text("""
                SELECT DISTINCT faculty_ids
                FROM normalized_weekly_assignment
                WHERE ay_label = :ay
                  AND term = :term
                  AND day_of_week = :day
                  AND period_index = :period
                  AND id != :current_id
                  AND (
                    -- No module dates (full term)
                    (module_start_date IS NULL AND module_end_date IS NULL)
                    OR
                    -- Date overlap check
                    (:mod_start IS NOT NULL AND :mod_end IS NOT NULL AND
                     module_start_date <= :mod_end AND module_end_date >= :mod_start)
                    OR
                    -- One has dates, other doesn't (assume conflict)
                    (:mod_start IS NULL OR :mod_end IS NULL)
                  )
            """)
            
            result = conn.execute(query, {
                'ay': ctx.ay,
                'term': ctx.term,
                'day': day,
                'period': period,
                'current_id': current_slot_id or -1,
                'mod_start': module_start,
                'mod_end': module_end
            })
            
            # Extract all conflicting emails
            conflicting_emails = set()
            for row in result:
                if row.faculty_ids:
                    import json
                    emails = json.loads(row.faculty_ids)
                    conflicting_emails.update(e.lower() for e in emails)
        
        # Filter out conflicting faculty
        available = [f for f in all_faculty if f.email.lower() not in conflicting_emails]
        return available
    
    def get_faculty_statistics(self, ctx: Context) -> dict:
        """Get statistics about faculty for context"""
        all_faculty = self.get_faculty_for_context(ctx)
        core_count = sum(1 for f in all_faculty if f.is_core)
        visiting_count = sum(1 for f in all_faculty if f.is_visiting)
        
        return {
            'total': len(all_faculty),
            'core': core_count,
            'visiting': visiting_count,
            'active': sum(1 for f in all_faculty if f.is_active),
            'inactive': sum(1 for f in all_faculty if not f.is_active),
        }
