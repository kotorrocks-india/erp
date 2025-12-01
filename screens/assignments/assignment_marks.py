# screens/timetable/assignment_marks.py
"""
Assignment Marks Entry & Scaling Component
Handles marks entry, scaling calculations, and grade computation.
"""

import streamlit as st
import pandas as pd
from typing import Dict, List
from datetime import datetime


def render_marks(service, offering_id: int, offering: Dict):
    """Main marks entry and scaling interface."""
    
    st.subheader("📊 Marks Entry & Scaling")
    
    # Get assignments for this offering
    assignments = service.list_assignments(offering_id=offering_id, status='published')
    
    if not assignments:
        st.warning("No published assignments found for this offering.")
        st.info("Publish assignments from the Assignments List tab first.")
        return
    
    # Tabs for Internal and External
    tab_internal, tab_external, tab_scaling = st.tabs([
        "📝 Internal Marks",
        "📝 External Marks",
        "📐 Scaling Overview"
    ])
    
    with tab_internal:
        render_marks_bucket(service, offering_id, offering, "Internal")
    
    with tab_external:
        render_marks_bucket(service, offering_id, offering, "External")
    
    with tab_scaling:
        render_scaling_overview(service, offering_id, offering)


def render_marks_bucket(service, offering_id: int, offering: Dict, bucket: str):
    """Render marks entry for a specific bucket."""
    
    st.write(f"### {bucket} Bucket Marks")
    
    # Get assignments in this bucket
    assignments = service.list_assignments(offering_id=offering_id, bucket=bucket, status='published')
    
    if not assignments:
        st.info(f"No published {bucket} assignments.")
        return
    
    # Display offering max
    bucket_max = offering['internal_marks_max'] if bucket == 'Internal' else offering['exam_marks_max']
    st.info(f"📌 {bucket} Bucket Maximum: **{bucket_max} marks**")
    
    # Calculate scaling factor
    total_raw_max = sum(a['max_marks'] for a in assignments)
    scaling_factor = bucket_max / total_raw_max if total_raw_max > 0 else 0
    
    st.write(f"""
    **Scaling Information:**
    - Total Raw Maximum: {total_raw_max} marks
    - Scaling Factor: {scaling_factor:.4f}
    - Each raw mark × {scaling_factor:.4f} = scaled mark
    """)
    
    st.divider()
    
    # Assignment selector
    assignment_options = {
        f"#{a['number']} - {a['title']} ({a['max_marks']} marks)": a['id']
        for a in assignments
    }
    
    selected_display = st.selectbox(
        "Select Assignment to Enter/View Marks",
        options=list(assignment_options.keys()),
        key=f"marks_{bucket}_selector"
    )
    
    if not selected_display:
        return
    
    assignment_id = assignment_options[selected_display]
    selected_assignment = next(a for a in assignments if a['id'] == assignment_id)
    
    st.write(f"### {selected_assignment['title']}")
    st.write(f"Max Marks: {selected_assignment['max_marks']} | Due: {selected_assignment['due_at'][:16]}")
    
    # Get students (placeholder - would integrate with student roster)
    # For demonstration, we'll show a marks entry interface
    
    # Check if we have existing marks
    stats = service.get_assignment_statistics(assignment_id)
    
    if stats:
        st.write(f"**Statistics:** {stats.get('graded_count', 0)} graded out of {stats.get('submission_count', 0)} submissions")
        if stats.get('avg_marks'):
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Average", f"{stats['avg_marks']:.2f}")
            with col2:
                st.metric("Minimum", f"{stats.get('min_marks', 0):.2f}")
            with col3:
                st.metric("Maximum", f"{stats.get('max_marks', 0):.2f}")
    
    st.divider()
    
    # Marks entry method selection
    entry_method = st.radio(
        "Marks Entry Method",
        ["Manual Entry", "Import from CSV", "View Existing Marks"],
        horizontal=True,
        key=f"marks_{bucket}_{assignment_id}_method"
    )
    
    if entry_method == "Manual Entry":
        render_manual_marks_entry(service, assignment_id, selected_assignment, scaling_factor)
    
    elif entry_method == "Import from CSV":
        render_marks_import(service, assignment_id, selected_assignment)
    
    elif entry_method == "View Existing Marks":
        render_marks_view(service, assignment_id, selected_assignment, scaling_factor)


