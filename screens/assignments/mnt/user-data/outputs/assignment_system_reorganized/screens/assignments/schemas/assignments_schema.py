# assignments_schema.py
"""
Assignments Schema (Slide 25) - Complete Implementation
Integrates with:
- subject_offerings (Slide 19)
- weekly_subject_distribution (faculty assignments)
- students (rosters)

Safe to run multiple times (idempotent).
"""

from __future__ import annotations
from sqlalchemy import text as sa_text
from sqlalchemy.engine import Engine
from core.schema_registry import register
import logging
import json

logger = logging.getLogger(__name__)


def _exec(conn, sql: str, params: dict = None):
    """Execute SQL with parameters."""
    return conn.execute(sa_text(sql), params or {})


def _table_exists(conn, table: str) -> bool:
    """Check if table exists."""
    result = _exec(conn, 
        "SELECT name FROM sqlite_master WHERE type='table' AND name=:t",
        {"t": table}
    ).fetchone()
    return result is not None


def _has_column(conn, table: str, col: str) -> bool:
    """Check if column exists in table."""
    rows = _exec(conn, f"PRAGMA table_info({table})").fetchall()
    return any(r[1].lower() == col.lower() for r in rows)


# ===========================================================================
# MAIN ASSIGNMENTS TABLE
# ===========================================================================

def install_assignments_table(engine: Engine):
    """
    Main assignments table - per-subject assessment components.
    """
    with engine.begin() as conn:
        _exec(conn, """
        CREATE TABLE IF NOT EXISTS assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            
            -- Offering Reference
            offering_id INTEGER NOT NULL,
            
            -- Context (denormalized for queries)
            ay_label TEXT NOT NULL COLLATE NOCASE,
            degree_code TEXT NOT NULL COLLATE NOCASE,
            program_code TEXT COLLATE NOCASE,
            branch_code TEXT COLLATE NOCASE,
            year INTEGER NOT NULL CHECK (year >= 1 AND year <= 10),
            term INTEGER NOT NULL CHECK (term >= 1 AND term <= 4),
            subject_code TEXT NOT NULL COLLATE NOCASE,
            
            -- Assignment Identity
            number INTEGER NOT NULL CHECK (number >= 1),
            title TEXT NOT NULL,
            description TEXT,
            
            -- Marks Structure
            bucket TEXT NOT NULL CHECK (bucket IN ('Internal', 'External')),
            max_marks REAL NOT NULL CHECK (max_marks > 0),
            
            -- Submission Configuration (JSON)
            submission_config TEXT NOT NULL DEFAULT '{}',
            -- {
            --   "types": ["MCQ", "File Upload", "Presentation", "Physical/Studio/Jury", "Viva/Test"],
            --   "file_upload": {
            --     "multiple_files": true,
            --     "max_file_mb": 100,
            --     "allowed_types": ["pdf", "pptx", "docx", "xlsx", "jpg", "png", "zip"],
            --     "storage": "local_signed_url"
            --   }
            -- }
            
            -- Dates & Deadlines
            due_at DATETIME NOT NULL,
            grace_minutes INTEGER NOT NULL DEFAULT 15,
            
            -- Late Policy (JSON)
            late_policy TEXT NOT NULL DEFAULT '{}',
            -- {
            --   "mode": "allow_with_penalty|no_late|allow_until_cutoff",
            --   "penalty_percent_per_day": 10,
            --   "penalty_cap_percent": 50,
            --   "hard_cutoff_at": null
            -- }
            
            -- Extensions (JSON)
            extensions_config TEXT NOT NULL DEFAULT '{}',
            -- {
            --   "allowed": true,
            --   "require_reason": true,
            --   "pd_approval_required_after_publish": true
            -- }
            
            -- Group Work (JSON)
            group_config TEXT NOT NULL DEFAULT '{}',
            -- {
            --   "enabled": false,
            --   "grouping_model": "free_form",
            --   "min_size": 2,
            --   "max_size": 4
            -- }
            
            -- Mentoring (JSON)
            mentoring_config TEXT NOT NULL DEFAULT '{}',
            -- {
            --   "enabled_at_subject": true,
            --   "enabled_at_assignment": true,
            --   "mentors_from_subject_faculty": true,
            --   "multiple_mentors_per_student": true
            -- }
            
            -- Visibility & Status
            visibility_state TEXT NOT NULL DEFAULT 'Hidden' 
                CHECK (visibility_state IN ('Hidden', 'Visible_Accepting', 'Closed', 'Results_Published')),
            results_publish_mode TEXT NOT NULL DEFAULT 'marks_and_rubrics'
                CHECK (results_publish_mode IN ('marks_and_rubrics', 'pass_fail_only', 'grade_pattern')),
            
            -- Plagiarism Detection (JSON)
            plagiarism_config TEXT NOT NULL DEFAULT '{}',
            -- {
            --   "enabled": true,
            --   "similarity_score": null,
            --   "warn_threshold_percent": 20,
            --   "block_threshold_percent": 40,
            --   "exclude_bibliography_flag": true
            -- }
            
            -- Drop/Ignore (JSON)
            drop_config TEXT NOT NULL DEFAULT '{}',
            -- {
            --   "class_wide_drop_requested": false,
            --   "class_wide_drop_reason": "",
            --   "per_student_excuse_allowed": true
            -- }
            
            -- Workflow
            status TEXT NOT NULL DEFAULT 'draft' 
                CHECK (status IN ('draft', 'published', 'archived', 'deactivated')),
            published_at DATETIME,
            published_by TEXT,
            
            -- Audit
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            created_by TEXT,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_by TEXT,
            
            -- Constraints
            UNIQUE(offering_id, number),
            FOREIGN KEY (offering_id) REFERENCES subject_offerings(id) ON DELETE CASCADE
        )
        """)
        
        # Indexes
        _exec(conn, "CREATE INDEX IF NOT EXISTS idx_assignments_offering ON assignments(offering_id)")
        _exec(conn, "CREATE INDEX IF NOT EXISTS idx_assignments_context ON assignments(ay_label, degree_code, year, term, subject_code)")
        _exec(conn, "CREATE INDEX IF NOT EXISTS idx_assignments_status ON assignments(status)")
        _exec(conn, "CREATE INDEX IF NOT EXISTS idx_assignments_due ON assignments(due_at)")
        _exec(conn, "CREATE INDEX IF NOT EXISTS idx_assignments_visibility ON assignments(visibility_state)")
        
        logger.info("✅ Installed assignments table")


