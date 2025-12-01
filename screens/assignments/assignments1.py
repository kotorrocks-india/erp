# screens/assignments1.py
"""
Assignments Management Screen (Slide 25)
Main entry point for assignment management system.

Modular structure:
- assignments1.py (this file): Main coordinator
- screens/timetable/assignment_list.py: List view
- screens/timetable/assignment_editor.py: Create/Edit form
- screens/timetable/assignment_co_rubrics.py: CO & Rubrics tab
- screens/timetable/assignment_evaluators.py: Evaluators management
- screens/timetable/assignment_groups.py: Groups management
- screens/timetable/assignment_submissions.py: Submissions tracking
- screens/timetable/assignment_marks.py: Marks entry & scaling
- screens/timetable/assignment_analytics.py: Analytics & reports
"""

import streamlit as st
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from connection import get_engine
from context import require_context, get_context
from services.assignment_service import AssignmentService


def render_assignments_page():
    """Main assignments page coordinator."""
    st.title("📝 Assignment Management")
    
    # Initialize services
    engine = get_engine()
    service = AssignmentService(engine)
    
    # Check context
    ctx = get_context()
    if not ctx.get('degree_code'):
        st.warning("⚠️ Please select context filters from the main page first.")
        st.info("Navigate to the main page and select: Degree → Program → Branch → AY → Year → Term")
        return
    
    # Display context
    with st.expander("📋 Current Context", expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.write(f"**Degree:** {ctx.get('degree_code', 'N/A')}")
            st.write(f"**Program:** {ctx.get('program_code', 'All')}")
            st.write(f"**Branch:** {ctx.get('branch_code', 'All')}")
        with col2:
            st.write(f"**AY:** {ctx.get('ay_label', 'N/A')}")
            st.write(f"**Year:** {ctx.get('year', 'N/A')}")
            st.write(f"**Term:** {ctx.get('term', 'N/A')}")
        with col3:
            st.write(f"**Division:** {ctx.get('division_code', 'All')}")
    
    # Subject selector (required)
    st.subheader("🎯 Select Subject")
    
    offerings = get_offerings_for_context(engine, ctx)
    
    if not offerings:
        st.warning("No subject offerings found for the selected context.")
        st.info("Please configure subject offerings first from the Subject Offerings page.")
        return
    
    offering_options = {
        f"{o['subject_code']} - {o['subject_name']} ({o['subject_type']})": o['id']
        for o in offerings
    }
    
    selected_offering_display = st.selectbox(
        "Subject",
        options=list(offering_options.keys()),
        key="assignment_subject_selector"
    )
    
    if not selected_offering_display:
        return
    
    offering_id = offering_options[selected_offering_display]
    selected_offering = next(o for o in offerings if o['id'] == offering_id)
    
    # Store in session state
    st.session_state['selected_offering_id'] = offering_id
    st.session_state['selected_offering'] = selected_offering
    
    # Display offering details
    with st.expander("📊 Subject Details", expanded=False):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Credits", f"{selected_offering['credits_total']}")
        with col2:
            st.metric("Internal Max", f"{selected_offering['internal_marks_max']}")
        with col3:
            st.metric("External Max", f"{selected_offering['exam_marks_max']}")
        with col4:
            st.metric("Total Max", f"{selected_offering['total_marks_max']}")
    
    st.divider()
    
    # Navigation tabs
    tab_list, tab_editor, tab_evaluators, tab_submissions, tab_marks, tab_analytics = st.tabs([
        "📋 Assignments List",
        "✏️ Create/Edit",
        "👥 Evaluators",
        "📤 Submissions",
        "📊 Marks & Scaling",
        "📈 Analytics"
    ])
    
    with tab_list:
        render_assignment_list(service, offering_id, selected_offering)
    
    with tab_editor:
        render_assignment_editor(service, offering_id, selected_offering)
    
    with tab_evaluators:
        render_evaluators_management(service, offering_id)
    
    with tab_submissions:
        render_submissions_tracking(service, offering_id)
    
    with tab_marks:
        render_marks_entry(service, offering_id, selected_offering)
    
    with tab_analytics:
        render_analytics(service, offering_id, selected_offering)


def get_offerings_for_context(engine, ctx) -> list:
    """Get subject offerings matching context."""
    from sqlalchemy import text as sa_text
    
    with engine.begin() as conn:
        query = """
        SELECT 
            so.id, so.subject_code, so.subject_type,
            so.credits_total, so.internal_marks_max, so.exam_marks_max, so.total_marks_max,
            COALESCE(sc.subject_name, so.subject_code) as subject_name
        FROM subject_offerings so
        LEFT JOIN subjects_catalog sc ON so.subject_code = sc.subject_code
        WHERE so.ay_label = :ay_label
        AND so.degree_code = :degree_code
        AND so.year = :year
        AND so.term = :term
        AND so.status = 'published'
        """
        
        params = {
            "ay_label": ctx['ay_label'],
            "degree_code": ctx['degree_code'],
            "year": ctx['year'],
            "term": ctx['term']
        }
        
        if ctx.get('program_code'):
            query += " AND so.program_code = :program_code"
            params["program_code"] = ctx['program_code']
        
        if ctx.get('branch_code'):
            query += " AND so.branch_code = :branch_code"
            params["branch_code"] = ctx['branch_code']
        
        if ctx.get('division_code'):
            query += " AND (so.division_code = :division_code OR so.applies_to_all_divisions = 1)"
            params["division_code"] = ctx['division_code']
        
        query += " ORDER BY so.subject_code"
        
        results = conn.execute(sa_text(query), params).fetchall()
        return [dict(r._mapping) for r in results]


def render_assignment_list(service, offering_id, offering):
    """Render assignments list view."""
    # Import the modular component
    try:
        from screens.timetable.assignment_list import render_list
        render_list(service, offering_id, offering)
    except ImportError as e:
        st.error(f"Failed to load assignment list component: {e}")
        st.info("Creating placeholder...")
        render_list_placeholder(service, offering_id, offering)


def render_assignment_editor(service, offering_id, offering):
    """Render assignment editor."""
    try:
        from screens.timetable.assignment_editor import render_editor
        render_editor(service, offering_id, offering)
    except ImportError as e:
        st.error(f"Failed to load assignment editor component: {e}")
        st.info("Creating placeholder...")
        render_editor_placeholder(service, offering_id, offering)


def render_evaluators_management(service, offering_id):
    """Render evaluators management."""
    try:
        from screens.timetable.assignment_evaluators import render_evaluators
        render_evaluators(service, offering_id)
    except ImportError as e:
        st.error(f"Failed to load evaluators component: {e}")
        st.info("Creating placeholder...")
        st.info("Evaluators management will be available here.")


def render_submissions_tracking(service, offering_id):
    """Render submissions tracking."""
    try:
        from screens.timetable.assignment_submissions import render_submissions
        render_submissions(service, offering_id)
    except ImportError as e:
        st.error(f"Failed to load submissions component: {e}")
        st.info("Creating placeholder...")
        st.info("Submissions tracking will be available here.")


def render_marks_entry(service, offering_id, offering):
    """Render marks entry and scaling."""
    try:
        from screens.timetable.assignment_marks import render_marks
        render_marks(service, offering_id, offering)
    except ImportError as e:
        st.error(f"Failed to load marks component: {e}")
        st.info("Creating placeholder...")
        st.info("Marks entry and scaling will be available here.")


def render_analytics(service, offering_id, offering):
    """Render analytics and reports."""
    try:
        from screens.timetable.assignment_analytics import render_analytics_view
        render_analytics_view(service, offering_id, offering)
    except ImportError as e:
        st.error(f"Failed to load analytics component: {e}")
        st.info("Creating placeholder...")
        st.info("Analytics and reports will be available here.")


# ===========================================================================
# PLACEHOLDER IMPLEMENTATIONS (temporary until modules are created)
# ===========================================================================

def render_list_placeholder(service, offering_id, offering):
    """Placeholder for list view."""
    st.info("📋 Assignment List View")
    
    # Get assignments
    assignments = service.list_assignments(offering_id=offering_id)
    
    if not assignments:
        st.warning("No assignments found for this subject.")
        st.info("Use the 'Create/Edit' tab to create your first assignment.")
        return
    
    # Display as table
    st.write(f"**{len(assignments)} assignment(s) found**")
    
    for idx, asg in enumerate(assignments, 1):
        with st.expander(f"#{asg['number']} - {asg['title']}", expanded=False):
            col1, col2, col3 = st.columns(3)
            with col1:
                st.write(f"**Bucket:** {asg['bucket']}")
                st.write(f"**Max Marks:** {asg['max_marks']}")
            with col2:
                st.write(f"**Due:** {asg['due_at']}")
                st.write(f"**Grace:** {asg['grace_minutes']} min")
            with col3:
                st.write(f"**Status:** {asg['status']}")
                st.write(f"**Visibility:** {asg['visibility_state']}")
            
            # Action buttons
            col_a, col_b, col_c = st.columns(3)
            with col_a:
                if st.button("✏️ Edit", key=f"edit_{asg['id']}"):
                    st.session_state['edit_assignment_id'] = asg['id']
                    st.rerun()
            with col_b:
                if st.button("👁️ View", key=f"view_{asg['id']}"):
                    st.session_state['view_assignment_id'] = asg['id']
            with col_c:
                if asg['status'] == 'draft':
                    if st.button("📤 Publish", key=f"publish_{asg['id']}"):
                        st.session_state['publish_assignment_id'] = asg['id']


def render_editor_placeholder(service, offering_id, offering):
    """Placeholder for editor."""
    st.info("✏️ Assignment Editor")
    
    # Check if editing existing
    edit_id = st.session_state.get('edit_assignment_id')
    
    if edit_id:
        st.subheader("Edit Assignment")
        assignment = service.get_assignment(edit_id)
        if assignment:
            st.json(assignment)
        
        if st.button("« Back to List"):
            del st.session_state['edit_assignment_id']
            st.rerun()
    else:
        st.subheader("Create New Assignment")
        
        with st.form("create_assignment_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                number = st.number_input("Assignment Number", min_value=1, value=1)
                title = st.text_input("Title", placeholder="e.g., Quiz 1, Lab Report 2")
                bucket = st.selectbox("Bucket", ["Internal", "External"])
            
            with col2:
                max_marks = st.number_input("Max Marks", min_value=1.0, value=10.0)
                due_date = st.date_input("Due Date")
                due_time = st.time_input("Due Time")
            
            description = st.text_area("Description / Instructions", height=100)
            
            submitted = st.form_submit_button("✅ Create Assignment")
            
            if submitted:
                if not title:
                    st.error("Title is required")
                else:
                    try:
                        from datetime import datetime
                        due_at = datetime.combine(due_date, due_time)
                        
                        assignment_id = service.create_assignment(
                            offering_id=offering_id,
                            number=number,
                            title=title,
                            bucket=bucket,
                            max_marks=max_marks,
                            due_at=due_at,
                            description=description,
                            actor="current_user",  # TODO: Get from auth
                            actor_role="subject_in_charge"
                        )
                        
                        st.success(f"✅ Created assignment #{number} - {title}")
                        st.balloons()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to create assignment: {e}")


if __name__ == "__main__":
    render_assignments_page()
