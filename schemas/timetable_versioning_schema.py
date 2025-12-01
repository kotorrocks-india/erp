# ============================================================================
# TIMETABLE VERSIONING SCHEMA
# ============================================================================
# Add this to your schema files or run as migration
# Supports: Draft → Publish → Archive workflow with version control
# ============================================================================

from sqlalchemy import text as sa_text
from sqlalchemy.engine import Engine
from datetime import datetime


def install_timetable_versioning_schema(engine: Engine):
    """
    Install timetable versioning and publishing system
    
    Features:
    - Draft/Published/Archived status
    - Version control (R0, R1, R2, etc.)
    - Complete timetable snapshots
    - Rollback capability
    """
    
    with engine.begin() as conn:
        
        # ================================================================
        # TIMETABLE VERSIONS (Master version control)
        # ================================================================
        conn.execute(sa_text("""
        CREATE TABLE IF NOT EXISTS timetable_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            
            -- Version Identity
            version_code TEXT NOT NULL,          -- e.g., 'TT-R0', 'TT-R1', 'TT-R2'
            version_name TEXT NOT NULL,          -- e.g., 'Initial Draft', 'Final Published'
            
            -- Context (What this timetable is for)
            ay_label TEXT NOT NULL,
            degree_code TEXT NOT NULL,
            program_code TEXT,
            branch_code TEXT,
            term INTEGER NOT NULL,
            division_code TEXT,
            
            -- Status & Workflow
            status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN (
                'draft',           -- Being edited
                'published',       -- Active/live version
                'archived',        -- Old version kept for history
                'deleted'          -- Soft deleted
            )),
            
            -- Version Metadata
            version_number INTEGER NOT NULL,     -- 0, 1, 2, 3, ...
            is_current_published INTEGER DEFAULT 0,  -- Only one published version can be current
            
            -- Template Reference
            template_id INTEGER,                 -- Links to day_templates
            
            -- Publishing Info
            published_at DATETIME,
            published_by TEXT,
            
            -- Archive Info
            archived_at DATETIME,
            archived_by TEXT,
            archived_reason TEXT,
            
            -- Snapshot Data (JSON)
            timetable_data TEXT,                 -- Complete timetable as JSON
            
            -- Audit
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            created_by TEXT,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_by TEXT,
            
            -- Notes
            description TEXT,
            notes TEXT,
            
            -- Constraints
            UNIQUE(ay_label, degree_code, term, division_code, version_code),
            FOREIGN KEY (template_id) REFERENCES day_templates(id) ON DELETE SET NULL
        )
        """))
        
        conn.execute(sa_text("""
            CREATE INDEX IF NOT EXISTS idx_tt_versions_context 
            ON timetable_versions(ay_label, degree_code, term, division_code)
        """))
        
        conn.execute(sa_text("""
            CREATE INDEX IF NOT EXISTS idx_tt_versions_status 
            ON timetable_versions(status)
        """))
        
        conn.execute(sa_text("""
            CREATE INDEX IF NOT EXISTS idx_tt_versions_current 
            ON timetable_versions(is_current_published)
        """))
        
        # ================================================================
        # TIMETABLE VERSION SLOTS (Detailed slot data per version)
        # ================================================================
        conn.execute(sa_text("""
        CREATE TABLE IF NOT EXISTS timetable_version_slots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            
            -- Parent version
            version_id INTEGER NOT NULL,
            
            -- Slot Context
            year INTEGER NOT NULL,
            division_code TEXT NOT NULL,
            day_of_week INTEGER NOT NULL,       -- 1=Monday, 2=Tuesday, etc.
            period_id INTEGER NOT NULL,
            
            -- Subject Info
            offering_id INTEGER NOT NULL,
            subject_code TEXT NOT NULL,
            subject_type TEXT,
            
            -- Faculty Assignments (JSON array)
            faculty_ids TEXT,                   -- ["email1@school.edu", "email2@school.edu"]
            
            -- Room
            room_code TEXT,
            
            -- Metadata
            notes TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            
            FOREIGN KEY (version_id) REFERENCES timetable_versions(id) ON DELETE CASCADE,
            FOREIGN KEY (offering_id) REFERENCES subject_offerings(id)
        )
        """))
        
        conn.execute(sa_text("""
            CREATE INDEX IF NOT EXISTS idx_tt_version_slots_version 
            ON timetable_version_slots(version_id)
        """))
        
        # ================================================================
        # VERSION AUDIT LOG
        # ================================================================
        conn.execute(sa_text("""
        CREATE TABLE IF NOT EXISTS timetable_version_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            
            version_id INTEGER NOT NULL,
            version_code TEXT NOT NULL,
            
            action TEXT NOT NULL CHECK (action IN (
                'create', 'update', 'delete',
                'publish', 'unpublish', 'archive',
                'restore', 'clone', 'rollback'
            )),
            
            old_status TEXT,
            new_status TEXT,
            
            note TEXT,
            changed_by TEXT NOT NULL,
            changed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            
            FOREIGN KEY (version_id) REFERENCES timetable_versions(id) ON DELETE CASCADE
        )
        """))
        
        # ================================================================
        # VIEWS
        # ================================================================
        
        # View: Current published versions
        conn.execute(sa_text("DROP VIEW IF EXISTS v_current_published_timetables"))
        conn.execute(sa_text("""
        CREATE VIEW v_current_published_timetables AS
        SELECT 
            v.*,
            t.template_name,
            (SELECT COUNT(*) FROM timetable_version_slots s WHERE s.version_id = v.id) as slot_count
        FROM timetable_versions v
        LEFT JOIN day_templates t ON t.id = v.template_id
        WHERE v.status = 'published' 
          AND v.is_current_published = 1
        """))
        
        # View: Version history
        conn.execute(sa_text("DROP VIEW IF EXISTS v_timetable_version_history"))
        conn.execute(sa_text("""
        CREATE VIEW v_timetable_version_history AS
        SELECT 
            v.*,
            t.template_name,
            (SELECT COUNT(*) FROM timetable_version_slots s WHERE s.version_id = v.id) as slot_count,
            CASE 
                WHEN v.status = 'published' THEN '✅ Published'
                WHEN v.status = 'draft' THEN '📝 Draft'
                WHEN v.status = 'archived' THEN '📦 Archived'
                WHEN v.status = 'deleted' THEN '🗑️ Deleted'
            END as status_display
        FROM timetable_versions v
        LEFT JOIN day_templates t ON t.id = v.template_id
        ORDER BY v.ay_label DESC, v.degree_code, v.term, v.version_number DESC
        """))
        
        # ================================================================
        # TRIGGERS
        # ================================================================
        
        # Ensure only one current published version per context
        conn.execute(sa_text("""
        CREATE TRIGGER IF NOT EXISTS trg_ensure_single_current_published
        BEFORE UPDATE ON timetable_versions
        WHEN NEW.is_current_published = 1 AND NEW.status = 'published'
        BEGIN
            UPDATE timetable_versions
            SET is_current_published = 0
            WHERE ay_label = NEW.ay_label
              AND degree_code = NEW.degree_code
              AND term = NEW.term
              AND COALESCE(division_code, '') = COALESCE(NEW.division_code, '')
              AND id != NEW.id;
        END;
        """))
        
        # Auto-update timestamp
        conn.execute(sa_text("""
        CREATE TRIGGER IF NOT EXISTS trg_tt_version_update_timestamp
        AFTER UPDATE ON timetable_versions
        BEGIN
            UPDATE timetable_versions
            SET updated_at = CURRENT_TIMESTAMP
            WHERE id = NEW.id;
        END;
        """))
        
        print("✅ Timetable versioning schema installed successfully")


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def generate_version_code(prefix: str, version_number: int) -> str:
    """
    Generate version code
    
    Examples:
        generate_version_code('TT', 0) → 'TT-R0'
        generate_version_code('TT', 1) → 'TT-R1'
        generate_version_code('BARCH-Y1', 5) → 'BARCH-Y1-R5'
    """
    return f"{prefix}-R{version_number}"


