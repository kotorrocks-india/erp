# schemas/students_schema.py
"""
Student Management Schema - COMPLETE VERSION
- Student profiles and enrollments
- Division management with audit trails
- Custom profile fields
- Batch and year scaffolding
- All audit tables for tracking changes
"""
from __future__ import annotations
from sqlalchemy.engine import Engine
from sqlalchemy import text as sa_text
from core.schema_registry import register


@register("students")
def install_schema(engine: Engine) -> None:
    """
    Installs all student-related tables with proper columns.
    """
    with engine.begin() as conn:
        # ════════════════════════════════════════════════════════════════════
        # 1. STUDENT PROFILES - Core student information
        # ════════════════════════════════════════════════════════════════════
        conn.execute(sa_text("""
            CREATE TABLE IF NOT EXISTS student_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id TEXT UNIQUE NOT NULL,
                name TEXT,
                email TEXT,
                username TEXT UNIQUE,
                phone TEXT,
                status TEXT DEFAULT 'Good',
                dob TEXT,
                gender TEXT,
                address TEXT,
                guardian_name TEXT,
                guardian_phone TEXT,
                guardian_email TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                active INTEGER DEFAULT 1
            )
        """))
        
        conn.execute(sa_text("CREATE INDEX IF NOT EXISTS idx_student_profiles_student_id ON student_profiles(student_id)"))
        conn.execute(sa_text("CREATE INDEX IF NOT EXISTS idx_student_profiles_email ON student_profiles(email)"))
        conn.execute(sa_text("CREATE INDEX IF NOT EXISTS idx_student_profiles_username ON student_profiles(username)"))
        conn.execute(sa_text("CREATE INDEX IF NOT EXISTS idx_student_profiles_status ON student_profiles(status)"))

        # ════════════════════════════════════════════════════════════════════
        # 2. STUDENT ENROLLMENTS - Degree/batch/year assignments
        # ════════════════════════════════════════════════════════════════════
        conn.execute(sa_text("""
            CREATE TABLE IF NOT EXISTS student_enrollments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_profile_id INTEGER NOT NULL,
                degree_code TEXT NOT NULL,
                program_code TEXT,
                branch_code TEXT,
                batch TEXT,
                current_year INTEGER,
                division_code TEXT,
                roll_number TEXT,
                admission_date TEXT,
                graduation_date TEXT,
                enrollment_status TEXT DEFAULT 'active',
                is_primary INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_profile_id) REFERENCES student_profiles(id) ON DELETE CASCADE
            )
        """))
        
        conn.execute(sa_text("CREATE INDEX IF NOT EXISTS idx_student_enrollments_profile ON student_enrollments(student_profile_id)"))
        conn.execute(sa_text("CREATE INDEX IF NOT EXISTS idx_student_enrollments_degree ON student_enrollments(degree_code)"))
        conn.execute(sa_text("CREATE INDEX IF NOT EXISTS idx_student_enrollments_batch ON student_enrollments(batch)"))
        conn.execute(sa_text("CREATE INDEX IF NOT EXISTS idx_student_enrollments_division ON student_enrollments(division_code)"))
        conn.execute(sa_text("CREATE INDEX IF NOT EXISTS idx_student_enrollments_year ON student_enrollments(current_year)"))
        conn.execute(sa_text("CREATE INDEX IF NOT EXISTS idx_student_enrollments_program ON student_enrollments(program_code)"))
        conn.execute(sa_text("CREATE INDEX IF NOT EXISTS idx_student_enrollments_branch ON student_enrollments(branch_code)"))

        # ════════════════════════════════════════════════════════════════════
        # 3. STUDENT CREDENTIALS - Initial login credentials
        # ════════════════════════════════════════════════════════════════════
        conn.execute(sa_text("""
            CREATE TABLE IF NOT EXISTS student_initial_credentials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_profile_id INTEGER NOT NULL UNIQUE,
                username TEXT NOT NULL,
                plaintext TEXT NOT NULL,
                consumed INTEGER DEFAULT 0,
                consumed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_profile_id) REFERENCES student_profiles(id) ON DELETE CASCADE
            )
        """))
        conn.execute(sa_text("CREATE INDEX IF NOT EXISTS idx_student_initial_credentials_profile ON student_initial_credentials(student_profile_id)"))

        # ════════════════════════════════════════════════════════════════════
        # 4. CUSTOM PROFILE FIELDS - Dynamic field definitions
        # ════════════════════════════════════════════════════════════════════
        conn.execute(sa_text("""
            CREATE TABLE IF NOT EXISTS student_custom_profile_fields (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                label TEXT NOT NULL,
                dtype TEXT NOT NULL,
                required INTEGER DEFAULT 0,
                active INTEGER DEFAULT 1,
                sort_order INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # ════════════════════════════════════════════════════════════════════
        # 5. CUSTOM PROFILE DATA - Values for custom fields
        # ════════════════════════════════════════════════════════════════════
        conn.execute(sa_text("""
            CREATE TABLE IF NOT EXISTS student_custom_profile_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_profile_id INTEGER NOT NULL,
                field_code TEXT NOT NULL,
                value TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_profile_id) REFERENCES student_profiles(id) ON DELETE CASCADE,
                FOREIGN KEY (field_code) REFERENCES student_custom_profile_fields(code) ON DELETE CASCADE,
                UNIQUE(student_profile_id, field_code)
            )
        """))
        conn.execute(sa_text("CREATE INDEX IF NOT EXISTS idx_student_custom_data_profile ON student_custom_profile_data(student_profile_id)"))

        # ════════════════════════════════════════════════════════════════════
        # 6. DEGREE BATCHES - Batch definitions per degree
        # ════════════════════════════════════════════════════════════════════
        conn.execute(sa_text("""
            CREATE TABLE IF NOT EXISTS degree_batches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                degree_code TEXT NOT NULL,
                batch_code TEXT NOT NULL,
                batch_name TEXT,
                start_date TEXT,
                end_date TEXT,
                active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(degree_code, batch_code)
            )
        """))
        conn.execute(sa_text("CREATE INDEX IF NOT EXISTS idx_degree_batches_degree ON degree_batches(degree_code)"))

        # ════════════════════════════════════════════════════════════════════
        # 7. APP SETTINGS - Key-value settings store
        # ════════════════════════════════════════════════════════════════════
        conn.execute(sa_text("""
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # ════════════════════════════════════════════════════════════════════
        # 8. DEGREE YEAR SCAFFOLD - Year structure per degree
        # ════════════════════════════════════════════════════════════════════
        conn.execute(sa_text("""
            CREATE TABLE IF NOT EXISTS degree_year_scaffold (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                degree_code TEXT NOT NULL,
                year_number INTEGER NOT NULL,
                year_name TEXT,
                sort_order INTEGER DEFAULT 0,
                active INTEGER DEFAULT 1,
                UNIQUE(degree_code, year_number)
            )
        """))

        # ════════════════════════════════════════════════════════════════════
        # 9. BATCH YEAR SCAFFOLD - AY links per batch year
        # ════════════════════════════════════════════════════════════════════
        conn.execute(sa_text("""
            CREATE TABLE IF NOT EXISTS batch_year_scaffold (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id INTEGER NOT NULL,
                year_number INTEGER NOT NULL,
                ay_code TEXT COLLATE NOCASE,
                active INTEGER DEFAULT 1,
                FOREIGN KEY (batch_id) REFERENCES degree_batches(id) ON DELETE CASCADE,
                FOREIGN KEY (ay_code) REFERENCES academic_years(ay_code) ON DELETE SET NULL,
                UNIQUE(batch_id, year_number)
            )
        """))

        # ════════════════════════════════════════════════════════════════════
        # 10. STUDENT MOVER AUDIT - Track batch/degree moves
        # ════════════════════════════════════════════════════════════════════
        conn.execute(sa_text("""
            CREATE TABLE IF NOT EXISTS student_mover_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                moved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                moved_by TEXT,
                student_profile_id INTEGER NOT NULL,
                enrollment_id INTEGER NOT NULL,
                from_degree_code TEXT,
                from_batch TEXT,
                from_year INTEGER,
                from_program_code TEXT,
                from_branch_code TEXT,
                from_division_code TEXT,
                to_degree_code TEXT,
                to_batch TEXT,
                to_year INTEGER,
                reason TEXT
            )
        """))
        conn.execute(sa_text("CREATE INDEX IF NOT EXISTS idx_mover_audit_student ON student_mover_audit(student_profile_id)"))
        conn.execute(sa_text("CREATE INDEX IF NOT EXISTS idx_mover_audit_at ON student_mover_audit(moved_at)"))

        # ════════════════════════════════════════════════════════════════════
        # 11. DIVISION MASTER - Division definitions
        # ════════════════════════════════════════════════════════════════════
        conn.execute(sa_text("""
            CREATE TABLE IF NOT EXISTS division_master (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                degree_code TEXT NOT NULL,
                batch TEXT,
                current_year INTEGER,
                division_code TEXT NOT NULL,
                division_name TEXT NOT NULL,
                capacity INTEGER,
                active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(degree_code, batch, current_year, division_code)
            )
        """))
        conn.execute(sa_text("CREATE INDEX IF NOT EXISTS idx_division_master_degree ON division_master(degree_code)"))
        conn.execute(sa_text("CREATE INDEX IF NOT EXISTS idx_division_master_batch ON division_master(batch)"))
        conn.execute(sa_text("CREATE INDEX IF NOT EXISTS idx_division_master_year ON division_master(current_year)"))

        # ════════════════════════════════════════════════════════════════════
        # 12. DIVISION ASSIGNMENT AUDIT - Track student division assignments
        # ════════════════════════════════════════════════════════════════════
        conn.execute(sa_text("""
            CREATE TABLE IF NOT EXISTS division_assignment_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_profile_id INTEGER NOT NULL,
                enrollment_id INTEGER NOT NULL,
                from_division_code TEXT,
                to_division_code TEXT,
                reason TEXT,
                assigned_by TEXT,
                assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_profile_id) REFERENCES student_profiles(id) ON DELETE CASCADE,
                FOREIGN KEY (enrollment_id) REFERENCES student_enrollments(id) ON DELETE CASCADE
            )
        """))
        conn.execute(sa_text("CREATE INDEX IF NOT EXISTS idx_division_assign_audit_student ON division_assignment_audit(student_profile_id)"))
        conn.execute(sa_text("CREATE INDEX IF NOT EXISTS idx_division_assign_audit_enrollment ON division_assignment_audit(enrollment_id)"))
        conn.execute(sa_text("CREATE INDEX IF NOT EXISTS idx_division_assign_audit_at ON division_assignment_audit(assigned_at)"))

        # ════════════════════════════════════════════════════════════════════
        # 13. DIVISION AUDIT LOG - Track division CRUD operations (NEW)
        # ════════════════════════════════════════════════════════════════════
        conn.execute(sa_text("""
            CREATE TABLE IF NOT EXISTS division_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                degree_code TEXT,
                batch TEXT,
                current_year INTEGER,
                division_code TEXT,
                note TEXT,
                actor TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(sa_text("CREATE INDEX IF NOT EXISTS idx_division_audit_log_degree ON division_audit_log(degree_code)"))
        conn.execute(sa_text("CREATE INDEX IF NOT EXISTS idx_division_audit_log_at ON division_audit_log(created_at)"))
        conn.execute(sa_text("CREATE INDEX IF NOT EXISTS idx_division_audit_log_action ON division_audit_log(action)"))

        # ════════════════════════════════════════════════════════════════════
        # 14. STUDENT STATUS AUDIT - Track status changes
        # ════════════════════════════════════════════════════════════════════
        conn.execute(sa_text("""
            CREATE TABLE IF NOT EXISTS student_status_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_profile_id INTEGER NOT NULL,
                from_status TEXT,
                to_status TEXT,
                reason TEXT,
                changed_by TEXT,
                changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_profile_id) REFERENCES student_profiles(id) ON DELETE CASCADE
            )
        """))
        conn.execute(sa_text("CREATE INDEX IF NOT EXISTS idx_status_audit_student ON student_status_audit(student_profile_id)"))
        conn.execute(sa_text("CREATE INDEX IF NOT EXISTS idx_status_audit_at ON student_status_audit(changed_at)"))

    print("✅ Student schema installed successfully with all tables:")
    print("   - student_profiles")
    print("   - student_enrollments")
    print("   - student_initial_credentials")
    print("   - student_custom_profile_fields")
    print("   - student_custom_profile_data")
    print("   - degree_batches")
    print("   - app_settings")
    print("   - degree_year_scaffold")
    print("   - batch_year_scaffold")
    print("   - student_mover_audit")
    print("   - division_master")
    print("   - division_assignment_audit")
    print("   - division_audit_log (NEW)")
    print("   - student_status_audit")
