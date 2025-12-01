"""
Operations Service - Handles Publish, Delete, Archive operations
"""

from typing import Optional, List, Dict
from sqlalchemy import text
from sqlalchemy.engine import Engine
from datetime import datetime
import json

from models.context import Context
from models.timetable import TimetableMetadata
from config import TimetableStatus


class OperationsService:
    """Service for timetable operations (publish, archive, delete)"""
    
    def __init__(self, engine: Engine):
        self.engine = engine
    
    def get_timetable_metadata(self, ctx: Context) -> Optional[TimetableMetadata]:
        """Get metadata for a timetable"""
        with self.engine.connect() as conn:
            # Get metadata from normalized_weekly_assignment
            query = text("""
                SELECT 
                    COUNT(*) as slot_count,
                    MAX(created_at) as last_modified,
                    'draft' as status
                FROM normalized_weekly_assignment
                WHERE ay_label = :ay
                  AND degree_code = :deg
                  AND year = :yr
                  AND term = :term
                  AND division_code = :div
            """)
            
            result = conn.execute(query, ctx.to_dict()).fetchone()
            
            if not result or result.slot_count == 0:
                return None
            
            # TODO: Implement proper metadata table for status tracking
            # For now, return basic metadata
            return TimetableMetadata(
                ay_label=ctx.ay,
                degree_code=ctx.degree,
                year=ctx.year,
                term=ctx.term,
                division_code=ctx.division,
                status=TimetableStatus.DRAFT,  # Default for now
                current_revision=1,
                total_revisions=1,
                last_modified_at=result.last_modified or datetime.now(),
                last_modified_by='system',  # TODO: Get from session
                published_at=None,
                published_by=None,
                archived_at=None,
                archived_by=None,
                is_finalized=False,
                is_editable=True
            )
    
    def publish_timetable(self, ctx: Context, actor: str, reason: Optional[str] = None) -> bool:
        """
        Publish a timetable.
        
        Publishing means:
        1. Validate all slots are assigned
        2. Mark as published status
        3. Create revision snapshot
        4. Log audit trail
        5. (Future) Send notifications
        
        Returns: True if successful
        """
        with self.engine.begin() as conn:
            # Check if any slots exist
            count = conn.execute(
                text("""
                    SELECT COUNT(*) FROM normalized_weekly_assignment
                    WHERE ay_label = :ay AND degree_code = :deg 
                      AND year = :yr AND term = :term AND division_code = :div
                """),
                ctx.to_dict()
            ).scalar()
            
            if count == 0:
                raise ValueError("Cannot publish empty timetable")
            
            # TODO: Additional validations
            # - Check for conflicts
            # - Check for missing in-charge assignments
            # - Check for date range issues
            
            # Create snapshot (future: timetable_revisions table)
            snapshot = self._create_snapshot(conn, ctx)
            
            # Log audit
            conn.execute(
                text("""
                    INSERT INTO weekly_subject_distribution_audit
                    (distribution_id, offering_id, ay_label, degree_code, division_code, 
                     change_reason, changed_by)
                    VALUES (0, 0, :ay, :deg, :div, :reason, :actor)
                """),
                {
                    **ctx.to_dict(),
                    'reason': f"PUBLISH: {reason or 'Published timetable'}",
                    'actor': actor
                }
            )
            
            # TODO: Update status in metadata table when implemented
            # TODO: Increment revision number
            # TODO: Send notifications
            
            return True
    
    def archive_timetable(self, ctx: Context, actor: str, reason: Optional[str] = None) -> bool:
        """
        Archive a timetable.
        
        Archiving means:
        1. Mark as archived status
        2. Create final snapshot
        3. Make read-only
        4. Log audit trail
        
        Returns: True if successful
        """
        with self.engine.begin() as conn:
            # Create final snapshot
            snapshot = self._create_snapshot(conn, ctx)
            
            # Log audit
            conn.execute(
                text("""
                    INSERT INTO weekly_subject_distribution_audit
                    (distribution_id, offering_id, ay_label, degree_code, division_code, 
                     change_reason, changed_by)
                    VALUES (0, 0, :ay, :deg, :div, :reason, :actor)
                """),
                {
                    **ctx.to_dict(),
                    'reason': f"ARCHIVE: {reason or 'Archived timetable'}",
                    'actor': actor
                }
            )
            
            # TODO: Update status in metadata table
            # TODO: Mark as read-only
            
            return True
    
    def delete_timetable(self, ctx: Context, actor: str, 
                        reason: Optional[str] = None,
                        confirm: bool = False) -> bool:
        """
        Delete a timetable completely.
        
        This is destructive! Requires confirmation.
        Deletes:
        1. All normalized_weekly_assignment slots
        2. All weekly_subject_distribution records
        3. Logs deletion in audit trail
        
        Returns: True if successful
        """
        if not confirm:
            raise ValueError("Deletion requires explicit confirmation (confirm=True)")
        
        with self.engine.begin() as conn:
            # Log before deletion (capture snapshot)
            snapshot = self._create_snapshot(conn, ctx)
            
            # Delete from normalized_weekly_assignment
            deleted_slots = conn.execute(
                text("""
                    DELETE FROM normalized_weekly_assignment
                    WHERE ay_label = :ay AND degree_code = :deg 
                      AND year = :yr AND term = :term AND division_code = :div
                """),
                ctx.to_dict()
            ).rowcount
            
            # Delete from weekly_subject_distribution
            deleted_dists = conn.execute(
                text("""
                    DELETE FROM weekly_subject_distribution
                    WHERE ay_label = :ay AND degree_code = :deg 
                      AND year = :yr AND term = :term AND division_code = :div
                """),
                ctx.to_dict()
            ).rowcount
            
            # Log audit
            conn.execute(
                text("""
                    INSERT INTO weekly_subject_distribution_audit
                    (distribution_id, offering_id, ay_label, degree_code, division_code, 
                     change_reason, changed_by)
                    VALUES (0, 0, :ay, :deg, :div, :reason, :actor)
                """),
                {
                    **ctx.to_dict(),
                    'reason': f"DELETE: {reason or 'Deleted timetable'} (slots={deleted_slots}, dists={deleted_dists})",
                    'actor': actor
                }
            )
            
            return True
    
    def duplicate_timetable(self, source_ctx: Context, target_ctx: Context, 
                           actor: str) -> bool:
        """
        Duplicate a timetable from source to target context.
        
        Useful for:
        - Copying from previous year
        - Copying between divisions
        - Creating templates
        
        Returns: True if successful
        """
        with self.engine.begin() as conn:
            # Copy distributions
            conn.execute(
                text("""
                    INSERT INTO weekly_subject_distribution
                    (offering_id, ay_label, degree_code, program_code, branch_code, 
                     year, term, division_code, subject_code, subject_type,
                     student_credits, teaching_credits, mon_periods, tue_periods, 
                     wed_periods, thu_periods, fri_periods, sat_periods,
                     module_start_date, module_end_date, week_start, week_end,
                     is_all_day_elective_block, extended_afternoon_days, room_code)
                    SELECT 
                     offering_id, :target_ay, :target_deg, :target_prog, :target_branch,
                     :target_yr, :target_term, :target_div, subject_code, subject_type,
                     student_credits, teaching_credits, mon_periods, tue_periods,
                     wed_periods, thu_periods, fri_periods, sat_periods,
                     module_start_date, module_end_date, week_start, week_end,
                     is_all_day_elective_block, extended_afternoon_days, room_code
                    FROM weekly_subject_distribution
                    WHERE ay_label = :source_ay AND degree_code = :source_deg
                      AND year = :source_yr AND term = :source_term 
                      AND division_code = :source_div
                """),
                {
                    'source_ay': source_ctx.ay, 'source_deg': source_ctx.degree,
                    'source_yr': source_ctx.year, 'source_term': source_ctx.term,
                    'source_div': source_ctx.division,
                    'target_ay': target_ctx.ay, 'target_deg': target_ctx.degree,
                    'target_prog': target_ctx.program, 'target_branch': target_ctx.branch,
                    'target_yr': target_ctx.year, 'target_term': target_ctx.term,
                    'target_div': target_ctx.division,
                }
            )
            
            # Copy timetable slots
            conn.execute(
                text("""
                    INSERT INTO normalized_weekly_assignment
                    (ay_label, degree_code, program_code, branch_code, year, term, division_code,
                     offering_id, subject_code, subject_type, day_of_week, period_index,
                     faculty_ids, room_code, is_override_in_charge, is_all_day_block,
                     module_start_date, module_end_date, week_start, week_end)
                    SELECT 
                     :target_ay, :target_deg, :target_prog, :target_branch, 
                     :target_yr, :target_term, :target_div,
                     offering_id, subject_code, subject_type, day_of_week, period_index,
                     faculty_ids, room_code, is_override_in_charge, is_all_day_block,
                     module_start_date, module_end_date, week_start, week_end
                    FROM normalized_weekly_assignment
                    WHERE ay_label = :source_ay AND degree_code = :source_deg
                      AND year = :source_yr AND term = :source_term 
                      AND division_code = :source_div
                """),
                {
                    'source_ay': source_ctx.ay, 'source_deg': source_ctx.degree,
                    'source_yr': source_ctx.year, 'source_term': source_ctx.term,
                    'source_div': source_ctx.division,
                    'target_ay': target_ctx.ay, 'target_deg': target_ctx.degree,
                    'target_prog': target_ctx.program, 'target_branch': target_ctx.branch,
                    'target_yr': target_ctx.year, 'target_term': target_ctx.term,
                    'target_div': target_ctx.division,
                }
            )
            
            # Log audit
            conn.execute(
                text("""
                    INSERT INTO weekly_subject_distribution_audit
                    (distribution_id, offering_id, ay_label, degree_code, division_code, 
                     change_reason, changed_by)
                    VALUES (0, 0, :ay, :deg, :div, :reason, :actor)
                """),
                {
                    **target_ctx.to_dict(),
                    'reason': f"DUPLICATE: From {source_ctx} to {target_ctx}",
                    'actor': actor
                }
            )
            
            return True
    
    def _create_snapshot(self, conn, ctx: Context) -> str:
        """Create JSON snapshot of current timetable state"""
        # Get all slots
        slots = conn.execute(
            text("""
                SELECT * FROM normalized_weekly_assignment
                WHERE ay_label = :ay AND degree_code = :deg 
                  AND year = :yr AND term = :term AND division_code = :div
                ORDER BY day_of_week, period_index
            """),
            ctx.to_dict()
        ).fetchall()
        
        # Convert to JSON
        snapshot = {
            'context': ctx.to_dict(),
            'timestamp': datetime.now().isoformat(),
            'slots': [dict(row._mapping) for row in slots]
        }
        
        return json.dumps(snapshot, default=str)
    
    def get_audit_log(self, ctx: Context, limit: int = 100) -> List[Dict]:
        """Get audit log for a timetable"""
        with self.engine.connect() as conn:
            result = conn.execute(
                text("""
                    SELECT changed_at, changed_by, change_reason
                    FROM weekly_subject_distribution_audit
                    WHERE degree_code = :deg AND division_code = :div
                      AND ay_label = :ay
                    ORDER BY changed_at DESC
                    LIMIT :limit
                """),
                {**ctx.to_dict(), 'limit': limit}
            )
            
            return [
                {
                    'timestamp': row.changed_at,
                    'actor': row.changed_by,
                    'reason': row.change_reason
                }
                for row in result
            ]
    
    def validate_before_publish(self, ctx: Context) -> tuple[bool, List[str]]:
        """
        Validate timetable before publishing.
        
        Returns: (is_valid, error_messages)
        """
        errors = []
        
        with self.engine.connect() as conn:
            # Check if timetable exists
            count = conn.execute(
                text("""
                    SELECT COUNT(*) FROM normalized_weekly_assignment
                    WHERE ay_label = :ay AND degree_code = :deg 
                      AND year = :yr AND term = :term AND division_code = :div
                """),
                ctx.to_dict()
            ).scalar()
            
            if count == 0:
                errors.append("Timetable is empty")
                return False, errors
            
            # Check for slots without faculty
            no_faculty = conn.execute(
                text("""
                    SELECT COUNT(*) FROM normalized_weekly_assignment
                    WHERE ay_label = :ay AND degree_code = :deg 
                      AND year = :yr AND term = :term AND division_code = :div
                      AND (faculty_ids IS NULL OR faculty_ids = '[]')
                """),
                ctx.to_dict()
            ).scalar()
            
            if no_faculty > 0:
                errors.append(f"{no_faculty} slot(s) without faculty assignment")
            
            # Check for conflicts (same faculty, same time, overlapping dates)
            # TODO: Implement comprehensive conflict check
            
            # Check for missing in-charge
            # TODO: Check first faculty in each slot is valid in-charge
        
        return len(errors) == 0, errors