def get_next_version_number(engine: Engine, context: dict) -> int:
    """
    Get next version number for a context
    
    Args:
        context: dict with ay_label, degree_code, term, division_code
    
    Returns:
        Next version number (0 if no versions exist)
    """
    with engine.connect() as conn:
        result = conn.execute(sa_text("""
            SELECT COALESCE(MAX(version_number), -1) + 1
            FROM timetable_versions
            WHERE ay_label = :ay
              AND degree_code = :deg
              AND term = :term
              AND COALESCE(division_code, '') = COALESCE(:div, '')
        """), {
            'ay': context['ay_label'],
            'deg': context['degree_code'],
            'term': context['term'],
            'div': context.get('division_code')
        }).fetchone()
        
        return result[0] if result else 0


def create_timetable_version(
    engine: Engine,
    context: dict,
    version_name: str,
    template_id: int = None,
    created_by: str = 'system'
) -> int:
    """
    Create a new draft timetable version
    
    Args:
        context: dict with ay_label, degree_code, term, division_code
        version_name: Human-readable name
        template_id: Optional template reference
        created_by: User identifier
    
    Returns:
        New version ID
    """
    version_number = get_next_version_number(engine, context)
    
    # Generate version code
    prefix = context.get('degree_code', 'TT')
    if context.get('division_code'):
        prefix = f"{prefix}-{context['division_code']}"
    
    version_code = generate_version_code(prefix, version_number)
    
    with engine.begin() as conn:
        result = conn.execute(sa_text("""
            INSERT INTO timetable_versions (
                version_code, version_name, version_number,
                ay_label, degree_code, program_code, branch_code, term, division_code,
                template_id, status, created_by
            ) VALUES (
                :code, :name, :ver_num,
                :ay, :deg, :prog, :branch, :term, :div,
                :template, 'draft', :created_by
            )
        """), {
            'code': version_code,
            'name': version_name,
            'ver_num': version_number,
            'ay': context['ay_label'],
            'deg': context['degree_code'],
            'prog': context.get('program_code'),
            'branch': context.get('branch_code'),
            'term': context['term'],
            'div': context.get('division_code'),
            'template': template_id,
            'created_by': created_by
        })
        
        version_id = result.lastrowid
        
        # Log audit
        conn.execute(sa_text("""
            INSERT INTO timetable_version_audit (
                version_id, version_code, action, new_status, changed_by
            ) VALUES (:vid, :code, 'create', 'draft', :by)
        """), {
            'vid': version_id,
            'code': version_code,
            'by': created_by
        })
        
        return version_id


