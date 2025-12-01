# app/screens/students/status_management.py
"""
Advanced Status Management UI

Provides interface for:
1. Viewing/editing status rules
2. Running status computations (manual trigger)
3. Viewing computation logs
4. Managing overrides
5. Checking exam eligibility
"""
from __future__ import annotations
import streamlit as st
from sqlalchemy.engine import Engine
from sqlalchemy import text as sa_text
import pandas as pd
from datetime import datetime


def render_status_management(engine: Engine):
    """Main UI for advanced status management."""
    
    st.markdown("### 🎯 Advanced Status Management")
    st.caption("Rule-based automatic status computation system")
    
    tabs = st.tabs([
        "📜 Status Rules",
        "⚙️ Compute Status",
        "📊 Computation Logs", 
        "🎓 Exam Eligibility",
        "🔧 Manual Overrides"
    ])
    
    with tabs[0]:
        _render_status_rules(engine)
    
    with tabs[1]:
        _render_compute_interface(engine)
    
    with tabs[2]:
        _render_computation_logs(engine)
    
    with tabs[3]:
        _render_exam_eligibility(engine)
    
    with tabs[4]:
        _render_manual_overrides(engine)


def _render_status_rules(engine: Engine):
    """View and edit status computation rules."""
    st.markdown("#### 📜 Status Computation Rules")
    st.info("Rules are evaluated in priority order (lower number = higher priority)")
    
    with engine.connect() as conn:
        rules = conn.execute(sa_text("""
            SELECT id, rule_code, rule_name, rule_category, condition_field, 
                   operator, threshold_value, target_status, target_eligibility, 
                   priority, active, description
            FROM student_status_rules
            ORDER BY priority ASC
        """)).fetchall()
    
    if not rules:
        st.warning("No rules defined. Run schema installation to create default rules.")
        return
    
    # Display rules in expandable sections
    for rule in rules:
        rule_id, code, name, category, field, op, threshold, status, eligibility, priority, active, desc = rule
        
        status_icon = "✅" if active else "❌"
        priority_badge = f"P{priority}"
        
        with st.expander(f"{status_icon} [{priority_badge}] {name} → {status}"):
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.markdown("**Rule Details**")
                st.text(f"Code: {code}")
                st.text(f"Category: {category}")
                st.text(f"Condition: {field} {op} {threshold}")
            
            with col2:
                st.markdown("**Outcome**")
                st.text(f"Status: {status}")
                st.text(f"Eligibility: {eligibility or 'both'}")
                st.text(f"Priority: {priority}")
            
            with col3:
                st.markdown("**Actions**")
                new_active = st.checkbox("Active", value=bool(active), key=f"rule_active_{rule_id}")
                
                if st.button("💾 Update", key=f"rule_save_{rule_id}"):
                    with engine.begin() as conn:
                        conn.execute(sa_text(
                            "UPDATE student_status_rules SET active = :a WHERE id = :id"
                        ), {"a": 1 if new_active else 0, "id": rule_id})
                    st.success("Updated")
                    st.rerun()
            
            st.caption(f"📝 {desc}")
    
    st.divider()
    
    # Add new rule
    with st.expander("➕ Create New Rule", expanded=False):
        col1, col2 = st.columns(2)
        
        with col1:
            new_code = st.text_input("Rule Code*", placeholder="e.g., ATT_LOW")
            new_name = st.text_input("Rule Name*", placeholder="e.g., Low Attendance Warning")
            new_category = st.selectbox("Category", ["attendance", "academic", "fees", "eligibility"])
            new_field = st.text_input("Condition Field*", placeholder="e.g., attendance_percentage")
            new_operator = st.selectbox("Operator", ["<", ">", "<=", ">=", "==", "!="])
            new_threshold = st.text_input("Threshold Value*", placeholder="e.g., 75")
        
        with col2:
            new_status = st.selectbox("Target Status", ["Good", "Hold", "Detained"])
            new_eligibility = st.selectbox("Exam Eligibility", ["both", "internal_only", "external_only", "none"])
            new_priority = st.number_input("Priority (lower = higher)", min_value=1, value=100)
            new_desc = st.text_area("Description", placeholder="Explain what this rule does")
        
        if st.button("➕ Create Rule", type="primary"):
            if not new_code or not new_name or not new_field or not new_threshold:
                st.error("Required fields missing")
            else:
                try:
                    with engine.begin() as conn:
                        conn.execute(sa_text("""
                            INSERT INTO student_status_rules 
                            (rule_code, rule_name, rule_category, rule_type, condition_field, operator, threshold_value,
                             target_status, target_eligibility, priority, description, active)
                            VALUES (:code, :name, :cat, 'threshold', :field, :op, :thresh, :status, :elig, :prio, :desc, 1)
                        """), {
                            "code": new_code, "name": new_name, "cat": new_category,
                            "field": new_field, "op": new_operator, "thresh": new_threshold,
                            "status": new_status, "elig": new_eligibility, "prio": new_priority, "desc": new_desc
                        })
                    st.success("✅ Rule created")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed: {e}")