def render_manual_marks_entry(service, assignment_id: int, assignment: Dict, scaling_factor: float):
    """Render manual marks entry interface."""
    
    st.write("#### Manual Marks Entry")
    
    st.info("""
    Enter marks for individual students. In production, this would show the student roster
    with input fields for each student. For demonstration purposes, we'll show the structure.
    """)
    
    # Placeholder student list (would come from database)
    sample_students = [
        {"roll_no": "22CS001", "name": "Student A"},
        {"roll_no": "22CS002", "name": "Student B"},
        {"roll_no": "22CS003", "name": "Student C"},
    ]
    
    with st.form(f"manual_marks_{assignment_id}"):
        st.write("**Student Marks**")
        
        marks_data = {}
        
        for student in sample_students:
            col1, col2, col3, col4 = st.columns([2, 2, 1, 1])
            
            with col1:
                st.write(student['roll_no'])
            
            with col2:
                st.write(student['name'])
            
            with col3:
                marks = st.number_input(
                    f"Marks (/{assignment['max_marks']})",
                    min_value=0.0,
                    max_value=float(assignment['max_marks']),
                    value=0.0,
                    step=0.5,
                    key=f"marks_{student['roll_no']}",
                    label_visibility="collapsed"
                )
                marks_data[student['roll_no']] = marks
            
            with col4:
                scaled = marks * scaling_factor
                st.write(f"{scaled:.2f}")
        
        st.divider()
        
        evaluator_id = st.text_input("Evaluator ID", value="current_faculty")
        comments = st.text_area("Overall Comments (optional)")
        
        submitted = st.form_submit_button("💾 Save Marks", type="primary")
        
        if submitted:
            st.success("Marks saved successfully! (This is a placeholder - would save to database)")
            st.info("In production, this would:")
            st.write("1. Validate all marks are within range")
            st.write("2. Create assignment_marks records")
            st.write("3. Log audit trail")
            st.write("4. Calculate scaled marks")
            st.write("5. Send notifications if configured")


def render_marks_import(service, assignment_id: int, assignment: Dict):
    """Render CSV import interface."""
    
    st.write("#### Import Marks from CSV")
    
    st.write("**CSV Format Requirements:**")
    st.code("""
student_roll_no,marks_obtained,comments,is_excused,excuse_reason
22CS001,8.5,"Good work",0,
22CS002,7.0,"",0,
22CS003,0,"Absent",1,"Medical leave"
    """)
    
    uploaded_file = st.file_uploader(
        "Upload CSV File",
        type=['csv'],
        key=f"marks_import_{assignment_id}"
    )
    
    if uploaded_file:
        try:
            df = pd.read_csv(uploaded_file)
            
            st.write("**Preview:**")
            st.dataframe(df.head())
            
            # Validation
            required_cols = ['student_roll_no', 'marks_obtained']
            missing = [col for col in required_cols if col not in df.columns]
            
            if missing:
                st.error(f"❌ Missing required columns: {', '.join(missing)}")
                return
            
            # Check marks range
            invalid_marks = df[
                (df['marks_obtained'] < 0) | 
                (df['marks_obtained'] > assignment['max_marks'])
            ]
            
            if not invalid_marks.empty:
                st.error(f"❌ {len(invalid_marks)} row(s) have marks outside valid range (0-{assignment['max_marks']})")
                st.dataframe(invalid_marks)
                return
            
            st.success(f"✅ File validated - {len(df)} rows ready to import")
            
            if st.button("🚀 Import Marks", type="primary"):
                st.success("Import successful! (This is a placeholder)")
                st.info("In production, this would bulk insert marks into assignment_marks table")
        
        except Exception as e:
            st.error(f"❌ Error reading CSV: {e}")
    
    # Download template
    if st.button("📥 Download Template CSV"):
        template_df = pd.DataFrame({
            'student_roll_no': ['22CS001', '22CS002', '22CS003'],
            'marks_obtained': [0.0, 0.0, 0.0],
            'comments': ['', '', ''],
            'is_excused': [0, 0, 0],
            'excuse_reason': ['', '', '']
        })
        
        csv = template_df.to_csv(index=False)
        st.download_button(
            "⬇️ Download",
            csv,
            f"marks_template_{assignment_id}.csv",
            "text/csv"
        )