def publish_timetable_version(
    engine: Engine,
    version_id: int,
    published_by: str = 'system'
) -> bool:
    """
    Publish a draft version (makes it current/active)
    
    - Unpublishes any existing current version
    - Sets this version as current published
    - Archives previous published version
    """
    with engine.begin() as conn:
        # Get version info
        version = conn.execute(sa_text("""
            SELECT version_code, status, ay_label, degree_code, term, division_code
            FROM timetable_versions
            WHERE id = :vid
        """), {'vid': version_id}).fetchone()
        
        if not version:
            return False
        
        if version[1] != 'draft':
            return False  # Can only publish drafts
        
        # Archive current published version
        conn.execute(sa_text("""
            UPDATE timetable_versions
            SET status = 'archived',
                is_current_published = 0,
                archived_at = CURRENT_TIMESTAMP,
                archived_by = :by,
                archived_reason = 'Replaced by new version'
            WHERE ay_label = :ay
              AND degree_code = :deg
              AND term = :term
              AND COALESCE(division_code, '') = COALESCE(:div, '')
              AND status = 'published'
              AND is_current_published = 1
        """), {
            'by': published_by,
            'ay': version[2],
            'deg': version[3],
            'term': version[4],
            'div': version[5]
        })
        
        # Publish this version
        conn.execute(sa_text("""
            UPDATE timetable_versions
            SET status = 'published',
                is_current_published = 1,
                published_at = CURRENT_TIMESTAMP,
                published_by = :by
            WHERE id = :vid
        """), {
            'vid': version_id,
            'by': published_by
        })
        
        # Log audit
        conn.execute(sa_text("""
            INSERT INTO timetable_version_audit (
                version_id, version_code, action, old_status, new_status, changed_by
            ) VALUES (:vid, :code, 'publish', 'draft', 'published', :by)
        """), {
            'vid': version_id,
            'code': version[0],
            'by': published_by
        })
        
        return True


def unpublish_timetable_version(
    engine: Engine,
    version_id: int,
    unpublished_by: str = 'system'
) -> bool:
    """
    Unpublish a version (back to draft for editing)
    """
    with engine.begin() as conn:
        # Get version info
        version = conn.execute(sa_text("""
            SELECT version_code, status
            FROM timetable_versions
            WHERE id = :vid
        """), {'vid': version_id}).fetchone()
        
        if not version or version[1] != 'published':
            return False
        
        # Unpublish
        conn.execute(sa_text("""
            UPDATE timetable_versions
            SET status = 'draft',
                is_current_published = 0
            WHERE id = :vid
        """), {'vid': version_id})
        
        # Log audit
        conn.execute(sa_text("""
            INSERT INTO timetable_version_audit (
                version_id, version_code, action, old_status, new_status, changed_by
            ) VALUES (:vid, :code, 'unpublish', 'published', 'draft', :by)
        """), {
            'vid': version_id,
            'code': version[0],
            'by': unpublished_by
        })
        
        return True


def archive_timetable_version(
    engine: Engine,
    version_id: int,
    reason: str,
    archived_by: str = 'system'
) -> bool:
    """Archive a version"""
    with engine.begin() as conn:
        version = conn.execute(sa_text("""
            SELECT version_code, status
            FROM timetable_versions
            WHERE id = :vid
        """), {'vid': version_id}).fetchone()
        
        if not version:
            return False
        
        old_status = version[1]
        
        conn.execute(sa_text("""
            UPDATE timetable_versions
            SET status = 'archived',
                is_current_published = 0,
                archived_at = CURRENT_TIMESTAMP,
                archived_by = :by,
                archived_reason = :reason
            WHERE id = :vid
        """), {
            'vid': version_id,
            'by': archived_by,
            'reason': reason
        })
        
        # Log audit
        conn.execute(sa_text("""
            INSERT INTO timetable_version_audit (
                version_id, version_code, action, old_status, new_status, note, changed_by
            ) VALUES (:vid, :code, 'archive', :old, 'archived', :reason, :by)
        """), {
            'vid': version_id,
            'code': version[0],
            'old': old_status,
            'reason': reason,
            'by': archived_by
        })
        
        return True