def _render_compute_interface(engine: Engine):
    """Interface to manually trigger status computation."""
    st.markdown("#### ⚙️ Compute Student Status")
    st.info("Manually trigger status computation for students based on current data")
    
    mode = st.radio("Compute for:", ["Single Student", "Entire Batch"], horizontal=True)
    
    if mode == "Single Student":
        search = st.text_input("Search Student ID or Email")
        
        if search:
            with engine.connect() as conn:
                student = conn.execute(sa_text("""
                    SELECT p.id, p.student_id, p.name, p.email, p.status,
                           e.degree_code, e.batch, e.current_year
                    FROM student_profiles p
                    LEFT JOIN student_enrollments e ON p.id = e.student_profile_id AND e.is_primary = 1
                    WHERE p.student_id = :s OR p.email = :s
                """), {"s": search}).fetchone()
            
            if student:
                st.success(f"Found: {student[2]} ({student[1]})")
                st.text(f"Current Status: {student[4]}")
                st.text(f"Degree: {student[5]} | Batch: {student[6]} | Year: {student[7]}")
                
                col1, col2 = st.columns(2)
                with col1:
                    ay_code = st.text_input("Academic Year", value="2024-25")
                with col2:
                    semester_num = st.number_input("Semester", min_value=1, max_value=12, value=1)
                
                if st.button("🔄 Compute Status", type="primary"):
                    try:
                        from core.student_status_engine import StudentStatusEngine
                        engine_obj = StudentStatusEngine(engine)
                        result = engine_obj.compute_student_status(student[0], ay_code, semester_num, commit=True)
                        
                        st.success(f"✅ Computed Status: **{result['status']}**")
                        st.info(f"Reason: {result['reason']}")
                        
                        col1, col2 = st.columns(2)
                        col1.metric("Internal Exam Eligible", "Yes" if result['internal_eligible'] else "No")
                        col2.metric("External Exam Eligible", "Yes" if result['external_eligible'] else "No")
                        
                    except Exception as e:
                        st.error(f"Computation failed: {e}")
            else:
                st.warning("Student not found")
    
    else:  # Batch mode
        with engine.connect() as conn:
            degrees = [d[0] for d in conn.execute(sa_text(
                "SELECT code FROM degrees WHERE active = 1"
            )).fetchall()]
        
        degree = st.selectbox("Degree", degrees)
        
        with engine.connect() as conn:
            batches = [b[0] for b in conn.execute(sa_text(
                "SELECT DISTINCT batch FROM student_enrollments WHERE degree_code = :d"
            ), {"d": degree}).fetchall()]
        
        batch = st.selectbox("Batch", batches if batches else [""])
        
        col1, col2 = st.columns(2)
        with col1:
            ay_code = st.text_input("Academic Year", value="2024-25", key="batch_ay")
        with col2:
            semester_num = st.number_input("Semester", min_value=1, max_value=12, value=1, key="batch_sem")
        
        if st.button("🔄 Compute for Entire Batch", type="primary"):
            if batch:
                try:
                    from core.student_status_engine import StudentStatusEngine
                    engine_obj = StudentStatusEngine(engine)
                    
                    with st.spinner(f"Computing status for all students in {degree}/{batch}..."):
                        summary = engine_obj.compute_batch_status(degree, batch, ay_code, semester_num)
                    
                    st.success(f"✅ Computed status for {summary['Total']} students")
                    
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Good Standing", summary.get('Good', 0))
                    col2.metric("On Hold", summary.get('Hold', 0))
                    col3.metric("Detained", summary.get('Detained', 0))
                    
                except Exception as e:
                    st.error(f"Batch computation failed: {e}")