def render_marks_view(service, assignment_id: int, assignment: Dict, scaling_factor: float):
    """Render existing marks view."""
    
    st.write("#### Existing Marks")
    
    st.info("This would display all entered marks from the assignment_marks table.")
    
    # Placeholder data
    sample_marks = [
        {"roll_no": "22CS001", "name": "Student A", "raw": 8.5, "scaled": 8.5 * scaling_factor, "status": "Graded"},
        {"roll_no": "22CS002", "name": "Student B", "raw": 7.0, "scaled": 7.0 * scaling_factor, "status": "Graded"},
        {"roll_no": "22CS003", "name": "Student C", "raw": 0.0, "scaled": 0.0, "status": "Excused"},
    ]
    
    df = pd.DataFrame(sample_marks)
    st.dataframe(df, use_container_width=True)
    
    # Export options
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("📥 Export to CSV"):
            csv = df.to_csv(index=False)
            st.download_button(
                "⬇️ Download CSV",
                csv,
                f"marks_export_{assignment_id}.csv",
                "text/csv"
            )
    
    with col2:
        if st.button("📊 Export to Excel"):
            st.info("Excel export feature would be available here")


def render_scaling_overview(service, offering_id: int, offering: Dict):
    """Render comprehensive scaling overview."""
    
    st.write("### 📐 Marks Scaling Overview")
    
    st.info("""
    This page shows how raw marks are scaled to match the offering's internal and external maxima.
    The system uses implicit weighting based on assignment max marks.
    """)
    
    # Internal bucket
    st.write("#### Internal Bucket")
    
    internal_assignments = service.list_assignments(offering_id=offering_id, bucket='Internal', status='published')
    
    if internal_assignments:
        scaling_factor_internal, scaled_marks_internal = service.calculate_scaled_marks(offering_id, 'Internal')
        
        st.write(f"**Scaling Factor:** {scaling_factor_internal:.4f}")
        
        # Assignment breakdown
        internal_df = pd.DataFrame([{
            'Number': a['number'],
            'Title': a['title'],
            'Raw Max': a['max_marks'],
            'Weight %': (a['max_marks'] / sum(x['max_marks'] for x in internal_assignments)) * 100,
            'Status': a['status']
        } for a in internal_assignments])
        
        st.dataframe(internal_df, use_container_width=True)
        
        st.metric("Total Raw Maximum", f"{sum(a['max_marks'] for a in internal_assignments):.1f}")
        st.metric("Offering Internal Maximum", offering['internal_marks_max'])
    else:
        st.info("No published internal assignments")
    
    st.divider()
    
    # External bucket
    st.write("#### External Bucket")
    
    external_assignments = service.list_assignments(offering_id=offering_id, bucket='External', status='published')
    
    if external_assignments:
        scaling_factor_external, scaled_marks_external = service.calculate_scaled_marks(offering_id, 'External')
        
        st.write(f"**Scaling Factor:** {scaling_factor_external:.4f}")
        
        # Assignment breakdown
        external_df = pd.DataFrame([{
            'Number': a['number'],
            'Title': a['title'],
            'Raw Max': a['max_marks'],
            'Weight %': (a['max_marks'] / sum(x['max_marks'] for x in external_assignments)) * 100,
            'Status': a['status']
        } for a in external_assignments])
        
        st.dataframe(external_df, use_container_width=True)
        
        st.metric("Total Raw Maximum", f"{sum(a['max_marks'] for a in external_assignments):.1f}")
        st.metric("Offering External Maximum", offering['exam_marks_max'])
    else:
        st.info("No published external assignments")
    
    st.divider()
    
    # Overall summary
    st.write("#### Overall Summary")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Total Published Assignments", len(internal_assignments) + len(external_assignments))
    
    with col2:
        total_raw = sum(a['max_marks'] for a in internal_assignments) + sum(a['max_marks'] for a in external_assignments)
        st.metric("Total Raw Maximum", f"{total_raw:.1f}")
    
    with col3:
        offering_total = offering['internal_marks_max'] + offering['exam_marks_max']
        st.metric("Offering Total Maximum", offering_total)
    
    # Visualization placeholder
    with st.expander("📊 Visual Breakdown", expanded=False):
        st.info("Charts would be displayed here showing:")
        st.write("- Weight distribution across assignments")
        st.write("- Internal vs External split")
        st.write("- Completion status")


if __name__ == "__main__":
    st.write("This module should be imported, not run directly.")
