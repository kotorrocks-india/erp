# services/assignment_service.py
"""
Assignment Service - Business Logic Layer
Handles CRUD operations, validations, and business rules.
"""

from sqlalchemy import text as sa_text
from sqlalchemy.engine import Engine
from typing import Dict, List, Optional, Tuple
import json
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class AssignmentService:
    """Service for managing assignments."""
    
    def __init__(self, engine: Engine):
        self.engine = engine
    
    def _exec(self, conn, sql: str, params: dict = None):
        """Execute SQL with parameters."""
        return conn.execute(sa_text(sql), params or {})
    
    # ===================================================================
    # CREATE OPERATIONS
    # ===================================================================
    
    def create_assignment(
        self,
        offering_id: int,
        number: int,
        title: str,
        bucket: str,
        max_marks: float,
        due_at: datetime,
        actor: str,
        actor_role: str,
        **kwargs
    ) -> int:
        """Create a new assignment."""
        with self.engine.begin() as conn:
            # Get offering context
            offering = self._exec(conn, """
            SELECT ay_label, degree_code, program_code, branch_code, year, term, subject_code
            FROM subject_offerings WHERE id = :id
            """, {"id": offering_id}).fetchone()
            
            if not offering:
                raise ValueError(f"Offering {offering_id} not found")
            
            # Check for duplicate number
            existing = self._exec(conn, """
            SELECT id FROM assignments WHERE offering_id = :offering_id AND number = :number
            """, {"offering_id": offering_id, "number": number}).fetchone()
            
            if existing:
                raise ValueError(f"Assignment number {number} already exists for this offering")
            
            # Prepare JSON configs
            submission_config = json.dumps(kwargs.get('submission_config', {
                "types": ["File Upload"],
                "file_upload": {
                    "multiple_files": True,
                    "max_file_mb": 100,
                    "allowed_types": ["pdf", "pptx", "docx", "xlsx", "jpg", "png", "zip"],
                    "storage": "local_signed_url"
                }
            }))
            
            late_policy = json.dumps(kwargs.get('late_policy', {
                "mode": "allow_with_penalty",
                "penalty_percent_per_day": 10,
                "penalty_cap_percent": 50,
                "hard_cutoff_at": None
            }))
            
            extensions_config = json.dumps(kwargs.get('extensions_config', {
                "allowed": True,
                "require_reason": True,
                "pd_approval_required_after_publish": True
            }))
            
            group_config = json.dumps(kwargs.get('group_config', {
                "enabled": False,
                "grouping_model": "free_form",
                "min_size": 2,
                "max_size": 4
            }))
            
            mentoring_config = json.dumps(kwargs.get('mentoring_config', {
                "enabled_at_subject": True,
                "enabled_at_assignment": True,
                "mentors_from_subject_faculty": True,
                "multiple_mentors_per_student": True
            }))
            
            plagiarism_config = json.dumps(kwargs.get('plagiarism_config', {
                "enabled": True,
                "similarity_score": None,
                "warn_threshold_percent": 20,
                "block_threshold_percent": 40,
                "exclude_bibliography_flag": True
            }))
            
            drop_config = json.dumps(kwargs.get('drop_config', {
                "class_wide_drop_requested": False,
                "class_wide_drop_reason": "",
                "per_student_excuse_allowed": True
            }))
            
            # Insert assignment
            result = self._exec(conn, """
            INSERT INTO assignments (
                offering_id, ay_label, degree_code, program_code, branch_code,
                year, term, subject_code, number, title, description,
                bucket, max_marks, due_at, grace_minutes,
                submission_config, late_policy, extensions_config,
                group_config, mentoring_config, plagiarism_config, drop_config,
                visibility_state, results_publish_mode, status,
                created_by, updated_by
            ) VALUES (
                :offering_id, :ay_label, :degree_code, :program_code, :branch_code,
                :year, :term, :subject_code, :number, :title, :description,
                :bucket, :max_marks, :due_at, :grace_minutes,
                :submission_config, :late_policy, :extensions_config,
                :group_config, :mentoring_config, :plagiarism_config, :drop_config,
                :visibility_state, :results_publish_mode, :status,
                :created_by, :updated_by
            )
            """, {
                "offering_id": offering_id,
                "ay_label": offering[0],
                "degree_code": offering[1],
                "program_code": offering[2],
                "branch_code": offering[3],
                "year": offering[4],
                "term": offering[5],
                "subject_code": offering[6],
                "number": number,
                "title": title,
                "description": kwargs.get('description', ''),
                "bucket": bucket,
                "max_marks": max_marks,
                "due_at": due_at.isoformat() if isinstance(due_at, datetime) else due_at,
                "grace_minutes": kwargs.get('grace_minutes', 15),
                "submission_config": submission_config,
                "late_policy": late_policy,
                "extensions_config": extensions_config,
                "group_config": group_config,
                "mentoring_config": mentoring_config,
                "plagiarism_config": plagiarism_config,
                "drop_config": drop_config,
                "visibility_state": kwargs.get('visibility_state', 'Hidden'),
                "results_publish_mode": kwargs.get('results_publish_mode', 'marks_and_rubrics'),
                "status": kwargs.get('status', 'draft'),
                "created_by": actor,
                "updated_by": actor
            })
            
            assignment_id = conn.execute(sa_text("SELECT last_insert_rowid()")).fetchone()[0]
            
            # Log audit
            from assignments_schema import log_audit
            log_audit(
                self.engine, assignment_id, offering_id, actor, actor_role,
                "create", "assignment", None, {"title": title, "number": number}
            )
            
            logger.info(f"✅ Created assignment {assignment_id} - {title}")
            return assignment_id
    
    def add_co_mapping(self, assignment_id: int, co_code: str, correlation_value: int, scale_type: str = '0_3'):
        """Add CO correlation mapping."""
        with self.engine.begin() as conn:
            self._exec(conn, """
            INSERT OR REPLACE INTO assignment_co_mapping
            (assignment_id, co_code, correlation_value, scale_type)
            VALUES (:assignment_id, :co_code, :correlation_value, :scale_type)
            """, {
                "assignment_id": assignment_id,
                "co_code": co_code,
                "correlation_value": correlation_value,
                "scale_type": scale_type
            })
            
            logger.info(f"✅ Added CO mapping {co_code} = {correlation_value} for assignment {assignment_id}")
    
    def attach_rubric(
        self,
        assignment_id: int,
        rubric_id: int,
        rubric_mode: str = 'A',
        top_level_weight: float = 100.0,
        rubric_version: str = None
    ):
        """Attach a rubric to an assignment."""
        with self.engine.begin() as conn:
            # Get next sequence order
            result = self._exec(conn, """
            SELECT COALESCE(MAX(sequence_order), 0) + 1 as next_order
            FROM assignment_rubrics WHERE assignment_id = :id
            """, {"id": assignment_id}).fetchone()
            
            next_order = result[0]
            
            self._exec(conn, """
            INSERT INTO assignment_rubrics
            (assignment_id, rubric_mode, rubric_id, rubric_version, top_level_weight_percent, sequence_order)
            VALUES (:assignment_id, :rubric_mode, :rubric_id, :rubric_version, :top_level_weight, :sequence_order)
            """, {
                "assignment_id": assignment_id,
                "rubric_mode": rubric_mode,
                "rubric_id": rubric_id,
                "rubric_version": rubric_version,
                "top_level_weight": top_level_weight,
                "sequence_order": next_order
            })
            
            logger.info(f"✅ Attached rubric {rubric_id} to assignment {assignment_id}")
    
    def assign_evaluator(
        self,
        assignment_id: int,
        faculty_id: str,
        evaluator_role: str = 'evaluator',
        can_edit_marks: bool = True,
        can_moderate: bool = False,
        assigned_by: str = None
    ):
        """Assign a faculty member as evaluator."""
        with self.engine.begin() as conn:
            self._exec(conn, """
            INSERT OR REPLACE INTO assignment_evaluators
            (assignment_id, faculty_id, evaluator_role, can_edit_marks, can_moderate, assigned_by)
            VALUES (:assignment_id, :faculty_id, :evaluator_role, :can_edit_marks, :can_moderate, :assigned_by)
            """, {
                "assignment_id": assignment_id,
                "faculty_id": faculty_id,
                "evaluator_role": evaluator_role,
                "can_edit_marks": 1 if can_edit_marks else 0,
                "can_moderate": 1 if can_moderate else 0,
                "assigned_by": assigned_by
            })
            
            logger.info(f"✅ Assigned {faculty_id} as {evaluator_role} for assignment {assignment_id}")
    
    # ===================================================================
    # READ OPERATIONS
    # ===================================================================
    
    def get_assignment(self, assignment_id: int) -> Optional[Dict]:
        """Get assignment by ID."""
        with self.engine.begin() as conn:
            result = self._exec(conn, """
            SELECT * FROM v_assignments_with_context WHERE id = :id
            """, {"id": assignment_id}).fetchone()
            
            if not result:
                return None
            
            assignment = dict(result._mapping)
            
            # Parse JSON fields
            for field in ['submission_config', 'late_policy', 'extensions_config',
                         'group_config', 'mentoring_config', 'plagiarism_config', 'drop_config']:
                if assignment.get(field):
                    try:
                        assignment[field] = json.loads(assignment[field])
                    except:
                        assignment[field] = {}
            
            return assignment
    
    def list_assignments(
        self,
        offering_id: Optional[int] = None,
        ay_label: Optional[str] = None,
        degree_code: Optional[str] = None,
        year: Optional[int] = None,
        term: Optional[int] = None,
        subject_code: Optional[str] = None,
        bucket: Optional[str] = None,
        status: Optional[str] = None,
        visibility_state: Optional[str] = None
    ) -> List[Dict]:
        """List assignments with filters."""
        with self.engine.begin() as conn:
            where_clauses = []
            params = {}
            
            if offering_id:
                where_clauses.append("offering_id = :offering_id")
                params["offering_id"] = offering_id
            
            if ay_label:
                where_clauses.append("ay_label = :ay_label")
                params["ay_label"] = ay_label
            
            if degree_code:
                where_clauses.append("degree_code = :degree_code")
                params["degree_code"] = degree_code
            
            if year:
                where_clauses.append("year = :year")
                params["year"] = year
            
            if term:
                where_clauses.append("term = :term")
                params["term"] = term
            
            if subject_code:
                where_clauses.append("subject_code = :subject_code")
                params["subject_code"] = subject_code
            
            if bucket:
                where_clauses.append("bucket = :bucket")
                params["bucket"] = bucket
            
            if status:
                where_clauses.append("status = :status")
                params["status"] = status
            
            if visibility_state:
                where_clauses.append("visibility_state = :visibility_state")
                params["visibility_state"] = visibility_state
            
            where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
            
            results = self._exec(conn, f"""
            SELECT * FROM v_assignments_with_context
            WHERE {where_sql}
            ORDER BY number
            """, params).fetchall()
            
            assignments = []
            for row in results:
                assignment = dict(row._mapping)
                # Parse JSON fields
                for field in ['submission_config', 'late_policy', 'extensions_config',
                             'group_config', 'mentoring_config', 'plagiarism_config', 'drop_config']:
                    if assignment.get(field):
                        try:
                            assignment[field] = json.loads(assignment[field])
                        except:
                            assignment[field] = {}
                assignments.append(assignment)
            
            return assignments
    
    def get_co_mappings(self, assignment_id: int) -> List[Dict]:
        """Get CO mappings for an assignment."""
        with self.engine.begin() as conn:
            results = self._exec(conn, """
            SELECT * FROM assignment_co_mapping WHERE assignment_id = :id
            ORDER BY co_code
            """, {"id": assignment_id}).fetchall()
            
            return [dict(r._mapping) for r in results]
    
    def get_attached_rubrics(self, assignment_id: int) -> List[Dict]:
        """Get attached rubrics for an assignment."""
        with self.engine.begin() as conn:
            results = self._exec(conn, """
            SELECT * FROM assignment_rubrics WHERE assignment_id = :id
            ORDER BY sequence_order
            """, {"id": assignment_id}).fetchall()
            
            return [dict(r._mapping) for r in results]
    
    def get_evaluators(self, assignment_id: int) -> List[Dict]:
        """Get evaluators for an assignment."""
        with self.engine.begin() as conn:
            results = self._exec(conn, """
            SELECT ae.*, f.name as faculty_name, f.email as faculty_email
            FROM assignment_evaluators ae
            LEFT JOIN faculty f ON ae.faculty_id = f.id
            WHERE ae.assignment_id = :id
            ORDER BY ae.evaluator_role, f.name
            """, {"id": assignment_id}).fetchall()
            
            return [dict(r._mapping) for r in results]
    
    def get_assignment_statistics(self, assignment_id: int) -> Optional[Dict]:
        """Get statistics for an assignment."""
        with self.engine.begin() as conn:
            result = self._exec(conn, """
            SELECT * FROM v_assignment_statistics WHERE assignment_id = :id
            """, {"id": assignment_id}).fetchone()
            
            return dict(result._mapping) if result else None
    
    # ===================================================================
    # UPDATE OPERATIONS
    # ===================================================================
    
    def update_assignment(
        self,
        assignment_id: int,
        actor: str,
        actor_role: str,
        reason: str = None,
        **updates
    ):
        """Update assignment fields."""
        with self.engine.begin() as conn:
            # Get current state for audit
            current = self.get_assignment(assignment_id)
            if not current:
                raise ValueError(f"Assignment {assignment_id} not found")
            
            # Check if published and if major edit
            if current['status'] == 'published':
                major_edit_fields = ['max_marks', 'bucket', 'due_at', 'late_policy']
                is_major = any(field in updates for field in major_edit_fields)
                
                if is_major and not reason:
                    raise ValueError("Reason required for major edits to published assignments")
            
            # Build update SQL
            update_fields = []
            params = {"id": assignment_id, "actor": actor}
            
            for key, value in updates.items():
                if key in ['submission_config', 'late_policy', 'extensions_config',
                          'group_config', 'mentoring_config', 'plagiarism_config', 'drop_config']:
                    # JSON fields
                    params[key] = json.dumps(value) if isinstance(value, dict) else value
                else:
                    params[key] = value
                
                update_fields.append(f"{key} = :{key}")
            
            if not update_fields:
                return
            
            update_sql = ", ".join(update_fields)
            
            self._exec(conn, f"""
            UPDATE assignments
            SET {update_sql}, updated_by = :actor, updated_at = CURRENT_TIMESTAMP
            WHERE id = :id
            """, params)
            
            # Log audit
            from assignments_schema import log_audit
            log_audit(
                self.engine, assignment_id, current['offering_id'], actor, actor_role,
                "update", "assignment", current, updates, reason
            )
            
            logger.info(f"✅ Updated assignment {assignment_id}")
    
    def update_visibility(
        self,
        assignment_id: int,
        new_state: str,
        actor: str,
        actor_role: str
    ):
        """Update assignment visibility state."""
        valid_states = ['Hidden', 'Visible_Accepting', 'Closed', 'Results_Published']
        if new_state not in valid_states:
            raise ValueError(f"Invalid visibility state: {new_state}")
        
        self.update_assignment(
            assignment_id, actor, actor_role,
            visibility_state=new_state
        )
        
        # Log specific audit
        from assignments_schema import log_audit
        assignment = self.get_assignment(assignment_id)
        log_audit(
            self.engine, assignment_id, assignment['offering_id'], actor, actor_role,
            "visibility_change", "assignment", None, {"new_state": new_state}
        )
    
    # ===================================================================
    # PUBLISH / ARCHIVE OPERATIONS
    # ===================================================================
    
    def publish_assignment(
        self,
        assignment_id: int,
        approver_id: str,
        approver_role: str,
        reason: str
    ):
        """Publish an assignment (requires approval)."""
        with self.engine.begin() as conn:
            assignment = self.get_assignment(assignment_id)
            if not assignment:
                raise ValueError(f"Assignment {assignment_id} not found")
            
            if assignment['status'] == 'published':
                raise ValueError("Assignment already published")
            
            # Validate requirements
            self._validate_for_publish(assignment_id)
            
            # Create snapshot before publishing
            from assignments_schema import create_assignment_snapshot
            create_assignment_snapshot(self.engine, assignment_id, "publish", approver_id, reason)
            
            # Update status
            self._exec(conn, """
            UPDATE assignments
            SET status = 'published', published_at = CURRENT_TIMESTAMP, published_by = :approver
            WHERE id = :id
            """, {"id": assignment_id, "approver": approver_id})
            
            # Log audit
            from assignments_schema import log_audit
            log_audit(
                self.engine, assignment_id, assignment['offering_id'], approver_id, approver_role,
                "publish", "assignment", None, {"reason": reason}, reason, step_up=True
            )
            
            logger.info(f"✅ Published assignment {assignment_id}")
    
    def _validate_for_publish(self, assignment_id: int):
        """Validate assignment can be published."""
        assignment = self.get_assignment(assignment_id)
        
        # Check due date is in future
        due_at = datetime.fromisoformat(assignment['due_at'])
        if due_at < datetime.now():
            raise ValueError("Due date must be in the future to publish")
        
        # Check at least one CO mapping with value > 0
        co_mappings = self.get_co_mappings(assignment_id)
        if not any(m['correlation_value'] > 0 for m in co_mappings):
            raise ValueError("At least one CO mapping must have correlation > 0")
        
        # Check rubric mode B weights sum to 100
        rubrics = self.get_attached_rubrics(assignment_id)
        mode_b_rubrics = [r for r in rubrics if r['rubric_mode'] == 'B']
        if mode_b_rubrics:
            total_weight = sum(r['top_level_weight_percent'] for r in mode_b_rubrics)
            if abs(total_weight - 100.0) > 0.01:
                raise ValueError("Mode B rubric weights must sum to 100%")
    
    def archive_assignment(
        self,
        assignment_id: int,
        actor: str,
        actor_role: str,
        reason: str
    ):
        """Archive an assignment."""
        assignment = self.get_assignment(assignment_id)
        if not assignment:
            raise ValueError(f"Assignment {assignment_id} not found")
        
        self.update_assignment(
            assignment_id, actor, actor_role, reason,
            status='archived'
        )
        
        logger.info(f"✅ Archived assignment {assignment_id}")
    
    # ===================================================================
    # DELETE OPERATIONS
    # ===================================================================
    
    def delete_assignment(self, assignment_id: int, actor: str, actor_role: str):
        """Delete an assignment (hard delete)."""
        with self.engine.begin() as conn:
            # Check for submissions or marks
            has_submissions = self._exec(conn, """
            SELECT COUNT(*) FROM assignment_submissions WHERE assignment_id = :id
            """, {"id": assignment_id}).fetchone()[0] > 0
            
            has_marks = self._exec(conn, """
            SELECT COUNT(*) FROM assignment_marks WHERE assignment_id = :id
            """, {"id": assignment_id}).fetchone()[0] > 0
            
            if has_submissions or has_marks:
                raise ValueError("Cannot delete assignment with submissions or marks. Archive instead.")
            
            # Get assignment for audit
            assignment = self.get_assignment(assignment_id)
            
            # Delete (cascades to related tables)
            self._exec(conn, "DELETE FROM assignments WHERE id = :id", {"id": assignment_id})
            
            # Log audit
            from assignments_schema import log_audit
            log_audit(
                self.engine, assignment_id, assignment['offering_id'], actor, actor_role,
                "delete", "assignment", assignment, None
            )
            
            logger.info(f"✅ Deleted assignment {assignment_id}")
    
    # ===================================================================
    # UTILITY FUNCTIONS
    # ===================================================================
    
    def auto_assign_evaluators_from_distribution(self, assignment_id: int):
        """Auto-assign evaluators based on weekly distribution."""
        with self.engine.begin() as conn:
            assignment = self.get_assignment(assignment_id)
            if not assignment:
                raise ValueError(f"Assignment {assignment_id} not found")
            
            # Get faculty from weekly distribution
            # This would integrate with your weekly_subject_distribution table
            # For now, a placeholder implementation
            
            logger.info(f"✅ Auto-assigned evaluators for assignment {assignment_id}")
    
    def calculate_scaled_marks(
        self,
        offering_id: int,
        bucket: str
    ) -> Tuple[float, List[Dict]]:
        """Calculate scaled marks for assignments."""
        with self.engine.begin() as conn:
            # Get offering max marks
            offering = self._exec(conn, """
            SELECT internal_marks_max, exam_marks_max
            FROM subject_offerings WHERE id = :id
            """, {"id": offering_id}).fetchone()
            
            if not offering:
                raise ValueError(f"Offering {offering_id} not found")
            
            bucket_max = offering[0] if bucket == 'Internal' else offering[1]
            
            # Get sum of assignment max marks in bucket
            result = self._exec(conn, """
            SELECT COALESCE(SUM(max_marks), 0) as total_raw_max
            FROM assignments
            WHERE offering_id = :id AND bucket = :bucket AND status = 'published'
            """, {"id": offering_id, "bucket": bucket}).fetchone()
            
            total_raw_max = result[0]
            
            if total_raw_max == 0:
                return 0, []
            
            scaling_factor = bucket_max / total_raw_max
            
            # Get all marks for this bucket
            marks_results = self._exec(conn, """
            SELECT m.*, a.max_marks, a.number, a.title
            FROM assignment_marks m
            JOIN assignments a ON m.assignment_id = a.id
            WHERE a.offering_id = :id AND a.bucket = :bucket AND a.status = 'published'
            """, {"id": offering_id, "bucket": bucket}).fetchall()
            
            scaled_marks = []
            for mark in marks_results:
                mark_dict = dict(mark._mapping)
                mark_dict['scaled_marks'] = mark_dict['marks_obtained'] * scaling_factor
                scaled_marks.append(mark_dict)
            
            return scaling_factor, scaled_marks


if __name__ == "__main__":
    # Test service
    from sqlalchemy import create_engine
    
    print("\n" + "="*60)
    print("TESTING ASSIGNMENT SERVICE")
    print("="*60 + "\n")
    
    engine = create_engine("sqlite:///test_assignments.db")
    service = AssignmentService(engine)
    
    print("\n✅ Service initialized successfully!")
    print("\n" + "="*60 + "\n")
