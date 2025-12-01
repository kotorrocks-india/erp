# screens/timetable/assignment_list.py
"""
Assignment List View Component
Displays all assignments for a subject with filtering, sorting, and actions.
"""

import streamlit as st
import pandas as pd
from datetime import datetime
from typing import Dict, List


def render_list(service, offering_id: int, offering: Dict):
    """Render assignments list with filters and actions."""
    
    st.subheader("📋 Assignments List")
    
    # Filters
    with st.expander("🔍 Filters", expanded=False):
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            filter_bucket = st.multiselect(
                "Bucket",
                ["Internal", "External"],
                default=None,
                key="list_filter_bucket"
            )
        
        with col2:
            filter_status = st.multiselect(
                "Status",
                ["draft", "published", "archived", "deactivated"],
                default=["draft", "published"],
                key="list_filter_status"
            )
        
        with col3:
            filter_visibility = st.multiselect(
                "Visibility",
                ["Hidden", "Visible_Accepting", "Closed", "Results_Published"],
                default=None,
                key="list_filter_visibility"
            )
        
        with col4:
            sort_by = st.selectbox(
                "Sort By",
                ["Number ↑", "Number ↓", "Due Date ↑", "Due Date ↓", "Max Marks ↑", "Max Marks ↓"],
                key="list_sort_by"
            )
    
    # Get assignments with filters
    assignments = service.list_assignments(offering_id=offering_id)
    
    # Apply filters
    if filter_bucket:
        assignments = [a for a in assignments if a['bucket'] in filter_bucket]
    
    if filter_status:
        assignments = [a for a in assignments if a['status'] in filter_status]
    
    if filter_visibility:
        assignments = [a for a in assignments if a['visibility_state'] in filter_visibility]
    
    # Apply sorting
    if "Number" in sort_by:
        reverse = "↓" in sort_by
        assignments = sorted(assignments, key=lambda x: x['number'], reverse=reverse)
    elif "Due Date" in sort_by:
        reverse = "↓" in sort_by
        assignments = sorted(assignments, key=lambda x: x['due_at'], reverse=reverse)
    elif "Max Marks" in sort_by:
        reverse = "↓" in sort_by
        assignments = sorted(assignments, key=lambda x: x['max_marks'], reverse=reverse)
    
    if not assignments:
        st.info("📭 No assignments found matching the filters.")
        st.write("Use the **Create/Edit** tab to create your first assignment.")
        return
    
    # Summary metrics
    col1, col2, col3, col4 = st.columns(4)
    
    internal_assignments = [a for a in assignments if a['bucket'] == 'Internal']
    external_assignments = [a for a in assignments if a['bucket'] == 'External']
    published_assignments = [a for a in assignments if a['status'] == 'published']
    
    with col1:
        st.metric("Total Assignments", len(assignments))
    with col2:
        st.metric("Internal", f"{len(internal_assignments)} ({sum(a['max_marks'] for a in internal_assignments):.0f} marks)")
    with col3:
        st.metric("External", f"{len(external_assignments)} ({sum(a['max_marks'] for a in external_assignments):.0f} marks)")
    with col4:
        st.metric("Published", len(published_assignments))
    
    # Scaling info
    with st.expander("📐 Marks Scaling Information", expanded=False):
        internal_total = sum(a['max_marks'] for a in internal_assignments if a['status'] == 'published')
        external_total = sum(a['max_marks'] for a in external_assignments if a['status'] == 'published')
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**Internal Bucket:**")
            st.write(f"• Raw Total: {internal_total:.1f}")
            st.write(f"• Offering Max: {offering['internal_marks_max']}")
            if internal_total > 0:
                scaling_factor = offering['internal_marks_max'] / internal_total
                st.write(f"• Scaling Factor: {scaling_factor:.4f}")
                st.info(f"Each raw mark will be multiplied by {scaling_factor:.4f}")
        
        with col2:
            st.write("**External Bucket:**")
            st.write(f"• Raw Total: {external_total:.1f}")
            st.write(f"• Offering Max: {offering['exam_marks_max']}")
            if external_total > 0:
                scaling_factor = offering['exam_marks_max'] / external_total
                st.write(f"• Scaling Factor: {scaling_factor:.4f}")
                st.info(f"Each raw mark will be multiplied by {scaling_factor:.4f}")
    
    st.divider()
    
    # Display assignments
    st.write(f"**Showing {len(assignments)} assignment(s)**")
    
    for idx, asg in enumerate(assignments, 1):
        render_assignment_card(service, asg, offering)
    
    # Bulk actions
    st.divider()
    render_bulk_actions(service, assignments)