# ===========================================================================
# CO MAPPING TABLE
# ===========================================================================

def install_co_mapping_table(engine: Engine):
    """CO correlation mapping per assignment."""
    with engine.begin() as conn:
        _exec(conn, """
        CREATE TABLE IF NOT EXISTS assignment_co_mapping (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            assignment_id INTEGER NOT NULL,
            co_code TEXT NOT NULL COLLATE NOCASE,
            correlation_value INTEGER NOT NULL CHECK (correlation_value >= 0 AND correlation_value <= 3),
            scale_type TEXT NOT NULL DEFAULT '0_3' CHECK (scale_type IN ('0_3', '0_N')),
            
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            
            UNIQUE(assignment_id, co_code),
            FOREIGN KEY (assignment_id) REFERENCES assignments(id) ON DELETE CASCADE
        )
        """)
        
        _exec(conn, "CREATE INDEX IF NOT EXISTS idx_co_mapping_assignment ON assignment_co_mapping(assignment_id)")
        _exec(conn, "CREATE INDEX IF NOT EXISTS idx_co_mapping_co ON assignment_co_mapping(co_code)")
        
        logger.info("✅ Installed assignment_co_mapping table")


# ===========================================================================
# RUBRICS ATTACHMENT TABLE
# ===========================================================================