def _render_computation_logs(engine: Engine):
    """View historical status computation logs."""
    st.markdown("#### 📊 Status Computation Logs")
    st.caption("Audit trail of all status computations")
    
    with engine.connect() as conn:
        try:
            logs = conn.execute(sa_text("""
                SELECT 
                    l.computed_at,
                    p.student_id,
                    p.name,
                    l.ay_code,
                    l.semester_number,
                    l.previous_status,
                    l.computed_status,
                    l.status_changed,
                    l.reason,
                    l.attendance_pct,
                    l.internal_pct,
                    l.active_backlogs
                FROM student_status_computation_log l
                JOIN student_profiles p ON p.id = l.student_profile_id
                ORDER BY l.computed_at DESC
                LIMIT 100
            """)).fetchall()
            
            if logs:
                df = pd.DataFrame(logs, columns=[
                    "Computed At", "Student ID", "Name", "AY", "Sem",
                    "Previous", "New Status", "Changed", "Reason",
                    "Attendance %", "Internal %", "Backlogs"
                ])
                
                # Highlight status changes
                def highlight_changes(row):
                    return ['background-color: yellow' if row['Changed'] else '' for _ in row]
                
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("No computation logs yet. Run status computation to generate logs.")
        
        except Exception as e:
            st.warning(f"Computation logs not available: {e}")


def _render_exam_eligibility(engine: Engine):
    """View exam eligibility status for students."""
    st.markdown("#### 🎓 Exam Eligibility Checker")
    st.caption("Check which students are eligible for internal/external exams")
    
    with engine.connect() as conn:
        degrees = [d[0] for d in conn.execute(sa_text("SELECT code FROM degrees WHERE active = 1")).fetchall()]
    
    degree = st.selectbox("Degree", degrees, key="elig_degree")
    
    with engine.connect() as conn:
        batches = [b[0] for b in conn.execute(sa_text(
            "SELECT DISTINCT batch FROM student_enrollments WHERE degree_code = :d"
        ), {"d": degree}).fetchall()]
    
    batch = st.selectbox("Batch", batches if batches else [""], key="elig_batch")
    
    col1, col2 = st.columns(2)
    with col1:
        ay_code = st.text_input("Academic Year", value="2024-25", key="elig_ay")
    with col2:
        semester_num = st.number_input("Semester", min_value=1, max_value=12, value=1, key="elig_sem")
    
    if st.button("🔍 Check Eligibility"):
        with engine.connect() as conn:
            try:
                students = conn.execute(sa_text("""
                    SELECT 
                        p.student_id,
                        p.name,
                        p.status,
                        perf.attendance_percentage,
                        perf.active_backlogs,
                        perf.eligible_for_externals,
                        elig.is_eligible as exam_eligible,
                        elig.exam_type,
                        elig.eligibility_reason
                    FROM student_profiles p
                    JOIN student_enrollments e ON p.id = e.student_profile_id AND e.is_primary = 1
                    LEFT JOIN student_semester_performance perf 
                        ON p.id = perf.student_profile_id 
                        AND perf.ay_code = :ay 
                        AND perf.semester_number = :sem
                    LEFT JOIN student_exam_eligibility elig
                        ON p.id = elig.student_profile_id
                        AND elig.ay_code = :ay
                        AND elig.semester_number = :sem
                    WHERE e.degree_code = :degree AND e.batch = :batch
                    ORDER BY p.student_id
                """), {"degree": degree, "batch": batch, "ay": ay_code, "sem": semester_num}).fetchall()
                
                if students:
                    df = pd.DataFrame(students, columns=[
                        "Student ID", "Name", "Status", "Attendance %", 
                        "Backlogs", "External Eligible", "Exam Eligible", 
                        "Exam Type", "Reason"
                    ])
                    
                    st.dataframe(df, use_container_width=True, hide_index=True)
                    
                    # Summary
                    internal_only = len([s for s in students if s[5] == 0])
                    fully_eligible = len([s for s in students if s[5] == 1])
                    
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Fully Eligible", fully_eligible)
                    col2.metric("Internal Only", internal_only)
                    col3.metric("Total Students", len(students))
                else:
                    st.info("No students found")
            
            except Exception as e:
                st.warning(f"Eligibility data not available: {e}")