def render_assignment_card(service, asg: Dict, offering: Dict):
    """Render a single assignment card."""
    
    # Status badge color
    status_colors = {
        "draft": "🟡",
        "published": "🟢",
        "archived": "⚪",
        "deactivated": "🔴"
    }
    
    visibility_colors = {
        "Hidden": "⚫",
        "Visible_Accepting": "🔵",
        "Closed": "🟠",
        "Results_Published": "🟢"
    }
    
    status_badge = status_colors.get(asg['status'], "⚪")
    visibility_badge = visibility_colors.get(asg['visibility_state'], "⚪")
    
    # Due date formatting
    try:
        due_dt = datetime.fromisoformat(asg['due_at'])
        due_str = due_dt.strftime("%b %d, %Y %I:%M %p")
        is_overdue = due_dt < datetime.now()
        due_display = f"⚠️ {due_str} (OVERDUE)" if is_overdue else due_str
    except:
        due_display = asg['due_at']
    
    # Card header
    with st.expander(
        f"{status_badge} #{asg['number']} - {asg['title']} ({asg['bucket']}) - {asg['max_marks']} marks",
        expanded=False
    ):
        # Details grid
        col1, col2, col3 = st.columns([2, 2, 1])
        
        with col1:
            st.write("**Details:**")
            st.write(f"• Bucket: {asg['bucket']}")
            st.write(f"• Max Marks: {asg['max_marks']}")
            st.write(f"• Grace Period: {asg['grace_minutes']} minutes")
            if asg.get('description'):
                with st.expander("📝 Description"):
                    st.write(asg['description'])
        
        with col2:
            st.write("**Schedule:**")
            st.write(f"• Due: {due_display}")
            st.write(f"• Created: {asg.get('created_at', 'N/A')[:16]}")
            if asg.get('published_at'):
                st.write(f"• Published: {asg['published_at'][:16]}")
        
        with col3:
            st.write("**Status:**")
            st.write(f"{status_badge} {asg['status'].title()}")
            st.write(f"{visibility_badge} {asg['visibility_state']}")
        
        # Get statistics
        stats = service.get_assignment_statistics(asg['id'])
        
        if stats:
            st.write("**Statistics:**")
            col_s1, col_s2, col_s3, col_s4 = st.columns(4)
            with col_s1:
                st.metric("Submissions", stats.get('submission_count', 0))
            with col_s2:
                st.metric("Late", stats.get('late_submission_count', 0))
            with col_s3:
                st.metric("Graded", stats.get('graded_count', 0))
            with col_s4:
                if stats.get('avg_marks'):
                    st.metric("Avg Marks", f"{stats['avg_marks']:.1f}")
        
        # CO Mappings
        co_mappings = service.get_co_mappings(asg['id'])
        if co_mappings:
            with st.expander("🎯 CO Mappings"):
                co_display = ", ".join([f"{m['co_code']}: {m['correlation_value']}" for m in co_mappings if m['correlation_value'] > 0])
                st.write(co_display if co_display else "No CO correlations set")
        
        # Rubrics
        rubrics = service.get_attached_rubrics(asg['id'])
        if rubrics:
            with st.expander("📋 Rubrics"):
                for rub in rubrics:
                    st.write(f"• Rubric ID: {rub['rubric_id']} (Mode {rub['rubric_mode']}, Weight: {rub['top_level_weight_percent']}%)")
        
        # Evaluators
        evaluators = service.get_evaluators(asg['id'])
        if evaluators:
            with st.expander("👥 Evaluators"):
                for ev in evaluators:
                    st.write(f"• {ev.get('faculty_name', ev['faculty_id'])} ({ev['evaluator_role']})")
        
        # Actions
        st.divider()
        render_assignment_actions(service, asg)


def render_assignment_actions(service, asg: Dict):
    """Render action buttons for an assignment."""
    
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        if st.button("✏️ Edit", key=f"edit_{asg['id']}", use_container_width=True):
            st.session_state['edit_assignment_id'] = asg['id']
            st.rerun()
    
    with col2:
        if st.button("👁️ View Details", key=f"view_{asg['id']}", use_container_width=True):
            st.session_state['view_assignment_id'] = asg['id']
            st.rerun()
    
    with col3:
        if asg['status'] == 'draft':
            if st.button("📤 Publish", key=f"publish_{asg['id']}", use_container_width=True):
                st.session_state['publish_assignment_id'] = asg['id']
                st.rerun()
        elif asg['status'] == 'published':
            if st.button("🔒 Close", key=f"close_{asg['id']}", use_container_width=True):
                # Close submissions
                try:
                    service.update_visibility(asg['id'], 'Closed', 'current_user', 'subject_in_charge')
                    st.success("Closed submissions")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed: {e}")
    
    with col4:
        if asg['status'] != 'archived':
            if st.button("📦 Archive", key=f"archive_{asg['id']}", use_container_width=True):
                with st.form(f"archive_form_{asg['id']}"):
                    reason = st.text_input("Reason for archiving")
                    if st.form_submit_button("Confirm Archive"):
                        try:
                            service.archive_assignment(asg['id'], 'current_user', 'subject_in_charge', reason)
                            st.success("Archived")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed: {e}")
    
    with col5:
        if asg['status'] == 'draft':
            if st.button("🗑️ Delete", key=f"delete_{asg['id']}", use_container_width=True, type="secondary"):
                if st.checkbox(f"Confirm delete #{asg['number']}", key=f"confirm_delete_{asg['id']}"):
                    try:
                        service.delete_assignment(asg['id'], 'current_user', 'superadmin')
                        st.success("Deleted")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed: {e}")


def render_bulk_actions(service, assignments: List[Dict]):
    """Render bulk action options."""
    
    st.subheader("🔧 Bulk Actions")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("📤 Publish All Drafts", use_container_width=True):
            drafts = [a for a in assignments if a['status'] == 'draft']
            if drafts:
                st.info(f"This will publish {len(drafts)} draft assignment(s). Feature coming soon.")
            else:
                st.info("No drafts to publish")
    
    with col2:
        if st.button("📥 Export to CSV", use_container_width=True):
            if assignments:
                # Create DataFrame
                df = pd.DataFrame([{
                    'Number': a['number'],
                    'Title': a['title'],
                    'Bucket': a['bucket'],
                    'Max Marks': a['max_marks'],
                    'Due Date': a['due_at'],
                    'Status': a['status'],
                    'Visibility': a['visibility_state']
                } for a in assignments])
                
                csv = df.to_csv(index=False)
                st.download_button(
                    "⬇️ Download CSV",
                    csv,
                    "assignments_export.csv",
                    "text/csv",
                    use_container_width=True
                )
            else:
                st.info("No assignments to export")
    
    with col3:
        if st.button("📊 Generate Report", use_container_width=True):
            st.info("Report generation feature coming soon")


if __name__ == "__main__":
    st.write("This module should be imported, not run directly.")