def install_rubrics_attachment_table(engine: Engine):
    """Rubrics attached to assignments."""
    with engine.begin() as conn:
        _exec(conn, """
        CREATE TABLE IF NOT EXISTS assignment_rubrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            assignment_id INTEGER NOT NULL,
            
            rubric_mode TEXT NOT NULL DEFAULT 'A' CHECK (rubric_mode IN ('A', 'B')),
            -- Mode A: Single rubric
            -- Mode B: Multiple rubrics with top-level weights
            
            rubric_id INTEGER NOT NULL,
            rubric_version TEXT,
            top_level_weight_percent REAL DEFAULT 100.0 CHECK (top_level_weight_percent >= 0 AND top_level_weight_percent <= 100),
            
            sequence_order INTEGER NOT NULL DEFAULT 1,
            
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            
            FOREIGN KEY (assignment_id) REFERENCES assignments(id) ON DELETE CASCADE
        )
        """)
        
        _exec(conn, "CREATE INDEX IF NOT EXISTS idx_rubrics_assignment ON assignment_rubrics(assignment_id)")
        _exec(conn, "CREATE INDEX IF NOT EXISTS idx_rubrics_rubric ON assignment_rubrics(rubric_id)")
        
        logger.info("✅ Installed assignment_rubrics table")


# ===========================================================================
# EVALUATORS TABLE
# ===========================================================================

def install_evaluators_table(engine: Engine):
    """Faculty assigned to evaluate assignments."""
    with engine.begin() as conn:
        _exec(conn, """
        CREATE TABLE IF NOT EXISTS assignment_evaluators (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            assignment_id INTEGER NOT NULL,
            faculty_id TEXT NOT NULL COLLATE NOCASE,
            evaluator_role TEXT NOT NULL DEFAULT 'evaluator' 
                CHECK (evaluator_role IN ('subject_in_charge', 'subject_faculty', 'mentor', 'external_examiner', 'evaluator')),
            
            can_edit_marks INTEGER NOT NULL DEFAULT 1,
            can_moderate INTEGER NOT NULL DEFAULT 0,
            
            assigned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            assigned_by TEXT,
            
            UNIQUE(assignment_id, faculty_id),
            FOREIGN KEY (assignment_id) REFERENCES assignments(id) ON DELETE CASCADE
        )
        """)
        
        _exec(conn, "CREATE INDEX IF NOT EXISTS idx_evaluators_assignment ON assignment_evaluators(assignment_id)")
        _exec(conn, "CREATE INDEX IF NOT EXISTS idx_evaluators_faculty ON assignment_evaluators(faculty_id)")
        
        logger.info("✅ Installed assignment_evaluators table")


# ===========================================================================
# GROUPS TABLE
# ===========================================================================

def install_groups_table(engine: Engine):
    """Student groups for group assignments."""
    with engine.begin() as conn:
        _exec(conn, """
        CREATE TABLE IF NOT EXISTS assignment_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            assignment_id INTEGER NOT NULL,
            group_name TEXT NOT NULL,
            group_code TEXT,
            
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            created_by TEXT,
            
            UNIQUE(assignment_id, group_name),
            FOREIGN KEY (assignment_id) REFERENCES assignments(id) ON DELETE CASCADE
        )
        """)
        
        _exec(conn, """
        CREATE TABLE IF NOT EXISTS assignment_group_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            student_roll_no TEXT NOT NULL COLLATE NOCASE,
            
            joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            
            UNIQUE(group_id, student_roll_no),
            FOREIGN KEY (group_id) REFERENCES assignment_groups(id) ON DELETE CASCADE
        )
        """)
        
        _exec(conn, "CREATE INDEX IF NOT EXISTS idx_groups_assignment ON assignment_groups(assignment_id)")
        _exec(conn, "CREATE INDEX IF NOT EXISTS idx_group_members_group ON assignment_group_members(group_id)")
        _exec(conn, "CREATE INDEX IF NOT EXISTS idx_group_members_student ON assignment_group_members(student_roll_no)")
        
        logger.info("✅ Installed assignment_groups and members tables")


# ===========================================================================
# MENTORING TABLE
# ===========================================================================