def _render_manual_overrides(engine: Engine):
    """Manage manual status overrides."""
    st.markdown("#### 🔧 Manual Status Overrides")
    st.caption("Override computed status for special cases")
    
    st.warning("⚠️ Overrides bypass the rules engine. Use with caution and document reason.")
    
    search = st.text_input("Search Student", placeholder="Student ID or Email")
    
    if search:
        with engine.connect() as conn:
            student = conn.execute(sa_text("""
                SELECT p.id, p.student_id, p.name, p.status
                FROM student_profiles p
                WHERE p.student_id = :s OR p.email = :s
            """), {"s": search}).fetchone()
        
        if student:
            st.success(f"Student: {student[2]} ({student[1]})")
            st.text(f"Current Status: {student[3]}")
            
            col1, col2 = st.columns(2)
            
            with col1:
                override_type = st.selectbox("Override Type", ["status", "eligibility", "fee_waiver"])
                new_value = st.selectbox("New Value", ["Good", "Hold", "Detained", "Left", "Graduated"])
            
            with col2:
                valid_until = st.date_input("Valid Until", value=None)
                reason = st.text_area("Reason (Required)*", placeholder="Medical leave, Administrative decision, etc.")
            
            if st.button("💾 Apply Override", type="primary"):
                if not reason:
                    st.error("Reason is required for audit trail")
                else:
                    try:
                        with engine.begin() as conn:
                            # Insert override record
                            conn.execute(sa_text("""
                                INSERT INTO student_status_overrides (
                                    student_profile_id, override_type, original_value, override_value,
                                    reason, approved_by, valid_until, is_active
                                ) VALUES (:sid, :type, :orig, :new, :reason, :by, :until, 1)
                            """), {
                                "sid": student[0],
                                "type": override_type,
                                "orig": student[3],
                                "new": new_value,
                                "reason": reason,
                                "by": "admin",  # TODO: get from auth
                                "until": str(valid_until) if valid_until else None
                            })
                            
                            # Update actual status
                            conn.execute(sa_text(
                                "UPDATE student_profiles SET status = :status WHERE id = :id"
                            ), {"status": new_value, "id": student[0]})
                        
                        st.success("✅ Override applied")
                        st.rerun()
                    
                    except Exception as e:
                        st.error(f"Failed: {e}")
        else:
            st.warning("Student not found")
    
    st.divider()
    st.markdown("#### 📜 Active Overrides")
    
    with engine.connect() as conn:
        try:
            overrides = conn.execute(sa_text("""
                SELECT 
                    p.student_id,
                    p.name,
                    o.override_type,
                    o.original_value,
                    o.override_value,
                    o.reason,
                    o.approved_by,
                    o.approved_at,
                    o.valid_until
                FROM student_status_overrides o
                JOIN student_profiles p ON p.id = o.student_profile_id
                WHERE o.is_active = 1
                ORDER BY o.approved_at DESC
            """)).fetchall()
            
            if overrides:
                df = pd.DataFrame(overrides, columns=[
                    "Student ID", "Name", "Type", "Original", "Override",
                    "Reason", "By", "At", "Valid Until"
                ])
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("No active overrides")
        
        except Exception as e:
            st.warning(f"Override data not available: {e}")
