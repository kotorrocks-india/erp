# schemas/student_status_enhanced_schema.py
"""
Enhanced Student Status Management Schema

Handles complex status rules:
1. Active (fees-based) - Fee payment status determines active enrollment
2. Good/Hold (marks-based) - Academic performance across semesters/AYs
3. Eligibility rules - Internal vs External exam eligibility
4. Historical dependencies - Previous AY performance affects current eligibility

This is a RULE-BASED system, not just manual dropdown selection.
"""
from __future__ import annotations
from sqlalchemy.engine import Engine
from sqlalchemy import text as sa_text
from core.schema_registry import register


@register("student_status_enhanced")
def install_enhanced_status_schema(engine: Engine) -> None:
    """
    Enhanced status management tables.
    Call this AFTER the base student schema is installed.
    """
    with engine.begin() as conn:
        
        # ════════════════════════════════════════════════════════════════════
        # 1. FEE PAYMENT TRACKING - Determines "Active" status
        # ════════════════════════════════════════════════════════════════════
        conn.execute(sa_text("""
            CREATE TABLE IF NOT EXISTS student_fee_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_profile_id INTEGER NOT NULL,
                enrollment_id INTEGER NOT NULL,
                ay_code TEXT NOT NULL,
                semester_number INTEGER,
                fee_type TEXT NOT NULL,  -- 'tuition', 'exam', 'semester', 'annual'
                amount_due DECIMAL(10,2) NOT NULL,
                amount_paid DECIMAL(10,2) DEFAULT 0,
                payment_date TEXT,
                due_date TEXT NOT NULL,
                status TEXT NOT NULL,  -- 'paid', 'partial', 'pending', 'waived', 'overdue'
                payment_method TEXT,  -- 'cash', 'card', 'bank_transfer', 'scholarship'
                reference_number TEXT,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_profile_id) REFERENCES student_profiles(id) ON DELETE CASCADE,
                FOREIGN KEY (enrollment_id) REFERENCES student_enrollments(id) ON DELETE CASCADE,
                FOREIGN KEY (ay_code) REFERENCES academic_years(ay_code)
            )
        """))
        
        conn.execute(sa_text("CREATE INDEX IF NOT EXISTS idx_fee_payments_student ON student_fee_payments(student_profile_id)"))
        conn.execute(sa_text("CREATE INDEX IF NOT EXISTS idx_fee_payments_ay ON student_fee_payments(ay_code)"))
        conn.execute(sa_text("CREATE INDEX IF NOT EXISTS idx_fee_payments_status ON student_fee_payments(status)"))
        
        # ════════════════════════════════════════════════════════════════════
        # 2. ACADEMIC PERFORMANCE TRACKING - Determines "Good/Hold" status
        # ════════════════════════════════════════════════════════════════════
        conn.execute(sa_text("""
            CREATE TABLE IF NOT EXISTS student_semester_performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_profile_id INTEGER NOT NULL,
                enrollment_id INTEGER NOT NULL,
                ay_code TEXT NOT NULL,
                semester_number INTEGER NOT NULL,
                degree_code TEXT NOT NULL,
                batch TEXT NOT NULL,
                current_year INTEGER NOT NULL,
                
                -- Attendance metrics
                total_classes INTEGER DEFAULT 0,
                attended_classes INTEGER DEFAULT 0,
                attendance_percentage DECIMAL(5,2) DEFAULT 0,
                attendance_status TEXT,  -- 'good', 'low', 'critical', 'detained'
                
                -- Academic metrics
                total_subjects INTEGER DEFAULT 0,
                subjects_passed INTEGER DEFAULT 0,
                subjects_failed INTEGER DEFAULT 0,
                subjects_absent INTEGER DEFAULT 0,
                
                -- Internal assessment
                internal_marks_obtained DECIMAL(10,2),
                internal_marks_total DECIMAL(10,2),
                internal_percentage DECIMAL(5,2),
                internal_status TEXT,  -- 'pass', 'fail', 'supplementary'
                
                -- External assessment
                external_marks_obtained DECIMAL(10,2),
                external_marks_total DECIMAL(10,2),
                external_percentage DECIMAL(5,2),
                external_status TEXT,  -- 'pass', 'fail', 'absent', 'detained'
                
                -- Overall
                sgpa DECIMAL(4,2),
                cgpa DECIMAL(4,2),
                credits_earned INTEGER DEFAULT 0,
                credits_attempted INTEGER DEFAULT 0,
                
                -- Eligibility flags
                eligible_for_externals BOOLEAN DEFAULT 1,
                eligible_for_promotion BOOLEAN DEFAULT 1,
                requires_supplementary BOOLEAN DEFAULT 0,
                detained BOOLEAN DEFAULT 0,
                
                -- Backlog tracking
                active_backlogs INTEGER DEFAULT 0,
                cleared_backlogs INTEGER DEFAULT 0,
                
                -- Computed status
                computed_status TEXT,  -- 'good', 'hold', 'detained', 'promoted', 'repeat'
                status_reason TEXT,
                
                computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                
                FOREIGN KEY (student_profile_id) REFERENCES student_profiles(id) ON DELETE CASCADE,
                FOREIGN KEY (enrollment_id) REFERENCES student_enrollments(id) ON DELETE CASCADE,
                FOREIGN KEY (ay_code) REFERENCES academic_years(ay_code),
                UNIQUE(student_profile_id, ay_code, semester_number)
            )
        """))
        
        conn.execute(sa_text("CREATE INDEX IF NOT EXISTS idx_perf_student ON student_semester_performance(student_profile_id)"))
        conn.execute(sa_text("CREATE INDEX IF NOT EXISTS idx_perf_ay_sem ON student_semester_performance(ay_code, semester_number)"))
        conn.execute(sa_text("CREATE INDEX IF NOT EXISTS idx_perf_status ON student_semester_performance(computed_status)"))
        
        # ════════════════════════════════════════════════════════════════════
        # 3. STATUS RULES CONFIGURATION - Define institution rules
        # ════════════════════════════════════════════════════════════════════
        conn.execute(sa_text("""
            CREATE TABLE IF NOT EXISTS student_status_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_code TEXT UNIQUE NOT NULL,
                rule_name TEXT NOT NULL,
                rule_category TEXT NOT NULL,  -- 'attendance', 'academic', 'fees', 'eligibility'
                rule_type TEXT NOT NULL,  -- 'threshold', 'boolean', 'cumulative'
                
                -- Rule definition
                condition_field TEXT NOT NULL,  -- e.g., 'attendance_percentage', 'active_backlogs'
                operator TEXT NOT NULL,  -- '<', '>', '>=', '<=', '==', '!='
                threshold_value TEXT,
                
                -- Dependencies on previous semesters
                lookback_semesters INTEGER DEFAULT 0,  -- How many previous sems to check
                lookback_scope TEXT DEFAULT 'current_ay',  -- 'current_ay', 'previous_ay', 'all'
                
                -- Outcome
                target_status TEXT NOT NULL,  -- 'Good', 'Hold', 'Detained', etc.
                target_eligibility TEXT,  -- 'internal_only', 'external_only', 'both', 'none'
                priority INTEGER DEFAULT 100,  -- Lower = higher priority when multiple rules match
                
                -- Metadata
                description TEXT,
                effective_from TEXT,  -- Date from which rule applies
                effective_to TEXT,
                degree_code TEXT,  -- NULL = applies to all degrees
                active INTEGER DEFAULT 1,
                
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        
        conn.execute(sa_text("CREATE INDEX IF NOT EXISTS idx_status_rules_category ON student_status_rules(rule_category)"))
        conn.execute(sa_text("CREATE INDEX IF NOT EXISTS idx_status_rules_active ON student_status_rules(active)"))
        
        # ════════════════════════════════════════════════════════════════════
        # 4. STATUS COMPUTATION LOG - Track when/why status was computed
        # ════════════════════════════════════════════════════════════════════
        conn.execute(sa_text("""
            CREATE TABLE IF NOT EXISTS student_status_computation_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_profile_id INTEGER NOT NULL,
                enrollment_id INTEGER NOT NULL,
                ay_code TEXT,
                semester_number INTEGER,
                
                -- Input data snapshot
                attendance_pct DECIMAL(5,2),
                internal_pct DECIMAL(5,2),
                external_pct DECIMAL(5,2),
                active_backlogs INTEGER,
                fee_status TEXT,
                
                -- Rules evaluated
                rules_evaluated TEXT,  -- JSON array of rule IDs
                rules_matched TEXT,  -- JSON array of matched rule IDs
                winning_rule_id INTEGER,
                
                -- Output
                computed_status TEXT NOT NULL,
                previous_status TEXT,
                status_changed BOOLEAN DEFAULT 0,
                reason TEXT,
                
                -- Eligibility
                internal_eligible BOOLEAN,
                external_eligible BOOLEAN,
                
                computed_by TEXT,  -- 'system_auto', 'manual_override', 'admin_user_id'
                computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                
                FOREIGN KEY (student_profile_id) REFERENCES student_profiles(id) ON DELETE CASCADE,
                FOREIGN KEY (winning_rule_id) REFERENCES student_status_rules(id)
            )
        """))
        
        conn.execute(sa_text("CREATE INDEX IF NOT EXISTS idx_comp_log_student ON student_status_computation_log(student_profile_id)"))
        conn.execute(sa_text("CREATE INDEX IF NOT EXISTS idx_comp_log_at ON student_status_computation_log(computed_at)"))
        
        # ════════════════════════════════════════════════════════════════════
        # 5. EXAM ELIGIBILITY TRACKING - Who can appear for which exams
        # ════════════════════════════════════════════════════════════════════
        conn.execute(sa_text("""
            CREATE TABLE IF NOT EXISTS student_exam_eligibility (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_profile_id INTEGER NOT NULL,
                enrollment_id INTEGER NOT NULL,
                ay_code TEXT NOT NULL,
                semester_number INTEGER NOT NULL,
                exam_type TEXT NOT NULL,  -- 'internal', 'external', 'supplementary', 'reappear'
                
                -- Eligibility determination
                is_eligible BOOLEAN DEFAULT 0,
                eligibility_reason TEXT,
                eligibility_computed_at TIMESTAMP,
                
                -- Restrictions
                subject_restrictions TEXT,  -- JSON: subjects student CAN or CANNOT appear for
                attempt_number INTEGER DEFAULT 1,
                max_attempts_allowed INTEGER DEFAULT 3,
                
                -- Based on
                based_on_attendance BOOLEAN DEFAULT 0,
                based_on_internal_marks BOOLEAN DEFAULT 0,
                based_on_previous_sem BOOLEAN DEFAULT 0,
                based_on_fee_payment BOOLEAN DEFAULT 0,
                based_on_manual_override BOOLEAN DEFAULT 0,
                
                override_by TEXT,
                override_reason TEXT,
                override_at TIMESTAMP,
                
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                
                FOREIGN KEY (student_profile_id) REFERENCES student_profiles(id) ON DELETE CASCADE,
                FOREIGN KEY (enrollment_id) REFERENCES student_enrollments(id) ON DELETE CASCADE,
                UNIQUE(student_profile_id, ay_code, semester_number, exam_type)
            )
        """))
        
        conn.execute(sa_text("CREATE INDEX IF NOT EXISTS idx_exam_elig_student ON student_exam_eligibility(student_profile_id)"))
        conn.execute(sa_text("CREATE INDEX IF NOT EXISTS idx_exam_elig_ay_sem ON student_exam_eligibility(ay_code, semester_number)"))
        
        # ════════════════════════════════════════════════════════════════════
        # 6. STATUS OVERRIDE TRACKING - Manual status changes by admin
        # ════════════════════════════════════════════════════════════════════
        conn.execute(sa_text("""
            CREATE TABLE IF NOT EXISTS student_status_overrides (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_profile_id INTEGER NOT NULL,
                override_type TEXT NOT NULL,  -- 'status', 'eligibility', 'fee_waiver', 'promotion'
                
                original_value TEXT,
                override_value TEXT NOT NULL,
                
                ay_code TEXT,
                semester_number INTEGER,
                
                reason TEXT NOT NULL,
                supporting_documents TEXT,  -- JSON: file paths or document IDs
                
                approved_by TEXT NOT NULL,
                approved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                
                valid_from TEXT,
                valid_until TEXT,
                
                is_active BOOLEAN DEFAULT 1,
                revoked_by TEXT,
                revoked_at TIMESTAMP,
                revoke_reason TEXT,
                
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                
                FOREIGN KEY (student_profile_id) REFERENCES student_profiles(id) ON DELETE CASCADE
            )
        """))
        
        conn.execute(sa_text("CREATE INDEX IF NOT EXISTS idx_overrides_student ON student_status_overrides(student_profile_id)"))
        conn.execute(sa_text("CREATE INDEX IF NOT EXISTS idx_overrides_active ON student_status_overrides(is_active)"))
        
        # ════════════════════════════════════════════════════════════════════
        # 7. Insert Default Rules (Examples)
        # ════════════════════════════════════════════════════════════════════
        
        # Rule 1: Attendance < 75% = Detained (cannot appear for externals)
        conn.execute(sa_text("""
            INSERT OR IGNORE INTO student_status_rules 
            (rule_code, rule_name, rule_category, rule_type, condition_field, operator, threshold_value, 
             target_status, target_eligibility, priority, description)
            VALUES 
            ('ATT_DETAINED', 'Attendance Detention', 'attendance', 'threshold', 
             'attendance_percentage', '<', '75', 'Detained', 'internal_only', 10,
             'Students with <75% attendance cannot appear for external exams')
        """))
        
        # Rule 2: Active backlogs >= 5 = Hold
        conn.execute(sa_text("""
            INSERT OR IGNORE INTO student_status_rules 
            (rule_code, rule_name, rule_category, rule_type, condition_field, operator, threshold_value, 
             target_status, target_eligibility, priority, description)
            VALUES 
            ('BACKLOG_HOLD', 'Excessive Backlogs', 'academic', 'threshold', 
             'active_backlogs', '>=', '5', 'Hold', 'both', 20,
             'Students with 5+ active backlogs are placed on Hold')
        """))
        
        # Rule 3: Fee status = overdue = Inactive
        conn.execute(sa_text("""
            INSERT OR IGNORE INTO student_status_rules 
            (rule_code, rule_name, rule_category, rule_type, condition_field, operator, threshold_value, 
             target_status, target_eligibility, priority, description)
            VALUES 
            ('FEE_OVERDUE', 'Overdue Fees', 'fees', 'threshold', 
             'fee_status', '==', 'overdue', 'Hold', 'none', 5,
             'Students with overdue fees cannot access any academic services')
        """))
        
        # Rule 4: SGPA < 4.0 in previous semester = Hold for current semester
        conn.execute(sa_text("""
            INSERT OR IGNORE INTO student_status_rules 
            (rule_code, rule_name, rule_category, rule_type, condition_field, operator, threshold_value, 
             target_status, target_eligibility, priority, lookback_semesters, description)
            VALUES 
            ('LOW_SGPA', 'Low Previous Semester SGPA', 'academic', 'threshold', 
             'sgpa', '<', '4.0', 'Hold', 'both', 30, 1,
             'Students with SGPA < 4.0 in previous semester are on academic probation')
        """))
        
        # Rule 5: All clear = Good
        conn.execute(sa_text("""
            INSERT OR IGNORE INTO student_status_rules 
            (rule_code, rule_name, rule_category, rule_type, condition_field, operator, threshold_value, 
             target_status, target_eligibility, priority, description)
            VALUES 
            ('DEFAULT_GOOD', 'Default Good Standing', 'academic', 'boolean', 
             'eligible_for_promotion', '==', '1', 'Good', 'both', 1000,
             'Default rule: students meeting all criteria are in Good standing')
        """))

    print("✅ Enhanced student status schema installed:")
    print("   - student_fee_payments")
    print("   - student_semester_performance")
    print("   - student_status_rules")
    print("   - student_status_computation_log")
    print("   - student_exam_eligibility")
    print("   - student_status_overrides")
    print("   - Default rules created")