def install_mentoring_table(engine: Engine):
    """Mentor assignments per student."""
    with engine.begin() as conn:
        _exec(conn, """
        CREATE TABLE IF NOT EXISTS assignment_mentors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            assignment_id INTEGER NOT NULL,
            student_roll_no TEXT NOT NULL COLLATE NOCASE,
            mentor_faculty_id TEXT NOT NULL COLLATE NOCASE,
            
            assigned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            assigned_by TEXT,
            
            FOREIGN KEY (assignment_id) REFERENCES assignments(id) ON DELETE CASCADE
        )
        """)
        
        _exec(conn, "CREATE INDEX IF NOT EXISTS idx_mentors_assignment ON assignment_mentors(assignment_id)")
        _exec(conn, "CREATE INDEX IF NOT EXISTS idx_mentors_student ON assignment_mentors(student_roll_no)")
        _exec(conn, "CREATE INDEX IF NOT EXISTS idx_mentors_faculty ON assignment_mentors(mentor_faculty_id)")
        
        logger.info("✅ Installed assignment_mentors table")


# ===========================================================================
# SUBMISSIONS TABLE
# ===========================================================================

def install_submissions_table(engine: Engine):
    """Student submissions tracking."""
    with engine.begin() as conn:
        _exec(conn, """
        CREATE TABLE IF NOT EXISTS assignment_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            assignment_id INTEGER NOT NULL,
            student_roll_no TEXT NOT NULL COLLATE NOCASE,
            group_id INTEGER,
            
            submission_type TEXT NOT NULL,
            submission_data TEXT,  -- JSON with file URLs, MCQ answers, etc.
            
            submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            is_late INTEGER NOT NULL DEFAULT 0,
            late_penalty_percent REAL DEFAULT 0,
            
            status TEXT NOT NULL DEFAULT 'submitted' 
                CHECK (status IN ('draft', 'submitted', 'under_review', 'graded', 'returned')),
            
            -- Plagiarism Results (JSON)
            plagiarism_result TEXT,
            -- {
            --   "similarity_score": 25.5,
            --   "flagged": false,
            --   "details": "..."
            -- }
            
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            
            FOREIGN KEY (assignment_id) REFERENCES assignments(id) ON DELETE CASCADE,
            FOREIGN KEY (group_id) REFERENCES assignment_groups(id) ON DELETE SET NULL
        )
        """)
        
        _exec(conn, "CREATE UNIQUE INDEX IF NOT EXISTS idx_submissions_student_assignment ON assignment_submissions(assignment_id, student_roll_no)")
        _exec(conn, "CREATE INDEX IF NOT EXISTS idx_submissions_status ON assignment_submissions(status)")
        _exec(conn, "CREATE INDEX IF NOT EXISTS idx_submissions_late ON assignment_submissions(is_late)")
        
        logger.info("✅ Installed assignment_submissions table")


# ===========================================================================
# MARKS TABLE
# ===========================================================================

def install_marks_table(engine: Engine):
    """Marks awarded per submission."""
    with engine.begin() as conn:
        _exec(conn, """
        CREATE TABLE IF NOT EXISTS assignment_marks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            assignment_id INTEGER NOT NULL,
            student_roll_no TEXT NOT NULL COLLATE NOCASE,
            submission_id INTEGER,
            
            evaluator_id TEXT COLLATE NOCASE,
            
            marks_obtained REAL NOT NULL CHECK (marks_obtained >= 0),
            max_marks REAL NOT NULL,
            
            rubric_breakdown TEXT,  -- JSON with per-criterion scores
            
            comments TEXT,
            
            is_excused INTEGER NOT NULL DEFAULT 0,
            excuse_reason TEXT,
            
            graded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            graded_by TEXT,
            
            moderated INTEGER NOT NULL DEFAULT 0,
            moderated_at DATETIME,
            moderated_by TEXT,
            
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            
            UNIQUE(assignment_id, student_roll_no),
            FOREIGN KEY (assignment_id) REFERENCES assignments(id) ON DELETE CASCADE,
            FOREIGN KEY (submission_id) REFERENCES assignment_submissions(id) ON DELETE SET NULL
        )
        """)
        
        _exec(conn, "CREATE INDEX IF NOT EXISTS idx_marks_assignment ON assignment_marks(assignment_id)")
        _exec(conn, "CREATE INDEX IF NOT EXISTS idx_marks_student ON assignment_marks(student_roll_no)")
        _exec(conn, "CREATE INDEX IF NOT EXISTS idx_marks_evaluator ON assignment_marks(evaluator_id)")
        _exec(conn, "CREATE INDEX IF NOT EXISTS idx_marks_excused ON assignment_marks(is_excused)")
        
        logger.info("✅ Installed assignment_marks table")


# ===========================================================================
# EXTENSIONS TABLE
# ===========================================================================

def install_extensions_table(engine: Engine):
    """Extension requests per student."""
    with engine.begin() as conn:
        _exec(conn, """
        CREATE TABLE IF NOT EXISTS assignment_extensions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            assignment_id INTEGER NOT NULL,
            student_roll_no TEXT NOT NULL COLLATE NOCASE,
            
            requested_new_due_at DATETIME NOT NULL,
            reason TEXT NOT NULL,
            
            status TEXT NOT NULL DEFAULT 'pending' 
                CHECK (status IN ('pending', 'approved', 'denied')),
            
            approved_by TEXT,
            approved_at DATETIME,
            approval_note TEXT,
            
            requested_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            requested_by TEXT,
            
            FOREIGN KEY (assignment_id) REFERENCES assignments(id) ON DELETE CASCADE
        )
        """)
        
        _exec(conn, "CREATE INDEX IF NOT EXISTS idx_extensions_assignment ON assignment_extensions(assignment_id)")
        _exec(conn, "CREATE INDEX IF NOT EXISTS idx_extensions_student ON assignment_extensions(student_roll_no)")
        _exec(conn, "CREATE INDEX IF NOT EXISTS idx_extensions_status ON assignment_extensions(status)")
        
        logger.info("✅ Installed assignment_extensions table")


# ===========================================================================
# GRADE PATTERNS TABLE
# ===========================================================================

def install_grade_patterns_table(engine: Engine):
    """Custom grade patterns per assignment."""
    with engine.begin() as conn:
        _exec(conn, """
        CREATE TABLE IF NOT EXISTS assignment_grade_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            assignment_id INTEGER NOT NULL,
            
            pattern_name TEXT NOT NULL,
            bands TEXT NOT NULL,  -- JSON array of grade bands
            -- [
            --   {"min_percent": 90, "max_percent": 100, "grade_label": "A+"},
            --   {"min_percent": 80, "max_percent": 89, "grade_label": "A"},
            --   ...
            -- ]
            
            is_active INTEGER NOT NULL DEFAULT 1,
            
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            created_by TEXT,
            
            FOREIGN KEY (assignment_id) REFERENCES assignments(id) ON DELETE CASCADE
        )
        """)
        
        _exec(conn, "CREATE INDEX IF NOT EXISTS idx_grade_patterns_assignment ON assignment_grade_patterns(assignment_id)")
        
        logger.info("✅ Installed assignment_grade_patterns table")


# ===========================================================================
# AUDIT TABLE
# ===========================================================================

def install_audit_table(engine: Engine):
    """Comprehensive audit trail."""
    with engine.begin() as conn:
        _exec(conn, """
        CREATE TABLE IF NOT EXISTS assignments_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            
            assignment_id INTEGER NOT NULL,
            offering_id INTEGER NOT NULL,
            
            actor_id TEXT NOT NULL,
            actor_role TEXT NOT NULL,
            
            operation TEXT NOT NULL,
            -- create, update, publish, unpublish, archive, restore,
            -- marks_import, marks_edit, moderation_apply, drop_class_wide,
            -- excuse_student, rollback, visibility_change
            
            scope TEXT NOT NULL,  -- assignment, marks, submission, etc.
            
            before_data TEXT,  -- JSON snapshot before change
            after_data TEXT,   -- JSON snapshot after change
            
            reason TEXT,
            source TEXT DEFAULT 'ui',  -- ui, import, api
            correlation_id TEXT,
            step_up_performed INTEGER DEFAULT 0,
            
            occurred_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            
            FOREIGN KEY (assignment_id) REFERENCES assignments(id) ON DELETE CASCADE
        )
        """)
        
        _exec(conn, "CREATE INDEX IF NOT EXISTS idx_audit_assignment ON assignments_audit(assignment_id)")
        _exec(conn, "CREATE INDEX IF NOT EXISTS idx_audit_actor ON assignments_audit(actor_id)")
        _exec(conn, "CREATE INDEX IF NOT EXISTS idx_audit_operation ON assignments_audit(operation)")
        _exec(conn, "CREATE INDEX IF NOT EXISTS idx_audit_occurred ON assignments_audit(occurred_at)")
        
        logger.info("✅ Installed assignments_audit table")


# ===========================================================================
# SNAPSHOTS TABLE (Versioning)
# ===========================================================================

def install_snapshots_table(engine: Engine):
    """Version snapshots for rollback."""
    with engine.begin() as conn:
        _exec(conn, """
        CREATE TABLE IF NOT EXISTS assignment_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            assignment_id INTEGER NOT NULL,
            
            snapshot_number INTEGER NOT NULL,
            snapshot_type TEXT NOT NULL,  -- create, publish, edit, rollback, etc.
            snapshot_data TEXT NOT NULL,  -- Full JSON of assignment + related data
            
            note TEXT,
            
            is_active_version INTEGER NOT NULL DEFAULT 0,
            
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            created_by TEXT,
            
            FOREIGN KEY (assignment_id) REFERENCES assignments(id) ON DELETE CASCADE
        )
        """)
        
        _exec(conn, "CREATE INDEX IF NOT EXISTS idx_snapshots_assignment ON assignment_snapshots(assignment_id)")
        _exec(conn, "CREATE INDEX IF NOT EXISTS idx_snapshots_active ON assignment_snapshots(is_active_version)")
        
        logger.info("✅ Installed assignment_snapshots table")


# ===========================================================================
# APPROVALS TABLE
# ===========================================================================

def install_approvals_table(engine: Engine):
    """Approval workflow tracking."""
    with engine.begin() as conn:
        _exec(conn, """
        CREATE TABLE IF NOT EXISTS assignment_approvals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            assignment_id INTEGER NOT NULL,
            
            approval_type TEXT NOT NULL,  -- publish, major_edit, drop_class_wide
            request_reason TEXT NOT NULL,
            
            status TEXT NOT NULL DEFAULT 'pending' 
                CHECK (status IN ('pending', 'approved', 'denied', 'cancelled')),
            
            requested_by TEXT NOT NULL,
            requested_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            
            approver_id TEXT,
            approver_role TEXT,
            approved_at DATETIME,
            approval_note TEXT,
            
            step_up_performed INTEGER DEFAULT 0,
            
            FOREIGN KEY (assignment_id) REFERENCES assignments(id) ON DELETE CASCADE
        )
        """)
        
        _exec(conn, "CREATE INDEX IF NOT EXISTS idx_approvals_assignment ON assignment_approvals(assignment_id)")
        _exec(conn, "CREATE INDEX IF NOT EXISTS idx_approvals_status ON assignment_approvals(status)")
        _exec(conn, "CREATE INDEX IF NOT EXISTS idx_approvals_type ON assignment_approvals(approval_type)")
        
        logger.info("✅ Installed assignment_approvals table")


# ===========================================================================
# VIEWS
# ===========================================================================

def install_views(engine: Engine):
    """Create helpful views."""
    with engine.begin() as conn:
        
        # View: Assignments with offering context
        _exec(conn, "DROP VIEW IF EXISTS v_assignments_with_context")
        _exec(conn, """
        CREATE VIEW v_assignments_with_context AS
        SELECT 
            a.*,
            so.subject_code || ' - ' || COALESCE(sc.subject_name, '') as subject_display,
            so.internal_marks_max as offering_internal_max,
            so.exam_marks_max as offering_external_max,
            so.status as offering_status
        FROM assignments a
        JOIN subject_offerings so ON a.offering_id = so.id
        LEFT JOIN subjects_catalog sc ON so.subject_code = sc.subject_code
        """)
        
        # View: Assignment statistics
        _exec(conn, "DROP VIEW IF EXISTS v_assignment_statistics")
        _exec(conn, """
        CREATE VIEW v_assignment_statistics AS
        SELECT 
            a.id as assignment_id,
            a.offering_id,
            a.title,
            a.bucket,
            a.max_marks,
            a.visibility_state,
            COUNT(DISTINCT s.id) as submission_count,
            COUNT(DISTINCT CASE WHEN s.is_late = 1 THEN s.id END) as late_submission_count,
            COUNT(DISTINCT m.id) as graded_count,
            AVG(m.marks_obtained) as avg_marks,
            MIN(m.marks_obtained) as min_marks,
            MAX(m.marks_obtained) as max_marks,
            COUNT(DISTINCT CASE WHEN m.is_excused = 1 THEN m.id END) as excused_count
        FROM assignments a
        LEFT JOIN assignment_submissions s ON a.id = s.assignment_id
        LEFT JOIN assignment_marks m ON a.id = m.assignment_id
        GROUP BY a.id
        """)
        
        # View: Faculty evaluation load
        _exec(conn, "DROP VIEW IF EXISTS v_faculty_evaluation_load")
        _exec(conn, """
        CREATE VIEW v_faculty_evaluation_load AS
        SELECT 
            ae.faculty_id,
            a.ay_label,
            a.term,
            COUNT(DISTINCT a.id) as assignment_count,
            COUNT(DISTINCT s.id) as submission_count,
            COUNT(DISTINCT m.id) as graded_count,
            COUNT(DISTINCT s.id) - COUNT(DISTINCT m.id) as pending_grading_count
        FROM assignment_evaluators ae
        JOIN assignments a ON ae.assignment_id = a.id
        LEFT JOIN assignment_submissions s ON a.id = s.assignment_id
        LEFT JOIN assignment_marks m ON a.id = m.assignment_id AND m.evaluator_id = ae.faculty_id
        GROUP BY ae.faculty_id, a.ay_label, a.term
        """)
        
        # View: Student assignment progress
        _exec(conn, "DROP VIEW IF EXISTS v_student_assignment_progress")
        _exec(conn, """
        CREATE VIEW v_student_assignment_progress AS
        SELECT 
            a.offering_id,
            a.ay_label,
            a.degree_code,
            a.year,
            a.term,
            a.subject_code,
            'STUDENT_ROLL' as student_roll_no,  -- Placeholder, join with actual students
            COUNT(DISTINCT a.id) as total_assignments,
            COUNT(DISTINCT s.id) as submitted_count,
            COUNT(DISTINCT m.id) as graded_count,
            COUNT(DISTINCT CASE WHEN a.visibility_state = 'Visible_Accepting' AND s.id IS NULL THEN a.id END) as pending_submission_count
        FROM assignments a
        LEFT JOIN assignment_submissions s ON a.id = s.assignment_id
        LEFT JOIN assignment_marks m ON a.id = m.assignment_id
        WHERE a.status = 'published'
        GROUP BY a.offering_id, a.ay_label, a.degree_code, a.year, a.term, a.subject_code
        """)
        
        logger.info("✅ Installed views")


# ===========================================================================
# MAIN INSTALLATION FUNCTION
# ===========================================================================

@register
def install_assignments_schema(engine: Engine):
    """Install complete assignments schema."""
    try:
        install_assignments_table(engine)
        install_co_mapping_table(engine)
        install_rubrics_attachment_table(engine)
        install_evaluators_table(engine)
        install_groups_table(engine)
        install_mentoring_table(engine)
        install_submissions_table(engine)
        install_marks_table(engine)
        install_extensions_table(engine)
        install_grade_patterns_table(engine)
        install_audit_table(engine)
        install_snapshots_table(engine)
        install_approvals_table(engine)
        install_views(engine)
        
        logger.info("✅ Assignments schema installation complete")
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to install assignments schema: {e}")
        raise


# ===========================================================================
# HELPER FUNCTIONS
# ===========================================================================

def create_assignment_snapshot(engine: Engine, assignment_id: int, snapshot_type: str, actor: str, note: str = None) -> int:
    """Create a version snapshot of an assignment."""
    with engine.begin() as conn:
        # Get current assignment data
        assignment = _exec(conn, "SELECT * FROM assignments WHERE id = :id", {"id": assignment_id}).fetchone()
        if not assignment:
            raise ValueError(f"Assignment {assignment_id} not found")
        
        # Collect related data
        co_mapping = _exec(conn, "SELECT * FROM assignment_co_mapping WHERE assignment_id = :id", {"id": assignment_id}).fetchall()
        rubrics = _exec(conn, "SELECT * FROM assignment_rubrics WHERE assignment_id = :id", {"id": assignment_id}).fetchall()
        evaluators = _exec(conn, "SELECT * FROM assignment_evaluators WHERE assignment_id = :id", {"id": assignment_id}).fetchall()
        
        snapshot_data = {
            "assignment": dict(assignment._mapping),
            "co_mapping": [dict(r._mapping) for r in co_mapping],
            "rubrics": [dict(r._mapping) for r in rubrics],
            "evaluators": [dict(r._mapping) for r in evaluators]
        }
        
        # Get next snapshot number
        result = _exec(conn, """
        SELECT COALESCE(MAX(snapshot_number), 0) + 1 as next_num
        FROM assignment_snapshots
        WHERE assignment_id = :id
        """, {"id": assignment_id}).fetchone()
        
        next_num = result[0]
        
        # Mark previous snapshots as inactive
        _exec(conn, """
        UPDATE assignment_snapshots
        SET is_active_version = 0
        WHERE assignment_id = :id
        """, {"id": assignment_id})
        
        # Create new snapshot
        _exec(conn, """
        INSERT INTO assignment_snapshots
        (assignment_id, snapshot_number, snapshot_type, snapshot_data, note, created_by, is_active_version)
        VALUES (:assignment_id, :snapshot_number, :snapshot_type, :snapshot_data, :note, :created_by, 1)
        """, {
            "assignment_id": assignment_id,
            "snapshot_number": next_num,
            "snapshot_type": snapshot_type,
            "snapshot_data": json.dumps(snapshot_data, default=str),
            "note": note,
            "created_by": actor
        })
        
        snapshot_id = conn.execute(sa_text("SELECT last_insert_rowid()")).fetchone()[0]
        
        logger.info(f"✅ Created snapshot #{next_num} for assignment {assignment_id}")
        return snapshot_id


def log_audit(engine: Engine, assignment_id: int, offering_id: int, actor_id: str, actor_role: str,
              operation: str, scope: str, before_data: dict = None, after_data: dict = None,
              reason: str = None, source: str = 'ui', step_up: bool = False):
    """Log an audit entry."""
    with engine.begin() as conn:
        _exec(conn, """
        INSERT INTO assignments_audit
        (assignment_id, offering_id, actor_id, actor_role, operation, scope,
         before_data, after_data, reason, source, step_up_performed)
        VALUES (:assignment_id, :offering_id, :actor_id, :actor_role, :operation, :scope,
                :before_data, :after_data, :reason, :source, :step_up)
        """, {
            "assignment_id": assignment_id,
            "offering_id": offering_id,
            "actor_id": actor_id,
            "actor_role": actor_role,
            "operation": operation,
            "scope": scope,
            "before_data": json.dumps(before_data) if before_data else None,
            "after_data": json.dumps(after_data) if after_data else None,
            "reason": reason,
            "source": source,
            "step_up": 1 if step_up else 0
        })


if __name__ == "__main__":
    # Test installation
    from sqlalchemy import create_engine
    
    print("\n" + "="*60)
    print("TESTING ASSIGNMENTS SCHEMA INSTALLATION")
    print("="*60 + "\n")
    
    engine = create_engine("sqlite:///test_assignments.db")
    success = install_assignments_schema(engine)
    
    if success:
        print("\n✅ Schema installation test PASSED!")
    else:
        print("\n❌ Schema installation test FAILED!")
    
    print("\n" + "="*60 + "\n")
